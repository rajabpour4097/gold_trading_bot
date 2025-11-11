from colorama import Fore


def get_swing_points(data, legs, min_candles=2):
    """
    نسخه Optimized: نیاز به 2 کندل به جای 3
    حتی با 2 leg هم کار می‌کند
    """
    if len(legs) >= 2:  # حتی با 2 leg هم کار می‌کند
        s_index = 0
        swing_type = ''
        is_swing = False
        
        # اگر 3 leg داریم، از منطق قبلی استفاده کن
        if len(legs) == 3:
            ### Up swing ###
            if legs[1]['end_value'] > legs[0]['start_value'] and legs[0]['end_value'] > legs[1]['end_value']:
                ### Check true swing ###
                s_index = data.index.tolist().index(legs[1]['start'])
                e_index = data.index.tolist().index(legs[1]['end'])
                true_candles = 0
                first_candle = False
                last_candle_close = None

                for k in range(s_index, e_index+1):
                    if data.iloc[k]['status'] == 'bearish':
                        if first_candle:
                            if last_candle_close is not None and data.iloc[k]['close'] < last_candle_close:
                                true_candles += 1
                        last_candle_close = data.iloc[k]['close']
                        first_candle = True
                
                if true_candles >= min_candles:  # 2 به جای 3
                    swing_type = 'bullish'
                    is_swing = True
            
            ### Down swing ###
            elif legs[1]['end_value'] < legs[0]['start_value'] and legs[0]['end_value'] < legs[1]['end_value']:
                ### Check true swing ###
                s_index = data.index.tolist().index(legs[1]['start'])
                e_index = data.index.tolist().index(legs[1]['end'])
                true_candles = 0
                first_candle = False
                last_candle_close = None

                for k in range(s_index, e_index+1):
                    if data.iloc[k]['status'] == 'bullish':
                        if first_candle:
                            if last_candle_close is not None and data.iloc[k]['close'] > last_candle_close:
                                true_candles += 1
                        last_candle_close = data.iloc[k]['close']
                        first_candle = True
                
                if true_candles >= min_candles:  # 2 به جای 3
                    swing_type = 'bearish'
                    is_swing = True
        
        # اگر 2 leg داریم، از منطق ساده‌تر استفاده کن
        elif len(legs) == 2:
            # تشخیص جهت بر اساس legs
            if legs[1]['end_value'] > legs[0]['start_value']:
                # روند صعودی
                if legs[0]['end_value'] > legs[1]['end_value']:
                    # pullback وجود دارد
                    swing_type = 'bullish'
                    is_swing = True
            elif legs[1]['end_value'] < legs[0]['start_value']:
                # روند نزولی
                if legs[0]['end_value'] < legs[1]['end_value']:
                    # pullback وجود دارد
                    swing_type = 'bearish'
                    is_swing = True
        
        return swing_type, is_swing
    
    return '', False
