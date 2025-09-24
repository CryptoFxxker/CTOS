from calendar import c
import  pandas as pd
import  numpy as np
import json
import socket
import os
import inspect
import math
from decimal import Decimal, getcontext
import re

try:
    import pyfiglet
except Exception as e:
    print('没这个pyfiglet包')

base_url = "https://data.binance.vision/data/spot/daily/klines"


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
    if not os.path.exists(name):
        name = 'trade_log_okex/' + name
    try:
        with open(name, 'r', encoding='utf8') as f:
            return json.load(f)
    except Exception as e:
        print('cannot load ', name, e)
        return {}


def save_para(paras, name='parameters.txt'):
    string = json.dumps(paras, indent=4)
    with open(f'trade_log_okex/{name}', 'w', encoding='utf8') as log:
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


def discover_min_trade_quantity(bp, symbol, start_usd=10, price_buffer=0.95, max_steps=8):
    """
    通过不断下单撤单的方式发现最小交易数量
    
    参数:
        bp: BackpackDriver实例
        symbol: 交易对符号
        start_usd: 起始测试金额（美元）
        price_buffer: 价格缓冲系数，用于设置远离市价的限价单
        max_steps: 最大测试步数
    
    返回:
        (min_qty_str, details): 最小交易数量字符串和详细信息
    """
    try:
        # 获取当前价格
        price = bp.get_price_now(symbol)
        print(f"当前价格: {price}")
        
        # 计算起始数量
        start_qty = start_usd / price
        print(f"起始数量: {start_qty}")
        
        # 确定精度步长
        # 根据价格大小调整精度策略
        if price < 0.01:  # 价格很小的情况，如SHIB等
            precision_steps = [1, 10, 100, 1000, 10000, 100000, 1000000]
        elif price < 1:   # 价格较小的情况
            precision_steps = [0.1, 1, 10, 100, 1000, 10000]
        else:             # 价格正常的情况
            precision_steps = [0.001, 0.01, 0.1, 1, 10, 100]
        
        # 设置限价单价格（远离市价）
        if price < 1:
            # 对于低价币种，使用更大的价格偏移
            test_price = price * (1 + price_buffer) if price_buffer > 0 else price * 1.5
        else:
            test_price = price * (1 + price_buffer) if price_buffer > 0 else price * 1.01
        
        print(f"测试价格: {test_price}")
        
        # 记录测试结果
        test_results = []
        min_successful_qty = None
        
        # 从最粗精度开始测试
        for step, precision in enumerate(precision_steps[:max_steps]):
            # 计算当前测试数量
            test_qty = round(start_qty * precision, 8)
            
            # 确保数量不为0
            if test_qty <= 0:
                test_qty = precision
                
            print(f"步骤 {step + 1}: 测试数量 {test_qty} (精度: {precision})")
            
            try:
                # 尝试下post_only限价单
                order_id, error = bp.place_order(
                    symbol=symbol,
                    side="buy",  # 使用买单，价格设置高于市价
                    order_type="limit",
                    size=test_qty,
                    price=test_price,
                    post_only=True  # 确保是post_only订单
                )
                
                if error is None and order_id:
                    print(f"  ✅ 订单成功: {order_id}")
                    min_successful_qty = test_qty
                    
                    # 立即撤单
                    cancel_ok, cancel_error = bp.revoke_order(order_id, symbol)
                    if cancel_ok:
                        print(f"  ✅ 撤单成功")
                    else:
                        print(f"  ⚠️ 撤单失败: {cancel_error}")
                    
                    test_results.append({
                        "step": step + 1,
                        "quantity": test_qty,
                        "precision": precision,
                        "success": True,
                        "order_id": order_id
                    })
                else:
                    print(f"  ❌ 订单失败: {error}")
                    test_results.append({
                        "step": step + 1,
                        "quantity": test_qty,
                        "precision": precision,
                        "success": False,
                        "error": str(error)
                    })
                    
                    # 如果第一个测试就失败，说明数量太大，尝试更小的数量
                    if step == 0:
                        # 尝试更小的起始数量
                        smaller_qty = test_qty / 10
                        print(f"  🔄 尝试更小数量: {smaller_qty}")
                        try:
                            order_id2, error2 = bp.place_order(
                                symbol=symbol,
                                side="buy",
                                order_type="limit", 
                                size=smaller_qty,
                                price=test_price,
                                post_only=True
                            )
                            if error2 is None and order_id2:
                                print(f"  ✅ 小数量订单成功: {order_id2}")
                                min_successful_qty = smaller_qty
                                # 撤单
                                bp.revoke_order(order_id2, symbol)
                                test_results.append({
                                    "step": step + 1,
                                    "quantity": smaller_qty,
                                    "precision": precision,
                                    "success": True,
                                    "order_id": order_id2,
                                    "note": "adjusted_smaller"
                                })
                        except Exception as e:
                            print(f"  ❌ 小数量订单也失败: {e}")
                    
                    # 如果连续失败，停止测试
                    if step > 2 and not any(r["success"] for r in test_results[-3:]):
                        print(f"  🛑 连续失败，停止测试")
                        break
                        
            except Exception as e:
                print(f"  ❌ 异常: {e}")
                test_results.append({
                    "step": step + 1,
                    "quantity": test_qty,
                    "precision": precision,
                    "success": False,
                    "error": str(e)
                })
        
        # 确定最小交易数量
        if min_successful_qty is not None:
            # 找到最小的成功数量
            successful_results = [r for r in test_results if r["success"]]
            if successful_results:
                min_qty = min(r["quantity"] for r in successful_results)
                min_qty_str = f"{min_qty:.8f}".rstrip('0').rstrip('.')
                print(f"\n🎯 发现最小交易数量: {min_qty_str}")
            else:
                min_qty_str = "未知"
                print(f"\n❌ 未找到可用的交易数量")
        else:
            min_qty_str = "未知"
            print(f"\n❌ 未找到可用的交易数量")
        
        # 返回结果
        details = {
            "symbol": symbol,
            "price": price,
            "test_price": test_price,
            "start_usd": start_usd,
            "min_quantity": min_qty_str,
            "test_results": test_results,
            "successful_tests": len([r for r in test_results if r["success"]])
        }
        
        return min_qty_str, details
        
    except Exception as e:
        print(f"❌ 发现最小交易数量时出错: {e}")
        return "错误", {"error": str(e)}


