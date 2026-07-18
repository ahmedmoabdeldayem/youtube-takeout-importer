import re
import json
import time
from pathlib import Path
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HISTORY_HTML  = Path(__file__).parent / "YouTube and YouTube Music/history/watch-history.html"
PROGRESS_FILE = Path(__file__).parent / ".watch_progress.json"
COOKIES_FILE  = Path(__file__).parent / ".yt_cookies.json"
SIGNAL_FILE   = Path(__file__).parent / "login_ready.txt"

BATCH_SIZE = 999999  # process all videos

def extract_video_ids():
    text = HISTORY_HTML.read_text(encoding="utf-8")
    ids = re.findall(r'href="https://www\.youtube\.com/watch\?v=([^"]+)"', text)
    # deduplicate while preserving order (most recent first)
    seen = set()
    unique = []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            unique.append(vid)
    return unique

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": []}

def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress))

def login_and_save_cookies():
    print("Opening Chrome incognito window — log into your NEW YouTube account.")
    print(f"\nOnce fully logged in, I will signal automatically.\n")
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

    SIGNAL_FILE.unlink(missing_ok=True)
    while not SIGNAL_FILE.exists():
        time.sleep(2)
        print(".", end="", flush=True)

    SIGNAL_FILE.unlink(missing_ok=True)
    print("\nSignal received! Saving session...")

    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies))
    driver.quit()
    print("Browser closed. Session saved for future runs.\n")
    return cookies

def build_headless_driver(cookies):
    chromedriver_autoinstaller.install()
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.page_load_strategy = "eager"  # don't wait for all resources, just DOM ready
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # Load cookies into the headless browser
    driver.get("https://www.youtube.com")
    for c in cookies:
        try:
            driver.add_cookie(c)
        except Exception:
            pass
    driver.get("https://www.youtube.com")
    return driver

def main():
    all_ids = extract_video_ids()
    print(f"Total unique videos in history: {len(all_ids)}")

    progress = load_progress()
    done_set = set(progress["done"])

    # Reverse so oldest videos are visited first, most recent last
    # This makes the new account's history match the original order
    all_ids = list(reversed(all_ids))

    # Find the next batch of videos not yet processed
    pending = [vid for vid in all_ids if vid not in done_set]
    batch = pending[:BATCH_SIZE]

    if not batch:
        print("All videos already processed!")
        return

    print(f"Already imported: {len(done_set)} | Remaining: {len(pending)} | This batch: {len(batch)}\n")

    # Load or create cookies
    if COOKIES_FILE.exists():
        print("Found saved session, reusing it...")
        cookies = json.loads(COOKIES_FILE.read_text())
    else:
        cookies = login_and_save_cookies()

    print("Starting headless browser...")
    driver = build_headless_driver(cookies)

    success = 0
    failed = 0

    for i, vid in enumerate(batch, 1):
        url = f"https://www.youtube.com/watch?v={vid}"
        print(f"[{i}/{len(batch)}] {vid} ... ", end="", flush=True)
        try:
            driver.get(url)
            # Wait until the video player appears — confirms page loaded and history was recorded
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#movie_player"))
            )
            progress["done"].append(vid)
            save_progress(progress)
            print("done")
            success += 1
        except Exception as e:
            print(f"skipped ({e.__class__.__name__})")
            failed += 1

    driver.quit()

    remaining_after = len(all_ids) - len(set(progress["done"]))
    print(f"\nBatch done — Success: {success} | Failed: {failed}")
    print(f"Total imported so far: {len(progress['done'])} / {len(all_ids)}")
    if remaining_after > 0:
        print(f"Still remaining: {remaining_after} — run the script again to continue.")
    else:
        print("All videos imported!")

if __name__ == "__main__":
    main()
