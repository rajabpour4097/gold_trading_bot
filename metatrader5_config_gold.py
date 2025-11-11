# ساعات مختلف بازار فارکس بر اساس ساعت ایران

# جلسه سیدنی (05:30 - 14:30 ایران)
SYDNEY_HOURS_IRAN = {
    'start': '05:30',
    'end': '14:30'
}

# جلسه توکیو (07:30 - 16:30 ایران)  
TOKYO_HOURS_IRAN = {
    'start': '07:30',
    'end': '16:30'
}

# جلسه لندن (12:30 - 21:30 ایران)
LONDON_HOURS_IRAN = {
    'start': '12:30',
    'end': '21:30'
}

# جلسه نیویورک (17:30 - 02:30 ایران)
NEWYORK_HOURS_IRAN = {
    'start': '17:30',
    'end': '02:30'  # روز بعد
}

# همپوشانی لندن-نیویورک (17:30 - 21:30 ایران) - بهترین زمان
OVERLAP_LONDON_NY_IRAN = {
    'start': '17:30',
    'end': '21:30'
}

# ساعات فعال ایرانی (09:00 - 21:00)
IRAN_ACTIVE_HOURS = {
    'start': '09:00',
    'end': '21:00'
}

# 24 ساعته
FULL_TIME_IRAN = {
    'start': '00:00',
    'end': '23:59'
}

MY_CUSTOM_TIME_IRAN = {
    'start': '01:00',
    'end': '23:59'
}

# تنظیمات MT5 برای طلا (XAUUSD)
MT5_CONFIG = {
    'symbol': 'XAUUSD',  # طلا
    'timeframe': 'M15',  # تایم‌فریم 15 دقیقه (M15)
    'lot_size': 0.01,  # خودکار محاسبه می‌شود بر اساس ریسک 1%
    'risk_percent': 1.0,  # ریسک 1 درصد در هر معامله
    'win_ratio': 2,
    'magic_number': 234001,  # متفاوت از EURUSD
    'deviation': 20,
    'max_spread': 30.0,  # برای طلا اسپرد بیشتر است (معمولاً 20-30 دلار)
    'min_balance': 1,
    'max_daily_trades': 5,  # کاهش از 10 به 5 (Optimized)
    'trading_hours': MY_CUSTOM_TIME_IRAN,
}

# تنظیمات استراتژی Optimized برای طلا
# بر اساس نتایج بک‌تست: 57.93% بازده در 10 ماه
TRADING_CONFIG = {
    'threshold': 12,  # کاهش از 20 به 12 (Optimized)
    'fib_705': 0.705,
    'fib_90': 0.9,
    'window_size': 60,  # کاهش از 100 به 60 (Optimized)
    'min_swing_size': 2,  # کاهش از 4 به 2 (Optimized - نیاز به 2 کندل)
    'min_dist': 0.5,  # حداقل فاصله SL از Entry
    'entry_tolerance': 0.01,  # tolerance 1% برای touch
    'lookback_period': 20,
    'prevent_multiple_positions': True,  # جلوگیری از چند پوزیشن همزمان (Optimized)
    'position_check_mode': 'all',
    'use_first_touch': True,  # امکان ورود با first touch در اولین معامله (Optimized)
}

# مدیریت خروج با Trailing Stop - تنظیم شده برای طلا
EXIT_MANAGEMENT_CONFIG = {
    'enable': True,
    'trailing_stop': {
        'enable': True,
        'start_r': 1.5,      # شروع Trailing در 1.5R
        'gap_r': 0.5,        # فاصله 0.5R از قیمت فعلی
    },
    'scale_out': {
        'enable': False,
    },
    'break_even': {
        'enable': False,
    },
    'take_profit': {
        'enable': False,     # TP ثابت غیرفعال (فقط Trailing Stop)
    }
}

# مدیریت پویا چند مرحله‌ای - DISABLED
DYNAMIC_RISK_CONFIG = {
    'enable': False,
    'commission_per_lot': 4.5,
    'commission_mode': 'per_lot',
    'round_trip': False,
    'base_tp_R': 2.0,
    'stages': []
}

# تنظیمات لاگ
LOG_CONFIG = {
    'log_level': 'INFO',
    'save_to_file': True,
    'max_log_size': 10,
}

