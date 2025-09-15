import os
import time

import pyautogui
import winsound
import json
import psutil
import argparse
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options

def switch_to_new_window(driver, old_handle, timeout=10):
    WebDriverWait(driver, timeout).until(lambda d: len(d.window_handles) > 1)
    for h in driver.window_handles:
        if h != old_handle:
            driver.switch_to.window(h)
            return h
    raise RuntimeError("New window not found")

def switch_into_iframe_containing(driver, by, value, timeout=10):
    """Switches into the iframe that contains (by, value). Leaves you inside it."""
    driver.switch_to.default_content()
    # try top-level first
    try:
        WebDriverWait(driver, 1).until(EC.presence_of_element_located((by, value)))
        return
    except TimeoutException:
        pass

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for f in iframes:
        driver.switch_to.default_content()
        driver.switch_to.frame(f)
        try:
            WebDriverWait(driver, 2).until(EC.presence_of_element_located((by, value)))
            return
        except TimeoutException:
            continue

    driver.switch_to.default_content()
    raise NoSuchElementException("Element not found in any iframe")

def check_checkbox(driver, checkbox_id="chkCanAgreeAll", timeout=0.5):
    # 1) leave any seat iframe; checkbox is usually in the main doc
    driver.switch_to.default_content()

    # 2) If it’s inside another frame/panel, hop into it
    try:
        WebDriverWait(driver, 0.1).until(EC.presence_of_element_located((By.ID, checkbox_id)))
    except TimeoutException:
        # use your helper if needed:
        try:
            switch_into_iframe_containing(driver, By.ID, checkbox_id, timeout=timeout)
        except Exception:
            pass  # if not in an iframe, this will just continue

    # 3) Locate input + label
    cb = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, checkbox_id)))
    label_elems = driver.find_elements(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")

    # 4) If not already checked, try clicking the label first (most reliable for hidden inputs)
    if not cb.is_selected():
        if label_elems and label_elems[0].is_displayed():
            try:
                label_elems[0].click()
            except ElementNotInteractableException:
                pass

    # 5) If still not selected, try scrolling & JS click on the input
    if not cb.is_selected():
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cb)
        try:
            cb.click()
        except Exception:
            # 6) Final fallback: force-check and fire events so site logic runs
            driver.execute_script("""
                const el = arguments[0];
                el.checked = true;
                el.dispatchEvent(new Event('input',  {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            """, cb)

    # 7) Verify
    is_checked = driver.execute_script("return arguments[0].checked;", cb)
    if not is_checked:
        raise RuntimeError("Checkbox did not become checked")
    return True

def click_final_payment(driver, timeout=0.5):
    btn_locator = (By.ID, "btnFinalPayment")

    # 1) leave seat iframe; button is often outside that frame
    driver.switch_to.default_content()

    # 2) if the button lives in another iframe/panel, hop into it
    try:
        WebDriverWait(driver, 2).until(EC.presence_of_element_located(btn_locator))
    except TimeoutException:
        try:
            # reuse your helper if you have it:
            switch_into_iframe_containing(driver, *btn_locator, timeout=10)
        except Exception:
            pass  # if not in an iframe, continue

    wait = WebDriverWait(driver, timeout)

    # 3) wait for the button to become enabled / clickable
    # many sites toggle classes like 'disabled', 'is-disabled', aria-disabled, or the 'disabled' attr
    def is_enabled(d):
        try:
            el = d.find_element(*btn_locator)
            cls = el.get_attribute("class") or ""
            aria = (el.get_attribute("aria-disabled") or "").lower()
            dis  = el.get_attribute("disabled")
            return el.is_displayed() and el.is_enabled() and "disabled" not in cls and aria not in ("true", "1") and dis is None
        except Exception:
            return False

    wait.until(is_enabled)

    btn = wait.until(EC.element_to_be_clickable(btn_locator))

    # 4) scroll into view
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)

    # 5) if there is a dimmer/overlay, wait for it to vanish
    # (adjust selectors to what you see in DevTools if needed)
    try:
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".modal-backdrop, .dim, .overlay, .loading, .spinner")))
    except TimeoutException:
        pass

    # 6) try normal click → actions → JS click fallback
    try:
        btn.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        try:
            ActionChains(driver).move_to_element(btn).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)

    # Optional: verify navigation/state change (e.g., title/url or a new panel)
    # wait.until(EC.url_changes(current_url))  # or wait for a unique element on next step



