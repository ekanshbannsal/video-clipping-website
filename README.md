# 🎬 Shorts Bot Studio (Open-Source AI Video Clipper & Auto-Scheduler)

An open-source, 100% free AI-powered automation tool that takes any long-form video (YouTube URL or local MP4), extracts the most engaging viral moments using AI, crops them into 9:16 vertical shorts with smart face tracking, generates animated styled captions, and automatically schedules them for upload to YouTube Shorts.

Runs completely on your local computer — **zero paid cloud subscriptions, zero per-minute transcription fees, unlimited videos**.

---

## ✨ Features

- **🌐 Modern Web Studio UI**: Interactive browser interface to paste links, drag-and-drop local videos, monitor real-time rendering logs, and preview generated shorts directly.
- **🤖 Smart AI Moment Selection**: Uses Google Gemini AI to analyze full timestamped transcripts, find hooks, craft viral titles, and pick standalone viral moments.
- **⚡ Local Fast Whisper Transcription**: Automatic speech-to-text with word-level timestamps using `faster-whisper` (supports Hindi, English, and 90+ languages).
- **📐 9:16 Smart Dynamic Cropping**: Uses OpenCV facial detection to dynamically center the speaker in vertical video format.
- **🎨 Word-by-Word Animated Captions**: Burns professional ASS subtitles with custom fonts, colors, and an eye-catching 3-second hook overlay.
- **🚀 1-Click YouTube Auto-Schedule**: Connect your YouTube channel via Google OAuth and auto-schedule shorts at optimal posting slots (e.g. 09:00, 13:00, 19:00).
- **🔄 Auto-Watch Mode (Set & Forget)**: Automatically polls your YouTube channel RSS feed or local `inbox/` folder and processes new uploads unattended.

---

## 📋 System Requirements

