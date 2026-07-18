import re
import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote_plus
import requests
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

SEARCH_HTML  = Path(__file__).parent / "YouTube and YouTube Music/history/search-history.html"
COOKIES_FILE = Path(__file__).parent / ".yt_cookies.json"
SIGNAL_FILE  = Path(__file__).parent / "login_ready.txt"

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
        "Referer": "https://www.youtube.com",
        "Accept-Language": "en-US,en;q=0.9",
    }

def extract_searches():
    text = SEARCH_HTML.read_text(encoding="utf-8")
    urls = re.findall(r'href="(https://www\.youtube\.com/results\?search_query=[^"]+)"', text)
    # Extract query strings and deduplicate while preserving order
    seen = set()
    queries = []
    for url in reversed(urls):  # reversed = oldest first
        parsed = urlparse(url)
        q = parse_qs(parsed.query).get("search_query", [""])[0]
        q = unquote_plus(q)
        if q and q not in seen:
            seen.add(q)
            queries.append(q)
    return queries

def main():
    queries = extract_searches()
    print(f"Found {len(queries)} unique searches to import (oldest first).\n")

    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text())
    else:
        cookies = login_and_save_cookies()

    session = build_session(cookies)
    headers = get_headers(cookies)

    # Verify session is valid
    test = session.get("https://www.youtube.com/feed/history", headers=headers, allow_redirects=False)
    if test.status_code in (301, 302):
        print("Session expired. Re-logging in...")
        cookies = login_and_save_cookies()
        session = build_session(cookies)
        headers = get_headers(cookies)

    print("Starting search history import...\n")
    done = failed = 0

    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query[:60]} ... ", end="", flush=True)
        try:
            r = session.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                print("done")
                done += 1
            else:
                print(f"failed (HTTP {r.status_code})")
                failed += 1
        except Exception as e:
            print(f"ERROR: {e.__class__.__name__}")
            failed += 1

        time.sleep(0.3)

    print(f"\nDone — Imported: {done} | Failed: {failed}")
    print("Check youtube.com/feed/history to verify searches appear.")

if __name__ == "__main__":
    main()
