"""
ربات معاملاتی طلا (XAUUSD) - آماده اجرا روی حساب دمو
استراتژی: Swing + Fibonacci Retracement + Trailing Stop
"""

import MetaTrader5 as mt5
from datetime import datetime
from fibo_calculate_gold import fibonacci_retracement
import numpy as np
import pandas as pd
from time import sleep
from colorama import init, Fore
from get_legs_gold import get_legs
from mt5_connector_gold import MT5ConnectorGold
from swing_gold import get_swing_points
from utils_gold import BotState
from save_file_gold import log
from metatrader5_config_gold import MT5_CONFIG, TRADING_CONFIG, EXIT_MANAGEMENT_CONFIG
from email_notifier_gold import send_trade_email_async
from analytics.hooks import log_signal, log_trade, log_position_event, log_market

init(autoreset=True)

def has_open_positions():
    """بررسی وجود پوزیشن باز"""
    positions = mt5.positions_get(symbol=MT5_CONFIG['symbol'])
    return positions is not None and len(positions) > 0

def manage_trailing_stop(position, tick, mt5_conn):
    """
    مدیریت Trailing Stop برای پوزیشن باز
    
    Parameters:
    -----------
    position: MT5 position object
    tick: MT5 tick object
    mt5_conn: MT5ConnectorGold instance
    
    Returns:
    --------
    bool: True if SL was updated, False otherwise
    """
    if not EXIT_MANAGEMENT_CONFIG.get('enable', False):
        return False
    
    trailing_config = EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {})
    if not trailing_config.get('enable', False):
        return False
    
    start_r = trailing_config.get('start_r', 1.5)
    gap_r = trailing_config.get('gap_r', 0.5)
    
    # محاسبه ریسک اولیه
    entry = position.price_open
    original_sl = position.sl
    risk = abs(entry - original_sl)
    
    if risk <= 0:
        return False
    
    # محاسبه سود فعلی بر حسب R
    if position.type == mt5.POSITION_TYPE_BUY:
        current_price = tick.bid
        current_profit = current_price - entry
        current_profit_R = current_profit / risk if risk > 0 else 0
        
        # اگر سود به start_r رسید، Trailing Stop را فعال کن
        if current_profit_R >= start_r:
            # محاسبه SL جدید
            new_sl = current_price - (gap_r * risk)
            
            # فقط اگر SL جدید بالاتر از SL فعلی باشد، به‌روزرسانی کن
            if new_sl > position.sl:
                result = mt5_conn.modify_sl_tp(position.ticket, new_sl=new_sl, new_tp=None)
                if result and result.retcode == 10009:  # TRADE_RETCODE_DONE
                    log(f"📈 Trailing Stop updated: Ticket={position.ticket}, Old SL={position.sl:.2f}, New SL={new_sl:.2f}, Profit={current_profit_R:.2f}R", color='green')
                    return True
                else:
                    log(f"❌ Failed to update Trailing Stop: {result.comment if result else 'No result'}", color='red')
    
    elif position.type == mt5.POSITION_TYPE_SELL:
        current_price = tick.ask
        current_profit = entry - current_price
        current_profit_R = current_profit / risk if risk > 0 else 0
        
        # اگر سود به start_r رسید، Trailing Stop را فعال کن
        if current_profit_R >= start_r:
            # محاسبه SL جدید
            new_sl = current_price + (gap_r * risk)
            
            # فقط اگر SL جدید پایین‌تر از SL فعلی باشد، به‌روزرسانی کن
            if new_sl < position.sl:
                result = mt5_conn.modify_sl_tp(position.ticket, new_sl=new_sl, new_tp=None)
                if result and result.retcode == 10009:  # TRADE_RETCODE_DONE
                    log(f"📉 Trailing Stop updated: Ticket={position.ticket}, Old SL={position.sl:.2f}, New SL={new_sl:.2f}, Profit={current_profit_R:.2f}R", color='green')
                    return True
                else:
                    log(f"❌ Failed to update Trailing Stop: {result.comment if result else 'No result'}", color='red')
    
    return False

def get_open_positions():
    """دریافت پوزیشن‌های باز"""
    positions = mt5.positions_get(symbol=MT5_CONFIG['symbol'], magic=MT5_CONFIG['magic_number'])
    return positions if positions else []

def get_positions_summary():
    """دریافت خلاصه‌ای از پوزیشن‌های باز برای ایمیل"""
    positions = get_open_positions()
    if not positions:
        return "No open positions"
    
    summary = []
    for pos in positions:
        pos_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
        summary.append(f"   - Ticket: {pos.ticket} | Type: {pos_type} | Volume: {pos.volume} | Entry: ${pos.price_open:.2f} | Profit: ${pos.profit:.2f}")
    
    return f"{len(positions)} open position(s):\n" + "\n".join(summary)

