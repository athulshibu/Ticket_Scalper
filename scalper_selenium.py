import os
import time
from datetime import datetime

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
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options

class BookingUnavailableError(Exception):
    """Raised when a searched movie has no clickable booking button."""

def switch_to_new_window(driver, old_handle, timeout=10):
    WebDriverWait(driver, timeout).until(lambda d: len(d.window_handles) > 1)
    for h in driver.window_handles:
        if h != old_handle:
            driver.switch_to.window(h)
            return h
    raise RuntimeError("New window not found")

def open_seat_window(driver, main_window, book_button_locator, timeout=10):
    driver.switch_to.window(main_window)
    for attempt in range(3):
        try:
            WebDriverWait(
                driver,
                0.02,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(EC.element_to_be_clickable(book_button_locator)).click()
            break
        except StaleElementReferenceException:
            if attempt == 2:
                raise
        except TimeoutException as error:
            raise BookingUnavailableError("Booking button is unavailable") from error

    accept_alert_if_present(driver, timeout=0.05)
    return switch_to_new_window(driver, main_window, timeout=timeout)

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

def find_in_document_or_frames(driver, by, value):
    """Find an element in the current window, preserving its document context."""
    driver.switch_to.default_content()

    def search_frames():
        matches = driver.find_elements(by, value)
        if matches:
            return matches[0]

        for frame in driver.find_elements(By.TAG_NAME, "iframe"):
            driver.switch_to.frame(frame)
            match = search_frames()
            if match:
                return match
            driver.switch_to.parent_frame()
        return None

    element = search_frames()
    if element is None:
        driver.switch_to.default_content()
        raise NoSuchElementException(f"Could not find {value!r} in the popup document or its iframes")
    return element

def refresh_seat_map(driver):
    refresh_button = find_in_document_or_frames(driver, By.CSS_SELECTOR, ".btn-map .btn-reset")
    try:
        refresh_button.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        driver.execute_script("arguments[0].click();", refresh_button)

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

def accept_alert_if_present(driver, timeout=0.1):
    """
    Checks if an alert/confirm/prompt is present within timeout seconds.
    If found, accepts it and returns True. If none, returns False.
    """
    try:
        WebDriverWait(driver, timeout).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print("⚠ Alert text:", alert.text)
        alert.accept()
        print("✅ Accepted alert")
        return True
    except TimeoutException:
        return False

def pick_first_blue_seat_then_confirm(driver, timeout=30):
    """
    Assumes you've already switched to the seat popup window.
    Finds the first available blue Konva seat and clicks its rendered center.
    Returns True when a blue seat is found, else False.
    """
    def find_first_available_seat(_):
        driver.switch_to.default_content()
        for frame in driver.find_elements(By.TAG_NAME, "iframe"):
            driver.switch_to.default_content()
            driver.switch_to.frame(frame)
            seat_map = driver.find_elements(By.ID, "seatMap")
            if not seat_map:
                continue

            seat = driver.execute_script("""
                const availableSeat = Konva.stages
                    .flatMap(stage => stage.find('Rect'))
                    .find(rect => rect.fill() === '#81abff');
                if (!availableSeat) return null;

                const bounds = availableSeat.getClientRect();
                return {
                    id: availableSeat.id(),
                    x: bounds.x + bounds.width / 2,
                    y: bounds.y + bounds.height / 2,
                };
            """)
            if seat:
                return seat_map[0], seat

        driver.switch_to.default_content()
        return False

    try:
        seat_map, seat = WebDriverWait(driver, timeout).until(find_first_available_seat)
    except TimeoutException:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] No available Konva seat found yet")
        return False
    map_width = seat_map.size["width"]
    map_height = seat_map.size["height"]
    offset_x = seat["x"] - map_width / 2
    offset_y = seat["y"] - map_height / 2
    ActionChains(driver).move_to_element(seat_map).move_by_offset(offset_x, offset_y).click().perform()
    print(f"Clicked available Konva seat {seat['id']} at ({seat['x']:.0f}, {seat['y']:.0f})")
    return True

def final_page(driver):
    checkbox = driver.find_element(By.ID, "chkCanAgreeAll")
    print("Going to check the T&C")
    if not checkbox.is_selected():
        check_checkbox(driver, checkbox_id="chkCanAgreeAll")
    time.sleep(1)
    # Text on Button for Payment = 결제하기
    print("Waiting for final Button")
    driver.maximize_window() # For some reason, the button is not recognised unless it's in full screen, which I guess has something to do with it not being in view when not in full screen
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

def beep_beep(count=None, message="Something happened!"):
    if count is not None:
        for _ in range(count):
            winsound.Beep(1000,500)
            time.sleep(0.1)

    with open("credentials.json", encoding="utf-8") as f:
        data = json.load(f)
    my_id = data.get("my_id")
    token = data.get("notification_bot_http_api")
    if token:
        url = f"https://api.telegram.org/bot{token}"
        params = {"chat_id": my_id, "text": message}
        r = requests.get(f"{url}/sendMessage", params=params)


