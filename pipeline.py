"""Download -> transcribe -> AI pick -> cut/crop/caption."""
import json, os, re, statistics, subprocess, sys, time
from pathlib import Path
import requests

# Ensure ffmpeg-full is preferred if installed
for _p in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
    if os.path.isdir(_p) and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_p}:{os.environ.get('PATH', '')}"

_log_cb = None
_has_ass = None


def _notify(msg):
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def has_ass_filter():
    global _has_ass
    if _has_ass is not None:
        return _has_ass
    try:
        r = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        _has_ass = bool(re.search(r"\bass\b", r.stdout))
    except Exception:
        _has_ass = False
    return _has_ass


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"Command fail: {' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")
    return r


# ---------------------------------------------------------------- download
def video_id_from_url(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})", url)
    return m.group(1) if m else None


def download(url, dest_dir="downloads"):
    vid = video_id_from_url(url)
    if not vid:
        raise ValueError(f"YouTube ID nahi mila: {url}")
    Path(dest_dir).mkdir(exist_ok=True)
    out = Path(dest_dir) / f"{vid}.mp4"
    if not out.exists():
        _notify(f"Downloading video from YouTube ({vid})...")
        run([sys.executable, "-m", "yt_dlp",
             "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
             "--merge-output-format", "mp4",
             "-o", Path(dest_dir) / f"{vid}.%(ext)s", url])
    return vid, out


def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "json", path])
    j = json.loads(r.stdout)
    return int(j["streams"][0]["width"]), int(j["streams"][0]["height"]), float(j["format"]["duration"])


# ---------------------------------------------------------------- transcribe
def transcribe(path, cfg, cache):
    cache = Path(cache)
    if cache.exists():
        _notify("Found cached transcript, loading...")
        d = json.loads(cache.read_text())
        return d["segments"], d["language"]
    _notify(f"Transcribing audio with Whisper ({cfg['whisper_model']})...")
    from faster_whisper import WhisperModel
    model = WhisperModel(cfg["whisper_model"], device="cpu", compute_type="int8")
    lang = None if cfg["language"] == "auto" else cfg["language"]
    segs, info = model.transcribe(str(path), language=lang, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        words = [{"w": w.word.strip(), "start": w.start, "end": w.end}
                 for w in (s.words or []) if w.word.strip()]
        out.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": words})
        print(f"   transcribing... {s.end/60:.1f} min", end="\r")
    print()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"segments": out, "language": info.language}, ensure_ascii=False))
    return out, info.language


# ---------------------------------------------------------------- AI pick
PROMPT = """You are an expert short-form video editor.
Below is a timestamped transcript ([seconds] text) of a long video.
Pick the {n} best moments to turn into YouTube Shorts.

Rules:
- each clip must be {mn}-{mx} seconds long
- start at the beginning of a sentence, end at a natural finish; clip must make sense standalone
- the first 3 seconds must have a strong hook (a bold claim, question, surprising fact); no slow intros
- clips must not overlap
- title: catchy, max 70 characters, in the SAME language/script as the transcript
- hook: max 8 words, shown on top of the video, same language
- description: 1-2 sentences
- hashtags: 3-5 relevant words, without '#'

Return ONLY a JSON array, nothing else:
[{{"start": 12.5, "end": 55.0, "title": "...", "hook": "...", "description": "...", "hashtags": ["..."]}}]

TRANSCRIPT:
{transcript}
"""


