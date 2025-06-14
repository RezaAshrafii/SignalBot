# price_updater.py
import json, websocket, ssl, threading, time

class PriceUpdater:
    def __init__(self, symbol, state_manager):
        self.symbol = symbol
        self.state_manager = state_manager
        self.ws = None

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            # استریم markPrice@1s داده‌ها را در این فرمت ارسال می‌کند
            if data.get('e') == 'markPriceUpdate':
                price = float(data['p'])
                self.state_manager.update_symbol_state(self.symbol, 'last_price', price)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[PriceUpdater][{self.symbol}] Error processing price message: {e}")

    def on_error(self, ws, error):
        print(f"[PriceUpdater][{self.symbol}] Connection Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[PriceUpdater][{self.symbol}] Connection closed. Attempting to reconnect in 5 seconds...")
        time.sleep(5)
        self.run() # تلاش برای اتصال مجدد

    def on_open(self, ws):
        print(f"[PriceUpdater] Live price connection opened for {self.symbol} using @markPrice stream.")

    def _connect(self):
        print(f"[PriceUpdater] Attempting to connect for {self.symbol}...")
        # --- این خط اصلاح و بهبود داده شد ---
        # استفاده از استریم Mark Price که هر ثانیه قیمت را ارسال می‌کند
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@markPrice@1s'
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def run(self):
        thread = threading.Thread(target=self._connect, daemon=True)
        thread.start()