def _reduce_significant_digits(val: float) -> float:
    """真正减少有效数字"""
    # 先转化成字符串
    val_str = str(val)
    if int(val) == val:
        for x in range(len(val_str)):
            if val_str[len(val_str)-1-x]=='0' or val_str[len(val_str)-1-x]=='.':
                continue
            else:
                val_str[len(val_str)-1-x]='0'
        return int(val_str[:len(val_str)-x])
    # 检查是否有结尾是一长串999或者000001这种模式，有的话想法子消掉得到clean_str
    clean_str = val_str
    
    # 使用正则表达式匹配结尾的重复模式
    import re
    
    # 匹配结尾的重复9模式 (如999, 9999, 99999等)
    if re.search(r'9{3,}$', clean_str):
        # 找到重复9的开始位置，替换为0并进位
        match = re.search(r'9+$', clean_str)
        if match:
            pos = match.start()
            # 将重复的9替换为0
            clean_str = clean_str[:pos] + '0' * (len(clean_str) - pos)
            # 尝试进位
            try:
                clean_str = str(float(clean_str) + 10 ** (len(clean_str) - pos - 1))
            except:
                pass
    
    # 匹配结尾的000001模式 (如000001, 0000001等)
    elif re.search(r'0+1$', clean_str):
        # 找到000001模式，直接去掉最后的1
        clean_str = re.sub(r'0+1$', '0' * len(re.search(r'0+1$', clean_str).group()), clean_str)
    
    # 去掉clean_str所有的0和.
    clean_str_no_zeros = clean_str.replace('0', '').replace('.', '')
    
    # 找到最后一个有效数字
    if not clean_str_no_zeros:
        return val
    
    last_significant_digit = clean_str_no_zeros[-1]
    
    # 对clean_str倒序检索最后一个有效数字的索引
    last_digit_index = clean_str.rfind(last_significant_digit)
    
    # 将其换成0
    if last_digit_index != -1:
        clean_str = clean_str[:last_digit_index] + '0' + clean_str[last_digit_index + 1:]
    
    # 返回置换之后的float str
    try:
        return float(clean_str)
    except:
        return val
# # 测试
# print(round_to_two_digits(554))       # 550
# print(round_to_two_digits(0.000145))  # 0.00014
# print(round_to_two_digits(5.55))      # 5.5
# print(round_to_two_digits(98765))     # 99000
# print(round_to_two_digits(0.00987))   # 0.0099



def round_like(ref: float, x: float ) -> float:
    
    """按 ref 的小数位数对齐 x"""
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
                if s[i] == '0':
                    decimals -= 1
                else:
                    break
    return round(x, decimals)


def fuzzy_exchange_input(user_input: str) -> str:
    """
    模糊输入处理函数，支持多种输入方式
    支持: okx, ok, o, ox, okex, okx交易所
    支持: bp, backpack, b, back
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
    bp_patterns = ['bp', 'backpack', 'b', 'back', 'bp交易所', '背包']
    for pattern in bp_patterns:
        if pattern in user_input:
            return 'backpack'
    
    # 默认返回okx
    return 'okx'