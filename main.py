import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

@app.route('/')
def home():
    return "Bot is Running!"

def run_bot():
    print("Bot Started...")
    while True:
        try:
            # তোমার আগের Bot এর Logic এখানে চলবে
            # এটা একটা Test Message
            if TELEGRAM_TOKEN and CHAT_ID:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                # এখানে তোমার আসল সিগন্যাল লজিক থাকবে
                pass
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    # Bot টা আলাদা Thread এ চালু হবে
    t = threading.Thread(target=run_bot)
    t.start()
    # Render এর জন্য Web Server চালু হবে
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