def gemini(prompt, cfg):
    env_f = Path(__file__).parent / ".env"
    key = os.environ.get("GEMINI_API_KEY") or (dict(l.strip().split("=", 1) for l in env_f.read_text().splitlines() if "=" in l).get("GEMINI_API_KEY") if env_f.exists() else None)
    if not key:
        raise RuntimeError("GEMINI_API_KEY set nahi hai (export GEMINI_API_KEY=...)")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg['gemini_model']}:generateContent")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    for attempt in range(5):
        r = requests.post(url, params={"key": key}, json=body, timeout=300)
        if r.status_code == 429 or r.status_code >= 500:
            wait = 20 * (attempt + 1)
            print(f"   Gemini busy ({r.status_code}), {wait}s wait...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError("Gemini ne jawab nahi diya")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def snap_clips(raw, segs, cfg):
    """AI ke timestamps ko sentence boundaries pe snap + validate."""
    mn, mx = cfg["clip_min_sec"], cfg["clip_max_sec"]
    out = []
    for c in raw:
        try:
            s, e = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        ss = min(segs, key=lambda x: abs(x["start"] - s))["start"]
        cands = [x["end"] for x in segs if x["end"] > ss]
        if not cands:
            continue
        ee = min(cands, key=lambda v: abs(v - e))
        if ee - ss > mx:
            ok = [v for v in cands if v - ss <= mx]
            if not ok:
                continue
            ee = max(ok)
        if ee - ss < mn:
            continue
        if any(not (ee <= o["start"] or ss >= o["end"]) for o in out):
            continue
        out.append({**c, "start": ss, "end": ee})
    return sorted(out, key=lambda x: x["start"])[: cfg["clips_per_video"]]


def pick_clips(segs, cfg):
    _notify(f"AI ({cfg['gemini_model']}) is selecting {cfg['clips_per_video']} best short clips...")
    transcript = "\n".join(f"[{s['start']:.0f}] {s['text']}" for s in segs)
    prompt = PROMPT.format(n=cfg["clips_per_video"] + 2, mn=cfg["clip_min_sec"],
                           mx=cfg["clip_max_sec"], transcript=transcript)
    raw = parse_json(gemini(prompt, cfg))
    if isinstance(raw, dict):
        raw = raw.get("clips", [])
    return snap_clips(raw, segs, cfg)


# ---------------------------------------------------------------- captions (ASS)
def ass_time(t):
    t = max(t, 0)
    return f"{int(t//3600)}:{int(t%3600//60):02d}:{t%60:05.2f}"


def clean(t):
    return t.replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words, clip_start, hook, cfg):
    cap = cfg["captions"]
    n = cap["words_per_line"]
    hi = cap["highlight_color"]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{cap['font']},{cap['font_size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1",
        f"Style: Hook,{cap['font']},{cap['hook_font_size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,6,2,8,80,80,260,1",
        "", "[Events]",
        "Format: Layer, Start, End, Name, Style, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook and cfg.get("hook_text", True):
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(3.0)},,Hook,0,0,0,,{clean(hook)}")

    if cap["enabled"] and words:
        for g in range(0, len(words), n):
            group = words[g:g + n]
            texts = [clean(w["w"].upper() if cap["uppercase"] else w["w"]) for w in group]
            for i, w in enumerate(group):
                start = w["start"] - clip_start
                if i + 1 < len(group):
                    end = group[i + 1]["start"] - clip_start
                elif g + n < len(words):
                    nxt = words[g + n]["start"] - clip_start
                    end = min(nxt, w["end"] - clip_start + 0.4)
                else:
                    end = w["end"] - clip_start + 0.2
                end = max(end, start + 0.08)
                parts = [(f"{{\\c{hi}&}}{t}{{\\c&H00FFFFFF&}}" if j == i else t) for j, t in enumerate(texts)]
                lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},,Cap,0,0,0,,{' '.join(parts)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- face crop + render
def face_center(src, start, end):
    """Median face x-position (0..1) in the clip, or None. Kabhi crash nahi karta."""
    try:
        import cv2
        base = getattr(getattr(cv2, "data", None), "haarcascades", None)
        if not base:
            return None
        cascade = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
        if cascade.empty():
            return None
        cap = cv2.VideoCapture(str(src))
        xs = []
        for i in range(1, 9):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * i / 9) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                xs.append((x + w / 2) / frame.shape[1])
        cap.release()
        return statistics.median(xs) if xs else None
    except Exception as e:  # face tracking optional hai; fail ho toh center crop
        print(f"   (face tracking skip: {type(e).__name__})")
        return None


def crop_filter(src, start, end, cfg):
    w, h, _ = probe(src)
    if w / h <= 9 / 16 + 0.01:  # already vertical
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    cw = int(h * 9 / 16) // 2 * 2
    frac = face_center(src, start, end) if cfg.get("face_tracking", True) else None
    cx = (frac if frac is not None else 0.5) * w
    x = int(min(max(cx - cw / 2, 0), w - cw))
    return f"crop={cw}:{h}:{x}:0,scale=1080:1920,setsar=1"


def render_clip(src, clip, words, out_dir, idx, cfg):
    _notify(f"Rendering clip {idx}: cropping 9:16 vertical & burning styled captions...")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"] + 0.3
    cw = [w for w in words if w["start"] >= clip["start"] - 0.05 and w["end"] <= end + 0.1]
    ass_name = f"clip_{idx:02d}.ass"
    (out_dir / ass_name).write_text(build_ass(cw, clip["start"], clip.get("hook"), cfg), encoding="utf-8")
    out_name = f"clip_{idx:02d}.mp4"
    vf = crop_filter(src, start, end, cfg)
    if cfg.get("captions", {}).get("enabled", True):
        if has_ass_filter():
            vf += f",ass={ass_name}"
        else:
            _notify("Notice: ffmpeg libass nahi mila; video bina burned captions ke render ho raha hai.")
    run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", Path(src).resolve(),
         "-vf", vf, "-c:v", "libx264", "-preset", cfg.get("video_preset", "veryfast"), "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_name],
        cwd=out_dir)  # cwd = out_dir so the ass path needs no escaping
    return out_dir / out_name
