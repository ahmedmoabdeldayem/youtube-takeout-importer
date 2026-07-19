# YouTube Takeout Importer

Import your YouTube history, subscriptions, search history, and music library from a Google Takeout export into a new YouTube account — without using the official YouTube API.

## What gets imported

| Data | Script | Method |
|------|--------|--------|
| Subscriptions | `subscribe.py` | HTTP requests |
| Watch history (ordered) | `watch_history.py` | Headless browser |
| Search history (ordered) | `import_search.py` | HTTP requests |
| YouTube Music library | `import_music.py` | HTTP requests |
| Playlists | `import_playlists.py` | Browser automation (WIP) |

- Watch and search history are imported **oldest first, most recent last** — so your history order matches the original account
- Duplicate entries are automatically removed
- Watch history tracks progress and can be **resumed** if interrupted

## Requirements

- Python 3.8+
- Google Chrome installed
- A Google Takeout export with YouTube data

**How to export your YouTube data:**
1. Go to [https://takeout.google.com/settings/takeout](https://takeout.google.com/settings/takeout)
2. Click **Deselect all**
3. Scroll down and select only **YouTube and YouTube Music**
4. Click **Next step** → choose your export format (zip) and frequency (export once)
5. Click **Create export** — Google will email you a download link when it's ready
6. Download and extract the zip — you'll find a `Takeout` folder inside

> **Important:** These scripts are designed for the **HTML export format** (the default). When selecting your export format in Google Takeout, make sure history is exported as **HTML**, not JSON.

## Setup

**1. Place the scripts inside your Takeout folder**, at the same level as the `YouTube and YouTube Music` folder:

```
Takeout/
├── YouTube and YouTube Music/
│   ├── history/
│   ├── subscriptions/
│   ├── playlists/
│   └── ...
├── subscribe.py
├── watch_history.py
├── import_search.py
├── import_music.py
└── requirements.txt
```

**2. Create a virtual environment and install dependencies:**

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt   # macOS/Linux
# or
venv\Scripts\pip install -r requirements.txt   # Windows
```

## Usage

Run each script in order. Each one will open a **Chrome incognito window once** for you to log into your new YouTube account — after that it runs silently in the background.

### 1. Subscriptions

```bash
venv/bin/python3 subscribe.py
```

- Opens Chrome incognito → log in → come back to terminal and create a file named `login_ready.txt` in the Takeout folder to signal you're done
- Subscribes to all your channels via HTTP requests

### 2. Watch History

```bash
venv/bin/python3 watch_history.py
```

- Same login flow as above
- Runs a headless browser to visit each video (required for YouTube to register the view)
- Progress is saved to `.watch_progress.json` — if interrupted, just re-run and it continues from where it left off
- Skips deleted/private videos automatically

### 3. Search History

```bash
venv/bin/python3 import_search.py
```

- Same login flow
- Sends authenticated requests to each search URL to record it in history

### 4. YouTube Music Library

```bash
venv/bin/python3 import_music.py
```

- Same login flow
- Saves each song to your YouTube Music library via the internal like API

## How the login works

Every script uses the same flow:
1. Opens a **real Chrome incognito window** (bypasses Google's bot detection)
2. You log into your new account manually
3. Create a file called `login_ready.txt` in the Takeout folder (or run `touch login_ready.txt` in a second terminal)
4. The browser closes and saves your session cookies
5. All subsequent requests reuse those cookies — no browser needed per item

Session cookies are saved to `.yt_cookies.json` and reused across scripts until they expire.

## Notes

- **Playlists** (`import_playlists.py`) are partially working — playlist creation via browser automation is fragile due to YouTube's UI. For small numbers of playlists, it's easier to create them manually.
- Watch history takes the longest — expect roughly **50–60 videos per minute** depending on your connection
- Search history runs at roughly **60 searches per minute**
- YouTube may show slight delays before history appears in your account

## Tested on

- macOS with Chrome 150
- Python 3.14
- Google Takeout export format as of 2025

## Contributing & Support

- **Questions?** Use the [Discussions](https://github.com/ahmedmoabdeldayem/youtube-takeout-importer/discussions) tab — ask anything and the community can help answer
- **Found a bug?** Open an [Issue](https://github.com/ahmedmoabdeldayem/youtube-takeout-importer/issues) with details about what went wrong
- **Want to contribute?** Fork the repo and submit a pull request
