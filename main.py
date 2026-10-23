import yfinance as yf, pandas as pd, mplfinance as mpf, os, asyncio
from telegram import Bot
import matplotlib
matplotlib.use('Agg')

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
bot = Bot(BOT_TOKEN)

REAL_PAIRS = ["EURUSD=X", "GBPUSD=X", "GBPJPY=X", "EURJPY=X", "AUDUSD=X", "USDJPY=X"]

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def advanced_scan(df):
    df['RSI'] = calc_rsi(df['Close'], 14)
    df['EMA200'] = df['Close'].ewm(span=200).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    
    signals = []
    for i in range(50, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        body = abs(float(curr['Open']) - float(curr['Close']))
        if body == 0: continue
        low_wick = min(float(curr['Open']), float(curr['Close'])) - float(curr['Low'])
        up_wick = float(curr['High']) - max(float(curr['Open']), float(curr['Close']))
        
        # Real Support/Resistance
        recent_low = df['Low'].iloc[i-20:i].min()
        recent_high = df['High'].iloc[i-20:i].max()
        
        bull_eng = float(curr['Close']) > float(curr['Open']) and float(prev['Close']) < float(prev['Open']) and float(curr['Close']) > float(prev['Open'])
        bear_eng = float(curr['Close']) < float(curr['Open']) and float(prev['Close']) > float(prev['Open']) and float(curr['Close']) < float(prev['Open'])
        
        rsi = float(curr['RSI'])
        atr = float(curr['ATR'])
        
        # ADVANCED REAL LOGIC
        is_buy = low_wick > body*2.0 and bull_eng and rsi < 38 and rsi > 22 and float(curr['Close']) > float(curr['EMA200']) and float(curr['Low']) <= float(recent_low)*1.001
        is_sell = up_wick > body*2.0 and bear_eng and rsi > 62 and rsi < 78 and float(curr['Close']) < float(curr['EMA200']) and float(curr['High']) >= float(recent_high)*0.999
        
        if is_buy:
            signals.append((df.index[i], 'BUY', float(curr['Low']), rsi))
        elif is_sell:
            signals.append((df.index[i], 'SELL', float(curr['High']), rsi))
    return signals

async def main():
    print("ADVANCED REAL PRO - Chart + 6 Filter Started")
    last_signal = None
    while True:
        for pair in REAL_PAIRS:
            try:
                df = yf.download(pair, period="2d", interval="1m", progress=False, auto_adjust=True)
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df = df.dropna()
                if len(df) < 60: continue
                
                sigs = advanced_scan(df)
                if not sigs: continue
                
                last = sigs[-1]
                # 90 Sec এর মধ্যে Signal হলে পাঠাবে - Non Repaint
                if last[0] != last_signal and (pd.Timestamp.now(tz='UTC') - last[0]).total_seconds() < 120:
                    last_signal = last[0]
                    
                    # Chart বানাও - তোমার ছবির মতো Dark Theme
                    df_plot = df.tail(50)
                    mpf.plot(df_plot, type='candle', style='nightclouds', 
                             title=f'{pair} - Candle Scanner Pro', 
                             savefig='real.png', figsize=(12,6), tight_layout=True)
                    
                    clean = pair.replace("=X","").replace("USD","/USD")
                    msg = f"🔥 **CANDLE SCANNER PRO - REAL** 🔥\n\n{'🟢 BUY' if last[1]=='BUY' else '🔴 SELL'} - {clean}\nRSI: {last[3]:.1f}\nLogic: Wick 2x + Engulf + RSI + EMA200 + Support/Resistance\nExpiry: 2 MIN (M1)\nMode: REAL PAIR ONLY - OTC OFF\n\n✅ High Accuracy Real Analysis"
                    
                    with open('real.png','rb') as photo:
                        await bot.send_photo(chat_id=CHAT_ID, photo=photo, caption=msg, parse_mode='Markdown')
                    print(f"Sent Advanced Signal {clean} {last[1]}")
                    
            except Exception as e:
                print(f"Error {pair}: {e}")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
