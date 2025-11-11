def fibonacci_retracement(start_price, end_price, fib_705=0.705):
    """
    محاسبه سطوح Fibonacci Retracement
    
    Parameters:
    -----------
    start_price: float
        قیمت شروع
    end_price: float
        قیمت پایان
    fib_705: float
        سطح Fibonacci برای ورود (پیش‌فرض 0.705)
    """
    fib_levels = {
        '0.0': start_price,
        str(fib_705): start_price + fib_705 * (end_price - start_price),
        '0.705': start_price + 0.705 * (end_price - start_price),  # برای سازگاری
        '0.9': start_price + 0.9 * (end_price - start_price),
        '1.0': end_price
    }
    return fib_levels

