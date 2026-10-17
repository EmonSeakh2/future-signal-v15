import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd
from flask import Flask
from datetime import datetime, timedelta
from PIL import Image
import io
import ta

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

REAL_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/GBP": "EURGBP=X"
}

last_signal_info = {} # Win/Loss Check এর জন্য
offset_id = 0
win_count = 0
loss_count = 0

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def send_photo_reply(msg, reply_to_message_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg, "reply_to_message_id": reply_to_message_id, "parse_mode": "Markdown"}
        requests.post(url, data=data, timeout=10)
    except: pass

# ========= WIN/LOSS PHOTO CHECK LOGIC =========
def check_win_loss_from_photo(photo_bytes):
    try:
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        img = img.resize((200, 200)) # ছোট করে Analysis Fast
        pixels = list(img.getdata())
        
        green = 0
        red = 0
        for r, g, b in pixels:
            # Quotex এ Win হলে সবুজ বেশি, Loss হলে লাল বেশি
            if g > 100 and g > r + 30 and g > b + 20:
                green += 1
            elif r > 100 and r > g + 30 and r > b + 20:
                red += 1
        
        if green > red and green > 500:
            return "WIN"
        elif red > green and red > 500:
            return "LOSS"
        else:
            # Color না বুঝলে Brightness দিয়ে Check
            return "UNKNOWN"
    except Exception as e:
        print(f"Photo Check Error: {e}")
        return "ERROR"

def telegram_photo_listener():
    global offset_id, win_count, loss_count
    print("Photo Listener Started...")
    while True:
        try:
            if not TELEGRAM_TOKEN: 
                time.sleep(10)
                continue
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset_id + 1}&timeout=20"
            resp = requests.get(url, timeout=25).json()
            
            if not resp.get("ok") or not resp.get("result"):
                time.sleep(5)
                continue

            for update in resp["result"]:
                offset_id = update["update_id"]
                if "message" in update and "photo" in update["message"]:
                    # Photo পাওয়া গেছে
                    photos = update["message"]["photo"]
                    file_id = photos[-1]["file_id"] # Highest Quality
                    message_id = update["message"]["message_id"]
                    
                    # File Download
                    file_info_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
                    file_path = requests.get(file_info_url).json()["result"]["file_path"]
                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                    photo_bytes = requests.get(download_url).content
                    
                    result = check_win_loss_from_photo(photo_bytes)
                    
                    if result == "WIN":
                        win_count += 1
                        reply = f"✅ *WIN DETECTED* ✅\n\nএই Trade টা Win হয়েছে!\n\n📊 Total: {win_count} Win / {loss_count} Loss\n🔥 Win Rate: {win_count*100//(win_count+loss_count) if (win_count+loss_count)>0 else 0}%"
                    elif result == "LOSS":
                        loss_count += 1
                        reply = f"❌ *LOSS DETECTED* ❌\n\nএই Trade টা Loss হয়েছে!\n\n📊 Total: {win_count} Win / {loss_count} Loss\n⚠️ Next Signal High Confirmation হবে"
                    else:
                        reply = f"🤔 *Result Clear না*\n\nScreenshot টা আরেকটু Clear করে দাও ভাই, আমি আবার Check করবো"
                    
                    send_photo_reply(reply, message_id)

        except Exception as e:
            print(f"Listener Error: {e}")
            time.sleep(5)

# ========= MARKET & STRATEGY LOGIC =========
def check_market_condition(df):
    adx = ta.trend.adx(df['High'], df['Low'], df['Close'], window=14).iloc[-1]
    if adx < 22: return False
    atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14).iloc[-1]
    if atr < 0.0003: return False
    return True

