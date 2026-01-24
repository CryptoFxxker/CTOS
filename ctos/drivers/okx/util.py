import  pandas as pd
import  numpy as np
import json
import socket
import os
import inspect
import math

try:
    import pyfiglet
except Exception as e:
    print('没这个pyfiglet包')

base_url = "https://data.binance.vision/data/spot/daily/klines"

def round_dynamic(x: float) -> float:
    """
    动态保留有效数字：
    - x > 1000: 保留 6 位有效数字
    - 100 <= x <= 1000: 保留 5 位有效数字
    - x < 100: 保留 4 位有效数字
    """
    if x == 0:
        return 0.0

    # 确定保留位数
    if abs(x) > 1000:
        digits = 6
    elif abs(x) >= 100:
        digits = 5
    else:
        digits = 4

    magnitude = math.floor(math.log10(abs(x)))
    scale = 10 ** (magnitude - digits + 1)
    result = round(x / scale) * scale

    # 额外处理浮点误差，保留到合理小数位
    return float(f"{result:.12g}")

def round_to_two_digits(x: float) -> float:
    """
    从第一个非零数字开始，保留两位有效数字，四舍五入。
    """
    if x == 0:
        return 0.0

    magnitude = math.floor(math.log10(abs(x)))
    scale = 10 ** (magnitude - 1)
    result = round(x / scale) * scale

    # 额外处理浮点误差，保留到合理小数位
    return float(f"{result:.12g}")

def who_called_me():
    # 获取当前调用栈的上一层
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_name = caller_frame.f_code.co_name
    return caller_name

def pad_dataframe_to_length_fast(df, length):
    """优化版，适合大数据量"""
    current_len = len(df)
    if current_len >= length:
        return df.iloc[:length].copy()

    # 使用numpy快速填充
    last_row = df.iloc[-1].values
    fill_data = np.tile(last_row, (length - current_len, 1))

    return pd.concat([
        df,
        pd.DataFrame(fill_data, columns=df.columns)
    ], ignore_index=True)

def cal_amount(coin, amount, coins, btc_rate=0.5, split_rate={}):
    # if len(coins) == 1:
    #     return amount
    # else:
    #     return amount / len(coins)

    if btc_rate <= 0 or btc_rate >= 1:
        btc_rate = 0.5
    if coin == 'btc':
        return amount * btc_rate
    else:
        if len(split_rate) == 0:
            return amount * (1 - btc_rate) / (len(coins) - 1)
        else:
            if 'btc' in split_rate:
                all_amount_of_shanzhai = sum({k:v for k,v in split_rate.items()}.values())
            else:
                all_amount_of_shanzhai = sum(split_rate.values())
            shanzhai_rate = split_rate[coin] / all_amount_of_shanzhai
            if shanzhai_rate <= 0 or shanzhai_rate > 1:
                shanzhai_rate = 0
            return amount * (1 - btc_rate) * shanzhai_rate


def number_to_ascii_art(number):
    """将数字转为ASCII艺术字"""
    ascii_art = pyfiglet.figlet_format(str(number), font="big")  # 可选字体：slant, block等
    return ascii_art



def format_decimal_places(df, decimal_places=1):
    # Apply formatting to each floating-point column
    for col in df.select_dtypes(include=['float64', 'float32']).columns:
        df[col] = df[col].map(lambda x: f"{x:.{decimal_places}f}")
    return df


def align_decimal_places(num1: float, num2: float) -> float:
    """
    将第二个数调整为与第一个数相同的小数位数

    参数:
        num1: 第一个浮点数，用于确定小数位数
        num2: 第二个浮点数，需要调整小数位数

    返回:
        调整小数位数后的第二个数
    """
    # 将数字转换为字符串以确定小数位数
    str_num1 = format(num1, '.10f')  # 使用足够大的精度来避免科学计数法
    str_num2 = format(num2, '.10f')

    # 找到第一个数的小数部分
    if '.' in str_num1:
        # 去除末尾的0
        decimal_part = str_num1.rstrip('0').split('.')[1]
        decimal_places = len(decimal_part)
    else:
        decimal_places = 0

    # 格式化第二个数以匹配小数位数
    if decimal_places == 0:
        return int(num2)
    else:
        return round(num2, decimal_places)


def convert_columns_to_numeric(df, columns=None):
    """
    Convert specified columns to numeric, or automatically detect and convert
    all columns that can be converted to numeric types.

    Parameters:
        df (DataFrame): The DataFrame to process.
        columns (list, optional): Specific list of columns to convert. If None,
                                  attempts to convert all columns.

    Returns:
        DataFrame: A DataFrame with converted columns.
    """
    if columns is None:
        # Attempt to convert all columns that can be interpreted as numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    else:
        # Only convert specified columns
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            else:
                print(f"Warning: Column '{col}' not found in DataFrame")
    return df




