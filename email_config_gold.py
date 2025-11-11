"""
تنظیمات ایمیل برای ربات طلا
می‌توانید از متغیرهای محیطی یا مقادیر مستقیم استفاده کنید
"""

import os

# استفاده از متغیرهای محیطی (پیشنهادی برای امنیت)
EMAIL_HOST_USER_NAME = os.getenv('EMAIL_HOST_USER_NAME', 'your_email@gmail.com')
EMAIL_HOST_PASSWORD_KEY = os.getenv('EMAIL_HOST_PASSWORD_KEY', 'your_app_password')
EMAIL_RECIPIENT_USER_NAME = os.getenv('EMAIL_RECIPIENT_USER_NAME', 'recipient@gmail.com')

# اگر می‌خواهید مستقیماً مقادیر را وارد کنید (کمتر امن):
# EMAIL_HOST_USER_NAME = 'your_email@gmail.com'
# EMAIL_HOST_PASSWORD_KEY = 'your_app_password'  # App Password از Gmail
# EMAIL_RECIPIENT_USER_NAME = 'recipient@gmail.com'

"""
نکات مهم:
1. برای Gmail باید App Password استفاده کنید (نه رمز اصلی)
2. برای فعال‌سازی App Password:
   - به Google Account > Security > 2-Step Verification بروید
   - App Passwords را فعال کنید
   - یک App Password برای "Mail" ایجاد کنید
3. می‌توانید چند گیرنده را با کاما جدا کنید: 'email1@gmail.com, email2@gmail.com'
"""

