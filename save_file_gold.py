from datetime import datetime
from colorama import init, Fore
from pathlib import Path

# راه‌اندازی colorama
init(autoreset=True)

# مسیر پوشه لاگ
LOG_DIR = Path(__file__).resolve().parent / "trading-analytics-logger" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(msg, level='info', color=None, save_to_file=True):
    color_prefix = getattr(Fore, color.upper(), '') if color else ''
    print(f"{color_prefix}{msg}")

    if save_to_file:
        # ذخیره در فایل TXT روزانه
        log_filename = LOG_DIR / f"gold_swing_logs_{datetime.now().strftime('%Y-%m-%d')}.txt"
        try:
            with open(log_filename, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {msg}\n")
        except Exception as e:
            print(f"خطا در ذخیره لاگ: {e}")


