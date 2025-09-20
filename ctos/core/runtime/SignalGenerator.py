from Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
import pandas as pd
from util import format_decimal_places, convert_columns_to_numeric
from DataHandler import DataHandler,
from IndicatorCalculator import IndicatorCalculator
import numpy as np
import time
import matplotlib.pyplot as plt
import mplfinance as mpf
np.seterr(divide='ignore',invalid='ignore') # 忽略warning
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
plt.rcParams['axes.unicode_minus']=False #用来正常显示负号
plt.figure(figsize=(10, 8),dpi=200)
import os

def time_transform(timestamp):
    time_local = time.localtime(timestamp / 1000)
    dt = time.strftime("%Y-%m-%d %H:%M:%S", time_local)
    return dt


def process_data(df):
    # 对数据进行改名，mplfinance名字必须是Date, Open, High, Low, Close, Volume
    print(df.columns)
    try:
        df.rename(
            columns={'trade_date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'vol': 'Volume'},
            inplace=True)
    except Exception as e:
        print(e)
    if df.loc[0, 'Date'] > df.loc[1, 'Date']:
        df = df[::-1]
    # 从 tushre下载的数据是按时间倒叙的，也就是从现在到过去的数据，这里把它改成从过去到现在的数据
    # 这里是我自己加的，可以直接根据unix毫秒时间戳生成时间
    if len(str(df.loc[0, 'Date'])) == len('1640336280000'):
        df['Date'] = df['Date'].apply(time_transform)
        df.set_index(["Date"], inplace=True)
        df.index = pd.to_datetime(df.index)
    else:
        df.set_index(["Date"], inplace=True)
        df.index = pd.to_datetime(df.index)
    # 把 Date 这列数据设置成索引，必须的，不设置会报错。
    # 把 Date这列数据装换成datetime 格式，也是 mplfinance 要求的
    # df.index = pd.to_datetime(df.index, format='%Y%m%d')
    return df



class SignalGenerator:
    def __init__(self, indicator_calculator):
        self.data_handler = indicator_calculator.data_handler
        self.indicator_calculator = indicator_calculator
        print('__init__ SignalGenerator success~~~')


    def check_and_add_indicators(self, df):
        """
        Check if necessary indicators are present and add them if not.
        """
        # Example checks and additions for Bollinger Bands and MACD
        if 'bollinger_upper' not in df.columns or 'bollinger_lower' not in df.columns:
            df = self.indicator_calculator.add_bollinger_bands(df)
        if 'macd' not in df.columns or 'signal' not in df.columns:
            df = self.indicator_calculator.add_macd(df)
        if 'ma5' not in df.columns or 'ma10' not in df.columns or 'ma20' not in df.columns:
            df = self.indicator_calculator.add_sma(df, window=5)
            df = self.indicator_calculator.add_sma(df, window=10)
            df = self.indicator_calculator.add_sma(df, window=20)



    def bolling_signals(self, df):
        """
        Calculate Bollinger Band signals for buy and sell points.
        """
        # print(df.columns)
        df['bolling_sell_point'] = df.apply(lambda x: x.high \
            if x.close < x.bollinger_upper and x.high > x.bollinger_upper and x.bollinger_middle < 1.5 and x.bollinger_middle < 0.6 else np.nan,
                                                                       axis=1)
        df['bolling_buy_point'] = df.apply(lambda x: x.low \
            if x.low < x.bollinger_lower and x.close > x.bollinger_lower else np.nan, axis=1)

    def ma_signals(self, df):
        """
        Calculate buy points based on moving averages (MA).
        """
        self.check_and_add_indicators(df)
        df['ma_buy_point'] = np.nan
        for idx in range(5, len(df)):
            if df.loc[df.index[idx], 'ma5'] < df.loc[df.index[idx], 'ma10'] or \
            df.loc[df.index[idx], 'ma5'] < df.loc[df.index[idx], 'ma20'] or \
            df.loc[df.index[idx], 'ma5'] < df.loc[df.index[idx - 1], 'ma10']:
                continue
            elif df.loc[df.index[idx - 1], 'ma5'] < df.loc[df.index[idx - 1], 'ma10'] and \
            df.loc[df.index[idx], 'ma5'] >= df.loc[df.index[idx], 'ma10'] and \
            df.loc[df.index[idx], 'ma5'] > df.loc[df.index[idx], 'ma20']:
                df.at[df.index[idx], 'ma_buy_point'] = df.loc[df.index[idx], 'low']

        df['ma_sell_point'] = np.nan
        for idx in range(5, len(df)):
            if df.loc[df.index[idx], 'ma5'] > df.loc[df.index[idx], 'ma20'] and \
            df.loc[df.index[idx - 1], 'ma5'] <= df.loc[df.index[idx - 1], 'ma20']:
                df.at[df.index[idx], 'ma_sell_point'] = df.loc[df.index[idx], 'high']

    def macd_signals(self, df):
        """
        Calculate buy points based on MACD indicator.
        """
        self.check_and_add_indicators(df)
        df['macd_buy_point'] = np.nan
        for idx in range(1, len(df)):
            if df.loc[df.index[idx], 'macd'] < 0 and \
            df.loc[df.index[idx], 'macd'] > df.loc[df.index[idx - 1], 'macd'] and \
            df.loc[df.index[idx], 'macd'] > df.loc[df.index[idx], 'signal'] and \
            df.loc[df.index[idx - 1], 'macd'] < df.loc[df.index[idx - 1], 'signal']:
                df.at[df.index[idx], 'macd_buy_point'] = df.loc[df.index[idx], 'low']

        df['macd_sell_point'] = np.nan
        for idx in range(1, len(df)):
            if df.loc[df.index[idx], 'macd'] > 0 and df.loc[df.index[idx], 'macd'] <= df.loc[df.index[idx - 1], 'macd'] and \
            df.loc[df.index[idx], 'macd'] <= df.loc[df.index[idx], 'signal'] and \
            df.loc[df.index[idx - 1], 'macd'] >= df.loc[df.index[idx - 1], 'signal']:
                df.at[df.index[idx], 'macd_sell_point'] = df.loc[df.index[idx], 'high']




    def check_nested_signals(self, start_time, end_time, point_type, timeframes):
        # This function checks for the presence of a point type in all specified timeframes within the given window
        ensure_rate = len(timeframes)
        for timeframe, df in timeframes.items():
            # Find any matching signals in this timeframe
            matching_signals = df[
                (df['trade_date'] >= start_time) & (df['trade_date'] <= end_time) & (~pd.isna(df[point_type]))]
            if matching_signals.empty:
                ensure_rate -= 1
        return True if ensure_rate >= (len(timeframes) // 2 + 1) else False  # Signal confirmed across all required timeframes


    def strong_macd_signals(self, df_15m, df_1h, df_4h, df_1d):
        # Ensure all dataframes have necessary MACD point columns
        timeframes = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
        if 'macd_buy_point' not in df_15m.columns or 'macd_sell_point' not in df_15m.columns:
            df_15m = self.macd_signals(
                df_15m)  # Assuming this function updates df in place or returns updated df

        # Initialize columns for strong MACD points in 15m df
        df_15m['strong_macd_buy_point'] = np.nan
        df_15m['strong_macd_sell_point'] = np.nan

        # Process each 15m MACD point and check for nested signals in higher timeframes
        for index, row in df_15m.iterrows():
            # Define the time window for this row
            start_time = row['trade_date']
            end_time = start_time + pd.Timedelta(minutes=15)

            # Check for strong buy signals
            if not pd.isna(row['macd_buy_point']) and self.check_nested_signals(start_time, end_time, 'macd_buy_point',
                                                                                timeframes):
                print('ok I found one strong_macd_buy_point!')
                df_15m.at[index, 'strong_macd_buy_point'] = row['macd_buy_point']

            # Check for strong sell signals
            if not pd.isna(row['macd_sell_point']) and self.check_nested_signals(start_time, end_time,
                                                                                 'macd_sell_point', timeframes):
                print('ok I found one strong_macd_sell_point!')
                df_15m.at[index, 'strong_macd_sell_point'] = row['macd_sell_point']

    def strong_bolling_signals(self, df_15m, df_1h, df_4h, df_1d):
        # Ensure all dataframes have necessary MACD point columns
        timeframes = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
        if 'bolling_buy_point' not in df_15m.columns or 'bolling_sell_point' not in df_15m.columns:
            df_15m = self.bolling_signals(df_15m)  # Assuming this function updates df in place or returns updated df

        # Initialize columns for strong MACD points in 15m df
        df_15m['strong_bolling_buy_point'] = np.nan
        df_15m['strong_bolling_sell_point'] = np.nan

        # Process each 15m MACD point and check for nested signals in higher timeframes
        for index, row in df_15m.iterrows():
            # Define the time window for this row
            start_time = row['trade_date']
            end_time = start_time + pd.Timedelta(minutes=15)

            # Check for strong buy signals
            if not pd.isna(row['bolling_buy_point']) and self.check_nested_signals(start_time, end_time, 'bolling_buy_point',
                                                                                timeframes):
                print('ok I found one strong_bolling_buy_point!')
                df_15m.at[index, 'strong_bolling_buy_point'] = row['bolling_buy_point']

            # Check for strong sell signals
            if not pd.isna(row['bolling_sell_point']) and self.check_nested_signals(start_time, end_time,
                                                                                 'bolling_sell_point', timeframes):
                print('ok I found one strong_bolling_sell_point!')
                df_15m.at[index, 'strong_bolling_sell_point'] = row['bolling_sell_point']


    def strong_ma_signals(self, df_15m, df_1h, df_4h, df_1d):
        # Ensure all dataframes have necessary MACD point columns
        timeframes = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
        if 'ma_buy_point' not in df_15m.columns or 'ma_sell_point' not in df_15m.columns:
            df_15m = self.ma_signals(df_15m)  # Assuming this function updates df in place or returns updated df

        # Initialize columns for strong MACD points in 15m df
        df_15m['strong_ma_buy_point'] = np.nan
        df_15m['strong_ma_sell_point'] = np.nan

        # Process each 15m MACD point and check for nested signals in higher timeframes
        for index, row in df_15m.iterrows():
            # Define the time window for this row
            start_time = row['trade_date']
            end_time = start_time + pd.Timedelta(minutes=15)

            # Check for strong buy signals
            if not pd.isna(row['ma_buy_point']) and self.check_nested_signals(start_time, end_time, 'ma_buy_point',
                                                                                timeframes):
                print('ok I found one strong_ma_buy_point!')
                df_15m.at[index, 'strong_ma_buy_point'] = row['ma_buy_point']

            # Check for strong sell signals
            if not pd.isna(row['ma_sell_point']) and self.check_nested_signals(start_time, end_time,
                                                                                 'ma_sell_point', timeframes):
                print('ok I found one strong_ma_sell_point!')
                df_15m.at[index, 'strong_ma_sell_point'] = row['ma_sell_point']



    # Function to check higher timeframe alignment
    def is_higher_timeframes(self, start_time, end_time, point_type, timeframes):
        # This function checks for the presence of a point type in all specified timeframes within the given window
        ensure_rate = len(timeframes) * 2
        count = 0
        for timeframe, df in timeframes.items():
            count+=1
            # Find any matching signals in this timeframe
            matching_signals = df[
                (df['trade_date'] >= start_time) & (df['trade_date'] <= end_time) & (~pd.isna(df[point_type]))]
            if matching_signals.empty:
                ensure_rate -= count
        return True if ensure_rate >= len(timeframes) else False  # Signal confirmed across all required timeframes
        # return True if ensure_rate >= (len(timeframes) // 2 + 1) else False  # Signal confirmed across all required timeframes



    def area_macd(self, df):
        # Calculate the MACD histogram as the difference between the MACD line and the signal line
        df['histogram'] = df['macd'] - df['signal']

        # Identify where the histogram is positive (upward momentum)
        df['histogram_positive'] = df['histogram'] > 0
        # Identify where the histogram is negative (downward momentum)
        df['histogram_negative'] = df['histogram'] < 0

        # Detect consecutive positive histogram bars
        df['consecutive_macd_positive'] = df['histogram_positive'] & df['histogram_positive'].shift(1)
        # Detect consecutive negative histogram bars
        df['consecutive_macd_negative'] = df['histogram_negative'] & df['histogram_negative'].shift(1)

        # Use boolean indexing to handle True/False conversion properly
        df['macd_positive_area'] = df['consecutive_macd_positive'] & (df['consecutive_macd_positive'].shift(-1) != True)
        # Generate sell signals: mark the transition from not less to consecutively less
        df['macd_negative_area'] = df['consecutive_macd_negative'] & (df['consecutive_macd_negative'].shift(-1) != True)

        return df



    def area_macd_signals(self, df_15m, df_1h, df_4h, df_1d):
        # Analyze 15m data for buy and sell points supported by higher timeframe trends
        area_buy_signals = []
        area_sell_signals = []
        timeframes = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
        for index, row in df_15m.iterrows():
            # Define the time window for this row
            start_time = row['trade_date']
            end_time = start_time + pd.Timedelta(minutes=15)

            # Check for strong buy signals
            if not pd.isna(row['macd_buy_point']) and self.is_higher_timeframes(start_time, end_time, 'macd_positive_area',
                                                                              timeframes):
                print('ok I found one area_macd_buy_point!')
                area_buy_signals.append(index)

            # Check for strong sell signals
            if not pd.isna(row['macd_sell_point']) and self.is_higher_timeframes(start_time, end_time,
                                                                               'macd_negative_area', timeframes):
                print('ok I found one area_macd_sell_point!')
                area_sell_signals.append(index)

        # Mark these strong buy and sell signals in the 15m dataframe
        df_15m['area_macd_buy_point'] = np.nan
        df_15m['area_macd_sell_point'] = np.nan
        df_15m.loc[area_buy_signals, 'area_macd_buy_point'] = True
        df_15m.loc[area_sell_signals, 'area_macd_sell_point'] = True

        return df_15m

    def area_ma(self, df):
        # Check where MA5 is greater than MA10
        df['ma_positive'] = df['ma5'] > df['ma10']
        # Check where MA5 is less than MA10
        df['ma_negative'] = df['ma5'] < df['ma10']

        # Identify consecutive periods where MA5 is greater than MA10
        df['consecutive_ma_positive'] = df['ma_positive'] & df['ma_positive'].shift(1)
        # Identify consecutive periods where MA5 is less than MA10
        df['consecutive_ma_negative'] = df['ma_negative'] & df['ma_negative'].shift(1)

        # Generate buy signals: mark the transition from not greater to consecutively greater
        # Use boolean indexing to handle True/False conversion properly
        df['ma_positive_area'] = df['consecutive_ma_positive'] & (df['consecutive_ma_positive'].shift(-1) != True)
        # Generate sell signals: mark the transition from not less to consecutively less
        df['ma_negative_area'] = df['consecutive_ma_negative'] & (df['consecutive_ma_negative'].shift(-1) != True)

        return df

    def area_ma_signals(self, df_15m, df_1h, df_4h, df_1d):
        # Analyze 15m data for buy and sell points supported by higher timeframe trends
        area_buy_signals = []
        area_sell_signals = []
        timeframes = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
        for index, row in df_15m.iterrows():
            # Define the time window for this row
            start_time = row['trade_date']
            end_time = start_time + pd.Timedelta(minutes=15)

            # Check for strong buy signals
            if not pd.isna(row['ma_buy_point']) and self.is_higher_timeframes(start_time, end_time, 'ma_positive_area',
                                                                              timeframes):
                print('ok I found one area_ma_buy_point!')
                area_buy_signals.append(index)

            # Check for strong sell signals
            if not pd.isna(row['ma_sell_point']) and self.is_higher_timeframes(start_time, end_time,
                                                                               'ma_negative_area', timeframes):
                print('ok I found one area_ma_sell_point!')
                area_sell_signals.append(index)

        # Mark these strong buy and sell signals in the 15m dataframe
        df_15m['area_ma_buy_point'] = np.nan
        df_15m['area_ma_sell_point'] = np.nan
        df_15m.loc[area_buy_signals, 'area_ma_buy_point'] = True
        df_15m.loc[area_sell_signals, 'area_ma_sell_point'] = True

        return df_15m

    def pre_process_for_plot(self, df):
        df['histogram'] = df['macd'] - df['signal']
        x = df['macd'] - df['signal']
        x[x < 0] = None
        histogram_positive_1 = x[x > x.shift(-1)]
        histogram_positive_2 = x[x <= x.shift(-1)]
        df['histogram_positive_add'] = histogram_positive_1
        df['histogram_positive_reduce'] = histogram_positive_2
        x = df['macd'] - df['signal']
        x[x >= 0] = None
        histogram_negative_1 = x[x > x.shift(-1)]
        histogram_negative_2 = x[x <= x.shift(-1)]
        df['histogram_negative_add'] = histogram_negative_1
        df['histogram_negative_reduce'] = histogram_negative_2
        return df

    def plotKLine(self, df, title='', savePath='', show=True):
        if 'histogram_negative_add' not in df.columns:
            self.pre_process_for_plot(df)
        # 设置marketcolors
        # up:设置K线线柱颜色，up意为收盘价大于等于开盘价
        # down:与up相反，这样设置与国内K线颜色标准相符
        # edge:K线线柱边缘颜色(i代表继承自up和down的颜色)，下同。详见官方文档)
        # wick:灯芯(上下影线)颜色
        # volume:成交量直方图的颜色
        # inherit:是否继承，选填
        mc = mpf.make_marketcolors(
            up='red',
            down='green',
            edge='i',
            wick='i',
            volume='in',
            inherit=True)
        # 设置图形风格
        # gridaxis:设置网格线位置
        # gridstyle:设置网格线线型
        # y_on_right:设置y轴位置是否在右
        s = mpf.make_mpf_style(
            gridaxis='both',
            gridstyle='-.',
            y_on_right=False,
            marketcolors=mc)


        plane_idx = {'main': 0, 'macd': 1, 'vol': 2}
        # plane_idx = {'main':0, 'macd':1, 'ma':2, 'vol':3}
        figscale_num = 1.5
        df = process_data(convert_columns_to_numeric(df))
        print(df)
        add_plot = [mpf.make_addplot(df[['bollinger_lower', 'bollinger_upper', 'bollinger_middle']]),
                    mpf.make_addplot(df['histogram_positive_add'], type='bar', width=0.7, panel=plane_idx['macd'],
                                     color='lightsalmon', alpha=1, secondary_y=False),
                    mpf.make_addplot(df['histogram_positive_reduce'], type='bar', width=0.7, panel=plane_idx['macd'],
                                     color='red', alpha=1, secondary_y=False),
                    mpf.make_addplot(df['histogram_negative_add'], type='bar', width=0.7, panel=plane_idx['macd'],
                                     color='green', alpha=1, secondary_y=False),
                    mpf.make_addplot(df['histogram_negative_reduce'], type='bar', width=0.7, panel=plane_idx['macd'],
                                     color='lightgreen', alpha=1, secondary_y=False),
                    mpf.make_addplot(df['macd'], panel=plane_idx['macd'], color='fuchsia', secondary_y=True),
                    mpf.make_addplot(df['signal'], panel=plane_idx['macd'], color='b', secondary_y=True),
                    ]

        # add_plot.append(mpf.make_addplot(df[['ma7', 'ma30']], panel=plane_idx['ma'], secondary_y=True))
        if len(df[np.isnan(df['bolling_buy_point'])]) < len(df):
            add_plot.append(
                mpf.make_addplot(df[['bolling_buy_point']], type='scatter', markersize=100 * int(figscale_num // 1.5),
                                 marker='^', color='r'))
        if len(df[np.isnan(df['bolling_sell_point'])]) < len(df):
            add_plot.append(
                mpf.make_addplot(df[['bolling_sell_point']], type='scatter', markersize=100 * int(figscale_num // 1.5),
                                 marker='v', color='g'))

        if len(df[np.isnan(df['macd_buy_point'])]) < len(df):
            add_plot.append(mpf.make_addplot(df[['macd_buy_point']], type='scatter', panel=plane_idx['main'],
                                             markersize=100 * int(figscale_num // 1.5), marker='^', color='orange'))

        if len(df[np.isnan(df['ma_buy_point'])]) < len(df):
            add_plot.append(mpf.make_addplot(df[['ma_buy_point']], type='scatter', panel=plane_idx['main'],
                                             markersize=100 * int(figscale_num // 1.5), marker='^', color='black'))

        try:
            add_plot.append(mpf.make_addplot(df[['ma_v_5']], panel=plane_idx['vol'], secondary_y=True))
            add_plot.append(mpf.make_addplot(df[['ma_v_10']], panel=plane_idx['vol'], secondary_y=True))
            add_plot.append(mpf.make_addplot(df[['ma_v_20']], panel=plane_idx['vol'], secondary_y=True))
        except Exception as e:
            print(e)
        if len(savePath) > 0:
            mpf.plot(df, type='candle', style=s, mav=(5, 20),
                     figscale=figscale_num, linecolor='r', title=title, main_panel=0, volume_panel=2,
                     panel_ratios=(1, 0.3, 0.2), tight_layout=True,
                     volume=True, addplot=add_plot, savefig=savePath)  # 绘制图形，用addplot变量传递参数
        else:
            mpf.plot(df, type='candle', style=s, figscale=figscale_num, title=title,
                     tight_layout=True,  linecolor='r',
                     volume=True, addplot=add_plot, main_panel=0, volume_panel=2,
                                    panel_ratios=(1, 0.3, 0.3),)
        if show:
            plt.show() #开始绘图

    def hammer_or_inverted_hammer(self, df):
        df['hammer'] = ((df['high'] - df['close']) > 2 * (df['close'] - df['low'])) & \
                       ((df['high'] - df['open']) < 0.5 * (df['high'] - df['low']))
        df['inverted_hammer'] = ((df['close'] - df['low']) > 2 * (df['high'] - df['close'])) & \
                                ((df['high'] - df['open']) < 0.5 * (df['high'] - df['low']))

        df['bullish_strength'] = np.nan
        df.loc[df['hammer'], 'bullish_strength'] = 1
        df.loc[df['inverted_hammer'], 'bullish_strength'] = 1
        df.loc[~df['hammer'] & ~df['inverted_hammer'], 'bullish_strength'] = -1

    def engulfing_pattern(self, df):
        df['bullish_engulfing'] = (df['close'] > df['open']) & \
                                  (df['close'].shift(1) < df['open'].shift(1)) & \
                                  (df['close'] > df['open'].shift(1)) & \
                                  (df['open'] < df['close'].shift(1))

        df['bearish_engulfing'] = (df['close'] < df['open']) & \
                                  (df['close'].shift(1) > df['open'].shift(1)) & \
                                  (df['close'] < df['open'].shift(1)) & \
                                  (df['open'] > df['close'].shift(1))

        df['bullish_strength'] = np.nan
        df.loc[df['bullish_engulfing'], 'bullish_strength'] = 1
        df.loc[df['bearish_engulfing'], 'bullish_strength'] = -1


    def doji_pattern(self, df):
        df['doji'] = abs(df['close'] - df['open']) <= 0.1 * (df['high'] - df['low'])

        df['bullish_strength'] = np.nan
        df.loc[df['doji'], 'bullish_strength'] = -1  # 可能反转为看跌

    def dark_cloud_cover(self, df):
        df['dark_cloud_cover'] = (df['close'] < df['open']) & \
                                 (df['close'].shift(1) > df['open'].shift(1)) & \
                                 (df['close'] < df['open'].shift(1)) & \
                                 (df['open'] > df['close'].shift(1))

        df['bullish_strength'] = np.nan
        df.loc[df['dark_cloud_cover'], 'bullish_strength'] = -1  # 看跌信号

    def piercing_line(self, df):
        # Check for Piercing Line Pattern: first day is a bearish candle, second day is a bullish candle,
        # and the close of the second day is above the midpoint of the first day's range.
        df['piercing_line'] = (df['close'] > df['open']) & \
                              (df['close'].shift(1) < df['open'].shift(1)) & \
                              (df['close'] > (df['open'].shift(1) + df['close'].shift(1)) / 2)

        df['bullish_strength'] = np.nan
        df.loc[df['piercing_line'], 'bullish_strength'] = 1  # Piercing Line is bullish signal

    def head_and_shoulders(self, df):
        # 假设我们正在检查每个可能的“头肩顶”形态
        df['head_and_shoulders'] = (
                (df['close'].shift(2) > df['close'].shift(1)) &  # 左肩高于头部左侧
                (df['close'].shift(1) > df['close']) &  # 头部高于右肩
                (df['close'].shift(1) > df['close'].shift(-1)) &  # 头部高于右肩
                (df['close'].shift(2) > df['close'].shift(3)) &  # 左肩高于右肩
                (df['close'].shift(-1) > df['close'].shift(0))  # 右肩比头部低
        )

        df['bullish_strength'] = np.nan
        df.loc[df['head_and_shoulders'], 'bullish_strength'] = -1  # 头肩顶是看跌信号

    def head_and_shoulders_bottom(self, df):
        # 假设我们正在检查每个可能的“头肩底”形态
        df['head_and_shoulders_bottom'] = (
                (df['close'].shift(2) < df['close'].shift(1)) &  # 头部低于左肩
                (df['close'].shift(1) < df['close']) &  # 头部低于右肩
                (df['close'].shift(1) < df['close'].shift(-1)) &  # 头部低于右肩
                (df['close'].shift(2) < df['close'].shift(3)) &  # 左肩低于右肩
                (df['close'].shift(-1) < df['close'].shift(0))  # 右肩比头部高
        )

        df['bullish_strength'] = np.nan
        df.loc[df['head_and_shoulders_bottom'], 'bullish_strength'] = 1  # 头肩底是看涨信号


    def plot_dataset(self):
        self.df_15m = self.data_handler.fetch_data('ETH-USD-SWAP', '15m', '2023-08-17', '2024-11-20')
        self.df_1h = self.data_handler.fetch_data('ETH-USD-SWAP', '1h', '2023-08-17', '2024-11-20')
        self.df_4h = self.data_handler.fetch_data('ETH-USD-SWAP', '4h', '2023-08-17', '2024-11-20')
        self.df_1d = self.data_handler.fetch_data('ETH-USD-SWAP', '1d', '2023-08-17', '2024-11-20')
        self.check_and_add_indicators(self.df_15m)
        self.check_and_add_indicators(self.df_1h)
        self.check_and_add_indicators(self.df_4h)
        self.check_and_add_indicators( self.df_1d)
        self.bolling_signals(self.df_15m)
        self.bolling_signals(self.df_1h)
        self.bolling_signals(self.df_4h)
        self.bolling_signals(self.df_1d)
        self.df_15m.fillna(method='ffill', inplace=True)  # 前向填充
        self.df_15m.fillna(method='bfill', inplace=True)  # 后向填充

        self.df_1h.fillna(method='ffill', inplace=True)  # 前向填充
        self.df_1h.fillna(method='bfill', inplace=True)  # 后向填充
        self.df_4h.fillna(method='ffill', inplace=True)  # 前向填充
        self.df_4h.fillna(method='bfill', inplace=True)  # 后向填充
        self.df_1d.fillna(method='ffill', inplace=True)  # 前向填充
        self.df_1d.fillna(method='bfill', inplace=True)  # 后向填充

        data_frames = [self.df_15m, self.df_1h, self.df_4h, self.df_1d]
        window_size = 40
        intervals = ['15m', '1h', '4h', '1d']
        for interval, df in zip(intervals, data_frames):
            folder_path = f'plot/{interval}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)  # 创建文件夹如果不存在

            # 滑动窗口遍历数据帧
            for start in range(0, len(df) - window_size, window_size):
                window = df.iloc[start:start + window_size]
                if len(window) < window_size:
                    continue  # 如果窗口不足，则跳过

                # 获取最后一根K线的时间作为文件名
                last_date = window.iloc[-1]['trade_date'].strftime('%Y-%m-%d_%H-%M-%S')
                save_path = f'{folder_path}/{last_date}.png'

                # 绘制K线图并保存
                self.plotKLine(window,
                         title=f"{interval.upper()} K-line for {last_date}",
                         savePath=save_path, show=False)
                print(f"Plot saved: {save_path}")

# Usage example (assuming df_15m is already loaded and prepared)
# plot_complex_kline(df_15m)


if __name__ == '__main__':
    data_handler = DataHandler(HOST_IP, 'TradingData', HOST_USER, 'zzb162122')
    indicator_calculator = IndicatorCalculator(data_handler)
    signal_generator = SignalGenerator(indicator_calculator)

    df = signal_generator.data_handler.fetch_data('ETH_USD-SWAP', '4h',  '2023-11-01',  '2023-11-21')
    print(df)
    df = indicator_calculator.update_indicators(df)
    # Initialize the signal generator and calculate buy/sell points
    signal_generator.bolling_signals(df)
    signal_generator.ma_signals(df)
    signal_generator.macd_signals(df)
    signal_generator.plotKLine(df, 'test', './test.png')
    formatted_df = format_decimal_places(df.copy())  # Use copy to keep the original df intact
    print(formatted_df.tail(100))
    signal_generator.plot_dataset()
    data_handler.close()
