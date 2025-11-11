import MetaTrader5 as mt5
import pandas as pd
import pytz
from datetime import datetime, time
from metatrader5_config_gold import MT5_CONFIG

RET_OK = 10009  # mt5.TRADE_RETCODE_DONE

class MT5ConnectorGold:
    def __init__(self):
        cfg = MT5_CONFIG
        self.symbol = cfg['symbol']
        self.lot = cfg['lot_size']
        self.deviation = cfg['deviation']
        self.magic = cfg['magic_number']
        self.max_spread = cfg['max_spread']
        self.min_balance = cfg['min_balance']
        self.trading_hours = cfg['trading_hours']
        self.iran_tz = pytz.timezone('Asia/Tehran')
        self.utc_tz = pytz.UTC

    def get_iran_time(self):
        return datetime.now(self.utc_tz).astimezone(self.iran_tz)

    def is_trading_time(self):
        start = time.fromisoformat(self.trading_hours['start'])
        end = time.fromisoformat(self.trading_hours['end'])
        now_t = self.get_iran_time().time()
        if start <= end:
            return start <= now_t <= end
        return now_t >= start or now_t <= end

    def check_weekend(self):
        wd = self.get_iran_time().weekday()
        return wd not in (5, 6)

    def can_trade(self):
        if not self.check_weekend():
            return False, "Weekend - trading disabled"
        if not self.is_trading_time():
            return False, "Outside configured trading hours"
        ti = mt5.terminal_info()
        if not ti:
            return False, "Terminal info unavailable"
        if not ti.trade_allowed:
            return False, "Terminal AutoTrading disabled"
        acc = mt5.account_info()
        if not acc:
            return False, "Account info unavailable"
        if acc.balance < self.min_balance:
            return False, f"Insufficient balance < {self.min_balance}"
        return True, "Trading is allowed"

    def initialize(self):
        if not mt5.initialize():
            print("❌ MT5 initialize failed:", mt5.last_error())
            return False
        acc = mt5.account_info()
        if acc and acc.balance < self.min_balance:
            print(f"❌ Balance {acc.balance} < min {self.min_balance}")
            return False
        print("✅ MT5 connection established")
        return True

    def shutdown(self):
        mt5.shutdown()

    def get_live_price(self):
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return None
        spread = (tick.ask - tick.bid)
        if spread > self.max_spread:
            print(f"⚠️ Spread ${spread:.2f} > max ${self.max_spread}")
        utc_time = datetime.fromtimestamp(tick.time, tz=self.utc_tz)
        return {
            'bid': tick.bid,
            'ask': tick.ask,
            'spread': spread,
            'time': utc_time.astimezone(self.iran_tz),
            'utc_time': utc_time
        }

    def get_historical_data(self, timeframe=mt5.TIMEFRAME_M15, count=500):
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
        if rates is None:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert(self.iran_tz)
        df.set_index('time', inplace=True)
        df = df.rename(columns={'tick_volume': 'volume'})
        df['timestamp'] = df.index
        return df

    def get_supported_filling_modes(self):
        info = mt5.symbol_info(self.symbol)
        if not info:
            return []
        fm = getattr(info, 'filling_mode', 0)
        modes = []
        for m in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            try:
                if (fm & m) == m:
                    modes.append(m)
            except Exception:
                if fm == m:
                    modes.append(m)
        return modes

    def try_all_filling_modes(self, request):
        tried = []
        modes = self.get_supported_filling_modes()

        for m in modes:
            req = dict(request)
            req["type_filling"] = m
            res = mt5.order_send(req)
            tried.append((m, getattr(res, 'retcode', None)))
            if res and res.retcode in (RET_OK, mt5.TRADE_RETCODE_PLACED):
                return res

        req = dict(request)
        req.pop("type_filling", None)
        res = mt5.order_send(req)
        tried.append(("auto", getattr(res, 'retcode', None)))
        if res and res.retcode in (RET_OK, mt5.TRADE_RETCODE_PLACED):
            return res

        for m in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            if m in modes:
                continue
            req = dict(request)
            req["type_filling"] = m
            res = mt5.order_send(req)
            tried.append((m, getattr(res, 'retcode', None)))
            if res and res.retcode in (RET_OK, mt5.TRADE_RETCODE_PLACED):
                return res

        print(f"[order_send] filling mode attempts: {tried}")
        return res

    def calculate_valid_stops(self, entry_price, sl_price, tp_price, order_type):
        info = mt5.symbol_info(self.symbol)
        if not info:
            print("Symbol info unavailable")
            return None, None
        
        point = info.point
        min_distance = 0.5  # حداقل 0.5 دلار برای طلا

        if order_type == mt5.ORDER_TYPE_BUY and sl_price >= entry_price:
            print("❌ SL برای BUY باید پایین‌تر از ورود باشد")
            return None, None
        if order_type == mt5.ORDER_TYPE_SELL and sl_price <= entry_price:
            print("❌ SL برای SELL باید بالاتر از ورود باشد")
            return None, None

        distance = abs(entry_price - sl_price)
        if distance < min_distance:
            print(f"❌ فاصله SL ({distance:.2f}) < حداقل ({min_distance})")
            return None, None

        if tp_price is not None:
            if order_type == mt5.ORDER_TYPE_BUY and tp_price <= entry_price:
                print("❌ TP برای BUY باید بالاتر از ورود باشد")
                return None, None
            if order_type == mt5.ORDER_TYPE_SELL and tp_price >= entry_price:
                print("❌ TP برای SELL باید پایین‌تر از ورود باشد")
                return None, None

        def norm(p):
            if p is None:
                return None
            return float(f"{p:.{info.digits}f}")

        return norm(sl_price), norm(tp_price)

    def _normalize_volume(self, vol: float) -> float:
        info = mt5.symbol_info(self.symbol)
        if not info:
            return vol
        step = info.volume_step or 0.01
        vmin = info.volume_min or step
        vmax = info.volume_max or 100.0
        steps = round(vol / step)
        vol_rounded = steps * step
        return max(vmin, min(vmax, vol_rounded))

    def _get_tick_specs(self, info):
        tick_size = getattr(info, 'trade_tick_size', None) or getattr(info, 'tick_size', None) or getattr(info, 'point', None)
        tick_value = getattr(info, 'trade_tick_value', None) or getattr(info, 'tick_value', None)
        if tick_value is None:
            contract = getattr(info, 'trade_contract_size', None)
            if contract and tick_size:
                tick_value = contract * tick_size
        return tick_size, tick_value

    def calculate_volume_by_risk(self, entry: float, sl: float, tick, risk_pct: float = 0.01) -> float:
        acc = mt5.account_info()
        info = mt5.symbol_info(self.symbol)
        if not acc or not info:
            return self.lot

        tick_size, tick_value = self._get_tick_specs(info)
        if not tick_size or not tick_value:
            return self.lot

        risk_money = acc.balance * float(risk_pct)
        risk_points = abs(entry - sl) / float(tick_size)
        price_risk_per_lot = risk_points * float(tick_value)

        spread_points = abs(getattr(tick, 'ask', 0.0) - getattr(tick, 'bid', 0.0)) / float(tick_size)
        spread_cost_per_lot = spread_points * float(tick_value)

        total_cost_per_lot = price_risk_per_lot + spread_cost_per_lot
        if total_cost_per_lot <= 0:
            return self.lot

        vol = risk_money / total_cost_per_lot

        MAX_LEVERAGE_FACTOR = 0.02
        theoretical_loss_per_lot = price_risk_per_lot
        if theoretical_loss_per_lot <= 0:
            return self.lot
        max_allowed_vol = (acc.balance * MAX_LEVERAGE_FACTOR) / theoretical_loss_per_lot
        if vol > max_allowed_vol:
            vol = max_allowed_vol

        return self._normalize_volume(vol)

    def _resolve_volume(self, volume, entry, sl, tick, risk_pct):
        if volume is not None:
            return self._normalize_volume(volume)
        if risk_pct is not None:
            return self.calculate_volume_by_risk(entry, sl, tick, risk_pct)
        return self.lot

    def open_buy_position(self, tick, sl, tp, comment="", volume=None, risk_pct=None):
        if not tick:
            print("No tick data")
            return None
        entry = tick.ask
        sl_adj, tp_adj = self.calculate_valid_stops(entry, sl, tp, mt5.ORDER_TYPE_BUY)
        if sl_adj is None:
            return None
        vol = self._resolve_volume(volume, entry, sl_adj, tick, risk_pct)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": vol,
            "type": mt5.ORDER_TYPE_BUY,
            "price": entry,
            "sl": sl_adj,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if tp_adj is not None:
            request["tp"] = tp_adj
        print(f"📤 BUY {self.symbol} @ {entry} VOL={vol} SL={sl_adj} TP={tp_adj if tp_adj else 'None'}")
        result = self.try_all_filling_modes(request)
        return result

    def open_sell_position(self, tick, sl, tp, comment="", volume=None, risk_pct=None):
        if not tick:
            print("No tick data")
            return None
        entry = tick.bid
        sl_adj, tp_adj = self.calculate_valid_stops(entry, sl, tp, mt5.ORDER_TYPE_SELL)
        if sl_adj is None:
            return None
        vol = self._resolve_volume(volume, entry, sl_adj, tick, risk_pct)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": vol,
            "type": mt5.ORDER_TYPE_SELL,
            "price": entry,
            "sl": sl_adj,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if tp_adj is not None:
            request["tp"] = tp_adj
        print(f"📤 SELL {self.symbol} @ {entry} VOL={vol} SL={sl_adj} TP={tp_adj if tp_adj else 'None'}")
        result = self.try_all_filling_modes(request)
        return result

    def get_positions(self):
        return mt5.positions_get(symbol=self.symbol)

    def modify_sl_tp(self, ticket: int, new_sl=None, new_tp=None):
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": self.symbol,
        }
        if new_sl is not None:
            req["sl"] = new_sl
        if new_tp is not None:
            req["tp"] = new_tp
        res = mt5.order_send(req)
        return res

    def check_symbol_properties(self):
        info = mt5.symbol_info(self.symbol)
        if not info:
            print("Symbol info not found")
            return
        if not info.visible:
            mt5.symbol_select(self.symbol, True)

    def test_filling_modes(self):
        info = mt5.symbol_info(self.symbol)
        if not info:
            print("Symbol info not available")
            return None
        print(f"Filling mode raw: {info.filling_mode}")
        return info.filling_mode

    def check_trading_limits(self):
        return True

    def check_account_trading_permissions(self):
        return True

    def check_market_state(self):
        return True

