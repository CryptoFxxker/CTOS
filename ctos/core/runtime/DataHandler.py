from Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta, date
import pandas as pd
import os
from tqdm import tqdm
import requests
import zipfile
import time
import random
from util import base_url, rate_price2order, json
from collections import defaultdict
from mysql.connector.errors import DatabaseError

# 兼容不同列名的字典映射
COLUMN_MAPPING = {
    'trade_date': 'trade_date',
    'Open': 'open',
    'High': 'high',
    'Low': 'low',
    'Close': 'close',
    'vol1': 'vol1',
    'vol': 'vol',
}


class DataHandler:
    def __init__(self, host, database, user, password):
        self.conn = None
        try:
            self.conn = mysql.connector.connect(
                host=host,
                database=database,
                user=user,
                password=password
            )
            if self.conn.is_connected():
                print('__init__ DataHandler success~~~')

        except Error as e:
            print(e, '1111111111111')

    def create_table_if_not_exists(self, cursor, table_name):
        # 20250602 1730 这里需要考虑一个事情，那就是shib这种傻逼币种，价钱巨低，交易量巨大，狗日的直接超模了。
        # -- 修改 SHIBUSDT_1d 表
        # ALTER TABLE SHIBUSDT_1d
        # MODIFY vol1 DECIMAL(30,10),
        # MODIFY vol DECIMAL(30,10);

        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            trade_date DATETIME PRIMARY KEY,
            open DECIMAL(25, 10),
            high DECIMAL(25, 10),
            low DECIMAL(25, 10),
            close DECIMAL(25, 10),
            vol1 DECIMAL(25, 10),
            vol DECIMAL(25, 10)
        );
        """
        try:
            cursor.execute(create_table_query)
            print(f"Table {table_name} created successfully.")
        except Error as e:
            print(f"Failed to create table {table_name}: {e}")

    def insert_data(self, symbol, interval, data, remove_duplicates=False):
        table_name = f"{symbol.replace('-', '_')}_{interval}"
        try:
            if self.conn.is_connected():
                cursor = self.conn.cursor()
                # Ensure the table exists
                # self.create_table_if_not_exists(cursor, table_name)

                query = f"""INSERT INTO {table_name}
                            (trade_date, open, high, low, close, vol1, vol)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            open = VALUES(open), high = VALUES(high), low = VALUES(low),
                            close = VALUES(close), vol1 = VALUES(vol1), vol = VALUES(vol);"""
                # print('aaaaaa', data.iloc[0,0:10])
                data['vol1'] = data['vol1'] / 1e6
                formatted_data = [
                    (
                        parse_trade_date(row['trade_date']),  # Assume there's a function to parse trade_date correctly
                        row['open'],
                        row['high'],
                        row['low'],
                        row['close'],
                        row['vol1'],
                        row['vol']
                    )
                    for index, row in data.iterrows()
                ]

                cursor.executemany(query, formatted_data)
                self.conn.commit()
                print(cursor.rowcount, "records inserted into", table_name)
                if remove_duplicates:
                    self.remove_duplicates(table_name)
            else:
                print('没连上？咋回事？')
        except Error as e:
            print(e, '222222222')

    def remove_duplicates(self, table_name):
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"CREATE TEMPORARY TABLE keep_dates AS "
                            f"SELECT MIN(trade_date) AS trade_date FROM {table_name} GROUP BY trade_date")

                # 删除不在 keep_dates 里的行（即同日期的重复行）
                cur.execute(f"""
                    DELETE t FROM {table_name} t
                    LEFT JOIN keep_dates k USING (trade_date)
                    WHERE k.trade_date IS NULL;
                """)
                self.conn.commit()
                cur.execute("DROP TEMPORARY TABLE keep_dates")
                print(f"Duplicates removed in table {table_name}.")
        except Error as e:
            print("Error removing duplicates:", e)


    def fetch_data(self, symbol, interval, *args):
        """
        Enhanced fetch function to handle different data retrieval scenarios.
        - If called with one argument: last_X_data -> fetches the last X data points.
        - If called with two arguments: start_date, X_data_after -> fetches X data points after start_date.
        - If called with two arguments: end_date, X_data_before -> fetches X data points before end_date.
        """
        table_name = f"{symbol.replace('-', '_')}_{interval}"
        safe_table_name = table_name

        if len(args) == 1 and isinstance(args[0], int):
            query = f"SELECT * FROM {safe_table_name} ORDER BY trade_date DESC LIMIT %s"
            params = (args[0],)

        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], int):
            if '-' in args[0]:  # 起始日期 + 条数
                query = f"""SELECT * FROM {safe_table_name}
                            WHERE trade_date >= %s
                            ORDER BY trade_date ASC
                            LIMIT %s"""
            else:  # 结束日期 + 条数
                query = f"""SELECT * FROM {safe_table_name}
                            WHERE trade_date <= %s
                            ORDER BY trade_date DESC
                            LIMIT %s"""
            params = (args[0], args[1])

        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str):
            query = f"""SELECT * FROM {safe_table_name}
                        WHERE trade_date BETWEEN %s AND %s"""
            params = (args[0], args[1])


        # query = ""
        # params = ()
        # if len(args) == 1 and isinstance(args[0], int):
        #     # Last X data points
        #     query = f"SELECT * FROM {table_name} ORDER BY trade_date DESC LIMIT %s"
        #     params = (args[0],)
        # elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], int):
        #     # X data after start_date or before end_date based on date format
        #     if '-' in args[0]:  # likely a date string
        #         query = f"SELECT * FROM {table_name} WHERE trade_date >= '%s' ORDER BY trade_date ASC LIMIT %s"
        #     else:
        #         query = f"SELECT * FROM {table_name} WHERE trade_date <= '%s' ORDER BY trade_date DESC LIMIT %s"
        #     params = (args[0], args[1])
        # elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str):
        #     # X data after start_date or before end_date based on date format
        #     if '-' in args[0] and '-' in args[1]:  # likely a date string
        #         query = f"SELECT * FROM {table_name} WHERE trade_date >= '%s' AND trade_date <= %s"
        #     params = (args[0], args[1])
        #
        try:
            if self.conn.is_connected():
                cursor = self.conn.cursor(dictionary=True)
                cursor.execute(query, params)
                result = cursor.fetchall()
                df = pd.DataFrame(result)
                if 'DESC' in query:  # If the query was in descending order, reverse the DataFrame
                    df = df.iloc[::-1].reset_index(drop=True)
                return df
        except Error as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()  # Return an empty DataFrame in case of error


    def close(self):
        if self.conn is not None and self.conn.is_connected():
            self.conn.close()
            print('Database connection closed.')

    def check_missing_days(self,
                           start_date=None,
                           coins=None,
                           intervals=None):
        """
        扫描数据库中 [start_date, 昨天] 区间的缺失交易日
        --------------------------------------------------
        :param data_handler: 初始化完成的 DataHandler 实例
        :param start_date:   起始日期 (str|datetime)，默认 '2017-01-01'
        :param coins:        币种列表，默认 rate_price2order 的键（去掉 'ip'）
        :param intervals:    K 线周期列表，默认 ['1m','15m','30m','1h','4h','1d']
        :return: dict{coin → dict{interval → list[缺失日期(date)]}}
        """
        # ⚑ 默认配置
        if intervals is None:
            intervals = ['1m', '15m', '30m', '1h', '4h', '1d']
        if coins is None:
            coins = [x for x in rate_price2order.keys() if x != 'ip']

        missing_map = {}

        for cc in coins:
            if not start_date:
                start_date = find_start_date(base_url, cc.upper() + 'USDT', '1d')
            start_dt = pd.to_datetime(start_date)
            end_dt = datetime.utcnow().date() - timedelta(days=1)  # 昨天

            coin = cc.upper() + 'USDT'
            for interval in intervals:
                try:
                    # ① 一次性拉取日期列
                    df = self.fetch_data(
                        coin, interval,
                        start_dt.strftime("%Y-%m-%d"),  # 无需时分秒
                        end_dt.strftime("%Y-%m-%d 23:59:59")
                    )
                    if df.empty:
                        # 数据全缺，直接记录整段
                        exp_days = pd.date_range(start_dt, end_dt, freq='D').date
                        missing_map.setdefault(coin, {})[interval] = list(exp_days)
                        print(f"[空表] {coin}-{interval} 缺失 {len(exp_days)} 天")
                        continue

                    # ② 现有日期集合
                    df['trade_date'] = pd.to_datetime(df['trade_date'], unit='ms')
                    present_days = set(df['trade_date'].dt.date.unique())

                    # ③ 期望日期集合
                    expected_days = pd.date_range(start_dt, end_dt, freq='D').date
                    missing_days = sorted(set(expected_days) - present_days)

                    if missing_days:  # 仅记录缺失
                        missing_map.setdefault(coin, {})[interval] = missing_days
                        print(f"[缺失] {coin}-{interval}: {len(missing_days)} 天")
                except Exception as e:
                    print(f"检查失败 {coin}-{interval}: {e}")
            start_date = None
        return missing_map



def fetch_kline_data(exchange, interval, limit, symbol):
    """
    获取指定交易对和时间段的K线数据。
    :param exchange: OkexSpot 实例。
    :param interval: K线图的时间间隔。
    :param limit: 返回的数据数量。
    :param symbol: 交易对，如 'ETH-USDT'。
    :return: K线数据的DataFrame。
    """
    df, _ = exchange.get_kline(interval, limit, symbol)
    return df


def check_data_exists(base_url, symbol, interval, date):
    date_str = date.strftime('%Y-%m-%d')
    filename = f"{symbol}-{interval}-{date_str}.zip"
    url = f"{base_url}/{symbol}/{interval}/{filename}"
    response = requests.get(url)
    return response.status_code == 200


# ── 缓存文件位置 ──────────────────────────────────────────────
CACHE_PATH = os.path.expanduser("~/Quantify/okx/trade_log_okex")
CACHE_FILE = os.path.join(CACHE_PATH, "start_date_cache.json")

def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}        # 读失败则视为无缓存

def _save_cache(cache):
    os.makedirs(CACHE_PATH, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, default=str, indent=2)

def find_start_date(base_url, symbol, interval, earliest_date=datetime(2015, 1, 1), latest_date=datetime.now()):
    key = f"{symbol}_{interval}"
    cache = _load_cache()

    # ① 命中缓存，直接返回
    if key in cache:
        cached_val = datetime.fromisoformat(cache[key])
        print(f"⚡ 缓存命中：{symbol}-{interval} -> {cached_val.date()}")
        return cached_val

    # ② 否则执行原逻辑（网络二分查找）
    print(f"🔍 正在查找 {symbol} - {interval} 最早的数据起始时间...")
    left, right, result = earliest_date, latest_date, None

    while left <= right:
        mid = left + (right - left) // 2
        exists = check_data_exists(base_url, symbol, interval, mid)
        print(f"检查 {mid.strftime('%Y-%m-%d')} : {'存在✅' if exists else '不存在❌'}")

        if exists:
            result = mid
            right = mid - timedelta(days=1)
        else:
            left = mid + timedelta(days=1)

    print(f"📌 最早的数据起始时间是：{result if result else '未找到'}")

    # ③ 写入缓存（仅在找到结果时）
    if result:
        cache[key] = result.isoformat()
        _save_cache(cache)

    return result


def download_and_process_binance_data(base_url, symbol, start_date, end_date, intervals, missing_days=None):
    """
    Download and process Binance k-line data from the specified URL.
    """
    # 1⃣ 预生成待处理日期列表
    if missing_days is None:
        all_days = pd.date_range(start_date.date(), end_date.date() - timedelta(days=1), freq='D').date
    else:
        all_days = sorted(missing_days)   # 转成 list 并排序，便于 tqdm

    # 2⃣ 遍历 interval 与日期
    for interval in intervals:
        for day in tqdm(all_days, desc=f"download_and_process_binance_data {symbol}-{interval}"):
            # 若 missing_days=None 则走全量；若非 None 且 day 不在集合，也不会进来
            date_str = day.strftime('%Y-%m-%d')
            filename = f"{symbol}-{interval}-{date_str}.zip"
            csv_filename = f"{symbol}-{interval}-{date_str}.csv"
            target_csv_path = os.path.join('data/{}'.format(interval), csv_filename)
            # Check if the file already exists to avoid re-downloading
            IS_DOWNLOAD = False
            if not os.path.exists(target_csv_path):
                # print('\r{} - {} --> {}'.format(interval, current_date, end_date), end='')
                time.sleep(0.1 + random.randint(0, 20) / 20)
                # Construct the URL and download the file
                url = f"{base_url}/{symbol}/{interval}/{filename}"
                response = requests.get(url)
                if response.status_code == 200:
                    # Save the zip file temporarily
                    zip_path = os.path.join('data/{}'.format(interval), filename)
                    with open(zip_path, 'wb') as f:
                        f.write(response.content)

                    # Extract the zip file
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall('data/{}'.format(interval))

                    # Rename and move the extracted CSV file
                    extracted_file = os.path.join('data/{}'.format(interval), csv_filename.replace('.csv',
                                                                               '.csv'))  # Assuming the extracted file has a predictable name
                    os.rename(extracted_file, target_csv_path)

                    # Remove the zip file after extraction
                    os.remove(zip_path)
                    IS_DOWNLOAD = True
                elif response.status_code == 404:
                    time.sleep(0.1)
                    continue
                else:
                    time.sleep(0.2)
                    print(f"Failed to download data for {date_str}: Status code {response.status_code}")
            # Read, process, and save the CSV data
            if os.path.exists(target_csv_path) and IS_DOWNLOAD:
                df = pd.read_csv(target_csv_path, header=None,
                                 names=["Open time", "Open", "High", "Low", "Close", "Volume", "Close time",
                                        "Quote asset volume", "Number of trades", "Taker buy base asset volume",
                                        "Taker buy quote asset volume", "Ignore"])
                try:
                    ### 2025年开始的数据采用了更细粒度的时间，一直无法转换，气人
                    open_time = pd.to_numeric(df['Open time'], errors='coerce')
                    # 如果时间戳太大，尝试除以 1000 或 1000000 缩小到毫秒级
                    if open_time.max() > 1e13:
                        open_time = open_time // 1000  # 转换为毫秒级
                    df['trade_date'] = pd.to_datetime(open_time, unit='ms')
                    # df['trade_date'] = pd.to_datetime(df['Open time'], unit='ms')
                    df['vol1'] = df['Quote asset volume']
                    df['vol'] = df['Volume']
                    df = df[['trade_date', 'Open', 'High', 'Low', 'Close', 'vol1', 'vol']]
                    df.columns = df.columns.str.lower()
                    df.to_csv(target_csv_path, index=False)
                except Exception as e:
                    print('\n', e, '\n', target_csv_path, '\n333333333333', '\n', df)
                    if str(e).find('Out of b') != -1:
                        break


def parse_trade_date(trade_date):
    """
    接收 Timestamp / datetime / int(ms|s) / str，统一返回 '%Y-%m-%d %H:%M:%S'
    """
    # ① Timestamp 或 datetime
    if isinstance(trade_date, (pd.Timestamp, datetime)):
        return trade_date.strftime('%Y-%m-%d %H:%M:%S')

    # ② 纯数字：毫秒级或秒级
    if isinstance(trade_date, (int, float)):
        # 粗判：10 位≈秒，13 位≈毫秒
        seconds = trade_date / 1000 if trade_date > 1e11 else trade_date
        return datetime.utcfromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')

    # ③ 字符串 → 尝试解析
    try:
        ts = pd.to_datetime(trade_date, errors='raise')
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        raise ValueError(f"无法解析 trade_date={trade_date}: {e}")



# 20250602 1500 修改完毕 先检查现有数据库的数据，然后查漏补缺去搜索数据
# 20250602 1500 还增加了check_csv_format.py来整体的检查一遍数据的保存格式
def get_all_binance_data(symbol_now='ETHUSDT', missing_days=None):
    # 感恩让我发现数据： https: // bmzhp.com / blockchain / 396
    # Usage example
    symbol = symbol_now
    start_date = find_start_date(base_url, symbol, '1d')
    # start_date = datetime(2020, 5, 1)
    end_date = datetime.now()
    intervals = time_gaps
    download_and_process_binance_data(base_url, symbol, start_date, end_date, intervals, missing_days)


def read_processed_data(symbol, interval, start_date, end_date, missing_days=None):
    """
    Reads processed trading data for a given symbol and interval within a specified date range.

    :param symbol: The trading symbol, e.g., 'ETHUSDT'
    :param interval: The data interval, e.g., '1m', '15m', '30m', '1h', '4h', '1d'
    :param start_date: The start date as a string in 'YYYY-MM-DD' format
    :param end_date: The end date as a string in 'YYYY-MM-DD' format
    :return: A pandas DataFrame containing the requested data
    """
    # Convert start and end dates to datetime objects
    # 0⃣ 统一日期类型
    start_date = pd.to_datetime(start_date).date()
    end_date   = pd.to_datetime(end_date).date()

    # 1⃣ 生成待读取日期列表
    if missing_days is None:
        dates_to_read = pd.date_range(start_date, end_date - timedelta(days=1), freq='D').date
    else:
        # 只保留落在 [start_date, end_date) 区间内的缺失日期，避免越界
        dates_to_read = sorted(d for d in missing_days if start_date <= d < end_date)

    # 2⃣ 遍历并读文件
    data_folder = f"data/{interval}"
    all_data = []

    for day in dates_to_read:
        date_str  = day.strftime('%Y-%m-%d')
        filename  = f"{symbol}-{interval}-{date_str}.csv"
        file_path = os.path.join(data_folder, filename)

        if os.path.exists(file_path):
            df = pd.read_csv(file_path, parse_dates=['trade_date'])  # ⬅️ 一行搞定
            df.columns = df.columns.str.lower()
            all_data.append(df)
        else:
            print(f"⚠️  文件缺失: {file_path}")

    # 3⃣ 合并返回
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        return combined_df
    else:
        return pd.DataFrame()      # 没找到任何数据


# 20250602 1500  将时间段性质的插入，转变为离散时间序列的插入
def batch_insert_data(data_handler, symbol, interval, df, batch_size=1000, missing_days=None):
    # 0⃣ 过滤缺失日
    if missing_days is not None and not df.empty:
        df = df[df['trade_date'].dt.date.isin(missing_days)]
        if df.empty:
            print(f"\r[{symbol}-{interval}] 无需插入（缺失日已全部补齐）", end='')
            return


    # 1⃣ 分批插入
    for start in tqdm(range(0, len(df), batch_size), desc=f"batch_insert_data {symbol}-{interval} insert"):
        end = start + batch_size
        batch_df = df.iloc[start:end]               # iloc 更稳妥
        data_handler.insert_data(symbol, interval, batch_df)
        print(f"Inserted batch rows {start} ~ {end - 1}")

    # 2⃣ 去重
    table_name = f"{symbol.replace('-', '_')}_{interval}"
    data_handler.remove_duplicates(table_name)




# 20250602 1500  需要支持针对特定的日期去插入，指定日期集合，由前面的获取数据函数提供到全局变量中
def insert_binance_data_into_mysql(data_handler, symbol_now='ETHUSDT', missing_days=None):
    symbol     = symbol_now.upper()
    start_date = find_start_date(base_url, symbol, '1d')                     # 可按需改成动态查找
    end_date   = datetime.now()

    for interval in tqdm(time_gaps, desc=f"insert_binance_data_into_mysql {symbol} loop"):
        # ① 读取本地已处理好的 CSV / Parquet
        df = read_processed_data(symbol, interval, start_date, end_date, missing_days)

        if df.empty:
            print(f"[{symbol}-{interval}] 无数据可读")
            continue

        # print(df.head(), '\n', df.tail(), '\n', len(df))

        # ② 批量写入，带 missing_days 过滤
        batch_insert_data(
            data_handler=data_handler,
            symbol=symbol,
            interval=interval,
            df=df,
            missing_days=missing_days              # ⬅️ 新增
        )


def export_daily_data(data_handler, base_path="~/Quantify/okx/data"):
    """
    按天导出K线数据到CSV文件
    :param data_handler: 已初始化的DataHandler实例
    :param base_path: 基础存储路径（默认 ~/Quantify/okx/data）
    """
    # 配置参数
    time_gaps = ['1m', '15m', '30m', '1h', '4h', '1d']
    coins = [x for x in list(rate_price2order.keys()) if x != 'ip']  # 替换为你的币种列表

    for cc in coins:
        for interval in time_gaps:
            # 获取表名对应的所有日期
            try:
                coin = cc.upper()+'USDT'
                # 查询所有数据点（仅获取日期列）
                df_all = data_handler.fetch_data(coin, interval, '2017-01-01', '2025-05-03')  # 假设足够大的数获取全部数据
                if df_all.empty:
                    print(f"无数据可导出: {coin}_{interval}")
                    continue

                # 转换日期列为日期对象
                df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
                # 提取唯一日期（按天分组）
                unique_dates = df_all['trade_date'].dt.date.unique()

                # 按天导出
                for date in unique_dates:
                    # 构造时间范围
                    start_time = datetime.combine(date, datetime.min.time())
                    end_time = start_time + timedelta(days=1) - timedelta(seconds=1)

                    # 获取当天数据
                    df_day = data_handler.fetch_data(
                        coin, interval,
                        start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        end_time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    if df_day.empty:
                        continue

                    # 创建目录
                    save_dir = os.path.expanduser(os.path.join(base_path, interval))
                    os.makedirs(save_dir, exist_ok=True)

                    # 生成文件名
                    filename = f"{coin}-{interval}-{date.strftime('%Y-%m-%d')}.csv"
                    filepath = os.path.join(save_dir, filename)

                    if os.path.exists(filepath):
                        print(f"\r 已存在: {filepath}", end='')
                    else:
                        # 保存CSV
                        df_day.to_csv(filepath, index=False)
                        print(f"\r已保存: {filepath}" ,end='')

            except Exception as e:
                print(f"处理失败 {coin}_{interval}: {str(e)}")
                continue



# 秒数步长映射
STEP_SEC = {
    '1m': 60,  '5m': 300,  '15m': 900,
    '30m': 1800,  '1h': 3600,  '4h': 14400,
    '1d': 86400
}

def check_and_repair_tables(data_handler, coins, time_gaps):
    """
    对每张表做“逐时间戳扫描”，发现缺口 => 把上一条记录复制插入
    """
    conn = data_handler.conn
    cur  = conn.cursor(dictionary=True)

    for coin in coins:
        symbol = f"{coin.upper()}USDT"
        for iv in time_gaps:
            step = STEP_SEC[iv]
            table = f"{symbol}_{iv}"

            # 0⃣ 最早、最晚时间
            cur.execute(f"SELECT MIN(trade_date) AS min_dt, MAX(trade_date) AS max_dt FROM {table}")
            row = cur.fetchone()
            if not row['min_dt']:
                print(f"[空表] {table} 跳过")
                continue
            t_min, t_max = row['min_dt'], row['max_dt']
            print(f"\n🔍 {table} 扫描 {t_min} → {t_max}")

            # 1⃣ 预编译 SQL
            exist_sql = f"SELECT 1 FROM {table} WHERE trade_date = %s LIMIT 1"
            insert_sql = (
                f"INSERT INTO {table} "
                f"(trade_date, open, high, low, close, vol1, vol)"   # 按实际列改
                f"SELECT %s, open, high, low, close, vol1, vol "
                f"FROM {table} WHERE trade_date = %s LIMIT 1"
            )

            # query = f"""INSERT INTO {table_name}
            #                             (trade_date, open, high, low, close, vol1, vol)
            #                             VALUES (%s, %s, %s, %s, %s, %s, %s)
            #                             ON DUPLICATE KEY UPDATE
            #                             open = VALUES(open), high = VALUES(high), low = VALUES(low),
            #                             close = VALUES(close), vol1 = VALUES(vol1), vol = VALUES(vol);"""

            t_cur   = t_min
            inserted, checked = 0, 0

            while t_cur < t_max:
                t_next = t_cur + timedelta(seconds=step)
                cur.execute(exist_sql, (t_next.strftime("%Y-%m-%d %H:%M:%S"),))
                exists = cur.fetchone()
                checked += 1
                print(f'\r {t_cur}', end='')
                if not exists:
                    # 复制上一行插入
                    cur.execute(insert_sql, (t_next.strftime("%Y-%m-%d %H:%M:%S"), t_cur.strftime("%Y-%m-%d %H:%M:%S")))
                    inserted += 1
                    print(f'\r 检测到 {t_cur} 不存在！插补一次！', end='')
                    if inserted % 5000 == 0:      # 批量提交
                        conn.commit()
                        print(f"   已修补 {inserted} 条 …")

                t_cur = t_next

            conn.commit()
            print(f"✅ {table} 扫描完成，检查 {checked} 步，补 {inserted} 行")

    cur.close()
    print("\n🎉 所有表修补完毕")

