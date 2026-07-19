import csv
import hashlib
import json
import re
import time
from pathlib import Path
import requests
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PLAYLISTS_CSV = Path(__file__).parent / "YouTube and YouTube Music/playlists/playlists.csv"
COOKIES_FILE  = Path(__file__).parent / ".yt_cookies.json"
SIGNAL_FILE   = Path(__file__).parent / "login_ready.txt"

def login_and_save_cookies():
    print("Opening Chrome incognito — log into your NEW YouTube account.")
    print("Waiting for login", end="", flush=True)
    chromedriver_autoinstaller.install()
    opts = Options()
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.get("https://www.youtube.com")
    SIGNAL_FILE.unlink(missing_ok=True)
    while not SIGNAL_FILE.exists():
        time.sleep(2)
        print(".", end="", flush=True)
    SIGNAL_FILE.unlink(missing_ok=True)
    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies))
    driver.quit()
    print("\nBrowser closed. Session saved.\n")
    return cookies

def sapisid_hash(sapisid):
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} https://www.youtube.com".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{digest}"

def build_session(cookies):
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".youtube.com"))
    return session

def get_headers(cookies):
    sapisid = next((c["value"] for c in cookies if c["name"] == "SAPISID"), None)
    if not sapisid:
        sapisid = next((c["value"] for c in cookies if c["name"] == "__Secure-3PAPISID"), None)
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Authorization": sapisid_hash(sapisid),
        "X-Goog-AuthUser": "0",
        "X-Origin": "https://www.youtube.com",
        "Content-Type": "application/json",
        "Referer": "https://www.youtube.com",
    }

def get_yt_config(session, headers):
    resp = session.get("https://www.youtube.com", headers=headers)
    api_key    = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', resp.text)
    client_ver = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', resp.text)
    visitor    = re.search(r'"visitorData":"([^"]+)"', resp.text)
    return (
        api_key.group(1) if api_key else None,
        client_ver.group(1) if client_ver else "2.20240101.00.00",
        visitor.group(1) if visitor else ""
    )

def ctx(client_ver, visitor_data):
    return {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": client_ver,
                "visitorData": visitor_data,
                "hl": "en",
                "gl": "US",
            }
        }
    }

def load_playlist_videos(title):
    slug = title.lower().replace(" ", "-")
    f = Path(__file__).parent / f"YouTube and YouTube Music/playlists/{slug}-videos.csv"
    if not f.exists():
        return []
    with open(f, newline="", encoding="utf-8") as fp:
        return [row["Video ID"].strip() for row in csv.DictReader(fp) if row["Video ID"].strip()]

def like_video(session, headers, api_key, client_ver, visitor_data, video_id):
    body = {**ctx(client_ver, visitor_data), "target": {"videoId": video_id}}
    r = session.post(
        f"https://www.youtube.com/youtubei/v1/like/like?key={api_key}",
        headers=headers, json=body, timeout=10
    )
    return r.status_code in (200, 204)

def add_to_playlist(session, headers, api_key, client_ver, visitor_data, playlist_id, video_id):
    body = {
        **ctx(client_ver, visitor_data),
        "playlistId": playlist_id,
        "actions": [{"addedVideoId": video_id, "action": "ACTION_ADD_VIDEO"}]
    }
    r = session.post(
        f"https://www.youtube.com/youtubei/v1/browse/edit_playlist?key={api_key}",
        headers=headers, json=body, timeout=10
    )
    return r.status_code in (200, 204)

def create_playlist(session, headers, api_key, client_ver, visitor_data, title, privacy):
    # Try given privacy first, fall back to PRIVATE if it fails
    for p in [privacy.upper(), "PRIVATE"]:
        body = {
            **ctx(client_ver, visitor_data),
            "title": title,
            "privacyStatus": p,
        }
        r = session.post(
            f"https://www.youtube.com/youtubei/v1/playlist/create?key={api_key}",
            headers=headers, json=body, timeout=10
        )
        data = r.json()
        playlist_id = data.get("playlistId")
        if playlist_id:
            print(f"  Created with privacy={p}")
            return playlist_id
        print(f"  privacy={p} failed ({r.status_code}), trying next...")
    return None

def load_playlists():
    playlists = []
    with open(PLAYLISTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = row.get("Playlist Title (Original)", "").strip()
            if title:
                playlists.append({
                    "id": row["Playlist ID"].strip(),
                    "title": title,
                    "privacy": row["Playlist Visibility"].strip(),
                })
    return playlists

def main():
    playlists = load_playlists()
    print(f"Found {len(playlists)} playlists.\n")

    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text())
    else:
        cookies = login_and_save_cookies()

    session = build_session(cookies)
    headers = get_headers(cookies)

    print("Fetching YouTube config...")
    api_key, client_ver, visitor_data = get_yt_config(session, headers)

    if not api_key:
        print("Session expired. Re-logging in...")
        cookies = login_and_save_cookies()
        session = build_session(cookies)
        headers = get_headers(cookies)
        api_key, client_ver, visitor_data = get_yt_config(session, headers)

    print(f"Config ready.\n")

    for pl in playlists:
        title   = pl["title"]
        pl_id   = pl["id"]
        privacy = pl["privacy"]
        videos  = load_playlist_videos(title)

        print(f'Playlist: "{title}" | {len(videos)} videos | {privacy}')

        # Determine playlist type by ID prefix
        if pl_id.startswith("FL"):
            # Favorites = liked videos
            print("  Type: Favorites (liked videos) — liking each video...")
            done = 0
            for vid in videos:
                ok = like_video(session, headers, api_key, client_ver, visitor_data, vid)
                print(f"  {'liked' if ok else 'failed'}: {vid}")
                done += 1 if ok else 0
                time.sleep(0.3)
            print(f"  Done: {done}/{len(videos)}\n")

        elif title.lower() == "watch later":
            # Watch Later = built-in playlist with ID "WL"
            print("  Type: Watch Later — adding to WL playlist...")
            done = 0
            for vid in videos:
                ok = add_to_playlist(session, headers, api_key, client_ver, visitor_data, "WL", vid)
                print(f"  {'added' if ok else 'failed'}: {vid}")
                done += 1 if ok else 0
                time.sleep(0.3)
            print(f"  Done: {done}/{len(videos)}\n")

        else:
            # Regular playlist — create it then add videos
            print(f"  Type: Regular — creating playlist...")
            new_id = create_playlist(session, headers, api_key, client_ver, visitor_data, title, privacy)
            if not new_id:
                print(f"  Failed to create playlist. Skipping.\n")
                continue
            print(f"  Created! ID: {new_id} — adding {len(videos)} videos...")
            done = 0
            for vid in videos:
                ok = add_to_playlist(session, headers, api_key, client_ver, visitor_data, new_id, vid)
                print(f"  {'added' if ok else 'failed'}: {vid}")
                done += 1 if ok else 0
                time.sleep(0.3)
            print(f"  Done: {done}/{len(videos)}\n")

    print("All playlists imported!")

if __name__ == "__main__":
    main()
