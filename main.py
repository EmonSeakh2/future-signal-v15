import yfinance as yf, pandas as pd, mplfinance as mpf, os, asyncio
from telegram import Bot
import pandas_ta as ta

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
bot = Bot(BOT_TOKEN)

REAL_PAIRS = ["EURUSD=X", "GBPUSD=X", "GBPJPY=X", "EURJPY=X", "AUDUSD=X", "USDCAD=X", "EURGBP=X", "USDJPY=X"]

def real_analysis(df):
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    
    signals = []
    for i in range(50, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Filter 1,2,3 - Structure
        body = abs(float(curr['Open']) - float(curr['Close']))
        if body == 0: continue
        lower_wick = min(float(curr['Open']), float(curr['Close'])) - float(curr['Low'])
        upper_wick = float(curr['High']) - max(float(curr['Open']), float(curr['Close']))
        
        bullish_engulf = float(curr['Close']) > float(curr['Open']) and float(prev['Close']) < float(prev['Open']) and float(curr['Close']) > float(prev['Open'])
        bearish_engulf = float(curr['Close']) < float(curr['Open']) and float(prev['Close']) > float(prev['Open']) and float(curr['Close']) < float(prev['Open'])
        
        # Filter 4 - RSI Real
        rsi_buy = float(curr['RSI']) < 38 and float(curr['RSI']) > 20
        rsi_sell = float(curr['RSI']) > 62 and float(curr['RSI']) < 80
        
        # Filter 5 - EMA Trend
        uptrend = float(curr['Close']) > float(curr['EMA200'])
        downtrend = float(curr['Close']) < float(curr['EMA200'])
        
        # FINAL REAL BUY/SELL
        if lower_wick > body*2 and bullish_engulf and rsi_buy and uptrend:
            signals.append((df.index[i], 'BUY', float(curr['RSI'])))
        elif upper_wick > body*2 and bearish_engulf and rsi_sell and downtrend:
            signals.append((df.index[i], 'SELL', float(curr['RSI'])))
            
    return signals

async def loop():
    print("REAL ANALYSIS PRO Started - OTC OFF")
    while True:
        # BD Time 11AM-9PM Real Market Check
        for pair in REAL_PAIRS:
            try:
                df = yf.download(pair, period="2d", interval="1m", progress=False)
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                sigs = real_analysis(df)
                if sigs and (pd.Timestamp.now(tz='UTC') - sigs[-1][0]).total_seconds() < 90:
                    last = sigs[-1]
                    # Chart বানাও
                    mpf.plot(df.tail(50), type='candle', style='yahoo', savefig='real.png', figsize=(10,5))
                    clean_pair = pair.replace("=X","")
                    msg = f"🔥 REAL ANALYSIS PRO 🔥\n{'🟢 BUY' if last[1]=='BUY' else '🔴 SELL'} - {clean_pair} (Real)\nRSI: {last[2]:.1f}\nFilters: Wick+Engulf+RSI+EMA200\nExpiry: 2 Min\nSession: London/NY Real Market"
                    with open('real.png','rb') as p:
                        await bot.send_photo(chat_id=CHAT_ID, photo=p, caption=msg)
            except Exception as e:
                print(e)
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(loop())