if __name__ == '__main__':
    from okex import OkexSpot
    # 假设exchange是OkexSpot的实例化对象
    exchange = OkexSpot(
            symbol="ETH-USD-SWAP",
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            passphrase=PASSPHRASE,
            host=None
        )
    # 调用fetch_kline_data函数获取K线数据
    # df_kline_1m = fetch_kline_data(exchange, '1m', 400, 'ETH-USD-SWAP')
    # df_kline_15m = fetch_kline_data(exchange, '15m', 400, 'ETH-USD-SWAP')
    # df_kline_30m = fetch_kline_data(exchange, '30m', 400, 'ETH-USD-SWAP')
    # df_kline_1h = fetch_kline_data(exchange, '1h', 400, 'ETH-USD-SWAP')
    # df_kline_4h = fetch_kline_data(exchange, '4h', 400, 'ETH-USD-SWAP')
    # df_kline_1d = fetch_kline_data(exchange, '1d', 400, 'ETH-USD-SWAP')

    # 显示获取的数据
    # print(df_kline_1m.head())

    # 假设data_handler是DataHandler的实例化对象
    data_handler = DataHandler(HOST_IP_1, 'TradingData', HOST_USER, HOST_PASSWD)
    #
    # # 将数据插入到数据库中
    # data_handler.insert_data( 'ETH-USD-SWAP', '1m', df_kline_1m)
    # data_handler.insert_data( 'ETH-USD-SWAP', '15m', df_kline_15m)
    # data_handler.insert_data( 'ETH-USD-SWAP', '30m', df_kline_30m)
    # data_handler.insert_data( 'ETH-USD-SWAP', '1h', df_kline_1h)
    # data_handler.insert_data( 'ETH-USD-SWAP', '4h', df_kline_4h)
    # data_handler.insert_data( 'ETH-USD-SWAP', '1d', df_kline_1d)
    # 'xrp', 'bnb', 'sol', 'ada', 'doge', 'trx',

    # export_daily_data(data_handler)

    time_gaps = ['1m', '15m', '30m', '1h', '4h', '1d']
    # time_gaps = ['1m']
    coins = list(rate_price2order.keys())
    check_and_repair_tables(data_handler, coins, time_gaps)
    # for coin in [x for x in coins]:
    #     for interval in time_gaps:
    #         try:
    #             coin_name = coin.upper() + 'USDT'
    #             # data_handler.remove_duplicates(coin_name + '_' + interval)
    #             missing_days = data_handler.check_missing_days(coins=[coin], intervals=[interval])
    #             # print(missing_days)
    #             print('process coin:', coin_name, len(missing_days[coin_name][interval]))
    #             get_all_binance_data(coin_name, missing_days[coin_name][interval])
    #             insert_binance_data_into_mysql(data_handler, coin_name, missing_days[coin_name][interval])
    #             os.system(f'echo {coin_name}日线完成 {" ".join(time_gaps)} >> 下载币安数据.txt')
    #         except Exception as e:
    #             print('qqqq', e)
    data_handler.close()

#
# coins = ['btc', 'eth', 'xrp', 'bnb', 'sol', 'ada', 'doge', 'trx', 'ltc', 'shib', 'link', 'dot', 'om', 'apt', 'uni', 'hbar', 'ton', 'sui', 'avax', 'fil', 'ip', 'gala', 'sand']
#
# for c in coins:
#     tbl = f"{c.upper()}USDT_1d"
#     print(
#         f"SELECT COUNT(*) "
#         f"FROM {tbl} "
#         f"WHERE trade_date > '2024-01-01 00:00:00';"
#     )