def pick_first_blue_seat_then_confirm(driver, timeout=30):
    """
    Assumes you've already switched to the seat popup window.
    This function will switch into the iframe that contains the seat map,
    click the first available (blue) seat, then click the '좌석선택' button.
    Returns True if it clicked a seat and the button, else False.
    """

    # --- 1) Go into the iframe that contains the seat layer ---
    # (re-use your helper if you like; this is inline to be explicit)
    def switch_into_iframe_with(selector_css, timeout=15):
        driver.switch_to.default_content()
        try:
            # Top-level first
            WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector_css)))
            return
        except:
            pass
        # Search all iframes
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for fr in frames:
            driver.switch_to.default_content()
            driver.switch_to.frame(fr)
            try:
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector_css)))
                return
            except:
                continue
        driver.switch_to.default_content()
        raise RuntimeError(f"Could not find {selector_css} in any iframe")

    # Make sure we are looking inside the SVG seat layer
    switch_into_iframe_with("g#ezSeatLayer", timeout=timeout)

    # --- 2) Wait for the seat layer and collect available seats ---
    seat_layer = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "g#ezSeatLayer"))
    )

    # Primary selector: attribute-based (most reliable)
    seats = seat_layer.find_elements(
        By.CSS_SELECTOR, 'g[id^="seatgroup_"] rect[gtype="SEAT"][use_yn="Y"][seat_status_cd="SS01000"]'
    )

    # Fallback: detect by blue fill (if attributes are late to appear)
    if not seats:
        seats = seat_layer.find_elements(
            By.XPATH, './/g[starts-with(@id,"seatgroup_")]//rect[contains(@style,"rgb(129, 171, 255)")]'
        )

    if not seats:
        print("❌ No available (blue) seats found under #ezSeatLayer")
        return False

    first = seats[0]

    # --- 3) Click the seat (JS click is safest for SVG) ---
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", first)
    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true}))", first)
    # Alternative: driver.execute_script("arguments[0].click();", first)

    print("✅ Clicked seat:", first.get_attribute("id"))

    # # --- 4) Click the red '좌석선택' button ---
    # # It may become enabled only after a seat is picked; wait for clickability.
    # btn = WebDriverWait(driver, timeout).until(
    #     EC.element_to_be_clickable((By.XPATH, '//button[contains(text(),"좌석선택")]'))
    # )
    # btn.click()
    # print("✅ Clicked '좌석선택'")

    return True

def final_page(driver):
    checkbox = driver.find_element(By.ID, "chkCanAgreeAll")
    print("Going to check the T&C")
    if not checkbox.is_selected():
        check_checkbox(driver, checkbox_id="chkCanAgreeAll")
    time.sleep(1)
    # Text on Button for Payment = 결제하기
    print("Waiting for final Button")
    # driver.find_element(By.ID, "btnFinalPayment").click()
    pyautogui.keyDown("win")
    pyautogui.press("up") # For some reason, the button is not recognised unless it's in full screen, which I guess has something to do with it not being in view when not in full screen
    pyautogui.keyUp("win")
    click_final_payment(driver)
    print("Final Button Found")

# For some reason, it is way slower, so go back to pyautogui
def final_page_fast():
    pyautogui.keyDown("win")
    pyautogui.press("up")
    pyautogui.keyUp("win")

    pyautogui.moveTo(197,385)
    pyautogui.scroll(-1000)
    pyautogui.click(197,385)
    pyautogui.click(2234,1452)

    return

def beep_beep(count=None):
    with open("credentials.json", encoding="utf-8") as f:
        data = json.load(f)
    my_id = data.get("my_id")
    token = data.get("notification_bot_http_api")
    if (count is not None) or (token is None or token == ""):
        for _ in range(count):
            winsound.Beep(1000,500)
            time.sleep(0.1)
    else:
        url = f"https://api.telegram.org/bot{token}"
        params = {"chat_id": my_id, "text": "Something happened!"}
        r = requests.get(f"{url}/sendMessage", params=params)


