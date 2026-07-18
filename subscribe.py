import csv
import hashlib
import time
import re
from pathlib import Path
import requests
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

SUBSCRIPTIONS_CSV = Path(__file__).parent / "YouTube and YouTube Music/subscriptions/subscriptions.csv"

def sapisid_hash(sapisid):
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} https://www.youtube.com".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{digest}"

def load_channels():
    channels = []
    with open(SUBSCRIPTIONS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            channels.append({
                "id": row["Channel Id"].strip(),
                "title": row["Channel Title"].strip(),
            })
    return channels

SIGNAL_FILE = Path(__file__).parent / "login_ready.txt"

def get_cookies_via_incognito():
    print("Opening Chrome incognito window — log into your NEW YouTube account there.")
    print(f"\nOnce you're fully logged in, open a NEW terminal and run:")
    print(f"  touch \"{SIGNAL_FILE}\"\n")
    print("Waiting for you to log in", end="", flush=True)

    chromedriver_autoinstaller.install()

    opts = Options()
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.get("https://www.youtube.com")

    # Wait for signal file
    SIGNAL_FILE.unlink(missing_ok=True)
    while not SIGNAL_FILE.exists():
        time.sleep(2)
        print(".", end="", flush=True)

    SIGNAL_FILE.unlink(missing_ok=True)
    print("\nSignal received!")

    # Extract cookies from the browser session
    selenium_cookies = driver.get_cookies()
    driver.quit()
    print("Browser closed.\n")
    return selenium_cookies

def build_session(selenium_cookies):
    session = requests.Session()
    for c in selenium_cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".youtube.com"))
    return session

def main():
    channels = load_channels()
    print(f"Found {len(channels)} channels to subscribe to.\n")

    selenium_cookies = get_cookies_via_incognito()

    sapisid = next((c["value"] for c in selenium_cookies if c["name"] == "SAPISID"), None)
    if not sapisid:
        sapisid = next((c["value"] for c in selenium_cookies if c["name"] == "__Secure-3PAPISID"), None)
    if not sapisid:
        print("ERROR: Could not find SAPISID cookie. Please make sure you fully logged in.")
        return

    session = build_session(selenium_cookies)
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    print("Fetching YouTube config...")
    resp = session.get("https://www.youtube.com", headers={"User-Agent": ua})
    api_key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', resp.text)
    client_ver = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', resp.text)
    if not api_key:
        print("ERROR: Could not extract YouTube API key. Are you logged in correctly?")
        return
    api_key = api_key.group(1)
    client_ver = client_ver.group(1) if client_ver else "2.20240101.00.00"

    headers = {
        "User-Agent": ua,
        "Authorization": sapisid_hash(sapisid),
        "X-Goog-AuthUser": "0",
        "X-Origin": "https://www.youtube.com",
        "Content-Type": "application/json",
        "Referer": "https://www.youtube.com",
    }

    done = skipped = failed = 0

    print("Starting subscriptions (running in background)...\n")
    for i, ch in enumerate(channels, 1):
        print(f"[{i}/{len(channels)}] {ch['title']} ... ", end="", flush=True)

        body = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": client_ver,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "channelIds": [ch["id"]],
        }

        try:
            r = session.post(
                f"https://www.youtube.com/youtubei/v1/subscription/subscribe?key={api_key}",
                headers=headers,
                json=body,
                timeout=10,
            )
            if r.status_code in (200, 204):
                print("subscribed")
                done += 1
            elif r.status_code == 400:
                print("already subscribed or invalid")
                skipped += 1
            else:
                print(f"failed (HTTP {r.status_code})")
                failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

        time.sleep(0.5)

    print(f"\nDone — Subscribed: {done} | Skipped: {skipped} | Failed: {failed}")

if __name__ == "__main__":
    main()
