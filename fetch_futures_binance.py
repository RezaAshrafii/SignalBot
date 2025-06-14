# fetch_futures_binance.py
import pandas as pd
import requests
import time
from datetime import datetime

def fetch_futures_klines(symbol, interval='1m', start_time_dt=None, end_time_dt=None):
    """
    داده‌های تاریخی کندل را از فیوچرز بایننس برای یک بازه زمانی مشخص دریافت می‌کند.
    این تابع با مدیریت صفحات (Pagination)، تمام داده‌های مورد نیاز را واکشی می‌کند.
    """
    url = "https://fapi.binance.com/fapi/v1/klines"
    limit = 1500  # حداکثر محدودیت API بایننس

    # تبدیل آبجکت‌های datetime به میلی‌ثانیه UTC برای API بایننس
    start_time_ms = int(start_time_dt.timestamp() * 1000)
    end_time_ms = int(end_time_dt.timestamp() * 1000)
    
    all_data = []
    
    print(f"Fetching {symbol} klines from {start_time_dt.strftime('%Y-%m-%d')} to {end_time_dt.strftime('%Y-%m-%d')}...")
    
    while start_time_ms < end_time_ms:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': start_time_ms,
            'endTime': end_time_ms,
            'limit': limit
        }
        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()  # بررسی خطاهای HTTP
            data = response.json()
            
            if not data:
                # اگر داده‌ای در این بازه نبود، حلقه را متوقف کن
                break
            
            all_data.extend(data)
            
            # زمان شروع برای درخواست بعدی را یک میلی‌ثانیه بعد از آخرین کندل دریافتی تنظیم کن
            last_candle_time = data[-1][0]
            start_time_ms = last_candle_time + 1
            
            # یک تأخیر کوتاه برای جلوگیری از بلاک شدن توسط API
            time.sleep(0.2)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {symbol} from Binance: {e}")
            return pd.DataFrame() # در صورت خطا، یک DataFrame خالی برگردان
        except Exception as e:
            print(f"An unexpected error occurred in fetch_futures_klines for {symbol}: {e}")
            return pd.DataFrame()

    if not all_data:
        print(f"No data could be fetched for {symbol} in the specified range.")
        return pd.DataFrame()

    print(f"Successfully fetched {len(all_data)} klines for {symbol}.")
    
    df = pd.DataFrame(all_data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
        'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    # تبدیل نوع داده‌ها
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'taker_buy_base_asset_volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # انتخاب ستون‌های مورد نیاز
    return df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_base_asset_volume']]