import random
import psutil
import sys
import pandas as pd
import numpy as np
from tqdm import tqdm
import time
import warnings
import os
import json
from datetime import datetime, timedelta
import gc
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.signal import savgol_filter    # pip install scipy
import itertools
import mkl; mkl.set_num_threads(1)
from numpy.linalg import lstsq
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import euclidean_distances, cosine_similarity
from sklearn.cluster import SpectralClustering
from matplotlib import cm



try:
    import matplotlib.pyplot as plt
    import mplfinance as mpf
except Exception as e:
    print(e)
import threading
from collections import defaultdict
import gzip, pickle, copy
from pathlib import Path


SERVER_IP = os.getenv('HOST_IP', '')
if not SERVER_IP:
    SERVER_IP = input('请输入服务器IP: ')
    
def add_project_paths(project_name="ctos", subpackages=None):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    
    :param project_name: 项目根目录标识（默认 'ctos'）
    :param subpackages: 需要暴露的子包列表（默认 ["ctos", "bpx", "okx", "backpack", "apps"]）
    """
    if subpackages is None:
        subpackages = ["ctos", "bpx", "okx", "backpack", "apps"]
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    # 向上回溯，找到项目根目录
    path = current_dir
    while path != os.path.dirname(path):  # 一直回溯到根目录
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")
    # 添加根目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # 添加子包目录
    for pkg in subpackages:
        pkg_path = os.path.join(project_root, pkg)
        if os.path.exists(pkg_path) and pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)
    return project_root
# 执行路径添加
PROJECT_ROOT = add_project_paths()
print('PROJECT_ROOT: ', PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))


def get_current_file_path() -> str:
    """返回当前文件的绝对路径"""
    return os.path.abspath(__file__)

def get_current_dir() -> str:
    """返回当前文件所在的目录"""
    return os.path.dirname(os.path.abspath(__file__))



print(PROJECT_ROOT)
from ctos.drivers.okx.util import BeijingTime, get_host_ip, rate_price2order, pad_dataframe_to_length_fast
from ctos.drivers.okx.driver import init_CexClient as get_okexExchage
# === 配置 ===

try:
    print(get_current_dir() + '/' + 'good_group_plot.txt')
    with open(get_current_dir() + '/' + 'good_group_plot.txt', 'r', encoding='utf8') as f:
        data = f.readlines()
        good_group = data[0].replace('，', ',').strip().split(',')
        all_rate = [float(x) for x in data[1].replace('，', ',').strip().split(',')]
        if len(good_group) != len(all_rate):
            print('TMD不对啊')
        btc_rate = all_rate[0] / sum(all_rate)
        if len(data) >= 3:
            bad_coins = [x for x  in data[2].replace(' ', '').replace('，', ',').strip().split(',') if x not in good_group]
        else:
            bad_coins = []
except Exception as e:
    print('我草拟吗 他么出什么傻逼问题了？！', e)
    good_group = []
    bad_coins = []

COINS = list(rate_price2order.keys())  if len(bad_coins) == 0 else list(set(good_group + bad_coins))

# TIMEFRAMES = {
#     '1m': 10/len(COINS),  # 每 1 秒拉一次
#     '5m': 1,  # 每 5  秒拉一次
#     '15m': 2,
#     '1h': 4,
#     '4h': 6,
#     '1d': 8
# }

TIMEFRAMES = {
    '1m': 20/len(COINS),  # 每 1 秒拉一次
    '5m': 2,  # 每 5  秒拉一次
    '15m': 4,
    '1h': 6,
    '4h': 8,
    '1d': 10,
}


# TIMEFRAMES = {
#     '1m': 3,  # 每 1 秒拉一次
#     '5m': 6,  # 每 5  秒拉一次
#     '15m': 10,
#     '1h': 20,
#     '4h': 40,
#     '1d': 80
# }

HOST_IP = get_host_ip()
KLINE_LENGTH = 300

# 嵌套字典  shared[timeframe][coin] = latest_df
shared_data = defaultdict(dict)
lock = threading.Lock()
lock_for_apis = threading.Lock()
exchange = get_okexExchage('eth', show=False)

MEMORY_LIMIT_MB = 1024*8  # 4GB内存限制
CPU_LIMIT_PERCENT = 95  # CPU使用率阈值

# ---------- 调色盘 & 线型循环 ----------------------------------------
color_cycle = ['#1f77b4','#ff7f0e','#2ca02c','#d62728',
               '#9467bd','#8c564b','#e377c2','#7f7f7f',
               '#bcbd22','#17becf','#00c4ff','#ff9f00']
ls_cycle    = ['-','--','-.',':']

color_iter = itertools.cycle(color_cycle)
ls_iter    = itertools.cycle(ls_cycle)
balance_file_path = get_current_dir() + '/' +'total_balance.json'



SNAP_DIR = Path(get_current_dir()) / 'hourly_snapshots'
SNAP_DIR.mkdir(parents=True, exist_ok=True)

def _snapshot_filename(ts: datetime) -> Path:
    """生成形如 2025-07-03_14.pkl.gz 的文件路径"""
    return SNAP_DIR / ts.strftime('%Y-%m-%d_%H.pkl.gz')

def save_snapshot(shared_data: dict):
    """深拷贝后压缩保存"""
    ts   = datetime.utcnow()
    path = _snapshot_filename(ts)
    obj  = copy.deepcopy(shared_data)      # 防止写盘时数据被改
    with gzip.open(path, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[{ts:%F %T}] 🔒 snapshot saved → {path.name}")

def load_last_snapshot():
    """读取最近一小时快照（若不存在返回 None）"""
    now = datetime.utcnow()
    last_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    path = _snapshot_filename(last_hour)
    if not path.exists():
        print(f"❗ 找不到上小时快照：{path.name}")
        return None
    with gzip.open(path, 'rb') as f:
        data = pickle.load(f)
    print(f"[{now:%F %T}] 📖 snapshot {path.name} loaded")
    return data

def clock_worker(shared_ref):
    """
    每 30 s 检查一次时间：
      - 进入 xx:59:00 ~ xx:59:59 期间 → 保存快照
      - 进入 xx:00:00 ~ xx:00:59 期间 → 读取上小时快照
    """
    last_save_hour = None
    last_load_hour = None
    while True:
        now = datetime.utcnow()
        if now.minute == 59 and now.hour != last_save_hour and HOST_IP.find('66.187') != -1:
            save_snapshot(shared_ref)
            last_save_hour = now.hour

        elif now.minute == 0 and now.hour != last_load_hour and HOST_IP.find('66.187') == -1:
            snap = load_last_snapshot()
            # 这里可调用 downstream(snap) 做分析 / 画图 / 写 DB …
            last_load_hour = now.hour
            return snap

        time.sleep(30)           # 分辨率 30 秒即可



# 获取资产总额并保存
def log_asset():
    total_equity_usd = exchange.fetch_balance()
    
    # 保存到文件（修复：使用 balance_file_path 检查存在性，并容错读取）
    if os.path.exists(balance_file_path):
        try:
            with open(balance_file_path, 'r') as f:
                data = json.load(f)
        except Exception:
            data = []
        data.append({'timestamp': time.time(), 'total_equity_usd': total_equity_usd})
    else:
        data = [{'timestamp': time.time(), 'total_equity_usd': total_equity_usd}]
    
    with open(balance_file_path, 'w') as f:
        json.dump(data, f)
    
    return data

# 绘制资产走势图
def plot_asset_trend():
    if not os.path.exists(balance_file_path):
        return
    
    with open(balance_file_path, 'r') as f:
        data = json.load(f)
    
    # 提取时间戳和资产总额
    timestamps = [entry['timestamp'] for entry in data]
    total_equity_usd = [float(entry['total_equity_usd']) for entry in data]
    
    # 将时间戳转换为日期时间格式
    times = [datetime.utcfromtimestamp(ts) for ts in timestamps]
    
    # 选择每五分钟一个点
    selected_times = []
    selected_equity = []
    
    # 每五分钟选择一个点
    gap = 1
    for i in range(0, len(times), gap):  # 10分钟一个点
        selected_times.append(times[i])
        selected_equity.append(total_equity_usd[i])
    
    # 如果数据少于1000条，补充数据
    while len(selected_equity) < 1000:
        selected_equity.append(selected_equity[-1])
        selected_times.append(selected_times[-1] + timedelta(minutes=5))

    # 绘制资产曲线
    plt.figure(figsize=(10, 6))
    plt.plot(selected_times[-300:], selected_equity[-300:], label=f"Trend ({gap} mins")

    plt.xlabel('Date')
    plt.ylabel('Total Pos (USD)')
    plt.title('Trend of my Pos')
    plt.legend()
    
    # 格式化时间显示为每小时标记
    plt.xticks(rotation=45)
    
    # 保存图像
    asset_dir = Path(get_current_dir()) / 'trade_runtime_files'
    asset_dir.mkdir(parents=True, exist_ok=True)
    local_asset = str(asset_dir / 'asset_trend.png')
    plt.savefig(local_asset)
    # 同步到远端（保留原有逻辑，只改本地路径）
    if HOST_IP.find(SERVER_IP) != -1:
        os.system(f'cp {local_asset} ~/mysite/static/images/')
    else:
        os.system(f'scp {local_asset} azureuser@{SERVER_IP}:~/Quantify/ctos/apps/website/static/images/')
    plt.close()



def check_system_resources():
    """检查系统资源使用情况，必要时触发清理"""
    process = psutil.Process(os.getpid())

    # 内存检查
    mem_info = process.memory_info()
    if mem_info.rss / (1024 * 1024) > MEMORY_LIMIT_MB:
        print(f"⚠️ 内存使用超过 {MEMORY_LIMIT_MB}MB，执行紧急清理")
        gc.collect()

    # CPU检查
    if process.cpu_percent(interval=1) > CPU_LIMIT_PERCENT:
        print(f"⚠️ CPU使用率超过 {CPU_LIMIT_PERCENT}%，暂停处理")
        time.sleep(10)

# 假设 time_gap 是 '1d', '1h', '15m' 等等
def generate_time_axis(time_gap, length):
    unit_map = {
        '1d': timedelta(days=1),
        '4h': timedelta(hours=4),
        '1h': timedelta(hours=1),
        '15m': timedelta(minutes=15),
        '5m': timedelta(minutes=5),
        '1m': timedelta(minutes=1),
    }
    now = datetime.now()
    step = unit_map.get(time_gap, timedelta(days=1))  # 默认按天
    return [now - i * step for i in reversed(range(length))]


# @TODO 需要改进下，不然以后数据量大了简直绝望

def store_coin_data_if_needed(df, coin, time_gap, base_path=None):
    """
    存储每个币种的处理后的 DataFrame 到本地 CSV。
    如果 CSV 已存在，则合并并去重后写入；否则创建新文件。
    """
    # 将默认路径改为当前脚本目录下的子目录（按要求使用 get_current_dir() + '/' + 形式）
    if base_path is None:
        base_path = get_current_dir() + '/' + 'data/coin_change_data'

    os.makedirs(base_path, exist_ok=True)
    file_path = os.path.join(base_path, f"{coin.upper()}_{time_gap}.csv")

    df = df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    if os.path.exists(file_path):
        try:
            existing_df = pd.read_csv(file_path, parse_dates=['trade_date'])
            combined_df = pd.concat([existing_df, df], ignore_index=True)
            combined_df.drop_duplicates(subset='trade_date', inplace=True)
            combined_df.sort_values('trade_date', inplace=True)
            combined_df.to_csv(file_path, index=False)
            print(f"\r✅ 已更新并保存 {coin.upper()} 数据到 {file_path}，共 {len(combined_df)} 条记录。", end='')
        except Exception as e:
            print(f"❌ 读取或合并 {file_path} 失败：{e}")
    else:
        df.sort_values('trade_date', inplace=True)
        df.to_csv(file_path, index=False)
        print(f"📄 初次保存 {coin.upper()} 数据到 {file_path}，共 {len(df)} 条记录。")


warnings.filterwarnings("ignore")


def calculate_daily_returns(data):
    """计算每日涨跌幅，确保数据按时间升序处理，并逆转索引"""
    data['trade_date'] = pd.to_datetime(data['trade_date'], unit='ms')
    data.sort_values('trade_date', ascending=True, inplace=True)  # 确保数据按日期升序排列
    data.reset_index(drop=True, inplace=True)  # 重置索引，丢弃旧索引
    data['close'] = pd.to_numeric(data['close'], errors='coerce')  # 确保close列为数值类型
    data['high'] = pd.to_numeric(data['high'], errors='coerce')  # 确保close列为数值类型
    data['low'] = pd.to_numeric(data['low'], errors='coerce')  # 确保close列为数值类型
    data['open'] = pd.to_numeric(data['open'], errors='coerce')  # 确保close列为数值类型
    data['vol'] = pd.to_numeric(data['vol'], errors='coerce')  # 确保close列为数值类型.
    data['vol1'] = pd.to_numeric(data['vol1'], errors='coerce')  # 确保close列为数值类型
    data.dropna(subset=['close'], inplace=True)  # 移除任何因转换失败而变为NaN的行
    data['daily_return'] = data['close'].pct_change() * 100
    data['daily_return_vol1'] = data['vol1'].pct_change() * 100
    return data


def fetch_and_process(coin, timeframe='5m'):
    """获取数据并处理"""
    try:
        data = shared_data[timeframe][coin]
        df = calculate_daily_returns(data)
        return df
    except Exception as e:
        print('aaa???', e, timeframe, coin, len(shared_data))
        time.sleep(3)
        return None


def pad_kline_data(data, target_length, tf):
    """
    补齐K线数据到目标长度，保持时间连续性
    
    Parameters:
    -----------
    data : pd.DataFrame
        原始K线数据
    target_length : int
        目标长度
    tf : str
        时间周期
        
    Returns:
    --------
    pd.DataFrame : 补齐后的数据
    """
    if len(data) >= target_length:
        return data.iloc[-target_length:]  # 取最新的数据
    
    if len(data) == 0:
        return data
    
    # 时间间隔（秒）
    interval_seconds = {
        '1m': 60, '5m': 300, '15m': 900, 
        '1h': 3600, '4h': 14400, '1d': 86400
    }.get(tf, 300)
    
    # 获取最新时间戳（毫秒）
    latest_timestamp = data['trade_date'].iloc[-1]
    if not isinstance(latest_timestamp, (int, float)):
        # 如果不是数字，尝试转换
        try:
            latest_timestamp = int(latest_timestamp)
        except:
            # 如果转换失败，使用当前时间
            latest_timestamp = int(pd.Timestamp.now().timestamp() * 1000)
    
    # 检查时间戳是否在合理范围内（2020-2030年）
    if latest_timestamp < 1577836800000 or latest_timestamp > 1893456000000:
        # 如果时间戳超出范围，使用当前时间
        latest_timestamp = int(pd.Timestamp.now().timestamp() * 1000)
    
    # 补齐数据
    padded_data = data.copy()
    missing_count = target_length - len(data)
    
    for i in range(missing_count):
        # 向前推算时间戳（毫秒）
        new_timestamp = latest_timestamp - (i + 1) * interval_seconds * 1000
        
        # 创建新行（使用最新数据的值作为默认值）
        new_row = data.iloc[-1].copy()
        new_row['trade_date'] = int(new_timestamp)
        
        # 插入到开头
        padded_data = pd.concat([pd.DataFrame([new_row]), padded_data], ignore_index=True)
    
    return padded_data

def fetch_loop(coins: list, tf: str, interval_sec: int):
    while True:
        for coin in coins:
            if shared_data.get(tf, None) is not None:
                if shared_data.get(tf).get(coin) is not None:
                    time.sleep(interval_sec)
                else:
                    time.sleep(0.1)
            else:
                time.sleep(0.1)
            symbol = f"{coin.upper()}-USDT-SWAP"
            try:
                data, err = exchange.get_kline(tf, KLINE_LENGTH, symbol)
                if err is not None:
                    time.sleep(5)
                    print(f"😔 fetch {symbol} {tf} err:", err)
                    continue
                
                # 检查数据长度并补齐
                if len(data) < KLINE_LENGTH:
                    print(f"⚠️ {symbol} {tf} 数据不足: {len(data)}/{KLINE_LENGTH}, 正在补齐...")
                    data = pad_kline_data(data, KLINE_LENGTH, tf)
                    print(f"✅ {symbol} {tf} 数据已补齐到: {len(data)}")
                
                with lock:
                    if coin in shared_data[tf]:
                        del shared_data[tf][coin]
                    shared_data[tf][coin] = data
            except Exception as e:
                print(f"❌ api fetch {symbol} {tf} err:", e)



def correlation_heatmap(coins, time_gap='5m', method='spearman',
                        btc_ticker='btc', figsize_base=0.4,
                        annot_threshold=30):
    """
    coins           : list[str]  所有币种（含 btc）
    btc_ticker      : str        谁当公共因子
    figsize_base    : float      每个币宽高倍率；0.4 → 40px
    annot_threshold : int        当币种多于此阈值时不写数字
    """
    # ---------- 1. 下载 + 取日收益 -------------------------
    dfs = {}
    for c in coins:
        df = fetch_and_process(c, time_gap)
        if df is not None:
            dfs[c] = df.set_index('trade_date')['daily_return']
    if len(dfs) < 3 or btc_ticker not in dfs:
        print("可用币种不足，或缺 btc 数据")
        return

    # ---------- 2. 对齐索引 & 组 DataFrame ---------------
    ret_df = pd.concat(dfs, axis=1).dropna(how='any')     # shape: (T, N)

    # ---------- 3. 去 BTC β 成分 --------------------------
    y = ret_df[btc_ticker]
    var_btc = y.var()
    betas = ret_df.apply(lambda col: col.cov(y) / var_btc if col.name != btc_ticker else 1)
    # demean
    adj_df = ret_df.subtract(y * betas, axis=0)

    # ---------- 4. 计算相关矩阵 ---------------------------
    corr_mat = adj_df.corr(method=method).round(2)

    # ---------- 5. 画热力图 ------------------------------
    n = len(corr_mat)
    figsize = (figsize_base * n, figsize_base * n)
    show_annot = n <= annot_threshold

    mask = np.triu(np.ones_like(corr_mat, dtype=bool))
    plt.figure(figsize=figsize)
    sns.set(style='white')
    sns.heatmap(corr_mat, mask=mask, cmap='coolwarm', vmin=-1, vmax=1,
                square=True, annot=show_annot, fmt=".2f",
                annot_kws={"size": max(6, int(240/n))},
                linewidths=.5, cbar_kws={"shrink": .8})

    plt.title(f"{method.capitalize()} Corr (after BTC-β)  – {time_gap}", fontsize=max(8, int(240/n)))
    plt.tight_layout()
    out_dir = Path(get_current_dir()) / 'chart_for_group'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / f'heatmap_{time_gap}.png')
    plt.savefig(out, dpi=150)
    plt.close(); gc.collect()
    print(f"✅ 相关热图已保存 → {out}")

def find_levels(series: pd.Series,
                win: int = 20,
                tol: float = 0.05,
                min_hits: int = 2):
    """
    返回 list[dict] ：{'value': 水平价, 'first': idx, 'last': idx, 'hits': n}
    支撑/压力依中位数分割
    """
    half, full = win, 2 * win + 1
    s = series.dropna()

    # 局部极值
    roll_max = s.rolling(full, center=True, min_periods=1).max()
    roll_min = s.rolling(full, center=True, min_periods=1).min()
    extrema  = pd.concat([
        pd.Series(s[s == roll_max], name='max'),
        pd.Series(s[s == roll_min], name='min')
    ]).sort_index()

    levels = []
    for ts, val in extrema.items():
        i = series.index.get_loc(ts)          # 数值索引
        for lvl in levels:
            if abs(val - lvl['value']) <= tol * lvl['value']:
                lvl['hits']  += 1
                lvl['value'] = (lvl['value'] * (lvl['hits']-1) + val) / lvl['hits']
                lvl['first'] = min(lvl['first'], i)
                lvl['last']  = max(lvl['last'],  i)
                break
        else:
            levels.append({'value': val, 'hits': 1, 'first': i, 'last': i})

    levels = [l for l in levels if l['hits'] >= min_hits]

    med = s.median()
    supports    = [l for l in levels if l['value'] <  med]
    resistances = [l for l in levels if l['value'] >= med]
    return supports, resistances


def draw_segment_levels(ax, levels, color, label, date_index, extend=10):
    """
    levels : list[dict] from find_levels
    date_index : 全时间轴的 DatetimeIndex / list
    """
    for i, lvl in enumerate(levels, 1):
        start = max(0, lvl['first'] - extend)
        end   = min(len(date_index)-1, lvl['last'] + extend)
        xs = date_index[start:end+1]
        ys = [lvl['value']] * (end - start + 1)
        ax.plot(xs, ys, color=color, lw=3, ls=(0, (6, 4)),
                label=f'{label} #{i}' if i == 1 else None, zorder=4)

def draw_allcoin_trend(time_gap, coins):
    # ① 取 close & vol Series 并 inner-join ------------------------------------------------
    close_df = pd.concat(
        {c: fetch_and_process(c, time_gap).set_index('trade_date')['close']
         for c in coins}, axis=1, join='inner'
    )
    if close_df.shape[1] < 2:
        print(f"[{time_gap}] 可用币不足")
        return

    vol_df = pd.concat(
        {c: fetch_and_process(c, time_gap).set_index('trade_date')['vol']
         for c in coins}, axis=1, join='inner'
    ).reindex(close_df.index)           # 保证索引一致

    # ② 价格 %Change
    trend_df = close_df.div(close_df.iloc[0]).sub(1).mul(100)

    # ③ 总成交量归一化
    total_vol_norm = vol_df.sum(axis=1) / vol_df.sum(axis=1).iloc[0] * 100

    # ④ 计算ma10和布林带
    ma10_df = close_df.rolling(10).mean()
    ma5_df = close_df.rolling(5).mean()
    bollinger_lower = close_df.rolling(20).mean() - 2 * close_df.rolling(20).std()

    # ⑤ 绘图 -------------------------------------------------------------------------------
    fig, (ax_price, ax_vol) = plt.subplots(2,1, sharex=True, figsize=(20,14),
                                           gridspec_kw={'height_ratios':[3,1]})

    colors   = sns.color_palette("husl", len(trend_df.columns))
    ls_cycle = itertools.cycle(['-','--','-.',':'])

    ma10_status = []
    boll_status = []
    for col, colr in zip(trend_df, colors):
        
        is_best = col.lower() in best_performance_coins      # ← 你的最佳列表

        lw      = 2 if is_best else 1
        alpha   = 0.9 if is_best else 0.75
        zorder  = 2   if is_best else 1
        ls = next(ls_cycle)
        if is_best:
            ls == '--'
        else:
            ls = next(ls_cycle)

        ax_price.plot(trend_df.index, trend_df[col],
                    color=colr, ls=next(ls_cycle),
                  lw=lw, alpha=alpha, zorder=zorder,)
        ax_price.text(trend_df.index[-1], trend_df[col].iloc[-1],
                        col.upper() + ('★' if is_best else ''),
                        color=colr,
                        fontsize=12 if is_best else 9,
                        fontweight='bold' if is_best else 'normal',
                        ha='left', va='center')

        # 只获取最新时间与指标的相对位置
        cur_val = close_df[col].iloc[-1]
        cur_ma10 = ma10_df[col].iloc[-1]
        cur_boll = bollinger_lower[col].iloc[-1]
        
        # 统计当前状态
        ma10_status.append(cur_val > cur_ma10)
        boll_status.append(cur_val > cur_boll)

    # BTC 粗线置顶（若在列表中）
    if 'btc' in trend_df.columns:
        ax_price.plot(trend_df.index, trend_df['btc'], ls='--',
                      color='#CC5500', lw=3, )

    n_above_ma10 = sum(ma10_status)
    n_below_ma10 = len(ma10_status) - n_above_ma10
    n_above_boll = sum(boll_status)
    n_below_boll = len(boll_status) - n_above_boll

    stat_text = f"> MA10: {n_above_ma10}  < MA10: {n_below_ma10}  |  > Boll: {n_above_boll}  < Boll: {n_below_boll}"
    ax_price.text(0.01, 0.99, stat_text, transform=ax_price.transAxes, fontsize=14, color='black', va='top', ha='left', bbox=dict(facecolor='white', alpha=0.7))

    ax_price.grid(alpha=.3)
    ax_price.set_title(f'All-Coin %Change — {time_gap.upper()}')
    ax_price.set_ylabel('% change')
    ax_price.legend(fontsize=8)

    ax_vol.plot(trend_df.index, total_vol_norm, color='black', lw=1.8)
    ax_vol.fill_between(trend_df.index, total_vol_norm,
                        color='steelblue', alpha=.25)
    ax_vol.set_title('Aggregate Volume (norm=100)')
    ax_vol.set_ylabel('Vol index')
    ax_vol.grid(alpha=.3)

    plt.tight_layout()


    out_dir = Path(get_current_dir()) / 'chart_for_group'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / f'allcoin_trend_{time_gap if ("m" in time_gap) else time_gap.upper()}.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"📈 保存 {out}")




# ---------------------- 核心函数 --------------------------------------
def multi_tf_ma_bBands_signal(df_1m, df_15m, df_1h, df_4h, df_1d,
                              symbol='ETH'):
    frames = {
        '1m' : df_1m.copy(),
        '15m': df_15m.copy(),
        '1h' : df_1h.copy(),
        '4h' : df_4h.copy(),
        '1d' : df_1d.copy()
    }

    # 1⃣ 计算 MA5/MA10/BollMid20 最新值
    state = {}   # 周期 -> 'bull' / 'bear' / 'mix'
    for tf, df in frames.items():
        c = df['close']
        ma5  = c.rolling(5).mean().iloc[-1]
        ma10 = c.rolling(10).mean().iloc[-1]
        mid  = c.rolling(20).mean().iloc[-1]

        if ma5 > ma10 > mid:
            state[tf] = 'bull'
        elif ma5 < ma10 < mid:
            state[tf] = 'bear'
        else:
            state[tf] = 'mix'

    # 2⃣ 检查高周期一致性（15m/1h/4h/1d）
    high_tfs = ['15m','1h','4h','1d']
    high_states = [state[t] for t in high_tfs]
    if len(set(high_states)) == 1 and high_states[0] in ('bull','bear'):
        mode = high_states[0]   # 全一致
    else:
        print(f"❌ {symbol} 各周期不一致 →", state)
        return

    # 3⃣ 在 1m 查找进入/退出
    df = frames['1m']
    close = df['close']
    ma5  = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    mid  = close.rolling(20).mean()

    if mode == 'bull':
        mask = (ma5 > ma10) & (ma10 > mid)
    else:  # bear
        mask = (ma5 < ma10) & (ma10 < mid)

    # 进入 / 退出 索引
    m = mask.values
    enter = np.where((m[1:] == 1) & (m[:-1] == 0))[0] + 1
    exit_ = np.where((m[1:] == 0) & (m[:-1] == 1))[0] + 1

    # 4⃣ 绘制 1m 蜡烛 + MA & 阴影 + 标记
    df_plot = df.dropna().copy()
    df_plot['ma5'] = ma5
    df_plot['ma10'] = ma10
    df_plot = df_plot.iloc[19:]              # 保障 MA20 完整

    fig, axes = mpf.plot(
        df_plot, type='candle', style='charles',
        mav=(5, 10), returnfig=True,
        figsize=(14, 8),
        title=f'{symbol} 1m — {mode.upper()} (MA5/MA10/BBmid)'
    )
    ax = axes[0]

    x = np.arange(len(df_plot))
    ma5_v, ma10_v = df_plot['ma5'].values, df_plot['ma10'].values

    # 阴影
    ax.fill_between(x, ma5_v, ma10_v, where=mask.iloc[-len(df_plot):].values,
                    color='orangered' if mode=='bull' else 'deepskyblue',
                    alpha=.15, interpolate=True)

    # 标记
    ax.scatter(x[enter], df_plot['close'].iloc[enter],
               marker='^', color='green', s=50, zorder=6, label='Entry')
    ax.scatter(x[exit_], df_plot['close'].iloc[exit_],
               marker='v', color='red',   s=50, zorder=6, label='Exit')

    ax.legend(fontsize=8)
    plt.tight_layout()

    out_dir = Path(get_current_dir()) / 'chart_for_group' / 'good_coins'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / f'{symbol.lower()}_multi_tf_signal_{int(time.time())}.png')

    plt.savefig(out, dpi=150)
    plt.close()
    print("📈 📈 📈 已保存  📈  📈 ", out)


def factor_strength_ranking(
    data_frames: dict = None,
    lookback: int = 60,
    w_mom: float = 0.4,
    w_slope: float = 0.4,
    w_up: float = 0.2,
):
    """
    仅基于 K 线走势强弱打分：动量 + 线性趋势斜率 + 上涨频率

    Parameters
    ----------
    data_frames : dict[str, pd.DataFrame]
        {"btc": df_btc, ...}；每个 df 至少含 'close', 'open'
    lookback : int, default 60
        计算窗口（根数）
    w_mom, w_slope, w_up : float
        三个角度的权重，和不限于 1

    Returns
    -------
    score  : 综合得分（越大越强）
    ranks  : 1 表示最强
    weight : 仅对正得分归一后的权重
    """
    scores = {}
    for sym, df in data_frames.items():
        if len(df) < lookback or "close" not in df.columns or "open" not in df.columns:
            continue

        closes = df["close"].iloc[-lookback:].to_numpy()
        opens  = df["open"].iloc[-lookback:].to_numpy()

        # 1) 区间动量
        mom = closes[-1] / closes[0] - 1

        # 2) 线性趋势斜率（最小二乘）
        y = closes
        x = np.arange(len(y))
        # [slope, intercept] from lstsq( X @ beta = y )
        slope, _ = lstsq(np.column_stack([x, np.ones_like(x)]), y, rcond=None)[0]
        # 为可比性转成“每根百分比斜率”
        slope_pct = slope / closes[0]

        # 3) 上涨频率
        up_freq = np.mean(closes > opens)  # 占比 (0,1)

        # 综合得分
        score = w_mom * mom + w_slope * slope_pct + w_up * up_freq
        scores[sym.upper()] = score

    score = pd.Series(scores).sort_values(ascending=False)
    ranks = score.rank(method="dense", ascending=False).astype(int)

    pos = score.clip(lower=0)
    weight = pos / pos.sum() if pos.sum() > 0 else pos

    return score, ranks, weight


def calculate_bollinger_market_sentiment(data_frames: dict, time_gap: str, window: int = 20, std_multiplier: float = 2.0) -> dict:
    """
    计算所有币种的布林带，并分析市场整体情绪倾向
    
    Parameters:
    -----------
    data_frames : dict
        包含所有币种数据的字典，每个值为包含OHLCV数据的DataFrame
    time_gap : str
        时间周期标识，用于数据存储文件名
    window : int, default=20
        布林带计算窗口期
    std_multiplier : float, default=2.0
        标准差倍数
        
    Returns:
    --------
    dict : 包含市场情绪分析结果的字典
        {
            'sentiment_score': float,  # -1到1之间，-1表示极度超卖，1表示极度超买，0表示中性
            'upper_ratio': float,      # 价格接近上轨的币种比例
            'middle_ratio': float,     # 价格接近中轨的币种比例  
            'lower_ratio': float,      # 价格接近下轨的币种比例
            'extreme_filtered': dict,  # 过滤极端情况后的统计
            'coin_positions': dict,    # 每个币种的具体位置信息
            'timestamp': str           # 分析时间戳
        }
    """
    
    if not data_frames:
        return {}
    
    coin_positions = {}
    position_scores = []  # 用于计算整体情绪，-1(下轨) 到 1(上轨)
    
    # 为每个币种计算布林带并判断当前价格位置
    for coin, df in data_frames.items():
        if df is None or len(df) < window:
            continue
            
        try:
            # 确保数据按时间排序
            df_sorted = df.sort_values('trade_date').copy()
            
            # 计算布林带
            close_prices = df_sorted['close'].astype(float)
            sma = close_prices.rolling(window=window).mean()
            std = close_prices.rolling(window=window).std()
            
            upper_band = sma + (std * std_multiplier)
            middle_band = sma
            lower_band = sma - (std * std_multiplier)
            
            # 获取最新价格和布林带值
            latest_price = close_prices.iloc[-1]
            latest_upper = upper_band.iloc[-1]
            latest_middle = middle_band.iloc[-1]
            latest_lower = lower_band.iloc[-1]
            
            # 跳过无效数据
            if pd.isna(latest_upper) or pd.isna(latest_lower) or pd.isna(latest_middle):
                continue
                
            # 计算价格在布林带中的相对位置 (-1到1)
            band_width = latest_upper - latest_lower
            if band_width > 0:
                # 相对位置：-1(下轨), 0(中轨), 1(上轨)
                relative_position = (latest_price - latest_middle) / (band_width / 2)
                relative_position = max(-1, min(1, relative_position))  # 限制在[-1, 1]范围内
            else:
                relative_position = 0
                
            # 计算距离各轨道的相对距离
            if band_width > 0:
                dist_to_upper = abs(latest_price - latest_upper) / band_width
                dist_to_middle = abs(latest_price - latest_middle) / band_width  
                dist_to_lower = abs(latest_price - latest_lower) / band_width
            else:
                dist_to_upper = dist_to_middle = dist_to_lower = 1.0
                
            # 判断最接近哪条线
            distances = {
                'upper': dist_to_upper,
                'middle': dist_to_middle, 
                'lower': dist_to_lower
            }
            closest_band = min(distances.keys(), key=lambda k: distances[k])
            
            coin_positions[coin] = {
                'latest_price': latest_price,
                'upper_band': latest_upper,
                'middle_band': latest_middle,
                'lower_band': latest_lower,
                'relative_position': relative_position,
                'closest_band': closest_band,
                'distances': distances,
                'band_width': band_width
            }
            
            position_scores.append(relative_position)
            
        except Exception as e:
            print(f"计算 {coin} 布林带时出错: {e}")
            continue
    
    if not position_scores:
        return {}
    
    # 过滤极端值 (使用四分位数方法)
    position_scores_array = np.array(position_scores)
    q1 = np.percentile(position_scores_array, 25)
    q3 = np.percentile(position_scores_array, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # 过滤后的分数
    filtered_scores = position_scores_array[
        (position_scores_array >= lower_bound) & 
        (position_scores_array <= upper_bound)
    ]
    
    # 计算统计指标
    total_coins = len(position_scores)
    
    # 原始统计
    upper_count = sum(1 for score in position_scores if score > 0.5)
    middle_count = sum(1 for score in position_scores if -0.5 <= score <= 0.5) 
    lower_count = sum(1 for score in position_scores if score < -0.5)
    
    upper_ratio = upper_count / total_coins if total_coins > 0 else 0
    middle_ratio = middle_count / total_coins if total_coins > 0 else 0
    lower_ratio = lower_count / total_coins if total_coins > 0 else 0
    
    # 过滤后统计
    filtered_total = len(filtered_scores)
    if filtered_total > 0:
        filtered_upper_count = sum(1 for score in filtered_scores if score > 0.5)
        filtered_middle_count = sum(1 for score in filtered_scores if -0.5 <= score <= 0.5)
        filtered_lower_count = sum(1 for score in filtered_scores if score < -0.5)
        
        filtered_upper_ratio = filtered_upper_count / filtered_total
        filtered_middle_ratio = filtered_middle_count / filtered_total
        filtered_lower_ratio = filtered_lower_count / filtered_total
        
        # 计算整体情绪分数 (过滤后的平均值)
        sentiment_score = np.mean(filtered_scores)
    else:
        filtered_upper_ratio = filtered_middle_ratio = filtered_lower_ratio = 0
        sentiment_score = np.mean(position_scores_array)
    
    # 构建结果
    result = {
        'sentiment_score': float(sentiment_score),
        'upper_ratio': float(upper_ratio),
        'middle_ratio': float(middle_ratio), 
        'lower_ratio': float(lower_ratio),
        'extreme_filtered': {
            'upper_ratio': float(filtered_upper_ratio),
            'middle_ratio': float(filtered_middle_ratio),
            'lower_ratio': float(filtered_lower_ratio),
            'total_coins': filtered_total,
            'filtered_out': total_coins - filtered_total
        },
        'coin_positions': coin_positions,
        'timestamp': datetime.now().isoformat(),
        'total_analyzed_coins': total_coins
    }
    
    # 保存数据到文件
    save_bollinger_analysis(result, time_gap)
    
    # 打印简要信息
    print(f"\n📊 布林带市场情绪分析 (时间周期: {time_gap})")
    print(f"   总分析币种: {total_coins}")
    print(f"   情绪分数: {sentiment_score:.3f} ({'超买' if sentiment_score > 0.3 else '超卖' if sentiment_score < -0.3 else '中性'})")
    print(f"   上轨附近: {upper_ratio:.1%} | 中轨附近: {middle_ratio:.1%} | 下轨附近: {lower_ratio:.1%}")
    print(f"   过滤极值后: 上轨 {filtered_upper_ratio:.1%} | 中轨 {filtered_middle_ratio:.1%} | 下轨 {filtered_lower_ratio:.1%}")
    
    return result


def save_bollinger_analysis(analysis_result: dict, time_gap: str):
    """
    保存布林带分析结果到文件
    
    Parameters:
    -----------
    analysis_result : dict
        分析结果字典
    time_gap : str
        时间周期标识
    """
    try:
        # 创建保存目录
        save_dir = os.path.join(os.path.dirname(__file__), 'bollinger_analysis')
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'bollinger_sentiment_{time_gap}.json'
        filepath = os.path.join(save_dir, filename)
        
        # 保存简化版本（不包含详细的coin_positions以节省空间）
        simplified_result = {
            'sentiment_score': analysis_result['sentiment_score'],
            'upper_ratio': analysis_result['upper_ratio'],
            'middle_ratio': analysis_result['middle_ratio'],
            'lower_ratio': analysis_result['lower_ratio'],
            'extreme_filtered': analysis_result['extreme_filtered'],
            'timestamp': analysis_result['timestamp'],
            'total_analyzed_coins': analysis_result['total_analyzed_coins'],
            'time_gap': time_gap
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(simplified_result, f, indent=2, ensure_ascii=False)
            
        # 同时保存到历史汇总文件
        history_file = os.path.join(save_dir, f'bollinger_history_{time_gap}.json')
        
        # 读取现有历史记录
        history_data = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
            except:
                history_data = []
        
        # 添加新记录
        history_data.append(simplified_result)
        
        # 保持最近1000条记录
        if len(history_data) > 1000:
            history_data = history_data[-1000:]
            
        # 保存历史记录
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)
            
        print(f"   💾 布林带分析结果已保存: {filename}")
        
    except Exception as e:
        print(f"保存布林带分析结果时出错: {e}")


def market_strength_index(
    data_frames: dict,
    lookback: int = 60,
    w_mom: float = 0.5,   # 三因子权重，可按需调整
    w_slope: float = 0.3,
    w_up: float = 0.2,
) -> float:
    """
    计算整个币市的一维“强弱指数”。

    Parameters
    ----------
    data_frames : dict[str, pd.DataFrame]
        {"btc": df_btc, "eth": df_eth, ...}，每个 df 至少含 'close', 'open'
    lookback : int, default 60
        最近多少根 K 线作为评估窗口
    w_mom, w_slope, w_up : float
        M/S/U 三因子的组合权重（和不必 =1）

    Returns
    -------
    idx : float
        强弱相对值；>0 => 整体多头占优，<0 => 空头占优
    """
    m_list, s_list, u_list = [], [], []

    for df in data_frames.values():
        if len(df) < lookback or "close" not in df.columns or "open" not in df.columns:
            continue

        closes = df["close"].iloc[-lookback:].to_numpy()
        opens  = df["open"].iloc[-lookback:].to_numpy()

        # 1) 区间动量 M
        mom = closes[-1] / closes[0] - 1
        m_list.append(mom)

        # 2) 线性趋势斜率 S（转为百分比）
        x = np.arange(lookback)
        slope, _ = lstsq(np.column_stack([x, np.ones_like(x)]), closes, rcond=None)[0]
        slope_pct = slope / closes[0]
        s_list.append(slope_pct)

        # 3) 上涨频率 U
        up_freq = np.mean(closes > opens)   # 0–1 之间
        u_list.append(up_freq)

    if not m_list:
        return 0.0   # 没有可用数据

    # 所有币的因子均值
    m_avg = np.mean(m_list)
    s_avg = np.mean(s_list)
    u_avg = np.mean(u_list)

    # 综合成单一指数
    idx = w_mom * m_avg + w_slope * s_avg + w_up * (u_avg - 0.5)  # 上涨频率中心化

    return float(idx)

def optimize_hedge_configuration(
    data_frames: dict = None,
    lookback: int = 60,
    n_trials: int = 1000,
    precision: float = 0.1
) -> list:
    """
    搜索最优的多空配置，最小化diff_returns的波动率
    
    Parameters:
    -----------
    data_frames : dict
        包含所有币种日线数据的字典
    lookback : int
        回看期数
    n_trials : int
        搜索次数
    precision : float
        权重搜索精度
        
    Returns:
    --------
    list : 波动率最小的前10名配置
    """
    if not data_frames:
        return []
    
    # 读取good_group配置

    try:
        print(get_current_dir() + '/' + 'good_group_plot.txt')
        with open(get_current_dir() + '/' + 'good_group_plot.txt', 'r', encoding='utf8') as f:
            data = f.readlines()
            good_group = data[0].replace('，', ',').strip().split(',')
            all_rate = [float(x) for x in data[1].replace('，', ',').strip().split(',')]
            if len(good_group) != len(all_rate):
                print('TMD不对啊')
                return None
            btc_rate = all_rate[0] / sum(all_rate)
            if len(data) >= 3:
                bad_coins = [x for x  in data[2].replace(' ', '').replace('，', ',').strip().split(',') if x not in good_group]
            else:
                bad_coins = []
    except Exception as e:
        print('我草拟吗 他么出什么傻逼问题了？！', e)
        good_group = ['btc', 'sol']
        bad_coins = []
    if len(bad_coins) > 0:
        top10_coins = bad_coins
        
    # 确保有足够的币种数据
    available_coins = [coin for coin in good_group+bad_coins if coin in data_frames and len(data_frames[coin]) >= lookback]
    if len(available_coins) < 6:  # 至少需要6个币种
        print(f"可用币种不足: {len(available_coins)}")
        return []
    
    print(f"开始优化搜索，可用币种: {available_coins}")
    returns_data = {}
    for coin in available_coins:
        df = fetch_and_process(coin, '1d')
        data_frames[coin] = df
        df = data_frames[coin].iloc[-lookback:].copy()
        df['daily_return'] = df['close'].pct_change() * 100
        returns_data[coin] = df['daily_return'].dropna()

    # 对齐时间索引
    common_index = returns_data[available_coins[0]].index
    for coin in available_coins[1:]:
        common_index = common_index.intersection(returns_data[coin].index)
    
    for coin in available_coins:
        returns_data[coin] = returns_data[coin].loc[common_index]
    
    best_configs = []
    
    for trial in range(n_trials):
        try:
            # 随机选择多头币种（最多1/5，至少包含btc,eth,bnb）
            max_long = max(3, len(available_coins) // 5)
            long_coins = ['btc', 'bnb']  # 必须包含的币种
            
            # 添加其他随机币种
            remaining_coins = [c for c in available_coins if c not in long_coins]
            if len(remaining_coins) > 0:
                n_additional = min(max_long - 3, len(remaining_coins))
                additional = random.sample(remaining_coins, n_additional)
                long_coins.extend(additional)
            
            # 生成多头权重（btc至少1/5，最大权重不超过最小权重的3倍）
            long_weights = {}
            btc_weight = random.uniform(0.2, 0.6)  # btc权重至少20%
            long_weights['btc'] = btc_weight
            
            # 分配剩余权重给其他多头币种
            remaining_weight = 1.0 - btc_weight
            other_long_coins = [c for c in long_coins if c != 'btc']
            
            if other_long_coins:
                # 使用Dirichlet分布生成权重，但需要调整以满足比例约束
                max_attempts = 10
                for attempt in range(max_attempts):
                    weights = np.random.dirichlet(np.ones(len(other_long_coins))) * remaining_weight
                    
                    # 检查比例约束：最大权重 <= 最小权重 * 3
                    if len(weights) > 1:
                        min_weight = min(weights)
                        max_weight = max(weights)
                        if max_weight <= min_weight * 3:
                            # 满足约束，分配权重
                            for coin, weight in zip(other_long_coins, weights):
                                long_weights[coin] = weight
                            break
                    else:
                        # 只有一个其他币种，直接分配
                        long_weights[other_long_coins[0]] = remaining_weight
                        break
                else:
                    # 如果多次尝试都不满足约束，使用均匀分配
                    uniform_weight = remaining_weight / len(other_long_coins)
                    for coin in other_long_coins:
                        long_weights[coin] = uniform_weight
            
            # 计算多头组合收益
            long_returns = pd.Series(0.0, index=common_index)
            for coin, weight in long_weights.items():
                if coin in returns_data:
                    long_returns += returns_data[coin] * weight
            
            # 计算空头组合收益（等权重）
            short_coins = [c for c in available_coins if c not in long_coins]
            if short_coins:
                short_returns = pd.concat([returns_data[coin] for coin in short_coins], axis=1).mean(axis=1)
            else:
                short_returns = pd.Series(0.0, index=common_index)
            
            # 计算diff_returns
            diff_returns = long_returns - short_returns
            
            # 计算波动率
            volatility = diff_returns.std()
            
            # 记录配置
            config = {
                'volatility': volatility,
                'long_coins': long_coins,
                'long_weights': long_weights,
                'short_coins': short_coins,
                'diff_returns_mean': diff_returns.mean(),
                'sharpe_ratio': diff_returns.mean() / volatility if volatility > 0 else 0
            }
            
            best_configs.append(config)
            
        except Exception as e:
            continue
    
    # 按波动率排序，取前10名
    best_configs.sort(key=lambda x: x['volatility'])
    top_10 = best_configs[:10]
    
    print(f"\n📊 优化完成，找到 {len(best_configs)} 个有效配置")
    print("🏆 波动率最小的前10名配置:")
    print("-" * 80)
    
    for i, config in enumerate(top_10, 1):
        print(f"{i:2d}. 波动率: {config['volatility']:.4f} | "
              f"夏普比: {config['sharpe_ratio']:.4f} | "
              f"多头: {config['long_coins']}")
        print(f"    多头权重: {config['long_weights']}")
        print(f"    空头: {config['short_coins']}")
        print()
    
    return top_10


def cluster_kline_graph(
    data_frames: dict= None,
    lookback:   int   = 60,      # 取最近多少根日线
    n_clusters: int   = 4,       # 指定簇数
    scale:      bool  = True,    # 是否标准化每个时间步的特征
) -> dict:
    """
    根据日线 K 线相似性，把多币种分成 n_clusters 个簇（图聚类 / Spectral）。

    Parameters
    ----------
    data_frames : dict[str, pd.DataFrame]
        {"btc": df_btc, ...}，每个 df 至少含 ['open','high','low','close']
    lookback : int
        参与聚类的最近日线根数
    n_clusters : int
        目标簇个数
    scale : bool
        True 则对所有时间步特征做标准化，有助于距离度量

    Returns
    -------
    clusters : dict[int, list[str]]
        {簇编号: [symbol, …]}，编号从 0 开始
    """
    symbols, embeds = [], []

    # ---------- 1. 生成每个币的 K 线嵌入 ----------
    for sym, df in data_frames.items():
        if len(df) < lookback or not {'open','high','low','close'}.issubset(df.columns):
            continue

        # 最近 lookback 根日线
        slice_df = df.iloc[-lookback:]

        # ① 价格动量 ② 振幅
        mom     = (slice_df['close'] - slice_df['open']) / slice_df['open']
        amp     = (slice_df['high']  - slice_df['low'])  / slice_df['open']

        # 每根日线 → 两维特征；展平为 (2*lookback,) 向量
        embed_vec = np.vstack([mom, amp]).T.flatten()
        embeds.append(embed_vec)
        symbols.append(sym.upper())

    if len(embeds) < n_clusters:
        raise ValueError("可用币种不足以形成指定簇数")

    X = np.vstack(embeds)                       # shape = (N_coins, 2*lookback)

    # ---------- 2. （可选）标准化 ----------
    if scale:
        X = StandardScaler().fit_transform(X)

    # ---------- 3. 相似度矩阵（余弦） ----------
    affinity = cosine_similarity(X)            # 值域 [-1,1]

    # ---------- 4. 图聚类 ----------
    model = SpectralClustering(
        n_clusters   = n_clusters,
        affinity     = 'precomputed',
        assign_labels= 'kmeans',
        random_state = 42,
    )
    labels = model.fit_predict(affinity)       # ndarray, shape = (N_coins,)

    # ---------- 5. 组织输出 ----------
    clusters = {}
    for sym, lab in zip(symbols, labels):
        clusters.setdefault(int(lab), []).append(sym)

    return clusters



def main1(top10_coins=['btc', 'eth', 'xrp', 'bnb', 'sol', 'ada', 'doge', 'trx', 'ltc', 'shib'], prex='', time_gap='5m', good_group = [], all_rate={}, bad_coins=[]):
    # top10_coins = ['btc', 'eth','xrp', 'bnb', 'sol', 'ada', 'doge', 'trx', 'ltc', 'shib', 'link', 'dot', 'om', 'apt',
    #      'uni', 'hbar', 'ton', 'sui', 'avax', 'fil', 'ip', 'gala', 'sand']
    if len(good_group) == 0:
        try:
            config_path = get_current_dir() + '/' + 'good_group_plot.txt'
            print(config_path)
            with open(config_path, 'r', encoding='utf8') as f:
                data = f.readlines()
                configs = []
                # 以三行为一组读取多组配置
                for i in range(0, len(data), 3):
                    group = data[i].strip().replace('，', ',').split(',') if i < len(data) else []
                    rate = [float(x) for x in data[i+1].strip().replace('，', ',').split(',')] if i+1 < len(data) else []
                    if group and rate and len(group) == len(rate):
                        # 尝试读取bad_coins，如果没有则空
                        if i+2 < len(data):
                            bad_line = data[i+2].strip().replace(' ', '').replace('，', ',')
                            bad_coins_group = [x for x in bad_line.split(',') if x not in group]
                        else:
                            bad_coins_group = []
                        configs.append({
                            'good_group': group,
                            'all_rate': rate,
                            'bad_coins': bad_coins_group
                        })
                    else:
                        print(f'第{i//3+1}组配置有误，跳过')
                
                # 默认使用第一个配置，你可自定义切换
                if len(configs) > 0:
                    good_group = configs[0]['good_group']
                    all_rate = configs[0]['all_rate']
                    bad_coins = configs[0]['bad_coins']
                else:
                    # 没有合法配置 fallback
                    good_group = ['btc', 'sol']
                    all_rate = [1, 1]
                    bad_coins = []
        except Exception as e:
            print('我草拟吗 他么出什么傻逼问题了？！', e)
            good_group = ['btc', 'sol']
            all_rate = [1, 1]
            bad_coins = []
    if len(bad_coins) > 0:
        top10_coins = bad_coins
    
    data_frames = {}
    # 获取并处理所有币种的数据
    for coin in top10_coins + good_group:
        df = fetch_and_process(coin, time_gap)
        data_frames[coin] = df
    
    # market_idx_1 = market_strength_index(data_frame, lookback=30)
    
    # ⭐ ---------- 布林带市场情绪分析 ------------------------------------
    # bollinger_sentiment = calculate_bollinger_market_sentiment(data_frames, time_gap)
    
    # 针对前面得到的多组configs，配置使用前N个，然后得到其stack_profile，用于后续绘制多条曲线
    N_CONFIGS_TO_USE = min(3, len(configs))  # 例如最多取3组
    stack_profiles = []
    goodGroup_returns = []
    bad_average_returns = []
    configs_used = configs[:N_CONFIGS_TO_USE] if len(configs) > 0 else [{
        'good_group': good_group, 'all_rate': all_rate, 'bad_coins': bad_coins
    }]


    for cfg in configs_used:
        group = cfg['good_group']
        rate = cfg['all_rate']
        bad_coins = cfg['bad_coins']
        # 归一化权重
        total = sum(rate)
        weights = {c: r / total for c, r in zip(group, rate)}
        # 拼接 group 的收益列
        good_df = pd.concat(
            [data_frames[c]['daily_return'].rename(c)
             for c in group if c in data_frames],
            axis=1
        )
        bad_average_return = pd.concat([data_frames[coin]['daily_return']
            for coin in top10_coins if coin not in group and coin in data_frames and coin in bad_coins], axis=1).mean(axis=1)

        # 加权求和
        w_series = pd.Series(weights).reindex(good_df.columns, fill_value=0)
        goodGroup_return = (good_df.mul(w_series, axis=1)).sum(axis=1)
        goodGroup_returns.append(goodGroup_return)
        bad_average_returns.append(bad_average_return)
        # 计算 diff 和累积
        diff_returns = goodGroup_return - bad_average_return
        cur_stack = diff_returns.cumsum()
        stack_profiles.append(cur_stack)

    # 兼容性变量，保留默认行为（第一个配置组的 stack_profile 用于后续绘图/统计等）
    stack_profile = stack_profiles[0] if len(stack_profiles) > 0 else pd.Series([0])
    goodGroup_return = goodGroup_returns[0] if len(goodGroup_returns) > 0 else pd.Series([0])
    bad_average_return = bad_average_returns[0] if len(bad_average_returns) > 0 else pd.Series([0])


    upper_band_name = 'bollinger_upper'
    lower_band_name = 'bollinger_lower'
    column = ['close']
    window = 20
    sma = data_frames['btc'][column].rolling(window=window).mean()
    if upper_band_name not in data_frames['btc'].columns or lower_band_name not in data_frames['btc'].columns:
        std = data_frames['btc'][column].rolling(window=window).std()
        data_frames['btc'][upper_band_name] = sma + (std * 2)
        data_frames['btc'][lower_band_name] = sma - (std * 2)

        # 确保上下轨前20个空值被填充
        data_frames['btc'][upper_band_name] = data_frames['btc'][upper_band_name].fillna(method='bfill',
                                                                                         limit=window - 1)
        data_frames['btc'][lower_band_name] = data_frames['btc'][lower_band_name].fillna(method='bfill',
                                                                                         limit=window - 1)

    data_frames['btc']['bollinger_middle'] = sma
    # 获取BTC数据时也进行填充
    btc_upper_bollinger = data_frames['btc'][upper_band_name].fillna(method='bfill', limit=window - 1)
    btc_bollinger_lower = data_frames['btc'][lower_band_name].fillna(method='bfill', limit=window - 1)

    btc_close_price = data_frames['btc']['close']
    btc_high_price = data_frames['btc']['high']
    btc_low_price = data_frames['btc']['low']
    # sum_profile = 0

    WINDOW  = 20          # 滚动窗口
    N_STD   = 2           # n × 标准差

        # rolling mean / std
    stack_mid   = stack_profile.rolling(WINDOW).mean()
    stack_std   = stack_profile.rolling(WINDOW).std()

    stack_upper = stack_mid + N_STD * stack_std
    stack_lower = stack_mid - N_STD * stack_std

    # 头部 NaN 用前向填充，确保整条曲线连贯
    stack_mid   = stack_mid.fillna(method='bfill', limit=WINDOW-1)
    stack_upper = stack_upper.fillna(method='bfill', limit=WINDOW-1)
    stack_lower = stack_lower.fillna(method='bfill', limit=WINDOW-1)


    # ----------------- 1. 参数 -----------------------
    lookback = 200
    n_sigma  = 2
    r2_th    = 0.50

    y = stack_profile.iloc[-lookback:].values
    x = np.arange(len(y))

    # ① 线性拟合 (y = a·x + b)
    a, b = np.polyfit(x, y, 1)
    y_pred = a * x + b

    # ② R²
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot

    if r2 >= r2_th:
        sigma = np.std(y - y_pred)
        upper = y_pred + n_sigma * sigma
        lower = y_pred - n_sigma * sigma

        idx   = stack_profile.index[-lookback:]
        upper = pd.Series(upper, index=idx)
        lower = pd.Series(lower, index=idx)

    # for i in range(len(goodGroup_return)):
    #     sum_profile += (float(goodGroup_return[i]) - float(bad_average_return[i]))

    reduce_part = goodGroup_return - bad_average_return

    date_range = goodGroup_return.index
    btc_trend = (btc_close_price / btc_close_price[0] - 1) * 100
    high_trend = (btc_high_price / btc_close_price[0] - 1) * 100
    low_trend = (btc_low_price / btc_close_price[0] - 1) * 100
    upper_trend = (btc_upper_bollinger / btc_close_price[0] - 1) * 100
    lower_trend = (btc_bollinger_lower / btc_close_price[0] - 1) * 100


    # ── ❶ 高点 > 上轨 且 收盘 < 上轨  → "上影刺破" -----------------------------
    above_upper = np.where( (high_trend >= upper_trend) & (btc_trend  <  upper_trend))[0]

    # ── ❷ 低点 < 下轨 且 收盘 > 下轨  → "下影刺破" -----------------------------
    below_lower = np.where(  (low_trend  <= lower_trend) &  (btc_trend  >  lower_trend)  )[0]


    stack_above = [stack_profile[i] for i in above_upper]
    stack_below = [stack_profile[i] for i in below_lower]


    
    # ---------------------------------------------------------------
    # 0⃣  汇总 vol 序列
    vol_df = pd.concat(
        {c: data_frames[c]['vol'].rename(c) for c in data_frames},
        axis=1
    ).dropna(how='any')

    good_set = set(good_group)

    good_cols  = [c for c in vol_df.columns if c in good_set]          # ← list
    other_cols = [c for c in vol_df.columns if c not in good_set]      # ← list

    # 1⃣  组内求和
    vol_good  = vol_df[good_cols].sum(axis=1)
    vol_other = vol_df[other_cols].sum(axis=1)

    # 2⃣  各自归一化 0-1
    norm = lambda s: (s - s.min()) / (s.max() - s.min())
    vol_good_n  = norm(vol_good)
    vol_other_n = norm(vol_other)

    # 3⃣  差值走势
    vol_spread = vol_good_n - vol_other_n


    # ① 计算各自振幅
    stack_range = stack_profile.max() - stack_profile.min()
    target_range = 0.5 * stack_range            # 目标振幅

    vol_range = vol_spread.max() - vol_spread.min()
    if vol_range == 0:
        raise ValueError("vol_spread 振幅为 0，无法缩放")

    # ② 线性缩放（保持正负号 & 中心）
    scale = target_range / vol_range
    vol_spread_scaled = vol_spread * scale

    # ③ 可选：让零点对齐 stack_profile 的中位数
    # mid_shift = stack_profile.median() - vol_spread_scaled.median()
    # vol_spread_scaled += mid_shift



    # ───────── 数据准备 ─────────────────────────────────────────
    total_vol  = vol_df.sum(axis=1)                # 全市场总成交量
    vol_btc    = vol_df['btc']                     # BTC 成交量
    # ② 成交量栏 (ax_vol)  ────────────────────────────────────

    # if time_gap.find('h') != -1:
    #     # —— 1) 确保为按相同索引对齐的 Series —— 
    #     sp  = pd.Series(stack_profile, index=date_range)              # stack_profile
    #     mid = pd.Series(stack_mid,   index=date_range)                # 布林中轨(均线)
    #     ix  = sp.index.intersection(mid.index)
    #     sp, mid = sp.loc[ix], mid.loc[ix]

    #     # —— 2) 计算穿越点：差值符号发生改变（严格穿过）——
    #     diff = sp - mid
    #     s    = np.sign(diff.to_numpy())                               # -1/0/1
    #     valid = ~np.isnan(s[1:]) & ~np.isnan(s[:-1])
    #     cross_idx = np.where((s[1:] * s[:-1] < 0) & valid)[0] + 1     # 对应 sp 的索引位置

                
    # -------- 可视化示例 --------------------------------------------


    fig, (ax1, ax_trend, ax_vol) = plt.subplots(
        3, 1, sharex=True, figsize=(16, 11),
        gridspec_kw={'height_ratios': [4, 2, 1]}   # 上:中:下 = 4:2:1
    )

    # ── 2.2 成交量柱形图 ───────────────────────────────────
    ax_vol.bar(date_range, total_vol,
            color='gray', alpha=0.6, width=0.8, label='Total Volume')

    ax_vol.set_ylabel('Total Vol', fontsize=10)
    ax_vol.tick_params(axis='y', labelsize=8)
    ax_vol.grid(alpha=0.2, linestyle='--')
    # ax_vol.legend(loc='upper right', fontsize=8)

    # 2.1 灰色柱：总成交量  (左轴)
    ax_vol.bar(date_range, total_vol,
            color='gray', alpha=.6, width=0.8, label='Total Volume')
    ax_vol.set_ylabel('Total Vol', color='gray', fontsize=9)
    ax_vol.tick_params(axis='y', labelcolor='gray', labelsize=8)
    ax_vol.grid(alpha=0.25, ls='--')

    # 2.2 右轴：vol_spread_scaled + BTC vol
    axv = ax_vol.twinx()


    # 橙色折线：BTC 成交量（归一化到同轴方便对比）
    btc_scaled = (vol_btc - vol_btc.min()) / (vol_btc.max() - vol_btc.min())
    axv.plot(date_range, btc_scaled,
            color='orange', lw=1.8, label='BTC Volume (norm)')

    axv.set_ylabel('Norm Value', color='purple', fontsize=9)
    axv.tick_params(axis='y', labelcolor='purple', labelsize=8)

    # # ③ 图例合并 ────────────────────────────────────────────
    # h1, l1 = ax_vol.get_legend_handles_labels()
    # h2, l2 = axv.get_legend_handles_labels()
    # ax_vol.legend(h1+h2, l1+l2, loc='upper left', fontsize=8, ncol=2)

    ax1.bar(date_range, reduce_part,
            label='REDUCE Daily Returns in 1d', alpha=0.8, color='purple')

        # 紫色虚线：归一化差值
    ax1.plot(date_range, vol_spread_scaled,
            color='cyan', ls='--', lw=2, label='Vol-Spread (scaled)')


    # ① 计算水平位
    sup_stack, res_stack = find_levels(stack_profile, win=20, tol=0.05, min_hits=2)
    sup_btc,   res_btc   = find_levels(btc_trend,      win=20, tol=0.05, min_hits=2)

    # ② 绘图：粗点划线，支撑=绿，压力=深蓝
    draw_segment_levels(ax1, sup_stack, 'red', 'Stack Support',  date_range)
    draw_segment_levels(ax1, res_stack, 'pink', 'Stack Resist',   date_range)
    draw_segment_levels(ax1, sup_btc,   '#55CC77', 'BTC Support',    date_range)
    draw_segment_levels(ax1, res_btc,   '#3355FF', 'BTC Resist',     date_range)




    # 2.2 叠加布林带
    ax1.plot(date_range, stack_mid,   color='gray',  lw=1,  ls='--', label='Stack BB Middle')
    ax1.plot(date_range, stack_upper, color='black', lw=1,  ls='-.', label='Stack BB Upper')
    ax1.plot(date_range, stack_lower, color='black', lw=1,  ls='-.', label='Stack BB Lower')
    ax1.fill_between(date_range, stack_lower, stack_upper,  color='gray', alpha=0.08)            # 阴影区可选

    eps = 0.05 * (stack_upper - stack_lower)

    # ---------- 1. Bollinger 触碰点（绿三角）------------------------------
    touch_upper = np.where(stack_profile >= stack_upper)[0]
    touch_lower = np.where(stack_profile <= stack_lower)[0]

    # ax1.scatter(date_range[touch_upper], stack_profile.iloc[touch_upper],
    #             marker='v', color='#8fbce6', s=55,
    #             label='Touch BB Upper', zorder=5)
    # ax1.scatter(date_range[touch_lower], stack_profile.iloc[touch_lower],
    #             marker='^', color='#1f77b4', s=55,
    #             label='Touch BB Lower', zorder=5)

    # ---------- Bollinger 触碰 ----------
    ax1.scatter(date_range[touch_upper], stack_profile.iloc[touch_upper],#  * 1.0033,
                marker='v', color='#00E5FF', edgecolors='black', alpha=0.75,
                linewidths=.4, s=70, label='STACK Touch BB Upper', zorder=5)

    ax1.scatter(date_range[touch_lower], stack_profile.iloc[touch_lower],# * 0.9966,
                marker='^', color='#0066FF', edgecolors='black', alpha=0.75,
                linewidths=.4, s=70, label='STACK Touch BB Lower', zorder=5)



    if r2 >= r2_th:
        ax1.plot(idx, upper,  ls='--', color='red',  lw=1, label='LR Channel Upper')
        ax1.plot(idx, lower,  ls='--', color='red',  lw=1, label='LR Channel Lower')
        # ax1.fill_between(idx, lower, upper, color='green', alpha=0.075)

         # 2.1 保证 channel 上下轨扩展到完整索引（非通道区 NaN）
        upper_full = pd.Series(index=stack_profile.index, dtype=float)
        lower_full = pd.Series(index=stack_profile.index, dtype=float)
        upper_full.loc[idx] = upper
        lower_full.loc[idx] = lower

        # 2.2 取前后差分判断"穿破"
        prev = stack_profile.shift(1)
        up_cross = (prev < upper_full) & (stack_profile > upper_full)
        down_cross = (prev > lower_full) & (stack_profile < lower_full)

        # 2.3 标记
        # ax1.scatter(stack_profile.index[up_cross],
        #             stack_profile[up_cross],
        #             marker='v', color='#ffbb78', s=60,
        #             label='Break Channel ↑', zorder=6)

        # ax1.scatter(stack_profile.index[down_cross],
        #             stack_profile[down_cross],
        #             marker='^', color='#ff7f0e', s=60,
        #             label='Break Channel ↓', zorder=6)
        # ---------- 通道穿破 ----------
        ax1.scatter(stack_profile.index[up_cross], stack_profile[up_cross],# * 1.01,
                    marker='v', color='#FFA200', edgecolors='black',  alpha=0.75,
                    linewidths=.4, s=80, label='Touch UP Channel ↑', zorder=6)

        ax1.scatter(stack_profile.index[down_cross], stack_profile[down_cross],#  * 0.99,
                    marker='^', color='#FF2400', edgecolors='black',  alpha=0.75,
                    linewidths=.4, s=80, label='Touch LOW Channel ↓', zorder=6)


    ax1.plot(date_range, btc_trend,
             label='BTC/USDT Trend', color='orange')
    ax1.plot(date_range, upper_trend,
             label='upper bollinger', color='black', alpha=0.6)
    ax1.plot(date_range, lower_trend,
             label='lower bollinger', color='black', alpha=0.6)
    
    # ---------- 2. 其它币（含缩放后 BTC）-------------------------------
    # 收集所有币种的缩放数据用于计算布林带位置
    
    for coin, df in data_frames.items():
        scaled = (df['close'] / df['close'].iloc[0] - 1) * 100
        if coin == 'btc':
            # 缩放后 BTC : 深橘粗虚线
            ax_trend.plot(date_range, scaled,
                    color='#CC5500', lw=2.5, ls='--')
        else:
            ax_trend.plot(date_range, scaled,
                    color=next(color_iter),
                    ls=next(ls_iter),
                    lw=1.0, alpha=.5)        # label 省略避免图例过长

    # ---------- 3. 计算布林带位置变化并标记 --------------------------------
    if len(data_frames) > 0:
        # 为每个币种计算各自的布林带
        coin_bollinger_data = {}
        for coin, df in data_frames.items():
            if 'close' in df.columns and len(df) >= 20:
                # 计算每个币种的布林带
                close_prices = df['close']
                ma20 = close_prices.rolling(window=20).mean()
                std20 = close_prices.rolling(window=20).std()
                
                # 计算布林带上轨和下轨
                upper_band = ma20 + (std20 * 2.0)  # 2倍标准差
                lower_band = ma20 - (std20 * 2.0)  # 2倍标准差

                # 填充NaN值
                ma20 = ma20.fillna(method='bfill', limit=19)
                upper_band = upper_band.fillna(method='bfill', limit=19)
                lower_band = lower_band.fillna(method='bfill', limit=19)

                coin_bollinger_data[coin] = {
                    'close': close_prices,
                    'high': df['high'] if 'high' in df.columns else close_prices,
                    'low': df['low'] if 'low' in df.columns else close_prices,
                    'middle': ma20,
                    'upper': upper_band,
                    'lower': lower_band,
                }
        
        # 计算每个时间点最高价格在上布林带之上和最低价格在下布林带之下的币种比例
        above_upper_band_ratio = []
        below_lower_band_ratio = []
        
        for i in range(len(date_range)):
            above_upper_count = 0
            below_lower_count = 0
            total_count = 0
            
            for coin, boll_data in coin_bollinger_data.items():
                if i < len(boll_data['close']) and not pd.isna(boll_data['close'].iloc[i]):
                    total_count += 1
                    # 检查最高价格是否在上布林带之上
                    if (i < len(boll_data['high']) and not pd.isna(boll_data['high'].iloc[i]) and
                        i < len(boll_data['upper']) and not pd.isna(boll_data['upper'].iloc[i])):
                        if boll_data['high'].iloc[i] > boll_data['upper'].iloc[i]:
                            above_upper_count += 1
                    
                    # 检查最低价格是否在下布林带之下
                    if (i < len(boll_data['low']) and not pd.isna(boll_data['low'].iloc[i]) and
                        i < len(boll_data['lower']) and not pd.isna(boll_data['lower'].iloc[i])):
                        if boll_data['low'].iloc[i] < boll_data['lower'].iloc[i]:
                            below_lower_count += 1
            
            if total_count > 0:
                above_upper_band_ratio.append(above_upper_count / total_count)
                below_lower_band_ratio.append(below_lower_count / total_count)
            else:
                above_upper_band_ratio.append(0)
                below_lower_band_ratio.append(0)
        
        # 为布林带比例线创建独立的坐标系
        ax_bollinger = ax_trend.twinx()  # 创建共享x轴但独立y轴的坐标系
        
        # 将比例数据转换为百分比并绘制
        above_upper_percent = [ratio * 100 for ratio in above_upper_band_ratio]
        below_lower_percent = [ratio * 100 for ratio in below_lower_band_ratio]
        
        # 绘制最高价格在上布林带之上的比例（绿色细线，点线样式）
        ax_bollinger.plot(date_range, above_upper_percent, 
                         color='green', linewidth=1.5, alpha=0.7, 
                         linestyle=':', marker='o', markersize=2,
                         label='↑')
        
        # 绘制最低价格在下布林带之下的比例（红色细线，虚线样式）
        ax_bollinger.plot(date_range, below_lower_percent, 
                         color='red', linewidth=1.5, alpha=0.7, 
                         linestyle='--', marker='s', markersize=2,
                         label='↓')
        
        # 设置布林带比例坐标轴的标签和范围
        ax_bollinger.set_ylabel('布林带突破比例 (%)', fontsize=10)
        ax_bollinger.set_ylim(0, 100)
        ax_bollinger.grid(alpha=0.2)
        
        # 添加图例
        ax_bollinger.legend(loc='upper left', fontsize=8)


    # -------- 美化 trend 面板 -------------------------------------------
    ax_trend.set_ylabel('% change')
    ax_trend.grid(alpha=.3)

    # ax1.fill_between(date_range, lower_trend, upper_trend,  color='red', alpha=0.05)            # 阴影区可选

    ax1.scatter(date_range[above_upper], btc_trend[above_upper],
                marker='*', color='red', label='BTC > Upper Bollinger',
                zorder=2, alpha=0.75)
    ax1.scatter(date_range[below_lower], btc_trend[below_lower],
                marker='.', color='blue', label='BTC < Lower Bollinger',
                zorder=2, alpha=0.75)
    # ax1.scatter(date_range[above_upper], stack_above,
    #             color='#2ca02c', marker='v', label='Stack @ BTC > Upper',
    #             zorder=8)
    # ax1.scatter(date_range[below_lower], stack_below,
    #             color='#98df8a', marker='^', label='Stack @ BTC < Lower',
    #             zorder=8)
    ax1.scatter(date_range[above_upper], stack_above,# * 0.9933,
            marker='^', color='black', edgecolors='black',  alpha=0.75,
            linewidths=.4, s=75, label='BTC > Upper', zorder=8)

    ax1.scatter(date_range[below_lower], stack_below,# * 1.0066,
            marker='v', color='gray', edgecolors='black',  alpha=0.75,
            linewidths=.4, s=75, label='BTC < Lower', zorder=8)

    # # ① ---- 计算平滑序列 -------------------------------------------------
    # WINDOW = 31          # 必须为奇数；根据采样频率自行放大/缩小
    # POLY   = 3

    # s_stack = savgol_filter(stack_profile.values, WINDOW, POLY)
    # s_btc   = savgol_filter(btc_trend.values,     WINDOW, POLY)

    # # ② ---- 原始曲线（仍保留，可选择注释掉） ------------------------------

    # # ③ ---- 平滑拟合曲线 -------------------------------------------------
    # ax1.plot(date_range, s_stack,  ls='--', color='red',
    #          linewidth=2.5, label='BTC/Others Smoothed')
    # ax1.plot(date_range, s_btc,    ls='--', color='blue',
    #          linewidth=2.5, label='BTC/USDT Smoothed')


    # slope   = savgol_filter(stack_profile.values, WINDOW, POLY, deriv=1)

    # # 2⃣ 拐点检测
    # eps = 1e-4                       # 斜率阈值；可按数据量级调整
    # sign = np.sign(slope)

    # # 负→正 （底部拐点）
    # long_idx = np.where((sign[1:] > 0) & (sign[:-1] < 0) & (np.abs(slope[1:]) > eps))[0] + 1
    # # 正→负 （顶部拐点）
    # short_idx = np.where((sign[1:] < 0) & (sign[:-1] > 0) & (np.abs(slope[1:]) > eps))[0] + 1

    # # 拐点标注
    # ax1.scatter(date_range[long_idx],  s_stack[long_idx], 
    #             marker='o', color='blue',  s=50, zorder=6, label='Savegol Trend Up')
    # ax1.scatter(date_range[short_idx], s_stack[short_idx],
    #             marker='o', color='red',  s=50, zorder=6, label='Savegol Trend Down')

    
    # ── 1. 计算最后一个值 ───────────────────────────────
    y_last = stack_profile.iloc[-1]  # 或 stack_profile[-1]（若是 ndarray）
    pct_th = 0.015  # ±2%
    half_win = 10  # 前后各 10 步
    full_win = 2 * half_win + 1

    # ── 2. 条件①：与最后一个值相差 ≤1% ──────────────────
    mask_1pct = (stack_profile.sub(y_last).abs() <= pct_th * y_last)

    # ── 3. 条件②：前后 10 步窗口内是极值 ─────────────────
    roll_max = stack_profile.rolling(full_win, center=True, min_periods=1).max()
    roll_min = stack_profile.rolling(full_win, center=True, min_periods=1).min()
    mask_ext = (stack_profile == roll_max) | (stack_profile == roll_min)

    # ── 4. 综合两重条件 ──────────────────────────────────
    target_idx = mask_1pct & mask_ext

    # ── 5. 绘制紫色三角形 ────────────────────────────────
    ax1.scatter(date_range[target_idx],  # 横坐标
                stack_profile[target_idx],  # 纵坐标
                color='purple',
                marker='o',
                s=30,
                label=f'±1% & local extrema ({half_win}-step)',
                zorder=9)


    
    # 画水平线
    ax1.axhline(y=y_last, color='purple', linestyle='--', linewidth=0.8, label=f'Last stack_profile = {y_last:.2f}')

    ax1.plot(date_range, stack_profile, label='TOPDOGINDEX', color='green', linewidth=2)
    # 定义独特的颜色和统一线型（虚线）
    unique_colors = [
        '#FF6F61',  # 柔和红
        '#6B5B95',  # 静谧紫
        '#88B04B',  # 清新绿
        '#F7CAC9',  # 浅粉
        '#92A8D1',  # 温柔蓝
        '#955251',  # 棕紫
        '#B565A7',  # 淡紫
        '#009B77',  # 石绿
        '#DD4124',  # 鲜橙
        '#D65076',  # 玫紫
        '#45B8AC',  # 青绿
        '#EFC050',  # 金色
    ]
    unique_linestyle = (0, (5, 2))  # 自定义为虚线线型

    for stack_profile_idx in range(len(stack_profiles) - 1):
        color = unique_colors[stack_profile_idx % len(unique_colors)]
        ax1.plot(
            date_range,
            stack_profiles[stack_profile_idx + 1],
            label=f'TOPDOGINDEX {stack_profile_idx+1}',
            color=color,
            linewidth=2.5,
            linestyle=unique_linestyle
        )

    # if time_gap.find('h') != -1:
    #     # —— 3) 绘制黑色小圆点（不进图例）——
    #     ax1.scatter(sp.index[cross_idx], sp.iloc[cross_idx], marker='o', color='black', s=28, zorder=8)


    # ax1.set_xlabel('Date')
    ax1.set_ylabel('Price / Return')
    ax1.grid(alpha=0.3)

    # ── 2. 第二坐标轴：MACD & Signal ───────────────────────────────
    ax2 = ax1.twinx()  # 共用 x，独立 y
    bar_w = 0.8



    # ── 3. 合并图例 & 美化 ─────────────────────────────────────────
    # h1, l1 = ax1.get_legend_handles_labels()
    # h2, l2 = ax2.get_legend_handles_labels()
    # ax1.legend(h1 + h2, l1 + l2, loc='upper left')

    plt.title(
        f'goodGroup {",".join(good_group)} vs. Top {len(top10_coins)} Coins at {BeijingTime(format="%H:%M:%S")}, BTC: {round(exchange.get_price_now("btc"))}, T:{time_gap.upper()}')

    plt.tight_layout()
    plt.ylabel('Daily Returns (%)', fontsize=16)
    # plt.legend()
    plt.grid(True)
    out_dir = Path(get_current_dir()) / 'chart_for_group'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / f'comparison_chart_{prex}_{time_gap}.png')
    plt.savefig(out, dpi=150)  # 保存图表
    # plt.show()
    plt.close('all')  # 关闭所有图形
    gc.collect()  # 强制垃圾回收

    # ---------- 新增：绘制stack_profile和btc_trend不同系数的平均值图表 ----------
    fig_avg, ax_avg = plt.subplots(1, 1, figsize=(16, 8))
    # 定义系数列表，0.15 到 1.5，步长 0.15
    coefficients = [round(x, 2) for x in np.arange(0.15, 1.5 + 0.01, 0.15)]
    # 自动生成配色数量适应系数数量
    color_map = cm.get_cmap('rainbow', len(coefficients))
    colors = [color_map(i) for i in range(len(coefficients))]
    # 计算并绘制每条曲线
    for i, coeff in enumerate(coefficients):
        # 计算平均值：(stack_profile + btc_trend * coefficient) / 2
        avg_curve = (stack_profile + btc_trend * coeff) / 2
        
        ax_avg.plot(date_range, avg_curve, 
                   color=colors[i], linewidth=2.5, alpha=0.8,
                   label=f'Avg (Stack + BTC×{coeff})')
    
    # 单独绘制原始曲线作为参考
    ax_avg.plot(date_range, stack_profile, 
               color='green', linewidth=2, alpha=0.6, linestyle='--',
               label='Stack Profile (原始)')
    ax_avg.plot(date_range, btc_trend, 
               color='orange', linewidth=2, alpha=0.6, linestyle='--',
               label='BTC Trend (原始)')
    
    # 设置图表属性
    ax_avg.set_title(f'Stack Profile & BTC Trend 平均值曲线对比 - {time_gap.upper()}', fontsize=14)
    ax_avg.set_xlabel('时间', fontsize=12)
    ax_avg.set_ylabel('数值', fontsize=12)
    ax_avg.grid(alpha=0.3)
    ax_avg.legend(loc='upper left', fontsize=10)
    
    # 保存新图表
    out_avg = str(out_dir / f'avg_curves_{prex}_{time_gap}.png')
    plt.savefig(out_avg, dpi=150)
    plt.close(fig_avg)
    gc.collect()
    
    # 同步到 /var/www/html/ 目录
    if HOST_IP.find(SERVER_IP) != -1:
        os.system(f'cp {out_avg} /var/www/html/')
    else:
        # os.system(f'scp {out_avg} root@{SERVER_IP}:/var/www/html/')
        pass
    
    print(f"📊 平均值曲线图表已保存: {out_avg}")
    print(f"📤 已同步到 /var/www/html/ 目录")
    


def get_good_bad_coin_group(length=5):
    timeframes = ['1m', '5m', '15m', '1h']
    coins = COINS
    volatilities = {coin: [] for coin in coins}
    if length > len(coins) // 2:
        print(f'全部币数 {len(COINS)}, 你需要的长度是:{length}')
    # Fetch data for each coin across each timeframe
    for coin in tqdm(coins, desc='coin process'):
        for timeframe in tqdm(timeframes, desc='time'):
            data = fetch_and_process(coin, timeframe)
            volatility = data['daily_return'].std()  # Calculate standard deviation of daily returns
            volatilities[coin].append(volatility)

    # Calculate average volatility for each coin
    avg_volatilities = {coin: np.mean(stats) for coin, stats in volatilities.items()}

    # Sort coins by their average volatility (ascending order)
    sorted_coins = sorted(avg_volatilities, key=avg_volatilities.get)

    # Select the 5 coins with the highest average volatility
    worst_performance_coins = sorted_coins[:length]
    best_performance_coins = sorted_coins[-length:]
    print("Coins with the worst average volatility:", worst_performance_coins)
    print("Coins with the best average volatility:", best_performance_coins)
    local_bp = Path(get_current_dir()) / 'best_performance_coins.txt'
    with open(str(local_bp), 'w') as f:
        f.write(','.join(best_performance_coins))
    # 保持原有同步逻辑，但使用本地文件路径
    # os.system(f'scp {str(local_bp)} root@{SERVER_IP}:/root/Quantify/okx')
    return worst_performance_coins, best_performance_coins


def launch_fetchers():
    for tf, sec in TIMEFRAMES.items():
        th = threading.Thread(target=fetch_loop, args=(COINS, tf, sec), daemon=True)
        th.start()
    total = len(TIMEFRAMES) * len(COINS)
    print(f"🚀 已启动 {len(TIMEFRAMES)} 条采集线程，等待首轮数据…")



    # ② 阻塞检查 shared_data 完整性 -----------------------------------
    while True:
        ready = 0
        for tf in TIMEFRAMES:
            tf_dict = shared_data.get(tf, {})
            for c in COINS:
                df = tf_dict.get(c)
                if df is not None and not df.empty:
                    ready += 1

        pct = ready / total * 100
        print(f"\r⏳ 数据填充进度: {ready}/{total}  ({pct:5.1f}%)", end='', flush=True)

        if ready == total:
            print("\n✅ shared_data 已就绪，开始后续逻辑")
            break
        time.sleep(1)

# ---------------------------------------------------------------
# ② 多周期一致性扫描  (保持前面写好的 scan_coins 不变)
# ---------------------------------------------------------------
def scan_coins():
    tfs = ['1m', '15m', '1h', '4h', '1d']
    for coin in COINS:                                  # COINS: 全部小写
        dfs = {}
        try:
            for tf in tfs:
                dfs[tf] = fetch_and_process(coin, tf)
                time.sleep(0.05)                        # 节流
            multi_tf_ma_bBands_signal(
                dfs['1m'], dfs['15m'], dfs['1h'],
                dfs['4h'], dfs['1d'],
                symbol=coin.upper()
            )
        except Exception as e:
            print(f"❌ {coin.upper()} 处理失败:", e)

# ---------------------------------------------------------------
# ③ 每分钟运行一次 scan_coins 的循环线程
# ---------------------------------------------------------------
def scan_loop(interval=60):
    while True:
        t0 = time.time()
        scan_coins()
        dt = time.time() - t0
        sleep_sec = max(5, interval - dt)               # 至少歇 5 秒
        time.sleep(sleep_sec)


def hedge_optimization_worker():
    """
    等待数据准备就绪后，运行对冲配置优化
    """
    print("🔄 启动对冲配置优化线程...")
    
    # 等待数据准备就绪
    while True:
        try:
            # 检查日线数据是否可用
            daily_data = {}
            for coin in COINS:
                df = fetch_and_process(coin, '1d')
                if df is not None and len(df) >= 60:
                    daily_data[coin] = df
            
            if len(daily_data) >= 6:  # 至少需要6个币种的数据
                print(f"✅ 日线数据准备就绪，开始优化搜索...")
                break
            else:
                print(f"⏳ 等待日线数据准备就绪... (当前: {len(daily_data)} 个币种)")
                time.sleep(30)
        except Exception as e:
            print(f"❌ 检查数据时出错: {e}")
            time.sleep(30)
    
    # 运行优化搜索
    try:
        best_configs = optimize_hedge_configuration(
            data_frames=daily_data,
            lookback=200,
            n_trials=2000,  # 增加搜索次数
            precision=0.1
        )
        
        # 保存结果到文件
        if best_configs:
            save_dir = Path(get_current_dir()) / 'hedge_optimization'
            save_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 1. 保存原始JSON数据
            result_file = save_dir / f'best_hedge_configs_{timestamp}.json'
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(best_configs, f, indent=2, ensure_ascii=False)
            
            # 2. 保存直观的描述文档
            summary_file = save_dir / f'hedge_summary_{timestamp}.md'
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# 对冲配置优化结果\n\n")
                f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**数据来源**: 日线K线数据 (回看期: 60天)\n")
                f.write(f"**搜索次数**: 2000次\n")
                f.write(f"**约束条件**: BTC+BNB必选多头, BTC权重≥20%, 多头≤总币种1/5, 最大权重≤最小权重×3\n\n")
                f.write("---\n\n")
                
                f.write(f"## 📊 优化统计\n\n")
                f.write(f"- **总配置数**: {len(best_configs)}\n")
                f.write(f"- **前10名配置**: 按波动率升序排列\n")
                f.write(f"- **优化目标**: 最小化diff_returns波动率\n\n")
                
                f.write("## 🏆 最优配置详情\n\n")
                
                for i, config in enumerate(best_configs, 1):
                    f.write(f"### 第{i}名 - 波动率: {config['volatility']:.4f}\n\n")
                    f.write(f"**风险指标**:\n")
                    f.write(f"- 波动率: `{config['volatility']:.4f}`\n")
                    f.write(f"- 夏普比率: `{config['sharpe_ratio']:.4f}`\n")
                    f.write(f"- 平均收益: `{config['diff_returns_mean']:.4f}%`\n\n")
                    
                    f.write(f"**多头配置** (权重总和: {sum(config['long_weights'].values()):.3f}):\n")
                    for coin, weight in sorted(config['long_weights'].items(), key=lambda x: x[1], reverse=True):
                        f.write(f"- {coin.upper()}: `{weight:.3f}` ({weight*100:.1f}%)\n")
                    f.write(f"\n**空头配置**: {', '.join([c.upper() for c in config['short_coins']])}\n\n")
                    
                    f.write("---\n\n")
                
                f.write("## 📈 配置分析\n\n")
                f.write("### 权重分布统计\n\n")
                
                # 统计权重分布
                all_weights = {}
                for config in best_configs:
                    for coin, weight in config['long_weights'].items():
                        if coin not in all_weights:
                            all_weights[coin] = []
                        all_weights[coin].append(weight)
                
                f.write("| 币种 | 平均权重 | 最大权重 | 最小权重 | 出现次数 |\n")
                f.write("|------|----------|----------|----------|----------|\n")
                
                for coin in sorted(all_weights.keys()):
                    weights = all_weights[coin]
                    f.write(f"| {coin.upper()} | {np.mean(weights):.3f} | {max(weights):.3f} | {min(weights):.3f} | {len(weights)} |\n")
                
                f.write(f"\n### 空头币种统计\n\n")
                short_count = {}
                for config in best_configs:
                    for coin in config['short_coins']:
                        short_count[coin] = short_count.get(coin, 0) + 1
                
                for coin, count in sorted(short_count.items(), key=lambda x: x[1], reverse=True):
                    f.write(f"- {coin.upper()}: {count}次\n")
                
                f.write(f"\n---\n\n")
                f.write(f"*此报告由对冲配置优化系统自动生成*\n")
            
            print(f"💾 优化结果已保存:")
            print(f"   📄 原始数据: {result_file.name}")
            print(f"   📋 详细报告: {summary_file.name}")
            
            # 同步到服务器
            if HOST_IP.find(SERVER_IP) != -1:
                os.system(f'cp {result_file} ~/mysite/static/images/')
            else:
                os.system(f'scp {result_file} azureuser@{SERVER_IP}:~/Quantify/ctos/apps/website/static/images/')
        
    except Exception as e:
        print(f"❌ 对冲优化过程中出错: {e}")
    
    print("🏁 对冲配置优化完成")


def scan_loop(interval=60):
    while True:
        t0 = time.time()
        scan_coins()
        dt = time.time() - t0
        sleep_sec = max(5, interval - dt)               # 至少歇 5 秒
        time.sleep(sleep_sec)


if __name__ == '__main__':
    launch_fetchers()
    # time.sleep(len(COINS) * 1.5)

    start_time = time.time()
   # 将 shared_data 作为引用传入
   #  threading.Thread(target=clock_worker, args=(shared_data,), daemon=True).start()
    # 定义时间间隔到文件名的映射
    timegap_to_filename = {
        '1m':  '1m.png',
        '5m':  '15m.png',
        '15m': '30m.png',
        '1h':  '1H.png',
        '4h':  '4H.png',
        '1d':  '1D.png'
    }
    update_interval = {          # 每个周期的刷新秒数
        '1m': 5,
        '5m': 10,
        '15m':15,
        '1h': 20,
        '4h': 25,
        '1d': 30
    }
    last_run = {g: 0 for g in update_interval}   # 初始化
    worst_performance_coins, best_performance_coins = get_good_bad_coin_group(18)
    # threading.Thread(target=scan_loop, daemon=True).start()
    # threading.Thread(target=hedge_optimization_worker, daemon=True).start()
    # for idx, gap in enumerate(['1m','5m','15m','1h','4h','1d']):
    #     data_frame = {c: fetch_and_process(c, gap) for c in COINS}
    #     score, ranks, weight = factor_strength_ranking(
    #         data_frames=data_frame,
    #         lookback = 60,   # 60 根×5 min ≈ 5 h
    #     )

    #     print(f"{idx}, {gap} 综合得分:\n", score)

    #     market_idx = market_strength_index(data_frame, lookback=60)
    #     print(f"当前市场强弱指数：{market_idx:.4f}")
        # if idx == 5:
        #     clusters = cluster_kline_graph(
        #         data_frame,
        #         lookback   = 60,   # 过去 60 天
        #         n_clusters = 6     # 想分 4 簇
        #     )
        #     for cid, members in clusters.items():
        #         print(f"Cluster {cid}: {members}")
    # ---------------------------------------------------------------
    while True:
        debug_mode = False
        now = time.time()
        for idx, gap in enumerate(['1m','5m','15m','1h','4h','1d']):
            if now - last_run[gap] < update_interval[gap]:
                continue                      # 未到刷新点
            if idx == 1:
                for xx in ['1m', '5m', '15m']:
                    if debug_mode:  
                        draw_allcoin_trend(xx, COINS)        # COINS 是你的币种列表
                    else:
                        try:
                            draw_allcoin_trend(xx, COINS)        # COINS 是你的币种列表
                        except Exception as e:
                            print("主循环 draw_allcoin_trend异常:", e)
            # ---------- 生成并发送主图 ----------
            chart_name = f'all_coin-{idx}'
            good_group = []
            if not debug_mode:
                try:
                    main1(COINS, prex=chart_name, time_gap=gap, good_group=good_group, all_rate=[])
                except Exception as e:
                    print("主循环main1异常:", e)
            else:
                main1(COINS, prex=chart_name, time_gap=gap, good_group=good_group, all_rate=[])
            out_dir = Path(get_current_dir()) / 'chart_for_group'
            out_dir.mkdir(parents=True, exist_ok=True)
            local = str(out_dir / f'comparison_chart_{chart_name}_{gap}.png')
            remote = timegap_to_filename[gap]
            if HOST_IP.find(SERVER_IP) != -1:
                os.system(f'cp {local} ~/mysite/static/images/{remote}')
            else:
                os.system(f'scp {local} azureuser@{SERVER_IP}:~/Quantify/ctos/apps/website/static/images/comparison_chart_{chart_name}_{gap}.png')

            last_run[gap] = now              # 更新时间戳
            print(f"[{gap}] 更新完成，用时 {round(time.time()-now,2)} 秒")
                    # ---------- 调用 ----------

        # 每日刷新一次 best / worst 组合
        if int(now//3600) != int((now-10)//3600):
            worst_performance_coins, best_performance_coins = get_good_bad_coin_group(18)

        if (now - start_time) % 600 == 0:
            log_asset()
            plot_asset_trend()

        time.sleep(2)        # 轻量轮询
