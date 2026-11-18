"""State file + schedule slot logic."""
import json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path("data/state.json")


class Store:
    def __init__(self):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        if STATE.exists():
            self.d = json.loads(STATE.read_text())
        else:
            self.d = {"sources": {}, "clips": []}

    def save(self):
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=2, ensure_ascii=False))
        os.replace(tmp, STATE)

    # sources
    def source_done(self, sid):
        return self.d["sources"].get(sid, {}).get("status") in ("done", "skipped")

    def mark_source(self, sid, status, **kw):
        self.d["sources"][sid] = {"status": status, **kw}
        self.save()

    # clips
    def add_clip(self, clip):
        self.d["clips"].append(clip)
        self.save()

    def clips(self, status):
        return [c for c in self.d["clips"] if c["status"] == status]

    def taken_slots(self):
        return [c["publish_at"] for c in self.d["clips"] if c.get("publish_at")]


def next_free_slot(cfg, taken_iso):
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    now = datetime.now(tz) + timedelta(minutes=20)
    taken = [datetime.fromisoformat(t).astimezone(tz).replace(second=0, microsecond=0)
             for t in taken_iso]
    slots = sorted(cfg["schedule"]["slots"])
    per_day = cfg["schedule"].get("max_per_day", len(slots))
    for d in range(0, 180):
        day = (now + timedelta(days=d)).date()
        count = sum(1 for t in taken if t.date() == day)
        for s in slots:
            if count >= per_day:
                break
            hh, mm = map(int, s.split(":"))
            dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            if dt < now or dt in taken:
                continue
            return dt.astimezone(timezone.utc).isoformat()
    raise RuntimeError("Koi free slot nahi mila")
