"""
数据处理器服务 - 支持数据抓取和HTTP API服务两种模式
"""
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
import json
from collections import defaultdict
from mysql.connector.errors import DatabaseError
import argparse
import sys
from pathlib import Path

# 导入配置和工具函数
try:
    from ctos.drivers.okx.util import base_url, rate_price2order
except ImportError:
    # 如果导入失败，使用默认值
    base_url = "https://data.binance.vision/data/spot/daily/klines"
    rate_price2order = {
        'btc': 0.01, 'eth': 0.1, 'xrp': 100, 'bnb': 0.01, 'sol': 1,
        'ada': 100, 'doge': 1000, 'trx': 1000, 'ltc': 1, 'shib': 1000000,
        'link': 1, 'dot': 1, 'om': 10, 'apt': 1, 'uni': 1, 'hbar': 100,
        'ton': 1, 'sui': 1, 'avax': 1, 'fil': 0.1, 'ip': 1, 'gala': 10,
        'sand': 10, 'trump': 0.1, 'pol': 10, 'icp': 0.01, 'cro': 10,
        'aave': 0.1, 'xlm': 100, 'bch': 0.1, 'xaut': 0.001, 'core': 1,
        'theta': 10, 'algo': 10, 'etc': 10, 'near': 10, 'hype': 0.1,
        'inj': 0.1, 'ldo': 1, 'atom': 1, 'pengu': 100, 'wld': 1,
        'render': 1, 'pepe': 10000000, 'ondo': 10, 'stx': 10, 'arb': 10,
        'jup': 10, 'bonk': 100000, 'op': 1, 'tia': 1, 'crv': 1, 'imx': 1, 'xtz': 1
    }

try:
    from ctos.core.runtime.Config import HOST_IP_1, HOST_USER, HOST_PASSWD
except ImportError:
    HOST_IP_1 = "localhost"
    HOST_USER = "user"
    HOST_PASSWD = "password"

# 配置常量
DEFAULT_TIME_GAPS = ['1m', '15m', '30m', '1h', '4h', '1d']
STEP_SEC = {
    '1m': 60, '5m': 300, '15m': 900,
    '30m': 1800, '1h': 3600, '4h': 14400,
    '1d': 86400
}

# 获取 storage 目录路径 - 指向 ctos/core/io/storage
_STORAGE_BASE = Path(__file__).parent.parent / 'storage'
_STORAGE_BASE.mkdir(exist_ok=True)
STORAGE_PATH = _STORAGE_BASE
DATA_PATH = STORAGE_PATH / 'data'
CACHE_PATH = STORAGE_PATH / 'cache'
CACHE_FILE = CACHE_PATH / 'start_date_cache.json'