- **Operating System**: macOS, Linux, or Windows (WSL2 recommended)
- **Python**: Version 3.10 or 3.11
- **FFmpeg**: Must be compiled with `libass` (for subtitle burning)
- **RAM**: Minimum 4 GB (8 GB+ recommended)
- **Gemini API Key**: Free tier available at [Google AI Studio](https://aistudio.google.com/apikey)

---

## 🚀 Installation & Setup Guide

### 1. Install FFmpeg with Subtitle Support (`libass`)

> [!IMPORTANT]
> Standard FFmpeg on macOS Homebrew does not include `libass` by default. Make sure to install `ffmpeg-full`.

- **macOS (via Homebrew)**:
  ```bash
  brew install ffmpeg-full
  brew link --overwrite ffmpeg-full
  ```
  *(Verify installation: `ffmpeg -filters | grep ass` — should show `ass` and `subtitles` filters).*

- **Ubuntu / Debian Linux**:
  ```bash
  sudo apt update
  sudo apt install -y ffmpeg libass-dev python3-venv python3-pip
  ```

- **Windows**:
  Download the full build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (`ffmpeg-git-full.7z`) and add the `bin` directory to your system `PATH`.

---

### 2. Clone the Repository & Setup Python Environment

```bash
# Clone this repository
git clone https://github.com/arnavarya001/Open-source-free-video-clipping.git
cd Open-source-free-video-clipping

# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
# On macOS / Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

---

### 3. Get Your Free Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey).
2. Click **Create API Key** and copy it.
3. In the project folder, create a `.env` file:
   ```bash
   cp .env.example .env
   ```
4. Open `.env` and paste your key:
   ```env
   GEMINI_API_KEY="your_actual_api_key_here"
   ```

---

## 💻 How to Use

### Method 1: Web Studio UI (Recommended)

Simply start the server:
```bash
python main.py
# or: python main.py ui
```

Your browser will automatically open: **`http://127.0.0.1:8080`**

From the Studio UI, you can:
1. Paste any **YouTube URL** or drag & drop an **MP4 file**.
2. Select how many clips to generate (e.g. 5).
3. Click **⚡ Generate Shorts**.
4. View real-time progress (Download ➔ Whisper Transcription ➔ Gemini AI Selection ➔ 9:16 FFmpeg Cropping).
5. Watch generated shorts inside the built-in 9:16 player, download them, or schedule them to YouTube with 1 click.

---

### Method 2: Command Line (CLI)

- **Process a video and generate clips (without uploading)**:
  ```bash
  python main.py add "https://www.youtube.com/watch?v=VIDEO_ID"
  # or local file:
  python main.py add my_video.mp4
  ```

- **Process and schedule upload in one step**:
  ```bash
  python main.py run "https://www.youtube.com/watch?v=VIDEO_ID"
  ```

- **Upload already generated ready clips**:
  ```bash
  python main.py upload
  ```

- **Check status of all clips**:
  ```bash
  python main.py status
  ```

- **Full Auto Watch Mode (Set & Forget)**:
  Monitors `inbox/` folder, `links.txt`, or your channel's RSS feed:
  ```bash
  # Mac (caffeinate keeps Mac awake):
  caffeinate -i python main.py watch
  ```

---

## 📺 YouTube Auto-Upload & Scheduling Setup

To allow the bot to automatically upload and schedule shorts to your YouTube channel:

### 1. Create Google Cloud OAuth Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Shorts-Bot`).
3. Navigate to **APIs & Services ➔ Library**, search for **YouTube Data API v3**, and click **Enable**.
4. Navigate to **Google Auth Platform ➔ Audience** (or *OAuth consent screen*):
   - User Type: **External**
   - Under **Test users**, click **`+ Add users`** and enter your Google account email.
5. Navigate to **APIs & Services ➔ Credentials**:
   - Click **Create Credentials** ➔ **OAuth client ID**.
   - Application type: Select **Desktop App**.
   - Name it (e.g., `Shorts Bot Client`) and click **Create**.
6. Click **Download JSON** and save the file.

### 2. Connect in Studio UI
1. Open the Studio UI at `http://127.0.0.1:8080`.
2. Click the red **`🔗 Connect YouTube`** button on top.
3. Drag & drop the downloaded `client_secret.json` into the upload box.
4. Click **Start Google Sign-In** — your browser will open Google login.
5. Select your channel account and click **Continue / Allow**.
6. Once connected, status will turn **`🟢 YouTube Connected: (Your Channel)`**.

---

## ⚙️ Configuration (`config.yaml`)

You can customize the bot's behavior by editing `config.yaml`:

```yaml
# AI model for clip selection
gemini_model: gemini-3.5-flash-lite

# Transcription settings
whisper_model: small       # tiny, base, small, medium (medium gives best Hindi accuracy)
language: auto             # "auto", "en", or "hi"

# Clips duration limits
clips_per_video: 5
clip_min_sec: 20
clip_max_sec: 58           # Shorts must be under 60 seconds

# Captions & Video Styling
captions:
  enabled: true
  font: Arial              # For Hindi on Mac, use: "Kohinoor Devanagari"
  font_size: 80
  hook_font_size: 66
  words_per_line: 3
  uppercase: true          # Set false for Hindi
  highlight_color: "&H0000FFFF"  # Yellow highlight for current spoken word

hook_text: true            # Displays viral hook title on top for the first 3 seconds
face_tracking: true        # Auto-tracks face for 9:16 cropping
video_preset: veryfast     # FFmpeg render speed (ultrafast ... slow)

# Scheduling Slots (Timezone: Asia/Kolkata)
schedule:
  timezone: Asia/Kolkata
  slots: ["09:00", "13:00", "19:00"]  # Daily release time slots
  max_per_day: 3                       # YouTube API free tier allows ~6 uploads/day
```

---

## 📁 Directory Structure

```
shorts_bot/
├── web.py                 # Self-contained Web Studio UI server (built with Python stdlib)
├── main.py                # Main CLI entrypoint (ui, add, run, watch, upload, status)
├── pipeline.py            # Core engine: Download -> Whisper -> Gemini AI -> FFmpeg
├── uploader.py            # YouTube Data API v3 OAuth upload & scheduling handler
├── store.py               # Local JSON state database & scheduler slot calculation
├── config.yaml            # User preferences & styling settings
├── requirements.txt       # Python dependencies
├── .env.example           # Example environment file for GEMINI_API_KEY
├── .gitignore             # Git ignore file protecting keys, tokens, and media
├── inbox/                 # Put local MP4 files here for auto-processing
├── downloads/             # Downloaded source videos (cached)
├── output/                # Finished 9:16 vertical shorts with captions
└── data/                  # Transcription work cache and scheduling state
```

---

## ❓ Troubleshooting & FAQs

#### Q: FFmpeg error: `No option name near 'clip_01.ass'`
**A:** Your FFmpeg was built without `libass`. On macOS, run `brew install ffmpeg-full && brew link --overwrite ffmpeg-full`. On Linux, install `libass-dev` and rebuild or install `ffmpeg`.

#### Q: Google Sign-in error: `Access blocked: Error 403 access_denied`
**A:** Your Google Cloud OAuth project is in Testing mode. Go to **Google Cloud Console ➔ Google Auth Platform ➔ Audience ➔ Test users**, click **`+ Add users`**, and add your email address.

#### Q: Port 5000 gives `HTTP 403 Forbidden` on Mac
**A:** On macOS Monterey and later, Apple's built-in AirPlay Receiver occupies port 5000. Shorts Bot Studio runs on port **8080** by default (`http://127.0.0.1:8080`).

#### Q: Can I run this in the background continuously?
**A:** Yes! Run `caffeinate -i python main.py` or `python main.py watch` to prevent your computer from going to sleep while processing long videos.

---

## 📜 License

MIT License. Free to use, modify, and distribute.
