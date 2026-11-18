"""Web UI for Shorts Bot (zero external dependencies, runs on stdlib http.server)."""
import json, os, re, shutil, subprocess, sys, threading, urllib.parse, webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import uploader

# Thread-safe job state
job_lock = threading.Lock()
job_state = {
    "status": "idle",       # idle | running | done | error
    "step": "Ready",
    "target": "",
    "logs": [],
    "error": None,
    "last_run": None,
}

auth_lock = threading.Lock()
auth_state = {
    "status": "idle",       # idle | authenticating | success | error
    "message": ""
}

def add_log(msg):
    with job_lock:
        t = datetime.now().strftime("[%H:%M:%S]")
        formatted = f"{t} {msg}"
        job_state["logs"].append(formatted)
        if len(job_state["logs"]) > 300:
            job_state["logs"] = job_state["logs"][-300:]
        if any(w in msg.lower() for w in ("download", "transcribe", "gemini", "ai", "render", "clip", "fail", "done", "upload")):
            job_state["step"] = msg


def run_pipeline_job(cfg_base, store, target, clips_count, auto_upload):
    import pipeline, main
    cfg = dict(cfg_base)
    if clips_count and clips_count > 0:
        cfg["clips_per_video"] = int(clips_count)

    with job_lock:
        job_state["status"] = "running"
        job_state["step"] = "Starting process..."
        job_state["target"] = target
        job_state["error"] = None
        job_state["logs"] = []

    add_log(f"Starting job for: {target}")
    try:
        main._web_logger = add_log
        pipeline._log_cb = add_log

        main.check_tools()
        n = main.add_input(cfg, store, target)
        add_log(f"Generated {n} clips successfully!")

        if auto_upload:
            if uploader.is_connected():
                add_log("Uploading ready clips to YouTube...")
                uploaded = main.upload_ready(cfg, store)
                add_log(f"Scheduled {uploaded} clips on YouTube.")
            else:
                add_log("Notice: YouTube connect nahi hai, auto-upload skip kiya.")

        with job_lock:
            job_state["status"] = "done"
            job_state["step"] = f"Done! Created {n} clips."
            job_state["last_run"] = datetime.now().strftime("%H:%M:%S")

    except Exception as e:
        err = str(e)
        add_log(f"ERROR: {err}")
        with job_lock:
            job_state["status"] = "error"
            job_state["step"] = "Failed"
            job_state["error"] = err
    finally:
        main._web_logger = None
        pipeline._log_cb = None


