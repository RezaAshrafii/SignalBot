import os
from datetime import datetime, timedelta, timezone
from fetch_futures_binance import fetch_futures_klines

# --- تنظیمات ---
SYMBOLS_TO_DOWNLOAD = ['BTCUSDT', 'ETHUSDT']
DAYS_OF_DATA = 45
TIMEFRAME = '1m' # داده‌ها را با تایم فریم ۱ دقیقه‌ای دانلود می‌کنیم

def download_and_save_data():
    """
    داده‌های تاریخی را برای نمادهای مشخص شده دانلود کرده و در فایل‌های CSV ذخیره می‌کند.
    """
    print("Starting data download process...")
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=DAYS_OF_DATA)

    # اطمینان از وجود پوشه data
    if not os.path.exists('data'):
        os.makedirs('data')

    for symbol in SYMBOLS_TO_DOWNLOAD:
        file_path = f"data/{symbol}_{TIMEFRAME}.csv"
        print(f"\n----- Downloading data for {symbol} -----")
        
        # پراکسی را می‌توان به صورت اختیاری اضافه کرد اگر برای دانلود هم مشکل دارید
        # PROXY_URL = "socks5://127.0.0.1:2080"
        # PROXY_CONFIG = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        
        df = fetch_futures_klines(symbol, TIMEFRAME, start_time_dt=start_time, end_time_dt=end_time) #, proxies=PROXY_CONFIG)

        if not df.empty:
            df.to_csv(file_path, index=False)
            print(f"Successfully downloaded {len(df)} candles for {symbol}.")
            print(f"Data saved to: {file_path}")
        else:
            print(f"Could not download data for {symbol}.")

if __name__ == "__main__":
    download_and_save_data()
    print("\nData download finished.")