def main():
    """تابع اصلی ربات"""
    mt5_conn = MT5ConnectorGold()

    if not mt5_conn.initialize():
        log("❌ Failed to connect to MT5", color='red')
        return

    state = BotState()
    state.reset()

    threshold = TRADING_CONFIG['threshold']
    window_size = TRADING_CONFIG['window_size']
    win_ratio = MT5_CONFIG['win_ratio']
    risk_percent = MT5_CONFIG['risk_percent']

    i = 1
    last_swing_type = None
    last_data_time = None
    wait_count = 0
    max_wait_cycles = 100
    trade_count = 0  # شمارنده کل معاملات (برای استفاده از first touch در اولین معامله)
    trades_today = 0  # شمارنده معاملات امروز
    last_trade_date = None  # تاریخ آخرین معامله
    is_first_run = True  # Flag برای تشخیص اولین اجرا
    traded_swings = set()  # مجموعه swing هایی که برای آن‌ها معامله شده (با استفاده از fib 1.0)

    log("🚀 Gold Trading Bot Started...", color='green')
    trailing_config = EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {})
    if trailing_config.get('enable', False):
        log(f"📊 Config: Symbol={MT5_CONFIG['symbol']}, Risk={risk_percent}%, Trailing Stop (Start: {trailing_config.get('start_r', 1.5)}R, Gap: {trailing_config.get('gap_r', 0.5)}R)", color='cyan')
    else:
        log(f"📊 Config: Symbol={MT5_CONFIG['symbol']}, Risk={risk_percent}%, TP={win_ratio}R", color='cyan')
    log(f"⏰ Trading Hours (Iran): {MT5_CONFIG['trading_hours']['start']} - {MT5_CONFIG['trading_hours']['end']}", color='cyan')
    log(f"🇮🇷 Current Iran Time: {mt5_conn.get_iran_time().strftime('%Y-%m-%d %H:%M:%S')}", color='cyan')

    while True:
        try:
            # بررسی ساعات معاملاتی
            can_trade, trade_message = mt5_conn.can_trade()
            
            if not can_trade:
                log(f"⏰ {trade_message}", color='yellow', save_to_file=False)
                sleep(60)
                continue
            
            # بررسی تعداد معاملات روزانه
            current_date = mt5_conn.get_iran_time().date()
            if last_trade_date != current_date:
                trades_today = 0
                last_trade_date = current_date
            
            if trades_today >= MT5_CONFIG['max_daily_trades']:
                log(f"⚠️ Max daily trades reached ({MT5_CONFIG['max_daily_trades']})", color='yellow', save_to_file=False)
                sleep(300)  # 5 دقیقه صبر
                continue

            # دریافت داده از MT5
            cache_data = mt5_conn.get_historical_data(timeframe=mt5.TIMEFRAME_M15, count=window_size * 2)
            
            if cache_data is None:
                log("❌ Failed to get data from MT5", color='red')
                sleep(5)
                continue
            
            # ثبت داده‌های بازار (ticks)
            try:
                tick = mt5.symbol_info_tick(MT5_CONFIG['symbol'])
                if tick:
                    symbol_info = mt5.symbol_info(MT5_CONFIG['symbol'])
                    if symbol_info:
                        log_market(
                            symbol=MT5_CONFIG['symbol'],
                            bid=tick.bid,
                            ask=tick.ask,
                            last=tick.last,
                            point=symbol_info.point,
                            digits=symbol_info.digits,
                            source="mt5",
                            session="bot"
                        )
            except Exception as e:
                pass  # خطا در ثبت بازار را نادیده بگیر
            
            cache_data['status'] = np.where(cache_data['open'] > cache_data['close'], 'bearish', 'bullish')
            cache_data['timestamp'] = cache_data.index
            
            # بررسی تغییر داده
            current_time = cache_data.index[-1]
            process_data = False
            
            if last_data_time is None:
                log(f"🔄 First run - processing data from {current_time}", color='cyan')
                log(f"⏳ Waiting for new touch signals before entering trades...", color='yellow')
                last_data_time = current_time
                process_data = True
                is_first_run = True
            elif current_time != last_data_time:
                log(f"📊 New data received: {current_time}", color='cyan')
                last_data_time = current_time
                process_data = True
                if is_first_run:
                    is_first_run = False
                    log(f"✅ First run completed - now ready to enter trades", color='green')
            else:
                wait_count += 1
                if wait_count % 12 == 0:  # هر 60 ثانیه یک بار (12 * 5)
                    log(f"⏳ Waiting for new data... Current: {current_time} (wait cycles: {wait_count})", color='yellow', save_to_file=False)
                sleep(5)
                continue
            
            if process_data:
                log(f'📊 Processing {len(cache_data)} data points | Window: {window_size}', color='cyan')
                log(f'Current time: {cache_data.index[-1]}', color='yellow')
                
                # بررسی پوزیشن‌های باز و مدیریت Trailing Stop
                open_positions = get_open_positions()
                if open_positions:
                    log(f"📌 {len(open_positions)} open position(s) detected", color='yellow')
                    tick = mt5.symbol_info_tick(MT5_CONFIG['symbol'])
                    if tick:
                        for pos in open_positions:
                            tp_display = f"{pos.tp:.2f}" if pos.tp > 0 else "Trailing Stop"
                            log(f"   Ticket: {pos.ticket}, Type: {'BUY' if pos.type == 0 else 'SELL'}, "
                                f"Entry: {pos.price_open:.2f}, SL: {pos.sl:.2f}, TP: {tp_display}, "
                                f"Profit: {pos.profit:.2f}", color='yellow')
                            # مدیریت Trailing Stop
                            manage_trailing_stop(pos, tick, mt5_conn)
                else:
                    log(f"📌 No open positions", color='cyan')
                
                # محاسبه legs
                legs = get_legs(cache_data, threshold)
                log(f'📊 Legs identified: {len(legs)}', color='cyan')
                
                # استفاده از 2 یا 3 leg (Optimized)
                if len(legs) >= 2:
                    if len(legs) >= 3:
                        legs = legs[-3:]
                    else:
                        legs = legs[-2:]
                    
                    min_candles = TRADING_CONFIG.get('min_swing_size', 2)
                    swing_type, is_swing = get_swing_points(data=cache_data, legs=legs, min_candles=min_candles)
                    log(f'📊 Swing analysis: type={swing_type}, is_swing={is_swing}', color='cyan')

                    # Phase 1: ایجاد Fibonacci (Optimized)
                    # فقط اگر Fibonacci وجود نداشته باشد یا Swing جدید شناسایی شده باشد، Fibonacci ایجاد می‌شود
                    if is_swing:
                        # بررسی اینکه آیا باید Fibonacci جدید ایجاد شود
                        should_create_fib = False
                        
                        if swing_type == 'bullish':
                            # شرایط آسان‌تر: فقط بررسی کنیم که قیمت بالاتر از نقطه pullback باشد
                            if len(legs) >= 3:
                                check_price = legs[1]['start_value']
                            else:
                                check_price = legs[0]['start_value']
                            
                            # فقط اگر Fibonacci وجود نداشته باشد یا Swing جدید باشد، ایجاد کن
                            if not state.fib_levels or last_swing_type != swing_type:
                                if cache_data.iloc[-2]['close'] > check_price * 0.99:  # 1% tolerance
                                    should_create_fib = True
                            # اگر Fibonacci وجود دارد و Swing همان است، بررسی کن که آیا باید به‌روزرسانی شود
                            elif state.fib_levels and last_swing_type == swing_type:
                                # اگر Swing جدیدی شناسایی شده (legs تغییر کرده)، Fibonacci جدید ایجاد کن
                                if len(legs) >= 3:
                                    new_fib1_time = legs[2]['end']
                                else:
                                    new_fib1_time = legs[1]['end']
                                # اگر زمان fib1 تغییر کرده، Fibonacci جدید ایجاد کن
                                if state.fib1_time != new_fib1_time:
                                    if cache_data.iloc[-2]['close'] > check_price * 0.99:
                                        should_create_fib = True

                        elif swing_type == 'bearish':
                            if len(legs) >= 3:
                                check_price = legs[1]['start_value']
                            else:
                                check_price = legs[0]['start_value']
                            
                            # فقط اگر Fibonacci وجود نداشته باشد یا Swing جدید باشد، ایجاد کن
                            if not state.fib_levels or last_swing_type != swing_type:
                                if cache_data.iloc[-2]['close'] < check_price * 1.01:  # 1% tolerance
                                    should_create_fib = True
                            # اگر Fibonacci وجود دارد و Swing همان است، بررسی کن که آیا باید به‌روزرسانی شود
                            elif state.fib_levels and last_swing_type == swing_type:
                                # اگر Swing جدیدی شناسایی شده (legs تغییر کرده)، Fibonacci جدید ایجاد کن
                                if len(legs) >= 3:
                                    new_fib1_time = legs[2]['end']
                                else:
                                    new_fib1_time = legs[1]['end']
                                # اگر زمان fib1 تغییر کرده، Fibonacci جدید ایجاد کن
                                if state.fib1_time != new_fib1_time:
                                    if cache_data.iloc[-2]['close'] < check_price * 1.01:
                                        should_create_fib = True
                        
                        # ایجاد Fibonacci جدید
                        if should_create_fib:
                            state.reset()
                            if swing_type == 'bullish':
                                if len(legs) >= 3:
                                    state.fib_levels = fibonacci_retracement(
                                        start_price=legs[2]['end_value'],
                                        end_price=legs[2]['start_value']
                                    )
                                    state.fib0_time = legs[2]['start']
                                    state.fib1_time = legs[2]['end']
                                else:
                                    state.fib_levels = fibonacci_retracement(
                                        start_price=legs[1]['end_value'],
                                        end_price=legs[0]['start_value']
                                    )
                                    state.fib0_time = legs[0]['start']
                                    state.fib1_time = legs[1]['end']
                                last_swing_type = swing_type
                                log(f"📈 New bullish fibonacci created: fib1:{state.fib_levels['1.0']:.2f} "
                                    f"fib0.705:{state.fib_levels['0.705']:.2f} fib0:{state.fib_levels['0.0']:.2f}", 
                                    color='green')
                            elif swing_type == 'bearish':
                                if len(legs) >= 3:
                                    state.fib_levels = fibonacci_retracement(
                                        start_price=legs[2]['end_value'],
                                        end_price=legs[2]['start_value']
                                    )
                                    state.fib0_time = legs[2]['start']
                                    state.fib1_time = legs[2]['end']
                                else:
                                    state.fib_levels = fibonacci_retracement(
                                        start_price=legs[1]['end_value'],
                                        end_price=legs[0]['start_value']
                                    )
                                    state.fib0_time = legs[0]['start']
                                    state.fib1_time = legs[1]['end']
                                last_swing_type = swing_type
                                log(f"📉 New bearish fibonacci created: fib1:{state.fib_levels['1.0']:.2f} "
                                    f"fib0.705:{state.fib_levels['0.705']:.2f} fib0:{state.fib_levels['0.0']:.2f}", 
                                    color='green')

                else:
                    log(f'⚠️ Not enough legs ({len(legs)}) - need at least 2 for swing analysis', color='yellow')
                
                # Phase 2: به‌روزرسانی Fibonacci
                if state.fib_levels:
                    log(f'📊 Fibonacci levels active: fib0={state.fib_levels.get("0.0", "N/A"):.2f}, fib705={state.fib_levels.get("0.705", "N/A"):.2f}, fib1={state.fib_levels.get("1.0", "N/A"):.2f}', color='cyan')
                    if len(legs) > 2:
                        if last_swing_type == 'bullish':
                            if cache_data.iloc[-2]['high'] > state.fib_levels['0.0']:
                                state.fib_levels = fibonacci_retracement(
                                    start_price=cache_data.iloc[-2]['high'],
                                    end_price=state.fib_levels['1.0']
                                )
                                state.fib0_time = cache_data.iloc[-2]['timestamp']
                                state.first_touch = False
                                state.first_touch_value = None
                                log(f"📈 Updated fibonacci: fib0:{state.fib_levels['0.0']:.2f} "
                                    f"fib1:{state.fib_levels['1.0']:.2f}", color='green')
                            elif cache_data.iloc[-2]['low'] < state.fib_levels['1.0']:
                                state.reset()
                                last_swing_type = None
                                log(f"📈 Price dropped below fib1 - reset", color='red')
                            # شرایط touch آسان‌تر (Optimized): tolerance 1%
                            elif cache_data.iloc[-2]['low'] <= state.fib_levels['0.705'] * 1.01:
                                current_candle_time = cache_data.iloc[-2]['timestamp']
                                # بررسی اینکه آیا این کندل قبلاً پردازش شده است یا نه
                                if not state.first_touch:
                                    state.first_touch_value = cache_data.iloc[-2]
                                    state.first_touch = True
                                    log(f"📈 First touch on fib0.705", color='yellow')
                                elif state.first_touch and not state.second_touch:
                                    # بررسی اینکه آیا این کندل جدید است (نه همان کندل First Touch)
                                    if state.first_touch_value['timestamp'] != current_candle_time:
                                        # دومین touch: فقط بررسی کنیم که قیمت دوباره به سطح نزدیک شده
                                        if abs(cache_data.iloc[-2]['low'] - state.fib_levels['0.705']) < abs(state.first_touch_value['low'] - state.fib_levels['0.705']) * 1.5:
                                            state.second_touch_value = cache_data.iloc[-2]
                                            state.second_touch = True
                                            log(f"📈 Second touch detected - signal ready!", color='green')

                        elif last_swing_type == 'bearish':
                            if cache_data.iloc[-2]['low'] < state.fib_levels['0.0']:
                                state.fib_levels = fibonacci_retracement(
                                    start_price=cache_data.iloc[-2]['low'],
                                    end_price=state.fib_levels['1.0']
                                )
                                state.fib0_time = cache_data.iloc[-2]['timestamp']
                                state.first_touch = False
                                state.first_touch_value = None
                                log(f"📉 Updated fibonacci: fib0:{state.fib_levels['0.0']:.2f} "
                                    f"fib1:{state.fib_levels['1.0']:.2f}", color='green')
                            elif cache_data.iloc[-2]['high'] > state.fib_levels['1.0']:
                                state.reset()
                                last_swing_type = None
                                log(f"📉 Price rose above fib1 - reset", color='red')
                            # شرایط touch آسان‌تر (Optimized): tolerance 1%
                            elif cache_data.iloc[-2]['high'] >= state.fib_levels['0.705'] * 0.99:
                                current_candle_time = cache_data.iloc[-2]['timestamp']
                                # بررسی اینکه آیا این کندل قبلاً پردازش شده است یا نه
                                if not state.first_touch:
                                    state.first_touch_value = cache_data.iloc[-2]
                                    state.first_touch = True
                                    log(f"📉 First touch on fib0.705", color='yellow')
                                elif state.first_touch and not state.second_touch:
                                    # بررسی اینکه آیا این کندل جدید است (نه همان کندل First Touch)
                                    if state.first_touch_value['timestamp'] != current_candle_time:
                                        # دومین touch: فقط بررسی کنیم که قیمت دوباره به سطح نزدیک شده
                                        if abs(cache_data.iloc[-2]['high'] - state.fib_levels['0.705']) < abs(state.first_touch_value['high'] - state.fib_levels['0.705']) * 1.5:
                                            state.second_touch_value = cache_data.iloc[-2]
                                            state.second_touch = True
                                            log(f"📉 Second touch detected - signal ready!", color='green')
                else:
                    if len(legs) <= 2:
                        log(f'📊 No fibonacci levels active - waiting for swing formation', color='yellow')
                
                # Phase 3: بررسی سیگنال و باز کردن پوزیشن (Optimized)
                # امکان ورود با first touch در اولین معامله (اما نه در اولین اجرای ربات)
                use_first_touch = TRADING_CONFIG.get('use_first_touch', True)
                # در اولین اجرا، از باز کردن پوزیشن جلوگیری می‌کنیم (حتی اگر second_touch وجود داشته باشد)
                # باید منتظر اولین کندل جدید بمانیم تا از داده‌های تاریخی استفاده نکنیم
                if is_first_run:
                    can_enter = False  # در اولین اجرا، هیچ پوزیشنی باز نمی‌کنیم
                    if state.second_touch:
                        log(f"⏸️ First run: Second touch detected in historical data, but waiting for new candle before entering", color='yellow')
                    elif state.first_touch:
                        log(f"⏸️ First run: First touch detected in historical data, waiting for second touch", color='yellow')
                else:
                    can_enter = state.second_touch or (use_first_touch and state.first_touch and trade_count == 0)
                
                if state.fib_levels and last_swing_type:
                    if last_swing_type == 'bullish' and can_enter:
                        # بررسی اینکه آیا برای این swing قبلاً معامله شده یا نه
                        swing_key = (last_swing_type, round(state.fib_levels['1.0'], 2))
                        if swing_key in traded_swings:
                            log(f"🚫 Skip BUY signal: Already traded this swing (fib 1.0: {state.fib_levels['1.0']:.2f})", color='yellow')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        # با توجه به تایم‌فریم M15، اجازه باز کردن چند پوزیشن همزمان داده می‌شود
                        # اگر می‌خواهید فقط یک پوزیشن باز باشد، prevent_multiple_positions را True کنید
                        if TRADING_CONFIG.get('prevent_multiple_positions', False) and has_open_positions():
                            log(f"🚫 Skip BUY signal: Position already open", color='yellow')
                            # ارسال ایمیل اطلاع‌رسانی skip شدن سیگنال BUY
                            try:
                                positions_summary = get_positions_summary()
                                send_trade_email_async(
                                    subject=f"SIGNAL SKIPPED - BUY {MT5_CONFIG['symbol']}",
                                    body=(
                                        f"🚫 TRADING SIGNAL SKIPPED 🚫\n\n"
                                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                        f"Symbol: {MT5_CONFIG['symbol']}\n"
                                        f"Signal Type: BUY (Bullish Swing)\n"
                                        f"Action: SKIPPED\n"
                                        f"Reason: Position(s) already open\n\n"
                                        f"📈 Fibonacci Levels:\n"
                                        f"   fib 0.0 (resistance): {state.fib_levels.get('0.0', 'N/A'):.2f}\n"
                                        f"   fib 0.705 (entry zone): {state.fib_levels.get('0.705', 'N/A'):.2f}\n"
                                        f"   fib 1.0 (support/SL): {state.fib_levels.get('1.0', 'N/A'):.2f}\n\n"
                                        f"🔒 Current Open Positions:\n{positions_summary}\n"
                                    )
                                )
                                log(f"📧 Skip signal email sent for BUY signal", color='cyan')
                            except Exception as e:
                                log(f'Skip signal email failed: {e}', color='red')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        tick = mt5.symbol_info_tick(MT5_CONFIG['symbol'])
                        if not tick:
                            log("❌ No tick data", color='red')
                            continue
                        
                        entry_price = tick.ask
                        candidate_sl = state.fib_levels['1.0']
                        
                        if candidate_sl >= entry_price:
                            log("❌ Invalid SL for BUY", color='red')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        min_dist = 0.5
                        if (entry_price - candidate_sl) < min_dist:
                            adj = entry_price - min_dist
                            if adj <= 0:
                                state.reset()
                                last_swing_type = None
                                continue
                            candidate_sl = adj
                        
                        sl = candidate_sl
                        risk = abs(entry_price - sl)
                        # بدون TP ثابت - فقط Trailing Stop
                        tp = None
                        
                        log(f"📈 BUY Signal: Entry={entry_price:.2f}, SL={sl:.2f}, TP=None (Trailing Stop)", color='green')
                        
                        # ثبت سیگنال در CSV
                        try:
                            log_signal(
                                symbol=MT5_CONFIG['symbol'],
                                strategy="swing_fib_gold",
                                direction="buy",
                                rr=win_ratio,
                                entry=entry_price,
                                sl=sl,
                                tp=tp,
                                fib=state.fib_levels,
                                confidence=None,
                                features_json=None,
                                note="triggered_by_pullback"
                            )
                        except Exception as e:
                            log(f'Signal logging failed: {e}', color='red')
                        
                        # ارسال ایمیل قبل از باز کردن پوزیشن
                        try:
                            tp_str = f"${tp:.2f}" if tp is not None else "Trailing Stop"
                            send_trade_email_async(
                                subject=f"NEW BUY ORDER {MT5_CONFIG['symbol']}",
                                body=(
                                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                    f"Symbol: {MT5_CONFIG['symbol']}\n"
                                    f"Type: BUY (Bullish Swing)\n"
                                    f"Entry: ${entry_price:.2f}\n"
                                    f"SL: ${sl:.2f}\n"
                                    f"TP: {tp_str}\n"
                                    f"Risk: ${risk:.2f} ({risk_percent}%)\n"
                                    f"Exit Strategy: Trailing Stop (Start: {EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {}).get('start_r', 1.5)}R, Gap: {EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {}).get('gap_r', 0.5)}R)\n"
                                )
                            )
                        except Exception as e:
                            log(f'Email dispatch failed: {e}', color='red')
                        
                        result = mt5_conn.open_buy_position(
                            tick=tick,
                            sl=sl,
                            tp=tp,
                            comment=f"Gold Swing Fib {win_ratio}R",
                            risk_pct=risk_percent / 100.0
                        )
                        
                        # ثبت معامله در CSV
                        try:
                            request_dict = {
                                "price": entry_price,
                                "volume": result.volume if result else None,
                                "deviation": MT5_CONFIG['deviation'],
                                "type_filling": None,
                                "sl": sl,
                                "tp": tp,
                                "magic": MT5_CONFIG['magic_number']
                            }
                            log_trade(
                                symbol=MT5_CONFIG['symbol'],
                                side="buy",
                                request=request_dict,
                                result=result,
                                reason="swing_fib_signal"
                            )
                        except Exception as e:
                            log(f'Trade logging failed: {e}', color='red')
                        
                        if result and result.retcode == 10009:  # TRADE_RETCODE_DONE
                            log(f"✅ BUY Position opened: Ticket={result.order}", color='green')
                            # ثبت این swing به عنوان معامله شده
                            swing_key = (last_swing_type, round(state.fib_levels['1.0'], 2))
                            traded_swings.add(swing_key)
                            trade_count += 1
                            trades_today += 1
                            
                            # ثبت رویداد باز شدن پوزیشن
                            try:
                                log_position_event(
                                    symbol=MT5_CONFIG['symbol'],
                                    ticket=result.order,
                                    event='open',
                                    direction='buy',
                                    entry=entry_price,
                                    current_price=entry_price,
                                    sl=sl,
                                    tp=tp,
                                    profit_R=0.0,
                                    stage=0,
                                    risk_abs=risk,
                                    locked_R=None,
                                    volume=result.volume if result else None,
                                    note='position opened'
                                )
                            except Exception as e:
                                log(f'Position event logging failed: {e}', color='red')
                            
                            # ارسال ایمیل نتیجه معامله
                            try:
                                tp_str = f"${tp:.2f}" if tp is not None else "Trailing Stop"
                                send_trade_email_async(
                                    subject=f"BUY ORDER EXECUTED {MT5_CONFIG['symbol']}",
                                    body=(
                                        f"✅ ORDER EXECUTED SUCCESSFULLY\n\n"
                                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                        f"Symbol: {MT5_CONFIG['symbol']}\n"
                                        f"Type: BUY\n"
                                        f"Ticket: {result.order}\n"
                                        f"Price: ${result.price:.2f}\n"
                                        f"Volume: {result.volume}\n"
                                        f"Entry: ${entry_price:.2f}\n"
                                        f"SL: ${sl:.2f}\n"
                                        f"TP: {tp_str}\n"
                                        f"Exit Strategy: Trailing Stop\n"
                                    )
                                )
                            except Exception as e:
                                log(f'Email dispatch failed: {e}', color='red')
                        else:
                            log(f"❌ Failed to open BUY: {result.comment if result else 'No result'}", color='red')
                        
                        # ریست کامل state و متغیرهای مرتبط بعد از باز شدن پوزیشن
                        state.reset()
                        last_swing_type = None
                        log(f"🧹 State reset after BUY position opened", color='magenta')

                    elif last_swing_type == 'bearish' and can_enter:
                        # بررسی اینکه آیا برای این swing قبلاً معامله شده یا نه
                        swing_key = (last_swing_type, round(state.fib_levels['1.0'], 2))
                        if swing_key in traded_swings:
                            log(f"🚫 Skip SELL signal: Already traded this swing (fib 1.0: {state.fib_levels['1.0']:.2f})", color='yellow')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        # با توجه به تایم‌فریم M15، اجازه باز کردن چند پوزیشن همزمان داده می‌شود
                        # اگر می‌خواهید فقط یک پوزیشن باز باشد، prevent_multiple_positions را True کنید
                        if TRADING_CONFIG.get('prevent_multiple_positions', False) and has_open_positions():
                            log(f"🚫 Skip SELL signal: Position already open", color='yellow')
                            # ارسال ایمیل اطلاع‌رسانی skip شدن سیگنال SELL
                            try:
                                positions_summary = get_positions_summary()
                                send_trade_email_async(
                                    subject=f"SIGNAL SKIPPED - SELL {MT5_CONFIG['symbol']}",
                                    body=(
                                        f"🚫 TRADING SIGNAL SKIPPED 🚫\n\n"
                                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                        f"Symbol: {MT5_CONFIG['symbol']}\n"
                                        f"Signal Type: SELL (Bearish Swing)\n"
                                        f"Action: SKIPPED\n"
                                        f"Reason: Position(s) already open\n\n"
                                        f"📉 Fibonacci Levels:\n"
                                        f"   fib 0.0 (support): {state.fib_levels.get('0.0', 'N/A'):.2f}\n"
                                        f"   fib 0.705 (entry zone): {state.fib_levels.get('0.705', 'N/A'):.2f}\n"
                                        f"   fib 1.0 (resistance/SL): {state.fib_levels.get('1.0', 'N/A'):.2f}\n\n"
                                        f"🔒 Current Open Positions:\n{positions_summary}\n"
                                    )
                                )
                                log(f"📧 Skip signal email sent for SELL signal", color='cyan')
                            except Exception as e:
                                log(f'Skip signal email failed: {e}', color='red')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        tick = mt5.symbol_info_tick(MT5_CONFIG['symbol'])
                        if not tick:
                            log("❌ No tick data", color='red')
                            continue
                        
                        entry_price = tick.bid
                        candidate_sl = state.fib_levels['1.0']
                        
                        if candidate_sl <= entry_price:
                            log("❌ Invalid SL for SELL", color='red')
                            state.reset()
                            last_swing_type = None
                            continue
                        
                        min_dist = 0.5
                        if (candidate_sl - entry_price) < min_dist:
                            adj = entry_price + min_dist
                            candidate_sl = adj
                        
                        sl = candidate_sl
                        risk = abs(entry_price - sl)
                        # بدون TP ثابت - فقط Trailing Stop
                        tp = None
                        
                        log(f"📉 SELL Signal: Entry={entry_price:.2f}, SL={sl:.2f}, TP=None (Trailing Stop)", color='green')
                        
                        # ثبت سیگنال در CSV
                        try:
                            log_signal(
                                symbol=MT5_CONFIG['symbol'],
                                strategy="swing_fib_gold",
                                direction="sell",
                                rr=win_ratio,
                                entry=entry_price,
                                sl=sl,
                                tp=tp,
                                fib=state.fib_levels,
                                confidence=None,
                                features_json=None,
                                note="triggered_by_pullback"
                            )
                        except Exception as e:
                            log(f'Signal logging failed: {e}', color='red')
                        
                        # ارسال ایمیل قبل از باز کردن پوزیشن
                        try:
                            tp_str = f"${tp:.2f}" if tp is not None else "Trailing Stop"
                            send_trade_email_async(
                                subject=f"NEW SELL ORDER {MT5_CONFIG['symbol']}",
                                body=(
                                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                    f"Symbol: {MT5_CONFIG['symbol']}\n"
                                    f"Type: SELL (Bearish Swing)\n"
                                    f"Entry: ${entry_price:.2f}\n"
                                    f"SL: ${sl:.2f}\n"
                                    f"TP: {tp_str}\n"
                                    f"Risk: ${risk:.2f} ({risk_percent}%)\n"
                                    f"Exit Strategy: Trailing Stop (Start: {EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {}).get('start_r', 1.5)}R, Gap: {EXIT_MANAGEMENT_CONFIG.get('trailing_stop', {}).get('gap_r', 0.5)}R)\n"
                                )
                            )
                        except Exception as e:
                            log(f'Email dispatch failed: {e}', color='red')
                        
                        result = mt5_conn.open_sell_position(
                            tick=tick,
                            sl=sl,
                            tp=tp,
                            comment=f"Gold Swing Fib {win_ratio}R",
                            risk_pct=risk_percent / 100.0
                        )
                        
                        # ثبت معامله در CSV
                        try:
                            request_dict = {
                                "price": entry_price,
                                "volume": result.volume if result else None,
                                "deviation": MT5_CONFIG['deviation'],
                                "type_filling": None,
                                "sl": sl,
                                "tp": tp,
                                "magic": MT5_CONFIG['magic_number']
                            }
                            log_trade(
                                symbol=MT5_CONFIG['symbol'],
                                side="sell",
                                request=request_dict,
                                result=result,
                                reason="swing_fib_signal"
                            )
                        except Exception as e:
                            log(f'Trade logging failed: {e}', color='red')
                        
                        if result and result.retcode == 10009:  # TRADE_RETCODE_DONE
                            log(f"✅ SELL Position opened: Ticket={result.order}", color='green')
                            # ثبت این swing به عنوان معامله شده
                            swing_key = (last_swing_type, round(state.fib_levels['1.0'], 2))
                            traded_swings.add(swing_key)
                            trade_count += 1
                            trades_today += 1
                            
                            # ثبت رویداد باز شدن پوزیشن
                            try:
                                log_position_event(
                                    symbol=MT5_CONFIG['symbol'],
                                    ticket=result.order,
                                    event='open',
                                    direction='sell',
                                    entry=entry_price,
                                    current_price=entry_price,
                                    sl=sl,
                                    tp=tp,
                                    profit_R=0.0,
                                    stage=0,
                                    risk_abs=risk,
                                    locked_R=None,
                                    volume=result.volume if result else None,
                                    note='position opened'
                                )
                            except Exception as e:
                                log(f'Position event logging failed: {e}', color='red')
                            
                            # ارسال ایمیل نتیجه معامله
                            try:
                                tp_str = f"${tp:.2f}" if tp is not None else "Trailing Stop"
                                send_trade_email_async(
                                    subject=f"SELL ORDER EXECUTED {MT5_CONFIG['symbol']}",
                                    body=(
                                        f"✅ ORDER EXECUTED SUCCESSFULLY\n\n"
                                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                        f"Symbol: {MT5_CONFIG['symbol']}\n"
                                        f"Type: SELL\n"
                                        f"Ticket: {result.order}\n"
                                        f"Price: ${result.price:.2f}\n"
                                        f"Volume: {result.volume}\n"
                                        f"Entry: ${entry_price:.2f}\n"
                                        f"SL: ${sl:.2f}\n"
                                        f"TP: {tp_str}\n"
                                        f"Exit Strategy: Trailing Stop\n"
                                    )
                                )
                            except Exception as e:
                                log(f'Email dispatch failed: {e}', color='red')
                        else:
                            log(f"❌ Failed to open SELL: {result.comment if result else 'No result'}", color='red')
                        
                        # ریست کامل state و متغیرهای مرتبط بعد از باز شدن پوزیشن
                        state.reset()
                        last_swing_type = None
                        log(f"🧹 State reset after SELL position opened", color='magenta')
                
                # لاگ خلاصه وضعیت
                log(f'📊 Status: Legs={len(legs)}, FibActive={state.fib_levels is not None}, '
                    f'FirstTouch={state.first_touch}, SecondTouch={state.second_touch}, '
                    f'SwingType={last_swing_type}', color='cyan')
                log(f'{"="*80}', color='cyan')

            sleep(5)

        except KeyboardInterrupt:
            log("🛑 Bot stopped by user", color='yellow')
            break
        except Exception as e:
            log(f"❌ Error: {e}", color='red')
            sleep(10)

    mt5_conn.shutdown()

if __name__ == "__main__":
    main()