def run_oauth_flow():
    with auth_lock:
        auth_state["status"] = "authenticating"
        auth_state["message"] = "Google login browser mein open ho raha hai..."
    try:
        uploader.get_service()
        info = uploader.get_channel_info()
        title = info.get("title", "My Channel") if info else "YouTube"
        with auth_lock:
            auth_state["status"] = "success"
            auth_state["message"] = f"YouTube Connected: {title}"
        add_log(f"YouTube connected successfully ({title})")
    except Exception as e:
        with auth_lock:
            auth_state["status"] = "error"
            auth_state["message"] = f"Login fail: {e}"
        add_log(f"YouTube login fail: {e}")


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Shorts Bot Studio</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card: #151c2c;
      --card-hover: #1b2438;
      --border: #232d42;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-rgb: 99, 102, 241;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --youtube: #ff0000;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
      min-height: 100vh;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    .logo span {
      background: linear-gradient(135deg, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .badge {
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 9999px;
      background: var(--border);
      color: var(--muted);
      font-weight: 500;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 18px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
      text-decoration: none;
      color: white;
    }
    .btn-primary { background: var(--accent); }
    .btn-primary:hover { background: var(--accent-hover); box-shadow: 0 4px 16px rgba(var(--accent-rgb), 0.35); }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; }
    .btn-secondary { background: var(--border); color: var(--text); }
    .btn-secondary:hover { background: #2e3a54; }
    .btn-yt { background: #cc0000; color: white; }
    .btn-yt:hover { background: #e60000; }
    .btn-sm { padding: 6px 12px; font-size: 12px; }

    /* YouTube Banner Bar */
    .yt-banner {
      background: #121826;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 20px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    .yt-status {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      font-weight: 500;
    }
    .yt-icon {
      width: 28px;
      height: 28px;
      background: #ff0000;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }
    .card-title {
      font-size: 18px;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }
    .tab {
      background: none;
      border: none;
      color: var(--muted);
      font-size: 14px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
    }
    .tab.active { background: var(--border); color: var(--text); }
    .input-group { margin-bottom: 16px; }
    .input-group label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
      margin-bottom: 6px;
    }
    input[type="text"], input[type="number"] {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      color: var(--text);
      font-size: 15px;
      outline: none;
      transition: border 0.2s;
    }
    input[type="text"]:focus, input[type="number"]:focus { border-color: var(--accent); }
    .settings-row {
      display: flex;
      gap: 20px;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      cursor: pointer;
      color: var(--text);
    }

    .dropzone {
      border: 2px dashed var(--border);
      border-radius: 10px;
      padding: 36px 20px;
      text-align: center;
      cursor: pointer;
      background: rgba(0,0,0,0.1);
      transition: all 0.2s;
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: var(--accent);
      background: rgba(var(--accent-rgb), 0.05);
    }
    .dropzone-icon { font-size: 36px; margin-bottom: 8px; }

    /* Live Progress Bar */
    .status-box {
      background: #0f1524;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin-top: 16px;
    }
    .status-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .status-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
      font-size: 14px;
    }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }
    .dot.running { background: var(--accent); animation: pulse 1.5s infinite; }
    .dot.done { background: var(--success); }
    .dot.error { background: var(--danger); }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.2); } }

    .console-log {
      background: #060911;
      border: 1px solid #1a2234;
      border-radius: 6px;
      padding: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      color: #94a3b8;
      max-height: 180px;
      overflow-y: auto;
      white-space: pre-wrap;
      line-height: 1.6;
    }

    /* Clips Grid */
    .clips-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 20px;
    }
    .clip-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.2s, border-color 0.2s;
    }
    .clip-card:hover { border-color: #3b4866; transform: translateY(-2px); }
    .video-wrap {
      background: #000;
      position: relative;
      aspect-ratio: 9/16;
      max-height: 480px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    video { width: 100%; height: 100%; object-fit: contain; }
    .clip-body { padding: 16px; display: flex; flex-direction: column; flex: 1; }
    .clip-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; line-height: 1.3; }
    .clip-hook {
      display: inline-block;
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 4px;
      margin-bottom: 8px;
      align-self: flex-start;
    }
    .clip-tags { font-size: 12px; color: var(--muted); margin-bottom: 12px; flex: 1; }
    .clip-footer {
      display: flex;
      gap: 8px;
      padding-top: 10px;
      border-top: 1px solid var(--border);
    }
    .empty-state { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 14px; }

    /* Modal */
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.7);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      backdrop-filter: blur(4px);
    }
    .modal {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 28px;
      max-width: 580px;
      width: 90%;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    .modal-title { font-size: 20px; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
    .step-list { margin: 16px 0; display: flex; flex-direction: column; gap: 12px; font-size: 13.5px; }
    .step-item { display: flex; gap: 12px; align-items: flex-start; }
    .step-num {
      width: 22px; height: 22px; border-radius: 50%; background: var(--accent);
      color: white; font-size: 12px; font-weight: bold;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .step-item a { color: #818cf8; text-decoration: none; font-weight: 600; }
    .step-item a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
        <div>Shorts Bot <span>Studio</span></div>
      </div>
      <div style="display: flex; gap: 10px; align-items: center;">
        <span class="badge" id="ai-model-badge">AI: Gemini 3.5</span>
        <button class="btn btn-secondary btn-sm" onclick="openFolder()">📂 Open Output Folder</button>
      </div>
    </header>

    <!-- YouTube Banner -->
    <div class="yt-banner">
      <div class="yt-status">
        <div class="yt-icon">▶</div>
        <div>
          <div id="yt-status-title" style="font-weight: 600;">YouTube Disconnected</div>
          <div id="yt-status-sub" style="font-size: 12px; color: var(--muted);">Connect YouTube account for 1-click scheduled uploads</div>
        </div>
      </div>
      <div style="display: flex; gap: 10px;">
        <button class="btn btn-yt btn-sm" id="btn-yt-connect" onclick="openYouTubeModal()">🔗 Connect YouTube</button>
        <button class="btn btn-secondary btn-sm" id="btn-yt-disconnect" style="display: none;" onclick="disconnectYouTube()">Disconnect</button>
      </div>
    </div>

    <!-- Processing Form Card -->
    <div class="card">
      <div class="tabs">
        <button class="tab active" id="tab-url-btn" onclick="switchTab('url')">🔗 YouTube Link</button>
        <button class="tab" id="tab-file-btn" onclick="switchTab('file')">📁 Upload Local Video</button>
      </div>

      <!-- URL Mode -->
      <div id="url-mode">
        <div class="input-group">
          <label>YouTube Video URL</label>
          <input type="text" id="video-url" placeholder="https://www.youtube.com/watch?v=..." />
        </div>
      </div>

      <!-- File Mode -->
      <div id="file-mode" style="display: none;">
        <div class="dropzone" id="drop-zone" onclick="document.getElementById('file-input').click()">
          <div class="dropzone-icon">📹</div>
          <div style="font-weight: 600; margin-bottom: 4px;" id="file-label">Click to select MP4 video or drag & drop here</div>
          <div style="font-size: 12px; color: var(--muted);">Supports MP4, MOV, MKV</div>
          <input type="file" id="file-input" accept="video/mp4,video/*" style="display: none;" onchange="handleFileSelected(this.files[0])">
        </div>
      </div>

      <!-- Parameters Row -->
      <div class="settings-row" style="margin-top: 18px;">
        <div style="width: 140px;">
          <label style="font-size: 13px; color: var(--muted); display: block; margin-bottom: 6px;">Clips count</label>
          <input type="number" id="clips-count" min="1" max="15" value="5" />
        </div>
        <div style="margin-top: 22px;">
          <label class="checkbox-label">
            <input type="checkbox" id="auto-upload" />
            <span>Auto-schedule YouTube upload (after generation)</span>
          </label>
        </div>
        <div style="margin-top: 18px; margin-left: auto;">
          <button class="btn btn-primary" id="btn-generate" onclick="startGeneration()">
            <span>⚡ Generate Shorts</span>
          </button>
        </div>
      </div>

      <!-- Live Progress & Logs Box -->
      <div class="status-box" id="status-card" style="display: none;">
        <div class="status-header">
          <div class="status-indicator">
            <div class="dot" id="status-dot"></div>
            <span id="status-step-text">Starting...</span>
          </div>
          <span style="font-size: 12px; color: var(--muted);" id="status-target"></span>
        </div>
        <div class="console-log" id="console-log">Connecting to bot...</div>
      </div>
    </div>

    <!-- Generated Shorts Gallery -->
    <div class="card">
      <div class="card-title">
        <span>Generated Shorts Library</span>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
          <a href="https://studio.youtube.com/channel/mine/videos/short" target="_blank" class="btn btn-secondary btn-sm">🎬 Open YouTube Studio ↗</a>
          <button class="btn btn-yt btn-sm" onclick="uploadAllReady()">🚀 Schedule All Ready Clips</button>
          <button class="btn btn-secondary btn-sm" onclick="fetchStatus()">🔄 Refresh</button>
        </div>
      </div>

      <div class="clips-grid" id="clips-grid">
        <div class="empty-state">Koi clips abhi generate nahi hui hain. Upar YouTube link daal kar 'Generate Shorts' par click karein!</div>
      </div>
    </div>
  </div>

  <!-- YouTube Setup Modal -->
  <div class="modal-backdrop" id="yt-modal">
    <div class="modal">
      <div class="modal-title">
        <span style="color: #ff0000;">▶</span> Connect YouTube Channel
      </div>
      <p style="font-size: 13.5px; color: var(--muted);">
        Google security rules ke tehat YouTube upload karne ke liye OAuth client ID chahiye hota hai (sirf ek baar setup):
      </p>

      <div class="step-list">
        <div class="step-item">
          <div class="step-num">1</div>
          <div>
            <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank">Google Cloud Console: YouTube Data API v3 ↗</a> kholo aur <b>Enable</b> par click karo.
          </div>
        </div>
        <div class="step-item">
          <div class="step-num">2</div>
          <div>
            <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Credentials Page ↗</a> par jao -> <b>Create Credentials</b> -> <b>OAuth Client ID</b> -> Application Type: <b>Desktop App</b> chuno.
          </div>
        </div>
        <div class="step-item">
          <div class="step-num">3</div>
          <div>
            JSON download karke neeche drop karo:
          </div>
        </div>
      </div>

      <div class="dropzone" id="secret-dropzone" onclick="document.getElementById('secret-file-input').click()" style="padding: 24px; margin-bottom: 16px;">
        <div style="font-size: 24px; margin-bottom: 6px;">📄</div>
        <div id="secret-label" style="font-size: 13px; font-weight: 600;">Drop client_secret.json here ya click karke upload karein</div>
        <input type="file" id="secret-file-input" accept=".json,application/json" style="display: none;" onchange="handleSecretUploaded(this.files[0])">
      </div>

      <div id="auth-status-msg" style="font-size: 13px; margin-bottom: 14px; display: none; color: #818cf8;"></div>

      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-secondary" onclick="closeYouTubeModal()">Cancel</button>
        <button class="btn btn-yt" id="btn-start-auth" onclick="startOAuthFlow()">Start Google Sign-In</button>
      </div>
    </div>
  </div>

  <script>
    let activeTab = 'url';
    let selectedFile = null;
    let isProcessing = false;
    let ytConnected = false;
    let hasSecret = false;

    function switchTab(tab) {
      activeTab = tab;
      document.getElementById('tab-url-btn').className = 'tab ' + (tab === 'url' ? 'active' : '');
      document.getElementById('tab-file-btn').className = 'tab ' + (tab === 'file' ? 'active' : '');
      document.getElementById('url-mode').style.display = tab === 'url' ? 'block' : 'none';
      document.getElementById('file-mode').style.display = tab === 'file' ? 'block' : 'none';
    }

    function handleFileSelected(file) {
      if (!file) return;
      selectedFile = file;
      document.getElementById('file-label').innerText = "Selected: " + file.name + " (" + (file.size / (1024*1024)).toFixed(1) + " MB)";
    }

    const dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    // Secret dropzone
    const secretZone = document.getElementById('secret-dropzone');
    secretZone.addEventListener('dragover', (e) => { e.preventDefault(); secretZone.classList.add('dragover'); });
    secretZone.addEventListener('dragleave', () => secretZone.classList.remove('dragover'));
    secretZone.addEventListener('drop', (e) => {
      e.preventDefault();
      secretZone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleSecretUploaded(e.dataTransfer.files[0]);
      }
    });

    async function handleSecretUploaded(file) {
      if (!file) return;
      document.getElementById('secret-label').innerText = "Uploading " + file.name + "...";
      try {
        const res = await fetch('/api/upload_secret', {
          method: 'POST',
          body: file
        });
        const data = await res.json();
        if (data.ok) {
          document.getElementById('secret-label').innerText = "✅ client_secret.json uploaded!";
          hasSecret = true;
          startOAuthFlow();
        } else {
          alert("Secret upload error: " + data.error);
        }
      } catch (e) {
        alert("Upload error: " + e.message);
      }
    }

    function openYouTubeModal() {
      document.getElementById('yt-modal').style.display = 'flex';
      checkYouTubeStatus();
    }

    function closeYouTubeModal() {
      document.getElementById('yt-modal').style.display = 'none';
    }

    async function startOAuthFlow() {
      const msg = document.getElementById('auth-status-msg');
      msg.style.display = 'block';
      msg.innerText = "⏳ Browser mein Google login open ho raha hai... Account choose karke 'Allow' karein.";
      try {
        const res = await fetch('/api/auth_youtube', { method: 'POST' });
        const d = await res.json();
        if (!d.ok) {
          msg.innerText = "Error: " + d.error;
        }
      } catch (e) {
        msg.innerText = "Auth request error: " + e.message;
      }
    }

    async function disconnectYouTube() {
      if (!confirm("YouTube disconnect karna chahte hain?")) return;
      await fetch('/api/disconnect_youtube', { method: 'POST' });
      checkYouTubeStatus();
      fetchStatus();
    }

    async function checkYouTubeStatus() {
      try {
        const res = await fetch('/api/youtube_status');
        const d = await res.json();
        ytConnected = d.connected;
        hasSecret = d.has_secret;

        const titleEl = document.getElementById('yt-status-title');
        const subEl = document.getElementById('yt-status-sub');
        const btnConn = document.getElementById('btn-yt-connect');
        const btnDisc = document.getElementById('btn-yt-disconnect');

        if (ytConnected) {
          const chanTitle = d.channel ? d.channel.title : 'Connected';
          titleEl.innerHTML = `<span style="color: var(--success)">●</span> YouTube Connected: ${chanTitle}`;
          subEl.innerText = "Ready to schedule uploads on YouTube!";
          btnConn.style.display = 'none';
          btnDisc.style.display = 'inline-flex';
          closeYouTubeModal();
        } else {
          titleEl.innerHTML = `<span style="color: var(--danger)">●</span> YouTube Disconnected`;
          subEl.innerText = "Connect YouTube account for 1-click scheduled uploads";
          btnConn.style.display = 'inline-flex';
          btnDisc.style.display = 'none';
        }

        if (hasSecret) {
          document.getElementById('secret-label').innerText = "✅ client_secret.json already present";
        }
      } catch (e) {
        console.error("yt status error", e);
      }
    }

    async function startGeneration() {
      const clipsCount = parseInt(document.getElementById('clips-count').value) || 5;
      const autoUpload = document.getElementById('auto-upload').checked;

      let target = '';
      if (activeTab === 'url') {
        target = document.getElementById('video-url').value.trim();
        if (!target) {
          alert("Kripya YouTube video link daalein!");
          return;
        }
      } else {
        if (!selectedFile) {
          alert("Kripya ek MP4 video file select karein!");
          return;
        }
        document.getElementById('btn-generate').disabled = true;
        document.getElementById('btn-generate').innerText = "Uploading file...";
        try {
          const res = await fetch('/api/upload_file', {
            method: 'POST',
            headers: { 'X-Filename': encodeURIComponent(selectedFile.name) },
            body: selectedFile
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Upload failed");
          target = data.path;
        } catch (err) {
          alert("File upload fail ho gaya: " + err.message);
          document.getElementById('btn-generate').disabled = false;
          document.getElementById('btn-generate').innerText = "⚡ Generate Shorts";
          return;
        }
      }

      document.getElementById('btn-generate').disabled = true;
      document.getElementById('btn-generate').innerText = "Processing...";
      document.getElementById('status-card').style.display = 'block';

      try {
        const res = await fetch('/api/process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, clips_count: clipsCount, auto_upload: autoUpload })
        });
        const d = await res.json();
        if (!d.ok) alert(d.error);
      } catch (err) {
        alert("Request error: " + err.message);
      }
    }

    async function openFolder() {
      await fetch('/api/open_folder');
    }

    async function uploadClip(clipId) {
      if (!ytConnected) {
        openYouTubeModal();
        return;
      }
      if (!confirm("Is clip ko YouTube pe upload schedule karna chahte hain?")) return;
      
      const btn = document.getElementById('btn-upload-' + clipId);
      if (btn) {
        btn.disabled = true;
        btn.innerText = "⏳ Uploading...";
      }

      try {
        const res = await fetch('/api/upload_clip', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ clip_id: clipId })
        });
        const data = await res.json();
        if (data.ok) {
          alert("✅ Upload ho gaya aur scheduled ho gaya!");
          fetchStatus();
        } else {
          alert("Upload error: " + (data.error || "Unknown"));
          if (btn) {
            btn.disabled = false;
            btn.innerText = "🚀 Schedule";
          }
        }
      } catch (e) {
        alert("Upload error: " + e.message);
        if (btn) {
          btn.disabled = false;
          btn.innerText = "🚀 Schedule";
        }
      }
    }

    async function uploadAllReady() {
      if (!ytConnected) {
        openYouTubeModal();
        return;
      }
      if (!confirm("Saare ready clips ko YouTube pe schedule karke upload karein?")) return;
      try {
        const res = await fetch('/api/upload_all', { method: 'POST' });
        const d = await res.json();
        alert(d.message || "Upload process start ho gaya!");
        fetchStatus();
      } catch (e) {
        alert("Error: " + e.message);
      }
    }

    function formatScheduleTime(isoStr) {
      if (!isoStr) return '';
      try {
        const d = new Date(isoStr);
        return d.toLocaleString('en-IN', {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        });
      } catch (e) {
        return isoStr;
      }
    }

    async function fetchStatus() {
      try {
        const r = await fetch('/api/status');
        const data = await r.json();

        // Model badge
        if (data.config && data.config.gemini_model) {
          document.getElementById('ai-model-badge').innerText = "AI: " + data.config.gemini_model;
        }

        // Job status
        const job = data.job;
        const statusBox = document.getElementById('status-card');
        const dot = document.getElementById('status-dot');
        const stepText = document.getElementById('status-step-text');
        const targetText = document.getElementById('status-target');
        const consoleLog = document.getElementById('console-log');
        const btnGen = document.getElementById('btn-generate');

        if (job.status !== 'idle' || job.logs.length > 0) {
          statusBox.style.display = 'block';
          dot.className = 'dot ' + job.status;
          stepText.innerText = job.step;
          targetText.innerText = job.target ? job.target.split('/').pop() : '';
          consoleLog.innerText = job.logs.join('\\n');
          consoleLog.scrollTop = consoleLog.scrollHeight;
        }

        if (job.status === 'running') {
          isProcessing = true;
          btnGen.disabled = true;
          btnGen.innerText = "⏳ Processing...";
        } else {
          if (isProcessing) {
            isProcessing = false;
            btnGen.disabled = false;
            btnGen.innerText = "⚡ Generate Shorts";
          }
        }

        // Render clips
        const clips = data.clips || [];
        const grid = document.getElementById('clips-grid');
        if (clips.length === 0) {
          grid.innerHTML = '<div class="empty-state">Koi clips abhi generate nahi hui hain. Upar YouTube link daal kar \\'Generate Shorts\\' par click karein!</div>';
        } else {
          grid.innerHTML = clips.map((c, idx) => {
            const videoUrl = '/' + c.path;
            const tags = (c.hashtags || []).map(t => '#' + t).join(' ');
            const isScheduled = c.status === 'scheduled';
            const scheduledTime = c.publish_at ? formatScheduleTime(c.publish_at) : '';
            const ytLink = c.video_id ? `https://youtu.be/${c.video_id}` : '';
            const studioLink = c.video_id ? `https://studio.youtube.com/video/${c.video_id}/edit` : '';
            return `
              <div class="clip-card" style="${isScheduled ? 'border-color: #22c55e;' : ''}">
                <div class="video-wrap">
                  <video controls preload="metadata" playsinline src="${videoUrl}"></video>
                </div>
                <div class="clip-body">
                  ${c.hook ? `<div class="clip-hook">Hook: ${c.hook}</div>` : ''}
                  <div class="clip-title">${c.title || 'Clip ' + (idx + 1)}</div>
                  <div class="clip-tags">${tags}</div>
                  
                  ${isScheduled ? `
                    <div style="background: rgba(34, 197, 94, 0.12); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
                      <div style="color: #4ade80; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                        <span>✓</span> UPLOADED TO YOUTUBE
                      </div>
                      <div style="font-size: 13px; font-weight: 600; color: #fff; margin-top: 3px;">
                        📅 Auto-Publishes: ${scheduledTime}
                      </div>
                      <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">
                        (Private on YouTube until publish time)
                      </div>
                    </div>
                  ` : `
                    <div style="font-size: 12px; margin-bottom: 8px; color: var(--warning); font-weight: 600;">
                      ⏳ Status: READY TO UPLOAD
                    </div>
                  `}

                  <div class="clip-footer" style="flex-wrap: wrap;">
                    <a href="${videoUrl}" download class="btn btn-secondary btn-sm" style="flex: 1; justify-content: center;">⬇️ Save</a>
                    ${isScheduled
                      ? `<a href="${ytLink}" target="_blank" class="btn btn-yt btn-sm" style="flex: 1; justify-content: center;">▶️ Watch Link ↗</a>
                         <a href="${studioLink}" target="_blank" class="btn btn-secondary btn-sm" style="flex: 1; justify-content: center;" title="Open in YouTube Studio">⚙️ Studio ↗</a>`
                      : `<button id="btn-upload-${c.id}" onclick="uploadClip('${c.id}')" class="btn btn-yt btn-sm" style="flex: 1; justify-content: center;">🚀 Schedule</button>`
                    }
                  </div>
                </div>
              </div>
            `;
          }).reverse().join('');
        }

      } catch (e) {
        console.error("fetchStatus error", e);
      }
    }

    // Auto poll status
    fetchStatus();
    checkYouTubeStatus();
    setInterval(fetchStatus, 1800);
    setInterval(checkYouTubeStatus, 4000);
  </script>
</body>
</html>
"""


class StudioHandler(BaseHTTPRequestHandler):
    cfg = None
    store = None

    def log_message(self, format, *args):
        return

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_static_file(self, filepath):
        path = Path(filepath).resolve()
        root = Path(".").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            self.send_error(404, "File Not Found")
            return

        size = path.stat().st_size
        mime = "video/mp4" if path.suffix == ".mp4" else "application/octet-stream"
        range_header = self.headers.get("Range")

        try:
            if range_header:
                m = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                    length = end - start + 1
                    self.send_response(206)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    with open(path, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                    return

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if path == "/api/status":
            with job_lock:
                j = dict(job_state)
            clips = self.store.d.get("clips", [])
            inbox_files = [f.name for f in Path("inbox").glob("*.mp4")] if Path("inbox").exists() else []
            safe_cfg = {
                "gemini_model": self.cfg.get("gemini_model", ""),
                "whisper_model": self.cfg.get("whisper_model", ""),
                "clips_per_video": self.cfg.get("clips_per_video", 5)
            }
            self.send_json({"job": j, "clips": clips, "inbox": inbox_files, "config": safe_cfg})
            return

        if path == "/api/youtube_status":
            connected = uploader.is_connected()
            info = uploader.get_channel_info() if connected else None
            self.send_json({
                "connected": connected,
                "has_secret": uploader.has_client_secret(),
                "channel": info,
                "auth_state": auth_state
            })
            return

        if path == "/api/open_folder":
            Path("output").mkdir(exist_ok=True)
            subprocess.run(["open", str(Path("output").resolve())])
            self.send_json({"ok": True})
            return

        if path.startswith("/output/") or path.startswith("/downloads/") or path.startswith("/inbox/"):
            clean_path = urllib.parse.unquote(path.lstrip("/"))
            self.serve_static_file(clean_path)
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/process":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except Exception:
                self.send_json({"ok": False, "error": "Invalid JSON"}, 400)
                return

            with job_lock:
                if job_state["status"] == "running":
                    self.send_json({"ok": False, "error": "Bot pehle se hi ek video process kar raha hai!"}, 409)
                    return

            target = data.get("target", "").strip()
            clips_count = data.get("clips_count", 5)
            auto_upload = bool(data.get("auto_upload", False))

            if not target:
                self.send_json({"ok": False, "error": "Video target zaroori hai"}, 400)
                return

            t = threading.Thread(
                target=run_pipeline_job,
                args=(self.cfg, self.store, target, clips_count, auto_upload),
                daemon=True
            )
            t.start()
            self.send_json({"ok": True})
            return

        if path == "/api/upload_file":
            length = int(self.headers.get("Content-Length", 0))
            raw_name = self.headers.get("X-Filename", "video.mp4")
            name = Path(urllib.parse.unquote(raw_name)).name
            if not name.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
                name += ".mp4"

            Path("inbox").mkdir(exist_ok=True)
            dest = Path("inbox") / name
            try:
                with open(dest, "wb") as f:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                self.send_json({"ok": True, "path": str(dest)})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/upload_secret":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                json.loads(body)
                Path("client_secret.json").write_bytes(body)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "error": "Invalid JSON file: " + str(e)}, 400)
            return

        if path == "/api/auth_youtube":
            if not uploader.has_client_secret():
                self.send_json({"ok": False, "error": "Pehle client_secret.json upload karein."}, 400)
                return
            t = threading.Thread(target=run_oauth_flow, daemon=True)
            t.start()
            self.send_json({"ok": True})
            return

        if path == "/api/disconnect_youtube":
            uploader.disconnect()
            self.send_json({"ok": True})
            return

        if path == "/api/upload_clip":
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length))
                clip_id = data.get("clip_id")
                vid, slot = uploader.upload_single_clip(clip_id, self.cfg, self.store)
                self.send_json({"ok": True, "video_id": vid, "publish_at": slot})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/upload_all":
            try:
                import main
                uploaded = main.upload_ready(self.cfg, self.store)
                self.send_json({"ok": True, "message": f"{uploaded} clips scheduled successfully!"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return

        self.send_error(404)


def find_free_port(start_port=8080):
    import socket
    for p in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start_port


def start(cfg, store, host="127.0.0.1", port=None):
    if port is None:
        port = find_free_port(8080)

    StudioHandler.cfg = cfg
    StudioHandler.store = store

    server = HTTPServer((host, port), StudioHandler)
    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f"  🎬 Shorts Bot Studio is LIVE at: {url}")
    print(f"  Browser automatically khul raha hai... (Ctrl+C = Stop)")
    print(f"=======================================================\n", flush=True)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio server band ho gaya.")
        server.server_close()
