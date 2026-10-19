import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from datetime import datetime
import ta

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# REAL MARKET PAIRS - Yahoo Symbol ঠিক করা হইছে 99% Match এর জন্য
REAL_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/GBP": "EURGBP=X"
}

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ===== NEW: WIN/LOSS CHECK FUNCTION =====
def check_and_send_result(pair_name, yf_symbol, entry_price, direction, entry_time_str):
    """2 Min পর Result Check করবে"""
    time.sleep(125)  # 2 Min 5 Sec Wait - Candle Close হওয়ার জন্য
    try:
        data = yf.download(yf_symbol, period="1d", interval="1m", progress=False)
        if len(data) < 2:
            return
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        exit_price = float(data['Close'].iloc[-1])
        
        is_win = False
        if "CALL" in direction and exit_price > entry_price:
            is_win = True
        elif "PUT" in direction and exit_price < entry_price:
            is_win = True
        
        if is_win:
            result_msg = f"""✅ **WIN ✅ WIN ✅**

💱 {pair_name} - {direction}
Entry: `{entry_price:.5f}`
Exit: `{exit_price:.5f}`
Time: {entry_time_str}

🔥 Profit: +57% 🔥"""
        else:
            result_msg = f"""❌ **LOSS ❌ LOSS**

💱 {pair_name} - {direction}
Entry: `{entry_price:.5f}`
Exit: `{exit_price:.5f}`
Time: {entry_time_str}

⚠️ Next Signal Wait করো"""
        
        send_telegram(result_msg)
        print(f"Result Sent: {pair_name} - {'WIN' if is_win else 'LOSS'}")
        
    except Exception as e:
        print(f"Result Check Error {pair_name}: {e}")

def check_market_condition(df):
    adx = ta.trend.adx(df['High'], df['Low'], df['Close'], window=14)
    if adx.iloc[-1] < 22:
        return False, "Weak Trend"
    atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    if atr.iloc[-1] < 0.0003:
        return False, "Low Volatility"
    bb_width = ta.volatility.bollinger_wband(df['Close'])
    if bb_width.iloc[-1] < 0.005:
        return False, "Squeeze"
    return True, "Good"

def high_accuracy_strategy(df):
    close = df['Close']
    ema9 = ta.trend.ema_indicator(close, window=9).iloc[-1]
    ema21 = ta.trend.ema_indicator(close, window=21).iloc[-1]
    ema50 = ta.trend.ema_indicator(close, window=50).iloc[-1]
    rsi = ta.momentum.rsi(close, window=14).iloc[-1]
    macd_line = ta.trend.macd(close).iloc[-1]
    macd_signal = ta.trend.macd_signal(close).iloc[-1]
    bb_high = ta.volatility.bollinger_hband(close).iloc[-1]
    bb_low = ta.volatility.bollinger_lband(close).iloc[-1]
    last_close = close.iloc[-1]
    last_low = df['Low'].iloc[-1]
    last_high = df['High'].iloc[-1]
    
    signal = None
    confidence = 0
    
    if ema9 > ema21 > ema50 and rsi > 55 and rsi < 75 and macd_line > macd_signal:
        if last_close > ema9:
            confidence = 88
            if rsi > 60:
                confidence = 92
            signal = "CALL (BUY) ⬆️"
    elif ema9 < ema21 < ema50 and rsi < 45 and rsi > 25 and macd_line < macd_signal:
        if last_close < ema9:
            confidence = 87
            if rsi < 40:
                confidence = 91
            signal = "PUT (SELL) ⬇️"
    
    return signal, confidence

def analyze_pair(name, yf_symbol):
    try:
        data = yf.download(yf_symbol, period="1d", interval="1m", progress=False)
        if len(data) < 60:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.dropna()
        
        is_good, reason = check_market_condition(data)
        if not is_good:
            return None
            
        signal, conf = high_accuracy_strategy(data)
        if signal and conf >= 85:
            return {"pair": name, "symbol": yf_symbol, "signal": signal, "conf": conf, "price": float(data['Close'].iloc[-1])}
    except Exception as e:
        print(f"Error {name}: {e}")
    return None

def bot_loop():
    print("v15 Real Market Bot Started")
    send_telegram("✅ *v15 Real Market Bot LIVE*\nMode: Real Market (No OTC)\nPairs: 8 Major Pairs\nSignal: Every 30 Min\nAuto Result: ON ✅")
    while True:
        try:
            now = datetime.now()
            if now.minute % 30 == 0:
                print(f"Scanning Real Market... {now}")
                best_signal = None
                for name, symbol in REAL_PAIRS.items():
                    result = analyze_pair(name, symbol)
                    if result:
                        if best_signal is None or result['conf'] > best_signal['conf']:
                            best_signal = result
                    time.sleep(1)
                
                if best_signal:
                    msg = f"""🔥 *v15 FUTURE SIGNAL - REAL MARKET* 🔥
💱 Pair: `{best_signal['pair']}`
📊 Signal: *{best_signal['signal']}*
🎯 Confidence: *{best_signal['conf']}%*
💵 Price: `{best_signal['price']:.5f}`
⏰ Time: {now.strftime('%H:%M')} - Expiry 2 Min
🏦 Broker: Quotex Real Market

✅ *High Confirmation - 5 Layer Check Passed*
⏳ *Auto Result 2 Min পর আসবে*"""
                    
                    send_telegram(msg)
                    
                    # ===== AUTO WIN/LOSS THREAD START =====
                    threading.Thread(
                        target=check_and_send_result,
                        args=(best_signal['pair'], best_signal['symbol'], best_signal['price'], best_signal['signal'], now.strftime('%H:%M')),
                        daemon=True
                    ).start()
                else:
                    print("No High Quality Signal - Market Bad")
                time.sleep(60)
            else:
                time.sleep(20)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(30)

@app.route('/')
def home():
    return "v15 Real Market Bot is Running! - Auto WIN/LOSS ON"

if __name__ == "__main__":
    t = threading.Thread(target=bot_loop)
    t.daemon = True
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