def main(link_to_ticketing, user_id, password, movies, seconds_per_session=550):
    counter = 0
    number_of_movies = len(movies)
    driver.get(link_to_ticketing)
    tel_box = driver.find_element(By.ID, "telNo") # ID of Username Textbox
    tel_box.send_keys(user_id)
    password_box = driver.find_element(By.ID, "password") # ID of Password Textbox
    password_box.send_keys(password)

    driver.find_element(By.CSS_SELECTOR, 'button[onclick="goReservation_Mypage();"]').click()
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "sdCode"))  # ID of the textbox to enter in the movie code
    )

    start_time = time.time()
    code_box = driver.find_element(By.ID, "sdCode")
    in_booking = False
    while time.time() - start_time < seconds_per_session and not in_booking: # Time in seconds
        movie = movies[counter % number_of_movies]

        print("Current handle:", driver.current_window_handle)
        print(movie)
        code_box.send_keys(movie[0])
        # driver.find_element(By.CLASS_NAME, "search-btn fas fa-search")
        driver.execute_script("sdCodeProdList();") # Essentially the same as clicking the search button

        # Button not available = 매진
        # Button available = 예매
        main_window = driver.current_window_handle
        try:
            print("All handles:", driver.window_handles)
            print("Current handle:", driver.current_window_handle)
            book_btn = WebDriverWait(driver, 0.05).until(
                EC.presence_of_element_located((By.XPATH, '//button[text()="예매"]'))
            )
            book_btn.click()
            seat_window = switch_to_new_window(driver, main_window, timeout=10)
            # time.sleep(5)
            print("Currently in New Window: ", driver.current_window_handle)
            in_booking = True

            # Colour of available seat is RGB(129,171,255)
            # Colour of not available seat is RGB(175,175,175)
            if not pick_first_blue_seat_then_confirm(driver):
                driver.execute_script("refreshMap();")
            else:
                # Text on Ticketing button before seat is selected = 좌석선택
                # Text on Tickeitng button after seat is selected = 다음단계
                # Text when seat is unselected = 좌석선택
                print("Waiting for button")
                ticketing_btn = WebDriverWait(driver, 0.5).until(
                    EC.presence_of_element_located((By.ID, "nextTicketSelection"))
                )
                ticketing_btn.click()

                # If someoone has already clicked the seat, dialogue box appears saying
                # 이미 선택된 좌석입니다. [T8280]

                # dropdown_box = WebDriverWait(driver, 0.5).until(
                #     EC.presence_of_element_located((By.ID, "volume_1_1"))
                # )
                dropdown = driver.find_element(By.ID, "volume_1_1")
                Select(dropdown).select_by_value("1")
                # Text on button = 가격선택
                driver.find_element(By.ID, "nextPayment").click()

                final_page(driver)
                # final_page_fast()

                beep_beep()

            break
            return
        except Exception as e:
            # driver.execute_script("refreshMap();")
            # in_booking = False
            print(e)
            pass

        counter += 1
        print()
        driver.switch_to.window(main_window)
        code_box.clear()

    driver.find_element(By.CSS_SELECTOR, 'a[href="/biff-logout"]').click()
    # driver.quit()
    time.sleep(1)

def parse_args(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser()

    parser.add_argument("-m", "--movie_id", type=int, default=-1, help="number of images to process")

    args, _ = parser.parse_known_args(argv)
    return args


if __name__ == "__main__":

    movies = [
        # [Movie code, Movie name, Theatre code, 19+ or not]
        ["020", "No Other Choice", "CGV_IMAX", False],
        ["083", "No Other Choice", "BCC_1", False],
        # ["083", "No Other Choice", "BCC_1", False],
        # ["020", "No Other Choice", "CGV_IMAX", False],

        # ["179", "Frankenstein", "CGV_IMAX", True],
        # ["023", "Frankenstein", "CGV_IMAX", True],
        # ["212", "If on a Winter′s Night", "Lotte_5", False],

        # ["586", "Tiger", "Lotte_5", True], # Actually CGV_6
        # ["528", "Adam's Sake", "Lotte_5", False],
        # ["560", "Eagles of the Republic", "BCC_1", False], 
        # ["494", "Romeria", "CGV_IMAX", False],
        # ["930", "Sora", "CGV_IMAX", False], # Actually Megabox 3 
    ]

    link_to_ticketing = "https://biff.maketicket.co.kr/ko/mypageLogin"
    number_of_movies = len(movies)

    with open("credentials.json", encoding="utf-8") as f:
        data = json.load(f)
    user_id = data.get("username")
    password = data.get("password")

    args = parse_args()
    if args.movie_id != -1:
        movies = [movies[args.movie_id]]

    opts = Options()
    opts.add_experimental_option("detach", True)   # keep Chrome open after script ends
    driver = webdriver.Chrome(options=opts)
    # driver = webdriver.Chrome()
    while(True):
        main(link_to_ticketing, user_id, password, movies, 550)
        battery = psutil.sensors_battery()
        if battery is not None:
            percent = battery.percent
            if percent < 10:
                beep_beep(100)
            elif percent < 20:
                beep_beep(20)
    # exit()