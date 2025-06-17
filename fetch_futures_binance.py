import pandas as pd
import requests
import time
from datetime import datetime

def fetch_futures_klines(symbol, interval='1m', start_time_dt=None, end_time_dt=None, proxies=None):
    """
    داده‌های تاریخی کندل را از فیوچرز بایننس دریافت می‌کند.
    این نسخه اصلاح شده و قابلیت استفاده از پروکسی را دارد.
    """
    url = "https://fapi.binance.com/fapi/v1/klines"
    limit = 1500  # حداکثر محدودیت API بایننس

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
            # استفاده از پروکسی در درخواست در صورت وجود
            response = requests.get(url, params=params, timeout=30, proxies=proxies)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            
            last_candle_time = data[-1][0]
            start_time_ms = last_candle_time + 1
            
            time.sleep(0.3)

        except requests.exceptions.ProxyError as e:
            print(f"Proxy Error for {symbol}: {e}. Please check your proxy settings and ensure it is running.")
            return pd.DataFrame()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {symbol} from Binance: {e}")
            return pd.DataFrame()
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
    
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'taker_buy_base_asset_volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_base_asset_volume']]