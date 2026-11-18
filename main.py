#!/usr/bin/env python3
"""Shorts Bot: long video -> AI shorts -> scheduled YouTube uploads.

  python main.py                   # Web Studio UI (default)
  python main.py ui                # Web Studio UI
  python main.py auth              # YouTube login (ek baar)
  python main.py add <link|file>   # video process karo + clips banao
  python main.py upload            # ready clips ko schedule karke upload
  python main.py run <link|file>   # add + upload ek saath
  python main.py watch             # AUTO MODE: naya video aate hi sab kuch apne aap
  python main.py status
"""
import argparse, shutil, sys, time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
import yaml

import pipeline
from store import Store, next_free_slot


_web_logger = None


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(datetime.now().strftime("[%H:%M:%S]"), msg, flush=True)
    if _web_logger:
        try:
            _web_logger(msg)
        except Exception:
            pass


def load_cfg():
    return yaml.safe_load(Path("config.yaml").read_text())


def check_tools():
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            sys.exit(f"{t} install nahi hai. Mac: brew install ffmpeg")


# ---------------------------------------------------------------- core steps
def process_source(cfg, store, sid, path, title=""):
    if store.source_done(sid):
        log("pehle hi process ho chuka:", sid)
        return 0
    _, _, dur = pipeline.probe(path)
    min_s = cfg["watch"]["min_source_minutes"] * 60
    if dur < min_s:
        log(f"{sid}: bahut chhota ({dur:.0f}s), skip")
        store.mark_source(sid, "skipped", reason="too short")
        return 0
    log(f"Processing {sid} {title} ({dur/60:.1f} min)")
    segs, lang = pipeline.transcribe(path, cfg, f"data/work/{sid}/transcript.json")
    log(f"Transcript ready (language: {lang}, {len(segs)} segments)")
    clips = pipeline.pick_clips(segs, cfg)
    log(f"AI ne {len(clips)} clips chune")
    words = [w for s in segs for w in s["words"]]
    n = 0
    for i, c in enumerate(clips, 1):
        log(f"  clip {i}: {c['start']:.0f}s-{c['end']:.0f}s  {c.get('title','')}")
        out = pipeline.render_clip(path, c, words, f"output/{sid}", i, cfg)
        store.add_clip({"id": f"{sid}_{i:02d}", "source": sid, "path": str(out),
                        "title": c.get("title", f"Short {i}"), "description": c.get("description", ""),
                        "hashtags": c.get("hashtags", []), "status": "ready"})
        n += 1
    store.mark_source(sid, "done", clips=n)
    return n


def add_input(cfg, store, arg):
    p = Path(arg)
    if p.exists():
        return process_source(cfg, store, p.stem, p, p.name)
    sid, path = pipeline.download(arg)
    return process_source(cfg, store, sid, path)


def upload_ready(cfg, store):
    from uploader import get_service, upload, QuotaExceeded
    ready = store.clips("ready")
    if not ready:
        return 0
    service = get_service()
    done = 0
    for c in ready:
        c["publish_at"] = next_free_slot(cfg, store.taken_slots())
        try:
            c["video_id"] = upload(service, c, cfg)
        except QuotaExceeded:
            c["publish_at"] = None
            store.save()
            log("YouTube daily quota khatam. Baaki clips kal upload honge.")
            break
        except Exception as e:
            c["publish_at"] = None
            c["error"] = str(e)[:300]
            store.save()
            log("Upload fail:", c["id"], e)
            continue
        c["status"] = "scheduled"
        store.save()
        done += 1
        log(f"Scheduled: {c['title']}  ->  {c['publish_at']}  (https://youtu.be/{c['video_id']})")
    return done


# ---------------------------------------------------------------- watch mode
def channel_feed(channel_id):
    r = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}, timeout=30)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    return [(e.find("yt:videoId", ns).text, e.find("a:title", ns).text)
            for e in ET.fromstring(r.content).findall("a:entry", ns)]


def cmd_watch(cfg, store):
    w = cfg["watch"]
    Path("inbox").mkdir(exist_ok=True)
    Path("links.txt").touch()
    if w.get("channel_id") and not w.get("process_existing") and not store.d.get("feed_seeded"):
        for vid, _ in channel_feed(w["channel_id"]):
            store.d["sources"].setdefault(vid, {"status": "skipped", "reason": "existing"})
        store.d["feed_seeded"] = True
        store.save()
        log("Purane channel videos ignore kiye; ab sirf naye videos process honge.")
    log("Watch mode ON. inbox/ folder, links.txt aur channel feed dekh raha hoon. (Ctrl+C = stop)")
    while True:
        try:
            jobs = []
            for f in sorted(Path("inbox").glob("*.mp4")):
                jobs.append(str(f))
            for line in Path("links.txt").read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    jobs.append(line)
            if w.get("channel_id"):
                for vid, title in channel_feed(w["channel_id"]):
                    if not store.source_done(vid):
                        jobs.append(f"https://www.youtube.com/watch?v={vid}")
            for j in jobs:
                sid = Path(j).stem if Path(j).exists() else pipeline.video_id_from_url(j)
                if sid and not store.source_done(sid):
                    try:
                        add_input(cfg, store, j)
                    except Exception as e:
                        log("Fail:", j, e)
                        store.mark_source(sid, "skipped", reason=str(e)[:200])
            upload_ready(cfg, store)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log("Loop error:", e)
        time.sleep(w["poll_minutes"] * 60)


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["auth", "add", "upload", "run", "watch", "status", "ui"], default="ui", nargs="?")
    ap.add_argument("target", nargs="?")
    a = ap.parse_args()
    cfg, store = load_cfg(), Store()
    if a.cmd == "ui":
        import web
        web.start(cfg, store)
        return
    if a.cmd == "auth":
        from uploader import get_service
        get_service()
        log("YouTube connect ho gaya (token.json save).")
        return
    check_tools()
    if a.cmd in ("add", "run"):
        if not a.target:
            sys.exit("Link ya file path do.")
        add_input(cfg, store, a.target)
    if a.cmd in ("upload", "run"):
        upload_ready(cfg, store)
    if a.cmd == "watch":
        cmd_watch(cfg, store)
    if a.cmd == "status":
        for st in ("ready", "scheduled"):
            for c in store.clips(st):
                print(f"{st:10} {c.get('publish_at') or '-':28} {c['title']}")


if __name__ == "__main__":
    main()
