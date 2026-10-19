import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
import pytz

# --- CONFIG ---
BOT_TOKEN = "YOUR_BOT_TOKEN"  # তোমার Bot Token
CHAT_ID = "YOUR_CHAT_ID"      # তোমার Chat ID

PAIRS = {
    "USD/JPY": "USDJPY=X",
    "EUR/USD": "EURUSD=X",
    "EUR/JPY": "EURJPY=X"
}

BD_TZ = pytz.timezone('Asia/Dhaka')
EXPIRY_MIN = 5

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_bd_time():
    return datetime.now(BD_TZ)

# --- INDICATORS ---
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def macd(df):
    ema12 = ema(df['Close'], 12)
    ema26 = ema(df['Close'], 26)
    macd_line = ema12 - ema26
    signal = ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist

def adx(df, period=14):
    high = df['High']; low = df['Low']; close = df['Close']
    plus_dm = high.diff(); minus_dm = low.diff() * -1
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.ewm(alpha=1/period).mean(), plus_di, minus_di, atr

def bollinger_width(close, period=20):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + (2*std)
    lower = sma - (2*std)
    return (upper - lower) / sma

# --- PRICE ACTION HIGH QUALITY ---
def detect_candle_pattern(df):
    last = df.iloc[-1]; prev = df.iloc[-2]
    body_last = abs(last['Close'] - last['Open'])
    body_prev = abs(prev['Close'] - prev['Open'])
    
    # Bullish Engulfing
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and last['Close'] > prev['Open'] and last['Open'] < prev['Close']:
        return "Bullish Engulfing", True
    # Bearish Engulfing
    if prev['Close'] > prev['Open'] and last['Close'] < last['Open'] and last['Close'] < prev['Open'] and last['Open'] > prev['Close']:
        return "Bearish Engulfing", True
    # Hammer / Pin Bar
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    if lower_wick > (body_last * 2) and upper_wick < body_last * 0.5:
        return "Hammer Pin Bar", True
    if upper_wick > (body_last * 2) and lower_wick < body_last * 0.5:
        return "Shooting Star Pin Bar", True
    return "No Pattern", False

def detect_bos_choch(df):
    # BOS = Higher High Higher Low, CHOCH = Break
    highs = df['High'].tail(10); lows = df['Low'].tail(10)
    hh = highs.iloc[-1] > highs.max() - highs.std()
    hl = lows.iloc[-1] > lows.min() + lows.std()
    ll = lows.iloc[-1] < lows.min() + lows.std()*0.5
    if hh and hl:
        return "BOS Uptrend", True
    if ll:
        return "CHOCH Downtrend", True
    return "BOS/CHOCH", False

def detect_liquidity_sweep(df):
    # Sweep previous High then close below
    prev_high = df['High'].iloc[-5:-1].max()
    curr_high = df['High'].iloc[-1]
    curr_close = df['Close'].iloc[-1]
    prev_low = df['Low'].iloc[-5:-1].min()
    curr_low = df['Low'].iloc[-1]
    if curr_high > prev_high and curr_close < prev_high:
        return "Liquidity Sweep High + Rejection", True
    if curr_low < prev_low and curr_close > prev_low:
        return "Liquidity Sweep Low + Rejection", True
    return "No Sweep", False

def detect_order_block_fvg(df):
    # FVG: Candle1 High < Candle3 Low (Bullish FVG)
    c1 = df.iloc[-3]; c2 = df.iloc[-2]; c3 = df.iloc[-1]
    bullish_fvg = c3['Low'] > c1['High']
    bearish_fvg = c3['High'] < c1['Low']
    # Order Block: Last opposite candle before impulse
    if bullish_fvg:
        return f"Bullish FVG + Order Block {c1['Low']:.5f}", True
    if bearish_fvg:
        return f"Bearish FVG + Order Block {c1['High']:.5f}", True
    return "No OB/FVG", False