def main(link_to_ticketing, user_id, password, movies, seconds_per_session=550, refresh_mode="map"):
    counter = 0
    number_of_movies = len(movies)
    driver.get(link_to_ticketing)
    tel_box = driver.find_element(By.ID, "telNo") # ID of Username Textbox
    tel_box.send_keys(user_id)
    password_box = driver.find_element(By.ID, "password") # ID of Password Textbox
    password_box.send_keys(password)

    driver.find_element(By.CSS_SELECTOR, 'button[onclick="goReservation_Mypage();"]').click()
    # This confirmation is raised by the login click, before the reservation page loads.
    accept_alert_if_present(driver, timeout=1)
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "bridgeReserveBtn"))  # ID of the textbox to enter in the movie code
    )
    driver.find_element(By.ID, "bridgeReserveBtn").click()
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
            book_button_locator = (By.XPATH, '//button[normalize-space()="예매"]')
            seat_window = open_seat_window(driver, main_window, book_button_locator)
            print("Currently in New Window: ", driver.current_window_handle)
            seat_window_opened_at = time.perf_counter()
            in_booking = True

            # Colour of available seat is RGB(129,171,255)
            # Colour of not available seat is RGB(175,175,175)
            no_seat_notified = False
            while True:
                if not pick_first_blue_seat_then_confirm(driver, timeout=1):
                    if not no_seat_notified:
                        beep_beep(message=f"Red button, but no seat for {movie[0]} - {movie[1]}")
                        no_seat_notified = True
                    if refresh_mode == "map":
                        refresh_seat_map(driver)
                    else:
                        driver.close()
                        seat_window = open_seat_window(driver, main_window, book_button_locator)
                    continue

                # Text on Ticketing button before seat is selected = 좌석선택
                # Text on Ticketing button after seat is selected = 다음단계
                print("Waiting for button")
                ticketing_btn = find_in_document_or_frames(driver, By.ID, "nextTicketSelection")
                ticketing_btn.click()

                # The selected seat may have been claimed by another customer.
                if accept_alert_if_present(driver, timeout=1):
                    print("Seat was already selected; refreshing and trying again")
                    if refresh_mode == "map":
                        refresh_seat_map(driver)
                    else:
                        driver.close()
                        seat_window = open_seat_window(driver, main_window, book_button_locator)
                    continue
                break

            elapsed = time.perf_counter() - seat_window_opened_at
            print(f"Time from popup opening to nextTicketSelection click: {elapsed:.3f}s")

            # dropdown_box = WebDriverWait(driver, 0.5).until(
            #     EC.presence_of_element_located((By.ID, "volume_1_1"))
            # )
            dropdown = WebDriverWait(driver, 3).until(
                lambda _: find_in_document_or_frames(driver, By.ID, "volume_1_1")
            )
            Select(dropdown).select_by_value("1")
            # Text on button = 가격선택
            payment_button = WebDriverWait(driver, 3).until(
                lambda _: find_in_document_or_frames(driver, By.ID, "nextPayment")
            )
            payment_button.click()

            final_page(driver)
            # final_page_fast()

            beep_beep(message=f"Something happened with {movie[0]} - {movie[1]}!", count=3)
            exit(0)
        except BookingUnavailableError:
            print(f"Movie {movie[0]} is unavailable; searching again")
        except Exception as e:
            print(f"Booking popup failed: {type(e).__name__}: {e}")
            raise

        counter += 1
        print()
        driver.switch_to.window(main_window)
        code_box.clear()

    driver.switch_to.window(main_window)
    logout_links = driver.find_elements(By.CSS_SELECTOR, 'a[href="/biff-logout"]')
    if logout_links:
        logout_links[0].click()
    # driver.quit()
    time.sleep(1)

def parse_args(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser()

    parser.add_argument("-m", "--movie_id", type=int, default=-1, help="ID of the movie in the list")
    parser.add_argument("-c", "--credentials", type=str, default="credentials.json", help="Credentials file")
    parser.add_argument(
        "--refresh-mode",
        choices=("map", "reopen"),
        default="map",
        help="Refresh the seat map in place or close and reopen the booking window",
    )


    args, _ = parser.parse_known_args(argv)
    return args


if __name__ == "__main__":

    movies = [
        # [Movie code, Movie name, Theatre code, 19+ or not]
        ["042", "Bucking Fastard", "Lotte_2", False],
        ["056", "Final Interview", "Lotte_6", False],
        ["129", "Final Interview", "Lotte_4", False],
        # ["382", "Ray Gunn", "CGV_IMAX", False],

        # ["089", "Possible Love", "CGV_IMAX", False],
        
        # ["021", "Mother Mary", "BCC", False],

        # ["605", "Final Interview", "Lotte_4", False],
        # ["320", "Sapiens", "Lotte_3", False],
        # ["692", "Sinner", "Lotte_4", False]
    ]

    link_to_ticketing = "https://biff.maketicket.co.kr/BIFF/ko/mypageLogin"
    number_of_movies = len(movies)
    args = parse_args()

    with open(args.credentials, encoding="utf-8") as f:
        data = json.load(f)
    user_id = data.get("username")
    password = data.get("password")

    if args.movie_id != -1:
        movies = [movies[args.movie_id]]

    opts = Options()
    opts.add_experimental_option("detach", True)   # keep Chrome open after script ends
    driver = webdriver.Chrome(options=opts)
    # driver = webdriver.Chrome()
    while(True):
        main(link_to_ticketing, user_id, password, movies, 550, args.refresh_mode)
        battery = psutil.sensors_battery()
        if battery is not None:
            percent = battery.percent
            if percent < 10:
                beep_beep(100)
            elif percent < 20:
                beep_beep(20)
    # exit()