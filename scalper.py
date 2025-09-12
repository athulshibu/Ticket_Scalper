import pyautogui
import pandas as pd
import os
import time
import winsound

movies = [
    # [Movie code, Movie name, Theatre code, 19+ or not]
    ["020", "No Other Choice", "CGV_IMAX", False],
    ["083", "No Other Choice", "BCC_1", False],
    ["023", "Frankenstein", "CGV_IMAX", True],
    ["179", "Frankenstein", "CGV_IMAX", True],
    # ["212", "If on a Winter′s Night", "Lotte_5", False],
    # ["586", "Tiger", "Lotte_5", True], # Actually CGV_6
    # ["528", "Adam's Sake", "Lotte_5", False],
    # ["560", "Eagles of the Republic", "BCC_1", False], 
    # ["494", "Romeria", "CGV_IMAX", False], 
]

theatres = []
for movie in movies:
    if movie[2] not in theatres:
        theatres.append(movie[2])

coordinates = {}
for theatre in theatres:
    csv_file = os.path.join("CSV_Seats", theatre+"_square_centers.csv")
    df = pd.read_csv(csv_file)
    coordinates[theatre] = list(df.itertuples(index=False, name=None))

link_to_ticketing = "https://biff.maketicket.co.kr/"
blue_seat = (132, 153, 222)
gray_seat = (173, 173, 173)
red_button = (166, 33, 28)

def check_seats(theatre):
    pyautogui.PAUSE=0.01
    for i, (x,y) in enumerate(coordinates[theatre]):
        pyautogui.click(x,y)
    pyautogui.PAUSE=0.1
    pyautogui.press("enter")
    pyautogui.click(1887, 1036) # Clicking the red button

    time.sleep(0.5)
    pyautogui.scroll(-200)
    pyautogui.moveTo(2051, 1018) # The Red button after scrolling
    time.sleep(0.5)
    button_availability = pyautogui.pixel(2051, 1018)
    if all(abs(p - t) <= 5 for p, t in zip(button_availability, red_button)): # Checking for a red button
        print("Red Button Found")
        pyautogui.click(1267,409)
        pyautogui.press("down")
        pyautogui.press("down")
        pyautogui.press("enter")
        pyautogui.click(2051, 1018) # Pressing Button after seats have been selected
        time.sleep(0.5)
        step_3 = pyautogui.pixel(1124,185)
        if all(abs(p - t) <= 5 for p, t in zip(step_3, (235,93,94))): # Checking for step 3 red
            pyautogui.moveTo(33, 283)
            pyautogui.scroll(-1000)
            pyautogui.click(33, 283) # Checking T&C
            # pyautogui.moveTo(1875, 1361) # Move to Payment Button
            pyautogui.click(1875, 1361) # Click Payment Button
            for i in range(1000):
                winsound.Beep(1000,500)
                time.sleep(0.5)
        exit()
    else:
        for i in range(1000):
            winsound.Beep(1000,500)
            time.sleep(0.5)
        exit()


def main():
    counter = 0
    # pyautogui.keyUp("win")
    # pyautogui.keyUp("alt")
    # pyautogui.keyUp("ctrl")
    
    # To open Chrome
    # pyautogui.keyDown("win")
    # pyautogui.press("2")
    # pyautogui.keyUp("win")
    pyautogui.click(1400,1553)
    time.sleep(0.5)
    pyautogui.click(600,120)
    pyautogui.keyDown("ctrl")
    pyautogui.press("a")
    pyautogui.keyUp("ctrl")
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.typewrite(link_to_ticketing, interval=0.01)
    pyautogui.press("enter")
    time.sleep(1)
    pyautogui.click(665,1261) # Red button to login
    time.sleep(1)
    pyautogui.click(1541,419) # Log in button
    time.sleep(1)
    
    start_time = time.time()
    pyautogui.click(1236,963) # Logging in
    time.sleep(0.5)
    pyautogui.click(368,400) # Text box to enter code
    pyautogui.keyDown("ctrl")
    pyautogui.press("a")
    pyautogui.keyUp("ctrl")
    while time.time() - start_time < 550: # Time in seconds
        # time.sleep(0.05)
        pyautogui.typewrite(movies[counter][0], interval=0.01)
        pyautogui.press("enter")
        pyautogui.click(368,400) # Text box to enter code
        pyautogui.keyDown("ctrl")
        pyautogui.press("a")
        pyautogui.keyUp("ctrl")
        time.sleep(0.4)

        # 2337, 479
        button_colour = pyautogui.pixel(2331, 480)
        # print(movies[counter][1], button_colour)
        # Red of the button is around (210, 59, 49)
        # Gray of no button is around (206, 206, 206)
        if all(abs(p - t) <= 5 for p, t in zip(button_colour, (210, 59, 49))):
            pyautogui.click(2331, 480) # click the button
            # print("Red found")
            if movies[counter][3]:
                time.sleep(0.7)
                pyautogui.click(1663, 413)
                # print("Click Okay")
            check_seats(movies[counter][2])
            return


        counter = (counter + 1) % len(movies)


    # Logout
    pyautogui.click(2329,237) # Log out
    time.sleep(0.1)

    # Close the window
    pyautogui.keyDown("alt")
    pyautogui.press("F4")
    pyautogui.keyUp("alt")

if __name__ == "__main__":
    print("Make sure Chrome is closed!!!")
    time.sleep(3)
    while(True):
        main()