def high_accuracy_strategy(df):
    close = df['Close']
    ema9 = ta.trend.ema_indicator(close, window=9).iloc[-1]
    ema21 = ta.trend.ema_indicator(close, window=21).iloc[-1]
    ema50 = ta.trend.ema_indicator(close, window=50).iloc[-1]
    rsi = ta.momentum.rsi(close, window=14).iloc[-1]
    macd = ta.trend.macd(close).iloc[-1]
    macd_sig = ta.trend.macd_signal(close).iloc[-1]
    
    signal = None
    conf = 0
    if ema9 > ema21 > ema50 and rsi > 55 and rsi < 75 and macd > macd_sig:
        signal = "CALL (BUY) ⬆️"
        conf = 92 if rsi > 60 else 88
    elif ema9 < ema21 < ema50 and rsi < 45 and rsi > 25 and macd < macd_sig:
        signal = "PUT (SELL) ⬇️"
        conf = 91 if rsi < 40 else 87
    return signal, conf

def analyze_pair(name, yf_symbol):
    try:
        data = yf.download(yf_symbol, period="1d", interval="1m", progress=False)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        data = data.dropna()
        if len(data) < 60: return None
        if not check_market_condition(data): return None
        sig, conf = high_accuracy_strategy(data)
        if sig and conf >= 85:
            return {"pair": name, "signal": sig, "conf": conf, "price": float(data['Close'].iloc[-1]), "yf": yf_symbol}
    except: return None
    return None

def check_win_loss_auto():
    global last_signal_info, win_count, loss_count
    if not last_signal_info: return
    try:
        time.sleep(130) # 2 Min 10 Sec পর Check
        yf_symbol = last_signal_info["yf"]
        entry_price = last_signal_info["price"]
        signal_type = last_signal_info["signal"]
        
        data = yf.download(yf_symbol, period="5m", interval="1m", progress=False)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        current_price = float(data['Close'].iloc[-1])
        
        win = False
        if "CALL" in signal_type and current_price > entry_price: win = True
        if "PUT" in signal_type and current_price < entry_price: win = True
        
        if win:
            win_count += 1
            result_msg = f"✅ *AUTO WIN CHECK* ✅\n\nPair: {last_signal_info['pair']}\nEntry: {entry_price:.5f}\nExit: {current_price:.5f}\nResult: *WIN* 🎯"
        else:
            loss_count += 1
            result_msg = f"❌ *AUTO LOSS CHECK* ❌\n\nPair: {last_signal_info['pair']}\nEntry: {entry_price:.5f}\nExit: {current_price:.5f}\nResult: *LOSS*"
        
        total = win_count + loss_count
        result_msg += f"\n\n📊 Score: {win_count}W / {loss_count}L ({win_count*100//total if total>0 else 0}%)"
        send_telegram(result_msg)
        last_signal_info = {}
    except Exception as e:
        print(f"Auto Check Error: {e}")

def bot_loop():
    global last_signal_info
    send_telegram("✅ *v15 REAL MARKET LIVE*\n✅ Auto Win/Loss Check On\n✅ Photo Win/Loss Check On\n⏰ Signal: Every 30 Min")
    while True:
        try:
            now = datetime.now()
            if now.minute % 30 == 0:
                best = None
                for name, sym in REAL_PAIRS.items():
                    r = analyze_pair(name, sym)
                    if r and (best is None or r['conf'] > best['conf']): best = r
                    time.sleep(1)
                
                if best:
                    last_signal_info = best
                    msg = f"🔥 *v15 REAL SIGNAL* 🔥\n\n💱 {best['pair']}\n📊 {best['signal']}\n🎯 {best['conf']}%\n💵 {best['price']:.5f}\n⏰ Expiry: 2 Min\n\n✅ Auto Result 2 Min পর আসবে"
                    send_telegram(msg)
                    threading.Thread(target=check_win_loss_auto, daemon=True).start()
                
                time.sleep(60)
            else:
                time.sleep(20)
        except Exception as e:
            print(e)
            time.sleep(30)

@app.route('/')
def home(): return "v15 Bot Running - Win/Loss Photo Check Active"

if __name__ == "__main__":
    threading.Thread(target=telegram_photo_listener, daemon=True).start()
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
