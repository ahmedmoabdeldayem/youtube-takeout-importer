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

MUSIC_CSV    = Path(__file__).parent / "YouTube and YouTube Music/music (library and uploads)/music library songs.csv"
COOKIES_FILE = Path(__file__).parent / ".yt_cookies.json"
SIGNAL_FILE  = Path(__file__).parent / "login_ready.txt"

def login_and_save_cookies():
    print("Opening Chrome incognito — log into your NEW YouTube/Google account.")
    print("Waiting for login", end="", flush=True)
    chromedriver_autoinstaller.install()
    opts = Options()
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.get("https://music.youtube.com")
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

def sapisid_hash(sapisid, origin="https://music.youtube.com"):
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
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
        "X-Origin": "https://music.youtube.com",
        "Content-Type": "application/json",
        "Referer": "https://music.youtube.com",
        "Origin": "https://music.youtube.com",
    }

def get_yt_music_config(session, headers):
    resp = session.get("https://music.youtube.com", headers=headers)
    api_key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', resp.text)
    client_ver = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', resp.text)
    return (
        api_key.group(1) if api_key else None,
        client_ver.group(1) if client_ver else "1.20240101.00.00"
    )

def load_songs():
    songs = []
    with open(MUSIC_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            songs.append({
                "id": row["Video ID"].strip(),
                "title": row["Song Title"].strip(),
                "artist": row["Artist Name 1"].strip(),
            })
    return songs

def main():
    songs = load_songs()
    print(f"Found {len(songs)} songs to add to YouTube Music library.\n")

    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text())
    else:
        cookies = login_and_save_cookies()

    session = build_session(cookies)
    headers = get_headers(cookies)

    print("Fetching YouTube Music config...")
    api_key, client_ver = get_yt_music_config(session, headers)

    if not api_key:
        print("Session expired. Re-logging in...")
        cookies = login_and_save_cookies()
        session = build_session(cookies)
        headers = get_headers(cookies)
        api_key, client_ver = get_yt_music_config(session, headers)

    print(f"Config ready. Starting import...\n")

    done = failed = 0

    for i, song in enumerate(songs, 1):
        print(f"[{i}/{len(songs)}] {song['title']} — {song['artist']} ... ", end="", flush=True)

        body = {
            "context": {
                "client": {
                    "clientName": "WEB_REMIX",
                    "clientVersion": client_ver,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "target": {
                "videoId": song["id"]
            }
        }

        try:
            r = session.post(
                f"https://music.youtube.com/youtubei/v1/like/like?key={api_key}",
                headers=headers,
                json=body,
                timeout=10,
            )
            if r.status_code in (200, 204):
                print("saved to library")
                done += 1
            else:
                print(f"failed (HTTP {r.status_code})")
                failed += 1
        except Exception as e:
            print(f"ERROR: {e.__class__.__name__}")
            failed += 1

        time.sleep(0.5)

    print(f"\nDone — Saved: {done} | Failed: {failed}")

if __name__ == "__main__":
    main()