def get_host_ip():
    """
    查询本机ip地址
    :return: ip
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('114.114.114.114', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
        return ip


def BeijingTime(format='%Y-%m-%d %H:%M:%S'):
    from datetime import datetime
    from datetime import timedelta
    from datetime import timezone

    SHA_TZ = timezone(
        timedelta(hours=8),
        name='Asia/Shanghai',
    )

    # 协调世界时
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    # print(utc_now, utc_now.tzname())
    # print(utc_now.date(), utc_now.tzname())

    # 北京时间
    beijing_now = utc_now.astimezone(SHA_TZ)
    return beijing_now.strftime(format)


def save_order_detail_once(para):
    # print(para)
    string = json.dumps(para, indent=4)
    with open('trade_log_okex/%s-%s-%s.txt' % (para['symbol'], para['data'], para['timestamp']), 'w',
              encoding='utf8') as log:
        log.write(string)


def load_trade_log_once(code):
    with open('trade_log_okex/%s-log.txt' % code, 'r', encoding='utf8') as f:
        return json.load(f)


def save_trade_log_once(code, para):
    # print(para)
    with open('trade_log_okex/%s-log.txt' % code, 'w', encoding='utf8') as f:
        string = json.dumps(para, indent=4)
        f.write(string)


def load_gaps():
    with open('trade_log_okex/gaps.txt', 'r', encoding='utf8') as f:
        return json.load(f)


def load_para(name='parameters.txt'):
    try:
        with open(name, 'r', encoding='utf8') as f:
            return json.load(f)
    except Exception as e:
        print('cannot load ', name, e)
        return {}


def save_para(paras, name='parameters.txt'):
    string = json.dumps(paras, indent=4)
    if os.path.exists(name):
        with open(name, 'w', encoding='utf8') as log:
            log.write(string)
        return 
    with open(f'{name}', 'w', encoding='utf8') as log:
        log.write(string)


def load_rates(type):
    with open('trade_log_okex/%s_rates.txt' % type, 'r', encoding='utf8') as f:
        return json.load(f)


def save_rates_once(rates, type):
    string = json.dumps(rates, indent=4)
    with open('trade_log_okex/%s_rates.txt' % type, 'w', encoding='utf8') as log:
        log.write(string)


def save_gaps(gaps):
    string = json.dumps(gaps, indent=4)
    with open('trade_log_okex/gaps.txt', 'w', encoding='utf8') as log:
        log.write(string)

def update_rates(_rates):
    with open('_rates.txt', 'w') as out:
        out.write(json.dumps(_rates, indent=4))


def save_to_json(sorted_money, filename="limited_digits.json"):
    """
    将排序后的四个数字列表保存为 JSON 文件

    参数:
        sorted_money (list): 包含四个数字的列表
        filename (str): 要保存的 JSON 文件名
    """


    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)



def read_from_json(filename="limited_digits.json"):
    """
    从 JSON 文件读取四个数字数据

    参数:
        filename (str): 要读取的 JSON 文件名

    返回:
        dict: 包含四个数字的字典
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"错误: 文件 {filename} 不存在")
        return None
    except json.JSONDecodeError:
        print(f"错误: 文件 {filename} 格式不正确")
        return None

def get_rates():
    _rates = {}
    try:
        _rates = json.load(open('_rates.txt', 'r'))
    except Exception as e:
        _rates = {
        # 'ETH-USD-SWAP': {'gap': 30, 'sell': 3, 'price_bit': 2, 'amount_base':3, 'change_base':3000, 'change_gap': 120, 'change_amount':1},
        'ETH-USDT-SWAP': {'gap': 18.88, 'sell': 6.66, 'price_bit': 2, 'amount_base':0.1, 'change_base':2000, 'change_gap': 88.88, 'change_amount':0.01},
        'BTC-USDT-SWAP': {'gap': 288.88, 'sell':6.66 , 'price_bit': 1, 'amount_base':0.01, 'change_base':80000, 'change_gap': 8888.88, 'change_amount':0.01},
                # 'SHIB-USDT-SWAP': {'gap': 0.0000002, 'sell': 10, 'price_bit': 8, 'amount_base':1, 'change_base':0.000026, 'change_gap': 0.000001, 'change_amount':1},
                # 'DOGE-USDT-SWAP': {'gap': 0.0025, 'sell': 2.5, 'price_bit': 5, 'amount_base':1, 'change_base':0.14, 'change_gap': 0.01, 'change_amount':1},
                # 'ETH-BTC': {'gap': 0.00008, 'sell': 10, 'price_bit': 5, 'amount_base':0.002, 'change_base':0.05150, 'change_gap': 0.0006, 'change_amount':0.001},
                  }
        print("Load Rates Failed")
        with open('_rates.txt', 'w') as out:
            out.write(json.dumps(_rates, indent=4))
    return _rates

def get_order_times(symbol):
    type_freq = {
        'buy': 0,
        'sell': 0
    }
    with open('exist_okex.txt', 'r', encoding='utf8') as log:
        for line in log.readlines():
            if line.find(symbol) == -1:
                if symbol != 'eth':
                    continue
            if line.find('SELL') != -1 or line.find('sell') != -1:
                type_freq['sell'] += 1
            else:
                type_freq['buy'] += 1
    return type_freq


