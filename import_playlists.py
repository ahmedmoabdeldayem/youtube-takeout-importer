import csv
import json
import time
from pathlib import Path
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PLAYLISTS_CSV = Path(__file__).parent / "YouTube and YouTube Music/playlists/playlists.csv"
COOKIES_FILE  = Path(__file__).parent / ".yt_cookies.json"
SIGNAL_FILE   = Path(__file__).parent / "login_ready.txt"

def login_and_save_cookies(driver):
    print("Opening browser for login...")
    driver.get("https://www.youtube.com")
    SIGNAL_FILE.unlink(missing_ok=True)
    print("Waiting for login", end="", flush=True)
    while not SIGNAL_FILE.exists():
        time.sleep(2)
        print(".", end="", flush=True)
    SIGNAL_FILE.unlink(missing_ok=True)
    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies))
    print("\nSession saved.\n")
    return cookies

def build_driver(headless=True):
    chromedriver_autoinstaller.install()
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=opts)

def load_playlist_videos(title):
    slug = title.lower().replace(" ", "-")
    videos_file = Path(__file__).parent / f"YouTube and YouTube Music/playlists/{slug}-videos.csv"
    if not videos_file.exists():
        return []
    with open(videos_file, newline="", encoding="utf-8") as f:
        return [row["Video ID"].strip() for row in csv.DictReader(f)]

def create_playlist_and_add_videos(driver, title, privacy, videos):
    wait = WebDriverWait(driver, 15)

    # Go to a video page to trigger the "Save" menu (easiest way to create playlist)
    if not videos:
        print(f'  No videos for "{title}", skipping.')
        return

    first_video = videos[0]
    print(f"  Opening video {first_video} to create playlist from Save menu...")
    driver.get(f"https://www.youtube.com/watch?v={first_video}")
    time.sleep(3)

    def js_click(el):
        driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)

    # Click the Save button under the video
    try:
        save_btn = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//button[.//yt-formatted-string[text()="Save"]] | //button[@aria-label="Save to playlist"]')
        ))
        js_click(save_btn)
        time.sleep(2)
    except Exception as e:
        print(f"  Could not find Save button: {e}")
        return

    # Click "+ Create new playlist"
    try:
        new_pl_btn = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[contains(text(),"Create new playlist") or contains(text(),"New playlist")]')
        ))
        js_click(new_pl_btn)
        time.sleep(1.5)
    except Exception as e:
        print(f"  Could not find New Playlist button: {e}")
        return

    # Save screenshot for debugging
    driver.save_screenshot(str(Path(__file__).parent / "debug_playlist.png"))
    print(f"  Screenshot saved. Looking for name input...")

    # Type playlist name — try multiple selectors
    name_input = None
    for selector in [
        (By.XPATH, '//input[@id="input"]'),
        (By.XPATH, '//input[contains(@placeholder,"Name") or contains(@placeholder,"name")]'),
        (By.CSS_SELECTOR, 'ytcp-text-input-field input'),
        (By.CSS_SELECTOR, '#title-field input'),
        (By.XPATH, '//input[@maxlength]'),
        (By.XPATH, '//div[@contenteditable="true"]'),
    ]:
        try:
            name_input = WebDriverWait(driver, 4).until(EC.presence_of_element_located(selector))
            print(f"  Found input with selector: {selector}")
            break
        except Exception:
            continue

    if not name_input:
        print(f"  Could not find name input. Check debug_playlist.png for the current state.")
        return

    name_input.clear()
    name_input.send_keys(title)
    time.sleep(0.5)

    # Set privacy
    try:
        privacy_select = driver.find_element(By.TAG_NAME, "select")
        for option in privacy_select.find_elements(By.TAG_NAME, "option"):
            if privacy.lower() in option.text.lower():
                js_click(option)
                break
        time.sleep(0.5)
    except Exception:
        pass

    # Click Create
    try:
        create_btn = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//button[.//yt-formatted-string[text()="Create"] or .//span[text()="Create"]]')
        ))
        js_click(create_btn)
        time.sleep(2)
        print(f'  Playlist "{title}" created with first video!')
    except Exception as e:
        print(f"  Could not click Create: {e}")
        return

    # Add remaining videos
    for vid in videos[1:]:
        print(f"  Adding video {vid}...")
        driver.get(f"https://www.youtube.com/watch?v={vid}")
        time.sleep(3)
        try:
            save_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, '//button[.//yt-formatted-string[text()="Save"]] | //button[@aria-label="Save to playlist"]')
            ))
            save_btn.click()
            time.sleep(1.5)

            # Find the checkbox for our playlist
            pl_checkbox = wait.until(EC.presence_of_element_located(
                (By.XPATH, f'//*[contains(text(),"{title}")]//preceding-sibling::*[@id="checkbox"] | //*[contains(@title,"{title}")]')
            ))
            if "checked" not in pl_checkbox.get_attribute("class"):
                pl_checkbox.click()
            time.sleep(1)

            # Close dialog
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.5)
            print(f"  Added.")
        except Exception as e:
            print(f"  Could not add video {vid}: {e}")

def main():
    playlists = []
    with open(PLAYLISTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Playlist Title (Original)"].strip():
                playlists.append(row)

    print(f"Found {len(playlists)} playlist(s) to import.\n")

    # Login with visible browser first
    driver = build_driver(headless=False)

    if COOKIES_FILE.exists():
        print("Found saved session, trying to reuse...")
        driver.get("https://www.youtube.com")
        for c in json.loads(COOKIES_FILE.read_text()):
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.get("https://www.youtube.com")
        time.sleep(2)
        if "Sign in" in driver.page_source or "accounts.google" in driver.current_url:
            print("Session expired.")
            login_and_save_cookies(driver)
        else:
            print("Session still valid.\n")
    else:
        login_and_save_cookies(driver)

    # Switch to headless not possible mid-session, so keep visible for now
    # but minimize interaction — this runs fast anyway (only 1 playlist, 1 video)

    for pl in playlists:
        title   = pl["Playlist Title (Original)"].strip()
        privacy = pl["Playlist Visibility"].strip()
        videos  = load_playlist_videos(title)
        print(f'Playlist: "{title}" | Visibility: {privacy} | Videos: {len(videos)}')
        create_playlist_and_add_videos(driver, title, privacy, videos)
        print()

    driver.quit()
    print("Done importing playlists!")

if __name__ == "__main__":
    main()