def detect_demand_supply(df):
    recent_low = df['Low'].tail(20).min()
    recent_high = df['High'].tail(20).max()
    curr_price = df['Close'].iloc[-1]
    if abs(curr_price - recent_low) / curr_price < 0.002: # Near Demand
        return f"Demand Zone {recent_low:.5f}", True
    if abs(curr_price - recent_high) / curr_price < 0.002: # Near Supply
        return f"Supply Zone {recent_high:.5f}", True
    return "Mid Zone", False

def detect_key_level(price, df_daily):
    round_level = round(price, 1) if "JPY" in str(price) else round(price, 2)
    prev_high = df_daily['High'].iloc[-2] if len(df_daily)>=2 else price
    prev_low = df_daily['Low'].iloc[-2] if len(df_daily)>=2 else price
    if abs(price - prev_high)/price < 0.0015 or abs(price - prev_low)/price < 0.0015 or abs(price - round_level)/price < 0.001:
        return f"Key Level {round_level}", True
    return "No Key Level", False

def get_data(symbol, interval):
    try:
        df = yf.download(symbol, period="5d", interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.dropna(inplace=True)
        return df
    except: return None

# --- MAIN ANALYSIS ---
def analyze_pair(pair_name, symbol):
    df_30m = get_data(symbol, "30m")
    df_15m = get_data(symbol, "15m")
    df_5m = get_data(symbol, "5m")
    df_1d = get_data(symbol, "1d")

    if df_30m is None or df_15m is None or df_5m is None or len(df_30m)<60 or len(df_5m)<60:
        return None

    # Indicators 5m
    df_5m['EMA9'] = ema(df_5m['Close'], 9)
    df_5m['EMA21'] = ema(df_5m['Close'], 21)
    df_5m['EMA50'] = ema(df_5m['Close'], 50)
    df_5m['RSI'] = rsi(df_5m['Close'])
    df_5m['MACD'], df_5m['MACD_SIG'], df_5m['MACD_HIST'] = macd(df_5m)
    df_5m['ADX'], pdi, mdi, atr = adx(df_5m)
    df_5m['BBW'] = bollinger_width(df_5m['Close'])
    
    df_15m['EMA9'] = ema(df_15m['Close'], 9)
    df_15m['EMA21'] = ema(df_15m['Close'], 21)
    df_30m['EMA50'] = ema(df_30m['Close'], 50)
    df_30m['EMA200'] = ema(df_30m['Close'], 200)

    last5 = df_5m.iloc[-1]; last15 = df_15m.iloc[-1]; last30 = df_30m.iloc[-1]

    # HTF Trend
    trend_30 = "UPTREND" if last30['Close'] > last30['EMA50'] and last30['EMA50'] > last30['EMA200'] else "DOWNTREND" if last30['Close'] < last30['EMA50'] else "SIDEWAYS"
    trend_15 = "UPTREND" if last15['Close'] > last15['EMA9'] and last15['EMA9'] > last15['EMA21'] else "DOWNTREND" if last15['Close'] < last15['EMA9'] else "SIDEWAYS"
    trend_5 = "UPTREND" if last5['EMA9'] > last5['EMA21'] > last5['EMA50'] else "DOWNTREND" if last5['EMA9'] < last5['EMA21'] < last5['EMA50'] else "SIDEWAYS"

    if not (trend_30 == trend_15 == trend_5 and trend_30 != "SIDEWAYS"):
        return None # Trend Match Fail

    # Market Condition
    if last5['ADX'] < 28 or last5['BBW'] < 0.006 or atr.iloc[-1] < 0.0003:
        return "BAD_MARKET"

    # Price Action Checks
    pattern_name, pattern_ok = detect_candle_pattern(df_5m)
    bos_name, bos_ok = detect_bos_choch(df_5m)
    sweep_name, sweep_ok = detect_liquidity_sweep(df_5m)
    ob_fvg_name, ob_ok = detect_order_block_fvg(df_5m)
    zone_name, zone_ok = detect_demand_supply(df_5m)
    key_name, key_ok = detect_key_level(last5['Close'], df_1d)

    # High Quality Price Action Must Pass
    price_action_ok = bos_ok or sweep_ok or ob_ok
    if not price_action_ok: return None
    if not pattern_ok: return None
    if not zone_ok: return None
    if not key_ok: return None

    # RSI & MACD Final
    rsi_val = last5['RSI']
    is_call_setup = trend_30 == "UPTREND" and 60 <= rsi_val <= 75 and last5['MACD'] > last5['MACD_SIG'] and last5['MACD_HIST'] > 0
    is_put_setup = trend_30 == "DOWNTREND" and 25 <= rsi_val <= 40 and last5['MACD'] < last5['MACD_SIG'] and last5['MACD_HIST'] < 0

    if not (is_call_setup or is_put_setup): return None

    signal = "CALL" if is_call_setup else "PUT"
    # Confidence Calculation
    score = 80
    if bos_ok: score+=5
    if sweep_ok: score+=5
    if ob_ok: score+=4
    if pattern_ok: score+=3
    confidence = min(score, 98)

    if confidence < 90: return None

    return {
        "pair": pair_name,
        "price": last5['Close'],
        "signal": signal,
        "confidence": confidence,
        "trend30": trend_30,
        "trend15": trend_15,
        "zone": zone_name,
        "key": key_name,
        "pattern": pattern_name,
        "pa": f"{bos_name} | {sweep_name} | {ob_fvg_name}"
    }

# --- MAIN LOOP ---
send_telegram(f"🚀 v16 PRO MAX Bot LIVE - BD Time {get_bd_time().strftime('%H:%M:%S')} - 3 Pair HTF Ready")
last_bad_market_msg = 0
no_signal_count = 0

while True:
    try:
        bd_time = get_bd_time()
        found_signal = False
        bad_market_pairs = 0

        for name, sym in PAIRS.items():
            result = analyze_pair(name, sym)
            if result == "BAD_MARKET":
                bad_market_pairs += 1
                continue
            if result is None:
                continue

            found_signal = True
            no_signal_count = 0
            
            msg = f"""🔥 <b>v16 PRO MAX SIGNAL</b> 🔥
💱 <b>{result['pair']}</b>
📈 HTF: 30M {result['trend30']} | 15M {result['trend15']} | 5M {result['trend30']}
📍 Zone: {result['zone']} ✅
🔑 Level: {result['key']} ✅
🕯️ Candle: {result['pattern']} ✅
💎 Price Action: {result['pa']} ✅
📊 Signal: <b>{result['signal']}</b> {'⬆️' if result['signal']=='CALL' else '⬇️'}
🎯 Confidence: {result['confidence']}%
💵 Price: {result['price']:.5f}
⏰ BD Time: {bd_time.strftime('%H:%M')} | Expiry: {EXPIRY_MIN} Min
✅ 12 Layer Passed - PRO MAX
"""
            send_telegram(msg)
            
            # Auto Result after 5 min
            entry_price = result['price']
            time.sleep(EXPIRY_MIN * 60 + 10)
            df_check = get_data(sym, "5m")
            if df_check is not None:
                exit_price = df_check['Close'].iloc[-1]
                win = (exit_price > entry_price and result['signal']=="CALL") or (exit_price < entry_price and result['signal']=="PUT")
                res_msg = f"{'✅ WIN' if win else '❌ LOSS'} - {result['pair']} {result['signal']}\nEntry: {entry_price:.5f} | Exit: {exit_price:.5f}\nBD Time: {get_bd_time().strftime('%H:%M')}"
                send_telegram(res_msg)

        if not found_signal:
            no_signal_count += 1
            # 60 min = 30 scans (2 min each)
            if no_signal_count >= 30 and (time.time() - last_bad_market_msg > 3600):
                if bad_market_pairs >= 2:
                    send_telegram(f"⚠️ মার্কেট খারাপ ভাই - Choppy / No Setup - 60 Min ধরে High Quality Setup পাচ্ছি না। Wait করো। BD Time {bd_time.strftime('%H:%M')}")
                else:
                    send_telegram(f"📉 Setup খুঁজছি... এখনো 12 Layer Match হয় নাই। Market Slow। BD Time {bd_time.strftime('%H:%M')}")
                last_bad_market_msg = time.time()
                no_signal_count = 0

        time.sleep(120) # Scan every 2 Min

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(60)
