
# BIFF 2025 Ticket Scalper

Will hopefully also work in 2026 🤞

## Initial Setup

### Step 1: Create you Telegram Account. 
With Phone number, without phone number, doesn't matter

### Step 2: Set up your Username
Go to Setting and click on Username. You'll need a unique one

### Step 3: Send a message to RawDataBot to get your id
Search for @RawDataBot, and send a message (or just click start if it's your first time)

### Step 4: Create a bot
Now search for BotFather and send the message `/start`. Help is displayed. Send the message `/newbot` and follow the instructions. You will need to set uo the bot name, and a username for the bot. Take a note of your token to access the HTTP API.

### Step 5: Create a Python Virtual environment, and enter it
```
python venv -m workspace
workspace\Scripts\activate.bat
```

### Step 6: Install required packages
```
pip install pyautogui winsound 
pip install psutil requests selenium
```

### Step 7: Run `json_creator.py`
Enter your ID from Step 3, and HTTP API token from step for, along with BIFF Phone number and password, in the input fields.

### Step 8: Edit the movies list
Search for `movies` inside the main. Edit it to add your movie code, name (unnecessary really), theatre name (also kinda unnecessary), and whether or not the movie is 19+ (not used right now, but will be used in future)

## Running Scalper

```
python scalper_selenium.py
# This will run every movie/code in the list, one after the other

python scalper_selenium.py -m 1
# This will only run movies[1], which is the second movie in the list
```

## References
Learning to send Push Notifications: https://stackoverflow.com/questions/49879993/push-notification-from-python-to-android