def batch_join_symbols(symbols, batch_size=9):
    """
    将字符串数组按指定批次大小拼接

    参数:
        symbols: 字符串列表
        batch_size: 每批处理的数量，默认为9

    返回:
        拼接后的字符串列表
    """
    result = []
    # 计算需要多少批次
    num_batches = len(symbols) // batch_size
    if len(symbols) % batch_size != 0:
        num_batches += 1
    for i in range(num_batches):
    # 获取当前批次的元素
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch = symbols[start_index:end_index]
        # 拼接当前批次的元素
        joined_str = ",".join(batch)  # 使用空格连接，可根据需要修改连接符
        result.append(joined_str)
    return result


rate_price2order = {
    'btc': 0.01,
    'eth': 0.1,
    'xrp': 100,
    'bnb': 0.01,
    'sol': 1,
    'ada': 100,
    'doge': 1000,
    'trx': 1000,
    'ltc': 1,
    'shib': 1000000,
    'link': 1,
    'dot': 1,
    'om': 10,
    'apt': 1,
    'uni': 1,
    'hbar': 100,
    'ton': 1,
    'sui': 1,
    'avax': 1,
    'fil': 0.1,
    'ip': 1,
    'gala': 10,
    'sand': 10,
    'trump': 0.1,
    'pol': 10,
    'icp': 0.01,
    'cro': 10,
    'aave': 0.1,
    'xlm': 100,
    'bch': 0.1,
    'xaut': 0.001,
    'core': 1,
    'theta': 10,
    'algo': 10,
    'etc': 10,
    'near': 10,
    'hype': 0.1,
    'inj': 0.1,
    'ldo': 1,
    'atom': 1,
    'pengu': 100,
    'wld':1,
    'render':1,
    'pepe': 10000000,
    'ondo': 10,
    'stx': 10,
    'arb': 10,
    'jup': 10,
    'bonk': 100000,
    'op':1,
    'tia':1,
    'crv':1,
    'imx':1,
    'xtz':1,
    #'okb':0.01,
}


def get_min_amount_to_trade(get_okexExchage, path='min_amount_to_trade.json'):
    min_amount_to_trade = load_para(path)
    print(min_amount_to_trade)
    need_to_update = False
    for k in rate_price2order.keys():
        if not min_amount_to_trade.get(k, None):
            need_to_update = True
            break

    if need_to_update:
        try:
            eth = get_okexExchage('eth', 0, False)
        except Exception as e:
            print(e,'没法初始化交易器啊老弟！')
            return min_amount_to_trade
        for coin in rate_price2order.keys():
            if coin not in min_amount_to_trade:
                eth.symbol = f'{coin.upper()}-USDT-SWAP'
                price_to_buy = eth.get_price_now() * 0.95
                amount = 1
                deincrease_times = 0
                order, err = eth.buy(price_to_buy, amount)
                while order is not None:
                    eth.revoke_order(order)
                    amount /= 10
                    deincrease_times += 1
                    amount = round(amount, deincrease_times)
                    order, err = eth.buy(price_to_buy, amount)
                if deincrease_times > 0:
                    deincrease_times -= 1
                min_amount_to_trade[coin] = deincrease_times
        save_para(min_amount_to_trade, path)
    return min_amount_to_trade


def get_current_file_path() -> str:
    """返回当前文件的绝对路径"""
    return os.path.abspath(__file__)

def get_current_dir() -> str:
    """返回当前文件所在的目录"""
    return os.path.dirname(os.path.abspath(__file__))

def round_like(ref: float, x: float ) -> float:
    """按 ref 的小数位数对齐 x"""
    if int(ref) == ref:
        ref=int(ref)
    # 处理科学计数法
    if 'e' in str(ref).lower():
        # 对于科学计数法，直接计算小数位数
        ref_str = f"{ref:.10f}".rstrip('0')
        if '.' in ref_str:
            decimals = len(ref_str.split('.')[1])
        else:
            decimals = 0
    else:
        s = str(ref)
        if "." in s:
            decimals = len(s.split(".")[1].rstrip("0"))  # 计算 ref 的小数位
        else:
            decimals = 0
            # 计算整数部分末尾的0的个数
            for i in range(len(s)):
                if s[len(s)-1-i] == '0':
                    decimals -= 1
                else:
                    break
    return round(x, decimals)


def fuzzy_exchange_input(user_input: str) -> str:
    """
    模糊输入处理函数，支持多种输入方式
    支持: okx, ok, o, ox, okex, okx交易所
    支持: bp, backpack, b, back
    如果无法匹配到已知模式，则直接返回输入内容（转换为小写）
    """
    if not user_input:
        return 'okx'
    
    user_input = user_input.strip().lower()
    
    # OKX相关匹配
    okx_patterns = ['okx', 'ok', 'o', 'ox', 'okex', 'okx交易所', '欧易']
    for pattern in okx_patterns:
        if pattern in user_input:
            return 'okx'
    
    # Backpack相关匹配
    bp_patterns = ['bp', 'backpack', 'back', 'bp交易所', '背包']
    for pattern in bp_patterns:
        if pattern in user_input:
            return 'backpack'
    
    # 如果无法匹配到已知模式，直接返回输入内容（转换为小写）
    return user_input