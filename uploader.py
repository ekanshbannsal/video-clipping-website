"""YouTube upload with scheduled publish time."""
import json
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
TOKEN = Path("token.json")
SECRET = Path("client_secret.json")


class QuotaExceeded(Exception):
    pass


def is_connected():
    return TOKEN.exists()


def has_client_secret():
    return SECRET.exists()


def disconnect():
    if TOKEN.exists():
        TOKEN.unlink()


def get_channel_info():
    if not TOKEN.exists():
        return None
    try:
        service = get_service()
        r = service.channels().list(part="snippet", mine=True).execute()
        items = r.get("items", [])
        if items:
            snip = items[0]["snippet"]
            return {"title": snip.get("title", "YouTube Channel"), "handle": snip.get("customUrl", "")}
    except Exception:
        pass
    return {"title": "Connected", "handle": ""}


def get_service():
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
        else:
            if not SECRET.exists():
                raise FileNotFoundError("client_secret.json nahi mili. Google Cloud se client_secret.json upload karein.")
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_single_clip(clip_id, cfg, store):
    from store import next_free_slot
    clip = next((c for c in store.d.get("clips", []) if c["id"] == clip_id), None)
    if not clip:
        raise ValueError(f"Clip {clip_id} nahi mili.")
    service = get_service()
    if not clip.get("publish_at"):
        clip["publish_at"] = next_free_slot(cfg, store.taken_slots())
    vid = upload(service, clip, cfg)
    clip["video_id"] = vid
    clip["status"] = "scheduled"
    store.save()
    return vid, clip["publish_at"]


def upload(service, clip, cfg):
    up = cfg["upload"]
    tags = list(dict.fromkeys(up.get("default_tags", []) + clip.get("hashtags", [])))
    hashtags = " ".join("#" + t.replace(" ", "") for t in ["Shorts"] + clip.get("hashtags", [])[:4])
    desc = f"{clip.get('description', '')}\n\n{hashtags}".strip()
    publish = datetime.fromisoformat(clip["publish_at"]).astimezone(timezone.utc)
    body = {
        "snippet": {"title": clip["title"][:95], "description": desc,
                    "tags": tags[:15], "categoryId": up.get("category_id", "22")},
        "status": {"privacyStatus": "private",
                   "publishAt": publish.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": up.get("made_for_kids", False)},
    }
    media = MediaFileUpload(clip["path"], mimetype="video/mp4", chunksize=-1, resumable=True)
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)
    try:
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
    except HttpError as e:
        if b"quotaExceeded" in e.content or b"uploadLimitExceeded" in e.content:
            raise QuotaExceeded(str(e))
        raise
    return resp["id"]