# 创建必要的目录
DATA_PATH.mkdir(exist_ok=True)
CACHE_PATH.mkdir(exist_ok=True)

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
    """数据处理核心类"""
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
                print('DataHandler 初始化成功')
        except Error as e:
            print(f'数据库连接失败: {e}')

    def create_table_if_not_exists(self, cursor, table_name):
        """创建表（如果不存在）"""
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
            print(f"表 {table_name} 创建成功")
        except Error as e:
            print(f"创建表 {table_name} 失败: {e}")

    def insert_data(self, symbol, interval, data, remove_duplicates=False):
        """插入数据到数据库"""
        table_name = f"{symbol.replace('-', '_')}_{interval}"
        try:
            if self.conn.is_connected():
                cursor = self.conn.cursor()
                query = f"""INSERT INTO {table_name}
                            (trade_date, open, high, low, close, vol1, vol)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            open = VALUES(open), high = VALUES(high), low = VALUES(low),
                            close = VALUES(close), vol1 = VALUES(vol1), vol = VALUES(vol);"""
                
                data['vol1'] = data['vol1'] / 1e6
                formatted_data = [
                    (
                        parse_trade_date(row['trade_date']),
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
                print(cursor.rowcount, "条记录已插入", table_name)
                if remove_duplicates:
                    self.remove_duplicates(table_name)
            else:
                print('数据库未连接')
        except Error as e:
            print(f'插入数据失败: {e}')

    def remove_duplicates(self, table_name):
        """移除重复数据"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"CREATE TEMPORARY TABLE keep_dates AS "
                            f"SELECT MIN(trade_date) AS trade_date FROM {table_name} GROUP BY trade_date")

                cur.execute(f"""
                    DELETE t FROM {table_name} t
                    LEFT JOIN keep_dates k USING (trade_date)
                    WHERE k.trade_date IS NULL;
                """)
                self.conn.commit()
                cur.execute("DROP TEMPORARY TABLE keep_dates")
                print(f"已移除表 {table_name} 中的重复数据")
        except Error as e:
            print(f"移除重复数据失败: {e}")

    def fetch_data(self, symbol, interval, *args):
        """
        获取数据
        - 一个参数: 获取最后 X 条数据
        - 两个参数(日期字符串, 整数): 从指定日期开始/结束获取 X 条数据
        - 两个参数(两个日期字符串): 获取指定日期范围的数据
        """
        table_name = f"{symbol.replace('-', '_')}_{interval}"
        safe_table_name = table_name

        if len(args) == 1 and isinstance(args[0], int):
            query = f"SELECT * FROM {safe_table_name} ORDER BY trade_date DESC LIMIT %s"
            params = (args[0],)

        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], int):
            if '-' in args[0]:
                query = f"""SELECT * FROM {safe_table_name}
                            WHERE trade_date >= %s
                            ORDER BY trade_date ASC
                            LIMIT %s"""
            else:
                query = f"""SELECT * FROM {safe_table_name}
                            WHERE trade_date <= %s
                            ORDER BY trade_date DESC
                            LIMIT %s"""
            params = (args[0], args[1])

        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str):
            query = f"""SELECT * FROM {safe_table_name}
                        WHERE trade_date BETWEEN %s AND %s"""
            params = (args[0], args[1])
        else:
            return pd.DataFrame()

        try:
            if self.conn.is_connected():
                cursor = self.conn.cursor(dictionary=True)
                cursor.execute(query, params)
                result = cursor.fetchall()
                df = pd.DataFrame(result)
                if 'DESC' in query:
                    df = df.iloc[::-1].reset_index(drop=True)
                return df
        except Error as e:
            print(f"获取数据失败: {e}")
            return pd.DataFrame()

    def close(self):
        """关闭数据库连接"""
        if self.conn is not None and self.conn.is_connected():
            self.conn.close()
            print('数据库连接已关闭')

    def check_missing_days(self, start_date=None, coins=None, intervals=None):
        """检查缺失的交易日"""
        if intervals is None:
            intervals = DEFAULT_TIME_GAPS
        if coins is None:
            coins = [x for x in rate_price2order.keys() if x != 'ip']

        missing_map = {}

        for cc in coins:
            if not start_date:
                start_date = find_start_date(base_url, cc.upper() + 'USDT', '1d')
            start_dt = pd.to_datetime(start_date)
            end_dt = datetime.utcnow().date() - timedelta(days=1)

            coin = cc.upper() + 'USDT'
            for interval in intervals:
                try:
                    df = self.fetch_data(
                        coin, interval,
                        start_dt.strftime("%Y-%m-%d"),
                        end_dt.strftime("%Y-%m-%d 23:59:59")
                    )
                    if df.empty:
                        exp_days = pd.date_range(start_dt, end_dt, freq='D').date
                        missing_map.setdefault(coin, {})[interval] = list(exp_days)
                        print(f"[空表] {coin}-{interval} 缺失 {len(exp_days)} 天")
                        continue

                    df['trade_date'] = pd.to_datetime(df['trade_date'], unit='ms')
                    present_days = set(df['trade_date'].dt.date.unique())
                    expected_days = pd.date_range(start_dt, end_dt, freq='D').date
                    missing_days = sorted(set(expected_days) - present_days)

                    if missing_days:
                        missing_map.setdefault(coin, {})[interval] = missing_days
                        print(f"[缺失] {coin}-{interval}: {len(missing_days)} 天")
                except Exception as e:
                    print(f"检查失败 {coin}-{interval}: {e}")
            start_date = None
        return missing_map


def check_data_exists(base_url, symbol, interval, date):
    """检查数据是否存在"""
    date_str = date.strftime('%Y-%m-%d')
    filename = f"{symbol}-{interval}-{date_str}.zip"
    url = f"{base_url}/{symbol}/{interval}/{filename}"
    response = requests.get(url)
    return response.status_code == 200


def _load_cache():
    """加载缓存"""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    """保存缓存"""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, default=str, indent=2)


def find_start_date(base_url, symbol, interval, earliest_date=datetime(2015, 1, 1), latest_date=datetime.now()):
    """查找数据的起始日期"""
    key = f"{symbol}_{interval}"
    cache = _load_cache()

    if key in cache:
        cached_val = datetime.fromisoformat(cache[key])
        print(f"⚡ 缓存命中：{symbol}-{interval} -> {cached_val.date()}")
        return cached_val

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

    if result:
        cache[key] = result.isoformat()
        _save_cache(cache)

    return result


def download_and_process_binance_data(base_url, symbol, start_date, end_date, intervals, missing_days=None):
    """下载并处理币安数据"""
    if missing_days is None:
        all_days = pd.date_range(start_date.date(), end_date.date() - timedelta(days=1), freq='D').date
    else:
        all_days = sorted(missing_days)

    for interval in intervals:
        interval_dir = DATA_PATH / interval
        interval_dir.mkdir(exist_ok=True)
        
        for day in tqdm(all_days, desc=f"下载 {symbol}-{interval}"):
            date_str = day.strftime('%Y-%m-%d')
            filename = f"{symbol}-{interval}-{date_str}.zip"
            csv_filename = f"{symbol}-{interval}-{date_str}.csv"
            target_csv_path = interval_dir / csv_filename
            
            IS_DOWNLOAD = False
            if not target_csv_path.exists():
                time.sleep(0.1 + random.randint(0, 20) / 20)
                url = f"{base_url}/{symbol}/{interval}/{filename}"
                response = requests.get(url)
                if response.status_code == 200:
                    zip_path = interval_dir / filename
                    with open(zip_path, 'wb') as f:
                        f.write(response.content)

                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(interval_dir)

                    extracted_file = interval_dir / csv_filename.replace('.csv', '.csv')
                    if extracted_file.exists():
                        extracted_file.rename(target_csv_path)
                    
                    zip_path.unlink()
                    IS_DOWNLOAD = True
                elif response.status_code == 404:
                    time.sleep(0.1)
                    continue
                else:
                    time.sleep(0.2)
                    print(f"下载失败 {date_str}: 状态码 {response.status_code}")
            
            if target_csv_path.exists() and IS_DOWNLOAD:
                df = pd.read_csv(target_csv_path, header=None,
                                 names=["Open time", "Open", "High", "Low", "Close", "Volume", "Close time",
                                        "Quote asset volume", "Number of trades", "Taker buy base asset volume",
                                        "Taker buy quote asset volume", "Ignore"])
                try:
                    open_time = pd.to_numeric(df['Open time'], errors='coerce')
                    if open_time.max() > 1e13:
                        open_time = open_time // 1000
                    df['trade_date'] = pd.to_datetime(open_time, unit='ms')
                    df['vol1'] = df['Quote asset volume']
                    df['vol'] = df['Volume']
                    df = df[['trade_date', 'Open', 'High', 'Low', 'Close', 'vol1', 'vol']]
                    df.columns = df.columns.str.lower()
                    df.to_csv(target_csv_path, index=False)
                except Exception as e:
                    print('\n', e, '\n', target_csv_path, '\n', df)
                    if str(e).find('Out of b') != -1:
                        break


def parse_trade_date(trade_date):
    """解析交易日期"""
    if isinstance(trade_date, (pd.Timestamp, datetime)):
        return trade_date.strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(trade_date, (int, float)):
        seconds = trade_date / 1000 if trade_date > 1e11 else trade_date
        return datetime.utcfromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')

    try:
        ts = pd.to_datetime(trade_date, errors='raise')
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        raise ValueError(f"无法解析 trade_date={trade_date}: {e}")


def get_all_binance_data(symbol_now='ETHUSDT', missing_days=None):
    """获取所有币安数据"""
    symbol = symbol_now
    start_date = find_start_date(base_url, symbol, '1d')
    end_date = datetime.now()
    intervals = DEFAULT_TIME_GAPS
    download_and_process_binance_data(base_url, symbol, start_date, end_date, intervals, missing_days)


def read_processed_data(symbol, interval, start_date, end_date, missing_days=None):
    """读取处理后的数据"""
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()

    if missing_days is None:
        dates_to_read = pd.date_range(start_date, end_date - timedelta(days=1), freq='D').date
    else:
        dates_to_read = sorted(d for d in missing_days if start_date <= d < end_date)

    interval_dir = DATA_PATH / interval
    all_data = []

    for day in dates_to_read:
        date_str = day.strftime('%Y-%m-%d')
        filename = f"{symbol}-{interval}-{date_str}.csv"
        file_path = interval_dir / filename

        if file_path.exists():
            df = pd.read_csv(file_path, parse_dates=['trade_date'])
            df.columns = df.columns.str.lower()
            all_data.append(df)
        else:
            print(f"⚠️  文件缺失: {file_path}")

    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        return combined_df
    else:
        return pd.DataFrame()


def batch_insert_data(data_handler, symbol, interval, df, batch_size=1000, missing_days=None):
    """批量插入数据"""
    if missing_days is not None and not df.empty:
        df = df[df['trade_date'].dt.date.isin(missing_days)]
        if df.empty:
            print(f"\r[{symbol}-{interval}] 无需插入（缺失日已全部补齐）", end='')
            return

    for start in tqdm(range(0, len(df), batch_size), desc=f"批量插入 {symbol}-{interval}"):
        end = start + batch_size
        batch_df = df.iloc[start:end]
        data_handler.insert_data(symbol, interval, batch_df)
        print(f"已插入批次 {start} ~ {end - 1}")

    table_name = f"{symbol.replace('-', '_')}_{interval}"
    data_handler.remove_duplicates(table_name)


def insert_binance_data_into_mysql(data_handler, symbol_now='ETHUSDT', missing_days=None):
    """将币安数据插入MySQL"""
    symbol = symbol_now.upper()
    start_date = find_start_date(base_url, symbol, '1d')
    end_date = datetime.now()

    for interval in tqdm(DEFAULT_TIME_GAPS, desc=f"插入数据 {symbol}"):
        df = read_processed_data(symbol, interval, start_date, end_date, missing_days)

        if df.empty:
            print(f"[{symbol}-{interval}] 无数据可读")
            continue

        batch_insert_data(
            data_handler=data_handler,
            symbol=symbol,
            interval=interval,
            df=df,
            missing_days=missing_days
        )


def export_daily_data(data_handler, base_path=None):
    """按天导出K线数据到CSV文件"""
    if base_path is None:
        base_path = STORAGE_PATH / 'exported_data'
    else:
        base_path = Path(base_path).expanduser()
    
    base_path.mkdir(exist_ok=True)
    
    time_gaps = DEFAULT_TIME_GAPS
    coins = [x for x in list(rate_price2order.keys()) if x != 'ip']

    for cc in coins:
        for interval in time_gaps:
            try:
                coin = cc.upper() + 'USDT'
                df_all = data_handler.fetch_data(coin, interval, '2017-01-01', '2025-05-03')
                if df_all.empty:
                    print(f"无数据可导出: {coin}_{interval}")
                    continue

                df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
                unique_dates = df_all['trade_date'].dt.date.unique()

                for date in unique_dates:
                    start_time = datetime.combine(date, datetime.min.time())
                    end_time = start_time + timedelta(days=1) - timedelta(seconds=1)

                    df_day = data_handler.fetch_data(
                        coin, interval,
                        start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        end_time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    if df_day.empty:
                        continue

                    save_dir = base_path / interval
                    save_dir.mkdir(exist_ok=True)

                    filename = f"{coin}-{interval}-{date.strftime('%Y-%m-%d')}.csv"
                    filepath = save_dir / filename

                    if filepath.exists():
                        print(f"\r 已存在: {filepath}", end='')
                    else:
                        df_day.to_csv(filepath, index=False)
                        print(f"\r已保存: {filepath}", end='')

            except Exception as e:
                print(f"处理失败 {coin}_{interval}: {str(e)}")
                continue


def check_and_repair_tables(data_handler, coins, time_gaps):
    """检查并修复表中的数据缺口"""
    conn = data_handler.conn
    cur = conn.cursor(dictionary=True)

    for coin in coins:
        symbol = f"{coin.upper()}USDT"
        for iv in time_gaps:
            step = STEP_SEC[iv]
            table = f"{symbol}_{iv}"

            cur.execute(f"SELECT MIN(trade_date) AS min_dt, MAX(trade_date) AS max_dt FROM {table}")
            row = cur.fetchone()
            if not row['min_dt']:
                print(f"[空表] {table} 跳过")
                continue
            t_min, t_max = row['min_dt'], row['max_dt']
            print(f"\n🔍 {table} 扫描 {t_min} → {t_max}")

            exist_sql = f"SELECT 1 FROM {table} WHERE trade_date = %s LIMIT 1"
            insert_sql = (
                f"INSERT INTO {table} "
                f"(trade_date, open, high, low, close, vol1, vol) "
                f"SELECT %s, open, high, low, close, vol1, vol "
                f"FROM {table} WHERE trade_date = %s LIMIT 1"
            )

            t_cur = t_min
            inserted, checked = 0, 0

            while t_cur < t_max:
                t_next = t_cur + timedelta(seconds=step)
                cur.execute(exist_sql, (t_next.strftime("%Y-%m-%d %H:%M:%S"),))
                exists = cur.fetchone()
                checked += 1
                print(f'\r {t_cur}', end='')
                if not exists:
                    cur.execute(insert_sql, (t_next.strftime("%Y-%m-%d %H:%M:%S"), t_cur.strftime("%Y-%m-%d %H:%M:%S")))
                    inserted += 1
                    print(f'\r 检测到 {t_cur} 不存在！插补一次！', end='')
                    if inserted % 5000 == 0:
                        conn.commit()
                        print(f"   已修补 {inserted} 条 …")

                t_cur = t_next

            conn.commit()
            print(f"✅ {table} 扫描完成，检查 {checked} 步，补 {inserted} 行")

    cur.close()
    print("\n🎉 所有表修补完毕")


# ==================== 命令行和API服务部分 ====================

def run_sync_mode(args):
    """运行数据同步模式 - 检查缺失 -> 下载 -> 插入"""
    print("=" * 60)
    print("数据同步模式 - 完整同步")
    print("=" * 60)
    
    data_handler = DataHandler(args.host, args.database, args.user, args.password)
    
    if not data_handler.conn or not data_handler.conn.is_connected():
        print("❌ 数据库连接失败，无法继续")
        return
    
    coins = args.coins if args.coins else list(rate_price2order.keys())
    intervals = args.intervals if args.intervals else DEFAULT_TIME_GAPS
    
    # 同步数据：检查缺失 -> 下载 -> 插入
    for coin in coins:
        try:
            coin_name = coin.upper() + 'USDT'
            print(f"\n处理币种: {coin_name}")
            
            missing_days = data_handler.check_missing_days(
                start_date=args.start_date,
                coins=[coin],
                intervals=intervals
            )
            
            if coin_name in missing_days:
                for interval in intervals:
                    if interval in missing_days[coin_name]:
                        missing_list = missing_days[coin_name][interval]
                        if missing_list:
                            print(f"  {coin_name}-{interval}: 缺失 {len(missing_list)} 天")
                            get_all_binance_data(coin_name, missing_list)
                            insert_binance_data_into_mysql(data_handler, coin_name, missing_list)
        except Exception as e:
            print(f'处理 {coin} 时出错: {e}')
    
    data_handler.close()
    print("\n✅ 数据同步完成")


def run_download_mode(args):
    """运行下载模式 - 仅下载数据"""
    print("=" * 60)
    print("下载模式 - 仅下载数据")
    print("=" * 60)
    
    coins = args.coins if args.coins else list(rate_price2order.keys())
    
    for coin in coins:
        coin_name = coin.upper() + 'USDT'
        print(f"\n下载币种: {coin_name}")
        get_all_binance_data(coin_name, args.missing_days)
    
    print("\n✅ 数据下载完成")


def run_insert_mode(args):
    """运行插入模式 - 仅插入数据"""
    print("=" * 60)
    print("插入模式 - 仅插入数据")
    print("=" * 60)
    
    data_handler = DataHandler(args.host, args.database, args.user, args.password)
    
    if not data_handler.conn or not data_handler.conn.is_connected():
        print("❌ 数据库连接失败，无法继续")
        return
    
    coins = args.coins if args.coins else list(rate_price2order.keys())
    
    for coin in coins:
        coin_name = coin.upper() + 'USDT'
        print(f"\n插入币种: {coin_name}")
        insert_binance_data_into_mysql(data_handler, coin_name, args.missing_days)
    
    data_handler.close()
    print("\n✅ 数据插入完成")


def run_repair_mode(args):
    """运行修复模式 - 修复表数据"""
    print("=" * 60)
    print("修复模式 - 修复表数据")
    print("=" * 60)
    
    data_handler = DataHandler(args.host, args.database, args.user, args.password)
    
    if not data_handler.conn or not data_handler.conn.is_connected():
        print("❌ 数据库连接失败，无法继续")
        return
    
    coins = args.coins if args.coins else list(rate_price2order.keys())
    intervals = args.intervals if args.intervals else DEFAULT_TIME_GAPS
    
    check_and_repair_tables(data_handler, coins, intervals)
    
    data_handler.close()
    print("\n✅ 表修复完成")


def run_export_mode(args):
    """运行导出模式 - 导出数据"""
    print("=" * 60)
    print("导出模式 - 导出数据到CSV")
    print("=" * 60)
    
    data_handler = DataHandler(args.host, args.database, args.user, args.password)
    
    if not data_handler.conn or not data_handler.conn.is_connected():
        print("❌ 数据库连接失败，无法继续")
        return
    
    export_daily_data(data_handler, args.export_path)
    
    data_handler.close()
    print("\n✅ 数据导出完成")


def run_server_mode(args):
    """运行HTTP API服务模式"""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("❌ 需要安装 Flask: pip install flask")
        return
    
    print("=" * 60)
    print("HTTP API 服务模式")
    print("=" * 60)
    
    app = Flask(__name__)
    data_handler = DataHandler(args.host, args.database, args.user, args.password)
    
    if not data_handler.conn or not data_handler.conn.is_connected():
        print("❌ 数据库连接失败，无法启动服务")
        return
    
    @app.route('/health', methods=['GET'])
    def health():
        """健康检查"""
        return jsonify({'status': 'ok', 'service': 'DataHandler API'})
    
    @app.route('/api/data', methods=['GET'])
    def get_data():
        """获取K线数据"""
        try:
            symbol = request.args.get('symbol', 'ETHUSDT')
            interval = request.args.get('interval', '1d')
            
            # 支持多种查询方式
            limit = request.args.get('limit', type=int)
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            if limit:
                df = data_handler.fetch_data(symbol, interval, limit)
            elif start_date and end_date:
                df = data_handler.fetch_data(symbol, interval, start_date, end_date)
            elif start_date:
                limit = request.args.get('limit', 100, type=int)
                df = data_handler.fetch_data(symbol, interval, start_date, limit)
            else:
                df = data_handler.fetch_data(symbol, interval, 100)
            
            if df.empty:
                return jsonify({'error': 'No data found'}), 404
            
            # 转换为字典列表
            result = df.to_dict('records')
            return jsonify({
                'symbol': symbol,
                'interval': interval,
                'count': len(result),
                'data': result
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/missing', methods=['GET'])
    def check_missing():
        """检查缺失数据"""
        try:
            coins = request.args.getlist('coins') or None
            intervals = request.args.getlist('intervals') or None
            start_date = request.args.get('start_date')
            
            missing = data_handler.check_missing_days(
                start_date=start_date,
                coins=coins,
                intervals=intervals
            )
            
            return jsonify({
                'missing_days': missing,
                'summary': {
                    coin: {iv: len(days) for iv, days in intervals.items()}
                    for coin, intervals in missing.items()
                }
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/symbols', methods=['GET'])
    def get_symbols():
        """获取支持的交易对列表"""
        return jsonify({
            'symbols': [f"{k.upper()}USDT" for k in rate_price2order.keys() if k != 'ip'],
            'intervals': DEFAULT_TIME_GAPS
        })
    
    host = args.server_host or '0.0.0.0'
    port = args.server_port or 5000
    
    print(f"🚀 服务启动在 http://{host}:{port}")
    print(f"📚 API 文档:")
    print(f"   GET /health - 健康检查")
    print(f"   GET /api/data?symbol=ETHUSDT&interval=1d&limit=100 - 获取数据")
    print(f"   GET /api/data?symbol=ETHUSDT&interval=1d&start_date=2024-01-01&end_date=2024-01-31 - 获取日期范围数据")
    print(f"   GET /api/missing?coins=btc&coins=eth&intervals=1d - 检查缺失数据")
    print(f"   GET /api/symbols - 获取支持的交易对")
    
    app.run(host=host, port=port, debug=args.debug)


def main():
    """主函数 - 命令行入口"""
    parser = argparse.ArgumentParser(
        description='数据处理器服务 - 支持数据同步和HTTP API服务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 数据同步模式 - 自动检查并同步数据
  python DataHandler.py sync --coins btc eth --intervals 1d
  
  # 仅下载数据
  python DataHandler.py download --coins btc
  
  # 仅插入数据
  python DataHandler.py insert --coins btc
  
  # 修复表数据
  python DataHandler.py repair --coins btc eth
  
  # 导出数据
  python DataHandler.py export --export-path ~/data/export
  
  # 启动HTTP API服务
  python DataHandler.py server --host 0.0.0.0 --port 5000
        """
    )
    
    # 添加子命令
    subparsers = parser.add_subparsers(dest='mode', help='运行模式')
    
    # 共享的数据库参数
    def add_db_args(subparser):
        subparser.add_argument('--host', default=HOST_IP_1, help='数据库主机')
        subparser.add_argument('--database', default='TradingData', help='数据库名')
        subparser.add_argument('--user', default=HOST_USER, help='数据库用户')
        subparser.add_argument('--password', default=HOST_PASSWD, help='数据库密码')
    
    # 同步模式子命令
    sync_parser = subparsers.add_parser('sync', help='数据同步模式（检查缺失 -> 下载 -> 插入）')
    add_db_args(sync_parser)
    sync_parser.add_argument('--coins', nargs='+', help='币种列表，如: btc eth xrp')
    sync_parser.add_argument('--intervals', nargs='+', default=DEFAULT_TIME_GAPS,
                            help='时间周期列表，如: 1m 15m 1d')
    sync_parser.add_argument('--start-date', dest='start_date', help='起始日期 YYYY-MM-DD')
    
    # 下载模式子命令
    download_parser = subparsers.add_parser('download', help='仅下载数据')
    download_parser.add_argument('--coins', nargs='+', help='币种列表，如: btc eth xrp')
    download_parser.add_argument('--missing-days', nargs='+', help='缺失日期列表')
    
    # 插入模式子命令
    insert_parser = subparsers.add_parser('insert', help='仅插入数据到数据库')
    add_db_args(insert_parser)
    insert_parser.add_argument('--coins', nargs='+', help='币种列表，如: btc eth xrp')
    insert_parser.add_argument('--missing-days', nargs='+', help='缺失日期列表')
    
    # 修复模式子命令
    repair_parser = subparsers.add_parser('repair', help='修复表数据（补缺）')
    add_db_args(repair_parser)
    repair_parser.add_argument('--coins', nargs='+', help='币种列表，如: btc eth xrp')
    repair_parser.add_argument('--intervals', nargs='+', default=DEFAULT_TIME_GAPS,
                               help='时间周期列表，如: 1m 15m 1d')
    
    # 导出模式子命令
    export_parser = subparsers.add_parser('export', help='导出数据到CSV')
    add_db_args(export_parser)
    export_parser.add_argument('--export-path', help='导出路径')
    
    # 服务器模式子命令
    server_parser = subparsers.add_parser('server', help='HTTP API 服务模式')
    server_parser.add_argument('--host', default='0.0.0.0', dest='server_host',
                              help='服务监听地址 (默认: 0.0.0.0)')
    server_parser.add_argument('--port', type=int, default=5000, dest='server_port',
                              help='服务端口 (默认: 5000)')
    server_parser.add_argument('--db-host', default=HOST_IP_1, dest='host',
                              help='数据库主机')
    server_parser.add_argument('--db-database', default='TradingData', dest='database',
                              help='数据库名')
    server_parser.add_argument('--db-user', default=HOST_USER, dest='user',
                              help='数据库用户')
    server_parser.add_argument('--db-password', default=HOST_PASSWD, dest='password',
                              help='数据库密码')
    server_parser.add_argument('--debug', action='store_true', help='开启调试模式')
    
    args = parser.parse_args()
    
    if not args.mode:
        parser.print_help()
        sys.exit(1)
    
    if args.mode == 'sync':
        run_sync_mode(args)
    elif args.mode == 'download':
        run_download_mode(args)
    elif args.mode == 'insert':
        run_insert_mode(args)
    elif args.mode == 'repair':
        run_repair_mode(args)
    elif args.mode == 'export':
        run_export_mode(args)
    elif args.mode == 'server':
        run_server_mode(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
