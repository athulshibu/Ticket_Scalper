import io
import os
import time
from collections import deque

import pyautogui
import winsound
import json
import psutil
import argparse
import requests
from PIL import Image, ImageChops

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, StaleElementReferenceException
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
    Finds the first available blue seat rendered in the canvas seat map and
    clicks it. Returns True when a blue seat is found, else False.
    """
    def largest_canvas_container():
        canvases = []
        for canvas in driver.find_elements(By.TAG_NAME, "canvas"):
            size = canvas.size
            if canvas.is_displayed() and size["width"] >= 200 and size["height"] >= 200:
                canvases.append(canvas)
        if not canvases:
            return False
        largest_canvas = max(
            canvases,
            key=lambda canvas: canvas.size["width"] * canvas.size["height"],
        )
        return largest_canvas.find_element(By.XPATH, "..")

    def find_canvas_container(_):
        driver.switch_to.default_content()
        seat_map = largest_canvas_container()
        if seat_map:
            return seat_map

        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            driver.switch_to.default_content()
            driver.switch_to.frame(frame)
            seat_map = largest_canvas_container()
            if seat_map:
                return seat_map

        driver.switch_to.default_content()
        return False

    try:
        seat_map = WebDriverWait(driver, timeout).until(find_canvas_container)
    except TimeoutException:
        print("No visible seat-map canvas found yet")
        return False
    print(
        "Using canvas container:",
        seat_map.get_attribute("id") or seat_map.get_attribute("class") or "unnamed",
    )
    screenshot = Image.open(io.BytesIO(seat_map.screenshot_as_png)).convert("RGB")
    width, height = screenshot.size
    red, green, blue = screenshot.split()
    mask = ImageChops.multiply(
        ImageChops.multiply(
            red.point([255 if 121 <= value <= 137 else 0 for value in range(256)]),
            green.point([255 if 163 <= value <= 179 else 0 for value in range(256)]),
        ),
        blue.point([255 if 247 <= value <= 255 else 0 for value in range(256)]),
    )
    bounds = mask.getbbox()
    if bounds:
        _, top, _, _ = bounds
        row_bounds = mask.crop((0, top, width, top + 1)).getbbox()
        if not row_bounds:
            print("No available blue seats found in #seatMap")
            return False
        left, _, _, _ = row_bounds
        search_width = min(50, width - left)
        search_height = min(50, height - top)
        seat_mask = mask.crop((left, top, left + search_width, top + search_height))
        seat_pixels = seat_mask.load()
        region = []
        queue = deque([(0, 0)])
        visited = {(0, 0)}

        while queue:
            current_x, current_y = queue.popleft()
            region.append((current_x, current_y))
            for next_x, next_y in (
                (current_x - 1, current_y),
                (current_x + 1, current_y),
                (current_x, current_y - 1),
                (current_x, current_y + 1),
            ):
                if (
                    0 <= next_x < search_width
                    and 0 <= next_y < search_height
                    and (next_x, next_y) not in visited
                    and seat_pixels[next_x, next_y]
                ):
                    visited.add((next_x, next_y))
                    queue.append((next_x, next_y))

        if len(region) >= 25:
            pixel_x = left + sum(point[0] for point in region) / len(region)
            pixel_y = top + sum(point[1] for point in region) / len(region)
            map_width = seat_map.size["width"]
            map_height = seat_map.size["height"]
            offset_x = pixel_x * map_width / width - map_width / 2
            offset_y = pixel_y * map_height / height - map_height / 2
            ActionChains(driver).move_to_element(seat_map).move_by_offset(offset_x, offset_y).click().perform()
            print(f"Clicked first blue seat at ({pixel_x:.0f}, {pixel_y:.0f})")
            return True

    print("No available blue seats found in #seatMap")
    return False

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
        params = {"chat_id": my_id, "text": message}
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
            for attempt in range(3):
                try:
                    WebDriverWait(
                        driver,
                        1,
                        ignored_exceptions=(StaleElementReferenceException,),
                    ).until(EC.element_to_be_clickable(book_button_locator)).click()
                    break
                except StaleElementReferenceException:
                    if attempt == 2:
                        raise

            # Possibility of a Popup
            accept_alert_if_present(driver, timeout=0.05)

            seat_window = switch_to_new_window(driver, main_window, timeout=10)
            # time.sleep(5)
            print("Currently in New Window: ", driver.current_window_handle)
            seat_window_opened_at = time.perf_counter()
            in_booking = True

            # Colour of available seat is RGB(129,171,255)
            # Colour of not available seat is RGB(175,175,175)
            if not pick_first_blue_seat_then_confirm(driver):
                beep_beep(message=f"Red button, but no seat for {movie[0]} - {movie[1]}")
                # this_start_time = 0
                while not pick_first_blue_seat_then_confirm(driver):
                    # print(time.time()-this_start_time)
                    driver.execute_script("refreshMap();")
                    # this_start_time = time.time()
                # while not pick_first_blue_seat_then_confirm(driver):
                #     print(time.time()-this_start_time)
                #     driver.switch_to.window(main_window)
                #     book_btn.click()
                #     driver.switch_to.window(seat_window)
                #     this_start_time = time.time()
                print("Seat found after Refreshing")

            # Text on Ticketing button before seat is selected = 좌석선택
            # Text on Tickeitng button after seat is selected = 다음단계
            # Text when seat is unselected = 좌석선택
            print("Waiting for button")
            # breakpoint()
            ticketing_btn = find_in_document_or_frames(driver, By.ID, "nextTicketSelection")
            ticketing_btn.click()
            elapsed = time.perf_counter() - seat_window_opened_at
            print(f"Time from popup opening to nextTicketSelection click: {elapsed:.3f}s")
            exit(0)

            # If someoone has already clicked the seat, dialogue box appears saying
            # 이미 선택된 좌석입니다. [T8280]

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

            beep_beep(message=f"Something happened with {movie[0]} - {movie[1]}!")
            return
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


    args, _ = parser.parse_known_args(argv)
    return args


if __name__ == "__main__":

    movies = [
        # [Movie code, Movie name, Theatre code, 19+ or not]
        # ["056", "Final Interview", "Lotte_6", False],
        # ["129", "Final Interview", "Lotte_4", False],
        ["605", "Final Interview", "Lotte_4", False],
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
        main(link_to_ticketing, user_id, password, movies, 550)
        battery = psutil.sensors_battery()
        if battery is not None:
            percent = battery.percent
            if percent < 10:
                beep_beep(100)
            elif percent < 20:
                beep_beep(20)
    # exit()