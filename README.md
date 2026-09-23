
# BIFF 2025 Ticket Scalper

Will hopefully also work in 2027 🤞

## Initial Setup

### Step 1: Create you Telegram Account. 
With Phone number, without phone number, doesn't matter

### Step 2: Send a message to RawDataBot to get your id
Search for `@RawDataBot` on Telegram, and send "/start" (or just click start if it's your first time). Your ID is `message.from.id`

### Step 3: Get your Notification bot token
Search for `@Botfather` on Telegram. Send `/start` and `/newbot` to create a new Bot, and not its HTTP API. Use `mybots` to verify your bot is ready, and `API Token` to find the API token for your bot. 

### Step 4: Create a Python Virtual environment, and enter it
```
python -m venv workspace
workspace\Scripts\activate
```

### Step 5: Install required packages
```
pip install pyautogui 
pip install psutil requests selenium Pillow
pip install winsound
```

### Step 6: Run `json_creator.py`
Enter your ID from Step 3, and HTTP API token from step for, along with BIFF Phone number and password, in the input fields.

### Step 7: Edit the movies list
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
