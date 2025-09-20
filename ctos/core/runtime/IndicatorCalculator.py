from Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
from DataHandler import DataHandler

class IndicatorCalculator:
    def __init__(self, data_handler):
        """
        Initialize IndicatorCalculator class.
        :param data_handler: An instance of DataHandler class for fetching trading data.
        """
        self.data_handler = data_handler
        print('__init__ IndicatorCalculator success~~~')

    def add_sma(self, df, column='close', window=14):
        sma_column_name = f'ma{window}'
        if sma_column_name not in df.columns:
            df[sma_column_name] = df[column].rolling(window=window).mean()
        return df

    def add_ema(self, df, column='close', span=14):
        ema_column_name = f'ema{span}'
        if ema_column_name not in df.columns:
            df[ema_column_name] = df[column].ewm(span=span, adjust=False).mean()
        return df

    def add_ma_v(self, df, column='vol', window=14):
        sma_column_name = f'ma_v_{window}'
        if sma_column_name not in df.columns:
            df[sma_column_name] = df[column].rolling(window=window).mean()
        return df

    def add_rsi(self, df, column='close', window=14):
        rsi_column_name = f'rsi_{window}'
        if rsi_column_name not in df.columns:
            delta = df[column].diff()
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            avg_gain = gain.rolling(window=window).mean()
            avg_loss = loss.rolling(window=window).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            df[rsi_column_name] = rsi
        return df

    def add_bollinger_bands(self, df, column='close', window=20):
        upper_band_name = f'bollinger_upper'
        lower_band_name = f'bollinger_lower'
        sma = df[column].rolling(window=window).mean()
        if upper_band_name not in df.columns or lower_band_name not in df.columns:
            std = df[column].rolling(window=window).std()
            df[upper_band_name] = sma + (std * 2)
            df[lower_band_name] = sma - (std * 2)
        df['bollinger_middle'] = sma
        return df

    def add_macd(self, df, column='close', fast=12, slow=26, signal=9):
        macd_name = 'macd'
        signal_name = 'signal'
        if macd_name not in df.columns or signal_name not in df.columns:
            exp1 = df[column].ewm(span=fast, adjust=False).mean()
            exp2 = df[column].ewm(span=slow, adjust=False).mean()
            macd = exp1 - exp2
            df[macd_name] = macd
            df[signal_name] = macd.ewm(span=signal, adjust=False).mean()
        return df

    def add_stochastic_oscillator(self, df, high_col='high', low_col='low', close_col='close', k_window=14, d_window=3):
        k_name = 'stochastic_k'
        d_name = 'stochastic_d'
        if k_name not in df.columns or d_name not in df.columns:
            df[high_col] = df[high_col].astype(float)
            df[low_col] = df[low_col].astype(float)
            df[close_col] = df[close_col].astype(float)
            low_min = df[low_col].rolling(window=k_window).min()
            high_max = df[high_col].rolling(window=k_window).max()
            k = 100 * ((df[close_col] - low_min) / (high_max - low_min))
            df[k_name] = k
            df[d_name] = k.rolling(window=d_window).mean()
        return df

    def update_indicators(self, df):
        df = self.add_sma(df, window=7)
        df = self.add_sma(df, window=20)
        df = self.add_sma(df, window=30)
        df = self.add_ma_v(df, window=5)
        df = self.add_ma_v(df, window=10)
        df = self.add_ma_v(df, window=20)
        df = self.add_ema(df, span=7)
        df = self.add_ema(df, span=20)
        df = self.add_ema(df, span=30)
        df = self.add_rsi(df)
        df = self.add_bollinger_bands(df)
        df = self.add_macd(df)
        df = self.add_stochastic_oscillator(df)
        return df



if __name__ == '__main__':
    data_handler = DataHandler(HOST_IP, 'TradingData', 'root', 'zzb162122')
    indicator_calculator = IndicatorCalculator(data_handler)

    # Fetch data from the database
    # Assume the symbol and interval are defined, e.g., 'ETH-USD-SWAP' and '1h'
    symbol = 'ETH-USD-SWAP'
    interval = '1h'
    table_name = f"{symbol.replace('-', '_')}_{interval}"  # Format as needed for your DB schema

    # Since we're assuming the fetch_data method needs a time range, define start and end dates for the fetch
    start_date = '2024-11-01'
    end_date = '2024-11-31'

    df = data_handler.fetch_data(symbol, interval, start_date, end_date)

    if not df.empty:
        # Update DataFrame with indicators
        df_with_indicators = indicator_calculator.update_indicators(df)
        # Display the DataFrame with indicators
        print(df_with_indicators.head(50), df_with_indicators.tail(50), len(df_with_indicators))
    else:
        print("No data returned from the database.")

    # Don't forget to close the database connection
    data_handler.close()