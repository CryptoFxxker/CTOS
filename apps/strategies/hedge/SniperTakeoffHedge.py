import os
import sys
import time
from pathlib import Path

def add_project_paths(project_name="ctos"):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    :param project_name: 项目根目录标识（默认 'ctos'）
    """
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
    return project_root
# 执行路径添加
_PROJECT_ROOT = add_project_paths()
print('_PROJECT_ROOT: ', _PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))


from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime, save_para, load_para
import json

def load_strategy_config(config_file="sniper_strategy_config.json"):
    """加载策略配置"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, config_file)
    
    default_config = {
        "account_ids": [0, 3],
        "cexes": ["bp", "bp"],
        "sanction_line": [0.01, 0.01],
        "sanction_money": [3, 3],
        "target_pool": [["btc", "bnb"], ["btc", "bnb"]],
        "check_interval": 30,
        "sleep_duration": 600
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"✓ 加载策略配置: {config_path}")
            return config
        except Exception as e:
            print(f"✗ 加载策略配置失败: {e}")
            return default_config
    else:
        save_strategy_config(default_config, config_file)
        return default_config

def save_strategy_config(config, config_file="sniper_strategy_config.json"):
    """保存策略配置"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, config_file)
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存策略配置: {config_path}")
    except Exception as e:
        print(f"✗ 保存策略配置失败: {e}")

def load_focus_coins(cex_name, account_id):
    """加载指定交易所和账户的关注币种"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sniper_coins_dir = os.path.join(current_dir, "SniperCoins")
    
    # 确保目录存在
    if not os.path.exists(sniper_coins_dir):
        os.makedirs(sniper_coins_dir)
        print(f"✓ 创建SniperCoins文件夹: {sniper_coins_dir}")
    
    coins_file = os.path.join(sniper_coins_dir, f"{cex_name}_Account{account_id}_focus_coins.json")
    
    # 默认配置
    default_coins = {
        "good_group": [],
        "bad_coins": [],
        "all_coins": [],
        "last_updated": None,
        "description": f"{cex_name}-{account_id} 关注币种配置"
    }
    
    if os.path.exists(coins_file):
        try:
            with open(coins_file, 'r', encoding='utf-8') as f:
                coins_config = json.load(f)
            print(f"✓ 加载关注币种配置: {coins_file}")
            return coins_config
        except Exception as e:
            print(f"✗ 加载关注币种配置失败: {e}")
            return default_coins
    else:
        # 从good_group文件初始化
        try:
            good_group_file = str(_PROJECT_ROOT) + f'/apps/strategies/hedge/good_group_{cex_name}.txt'
            if os.path.exists(good_group_file):
                with open(good_group_file, 'r', encoding='utf8') as f:
                    data = f.readlines()
                    good_group = data[0].strip().lower().split(',')
                    if len(data) >= 3 and data[2].strip() != '':
                        bad_coins = [x.lower() for x in data[2].replace(' ', '').replace('，',',').strip().split(',') if x.lower() not in good_group]
                    else:
                        bad_coins = []
                    all_coins = good_group + bad_coins
                
                coins_config = {
                    "good_group": good_group,
                    "bad_coins": bad_coins,
                    "all_coins": all_coins,
                    "last_updated": time.time(),
                    "description": f"{cex_name}-{account_id} 关注币种配置"
                }
                
                # 保存到文件
                with open(coins_file, 'w', encoding='utf-8') as f:
                    json.dump(coins_config, f, ensure_ascii=False, indent=2)
                print(f"✓ 初始化关注币种配置: {coins_file}")
                return coins_config
            else:
                print(f"✗ 未找到good_group文件: {good_group_file}")
                return default_coins
        except Exception as e:
            print(f"✗ 初始化关注币种配置失败: {e}")
            return default_coins


def save_focus_coins(cex_name, account_id, coins_config):
    """保存指定交易所和账户的关注币种"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sniper_coins_dir = os.path.join(current_dir, "SniperCoins")
    coins_file = os.path.join(sniper_coins_dir, f"{cex_name}_Account{account_id}_focus_coins.json")
    
    try:
        coins_config["last_updated"] = time.time()
        with open(coins_file, 'w', encoding='utf-8') as f:
            json.dump(coins_config, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存关注币种配置: {coins_file}")
    except Exception as e:
        print(f"✗ 保存关注币种配置失败: {e}")


def update_focus_coins(cex_name, account_id, new_good_group=None, new_bad_coins=None):
    """更新关注币种配置"""
    coins_config = self.load_focus_coins(cex_name, account_id)
    
    if new_good_group is not None:
        coins_config["good_group"] = new_good_group
    if new_bad_coins is not None:
        coins_config["bad_coins"] = new_bad_coins
    
    # 重新计算all_coins
    coins_config["all_coins"] = coins_config["good_group"] + coins_config["bad_coins"]
    
    save_focus_coins(cex_name, account_id, coins_config)
    return coins_config


class SniperTakeoffHedge:
    def __init__(self):
         # 自动用当前文件名（去除后缀）作为默认策略名，细节默认为COMMON
        default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
        
        # 加载策略配置
        self.config = load_strategy_config()

        # 从配置获取参数
        self.account_ids = self.config["account_ids"]
        self.cexes = self.config["cexes"]
        self.sanction_line = self.config["sanction_line"]
        self.sanction_money = self.config["sanction_money"]
        self.check_interval = self.config["check_interval"]
        self.sleep_duration = self.config["sleep_duration"]
        self.engines = []
        self.balances = []
        self.coin_names_all = {}
        self.coinPrices_for_openPositions = []
        self.check_interval = self.config["check_interval"]
        self.sleep_duration = self.config["sleep_duration"]

        # 初始化交易所和引擎
        # exch1, engine1 = pick_exchange('okx', 0, strategy=default_strategy, strategy_detail="COMMON")
        for i in range(len(self.cexes)):
            exch, engine = pick_exchange(self.cexes[i], self.account_ids[i], strategy=default_strategy, strategy_detail="COMMON")
            self.engines.append(engine) # 存储引擎
            self.balances.append(engine.cex_driver.fetch_balance()) # 存储余额
            self.coin_names_all[f"{self.cexes[i]}_{self.account_ids[i]}"] = load_focus_coins(self.cexes[i], self.account_ids[i])["all_coins"]
            print(f"✓ {self.cexes[i]}-{self.account_ids[i]} 关注币种: {len(self.coin_names_all[f'{self.cexes[i]}_{self.account_ids[i]}'])} 个")
            print(f"{BeijingTime()} 🎯 狙击飞升对冲策略启动")
            print(f"监控币种: {self.coin_names_all[f'{self.cexes[i]}_{self.account_ids[i]}']}")
            print(f"制裁阈值: {self.sanction_line[i] * 100}%")
            print(f"制裁金额: {self.sanction_money[i]} USDT")
            print(f"初始余额: {self.balances[i]}")
        for i in range(len(self.engines)):
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coinPrices_for_openPosition/' ,f'{self.cexes[i]}_{self.account_ids[i]}_coinPrices_for_openPosition.json')
            if not os.path.exists(file_path):
                self.coinPrices_for_openPositions.append(None)
            else:
                self.coinPrices_for_openPositions.append(load_para(file_path))
        self.start_time = time.time()

    # 这个部分是为了达成，在平稳的市场里，突然有不讲道理的家伙直接飞升，那我就超越btc 一个比例就开始制裁他！等他下坠的那一天！

    def sniperTakeoffHedge(
        self,
        engine,
        cex_name,
        coin_names,
        sanction_line=0.01,
        sanction_money=3,
        coinPrices_for_openPosition=None,
    ):
        """
        对指定币种进行“飞升制裁”对冲操作。

        参数说明:
            engine : object
                交易执行引擎实例，需包含 cex_driver 属性（如 OKX 驱动）。
            cex_name : str
                交易所名称（如 'okx', 'bp'）。
            coin_names : list[str]
                需要监控和判断是否“飞升”的币种名称列表（如 ['btc', 'eth', 'sol']）。
            sanction_line : float
                超越BTC涨幅的阈值（如 0.05 表示超5%即触发制裁）。
            coinPrices_for_openPosition : dict, optional
                各币种的参考开仓价格字典，格式如 {'btc': 30000, 'eth': 2000, ...}。
                若为 None，则自动从本地 coinPrices_for_openPosition.json 文件加载。

        返回:
            None
            （函数内部会打印检测和制裁信息，并返回满足条件的币种及相关数据到 selected 字典）
        """

        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coinPrices_for_openPosition/' ,f'{cex_name}_{engine.account}_coinPrices_for_openPosition.json')
        need_refresh = False
        
        # 使用新的关注币种管理机制
        if not coin_names:
            coins_config = load_focus_coins(cex_name, engine.account)
            coin_names = coins_config["all_coins"]
            print(f"✓ 使用关注币种配置: {len(coin_names)} 个币种")

        if coinPrices_for_openPosition is None:
            # 检查文件是否存在及其时间戳
            if os.path.exists(file_path):
                file_mtime = os.path.getmtime(file_path)
                now = time.time()
                if now - file_mtime > 24 * 3600:
                    print(f"coinPrices_for_openPosition.json 超过24小时未更新，强制刷新。")
                    need_refresh = True
            else:
                need_refresh = True

            if not need_refresh:
                coinPrices_for_openPosition = load_para(file_path)
            else:
                coinPrices_for_openPosition = None

        open_position_price = {x['symbol']: x['markPrice'] for x in engine.cex_driver.get_position()[0]}
        if not coinPrices_for_openPosition:
            print(f"✓ 没有找到 {file_path} 文件，重新获取开仓价格", open_position_price, coin_names)
            coinPrices_for_openPosition = {k.lower(): open_position_price.get(engine.cex_driver._norm_symbol(k.lower())[0]) for k in coin_names}
            save_para(coinPrices_for_openPosition, file_path)
        current_time = BeijingTime(format='%H:%M:%S')
        print(f"\r🕐 当前时间为 {current_time}，需要测试下是不是有的币要加关税了...", end='')
        time.sleep(2)
        positions, err = engine.cex_driver.get_position()
        if err:
            print('CEX DRIVER.get_position error ', err)
            positions = []
        coin_positions = {x['symbol']: x for x in positions}
        now_price_for_all_coins = {}
        min_money_to_buy_amounts = {}
        coin_exceed_btc_increase_rates = {}
        selected = {}  # 满足“超额+资金”条件的币都收进来
        btc_now_price = engine.cex_driver.get_price_now('btc')
        now_price_for_all_coins['btc'] = btc_now_price
        target_pool = {'btc'}  # 5 个候选
        # target_pool = {'btc', 'eth', 'sol', 'doge', 'xrp'}  # 5 个候选

        for coin_name in coin_names:  # 遍历你所有关注的币
            time.sleep(0.1)
            symbol_full, _, _ = engine.cex_driver._norm_symbol(coin_name)
            position = coin_positions.get(symbol_full, None)
            if position is None:
                price = engine.cex_driver.get_price_now(coin_name)
            else:
                price = position['markPrice']
            now_price_for_all_coins[coin_name] = price
            exchange_limits_info, eli_err = engine.cex_driver.exchange_limits(symbol=symbol_full)
            if eli_err:
                print('CEX DRIVER.exchange_limits error ', eli_err)
                continue
            min_order_size = exchange_limits_info['min_order_size']
            contract_value = exchange_limits_info['contract_value']

            min_buy = min_order_size * contract_value * price
            min_money_to_buy_amounts[coin_name] = min_buy
            if coin_name.lower() not in coinPrices_for_openPosition:
                coinPrices_for_openPosition[coin_name.lower()] = price
            last_time_price = coinPrices_for_openPosition[coin_name.lower()]
            exceed = (price / last_time_price) - (btc_now_price / coinPrices_for_openPosition['btc'])

            coin_exceed_btc_increase_rates[coin_name] = exceed

            prepared = exceed / 0.01 * sanction_money  # 每涨 1 个点，准备 3 USDT
            consle_show = f'🕐\r 当前时间为 {current_time}，{symbol_full}要加关税了啊! 超了btc {exceed:.4f}这么多个点！(当前价:{price:.4f}, 参考价:{coinPrices_for_openPosition[coin_name.lower()]:.4f})'
            if len(consle_show) <120:  
                consle_show = consle_show + ' ' * (120 - len(consle_show))
            print(f"\r{consle_show}", end='')
            if exceed > sanction_line and prepared > min_buy * 1.01:
                print(f"\r✅✅✅ 当前时间为 {current_time}，{coin_name}真的要加关税了啊!! 超了btc {exceed:.4f}这么多个点！", end='\t\t')
                time.sleep(2)
                selected[coin_name] = {
                    'price': price,
                    'prepared': prepared,
                    'min_buy': min_buy,
                    'exceed': exceed
                }
        # -------------- 选出 good 币（含 BTC）并按资金可行性轮换 -----------------
        good_candidates = {c: v for c, v in coin_exceed_btc_increase_rates.items() if c.lower() in target_pool}
        sell_list = []
        if good_candidates:
            time.sleep(2)
            # ① 把候选按照 exceed 从小到大排序
            ordered = sorted(good_candidates.items(), key=lambda kv: kv[1])  # [(coin, info), …]

            for good_coin, _ in ordered:
                sell_list = []
                good_min = min_money_to_buy_amounts[good_coin]

                # ---------- 先把“其他币 prepared”离散化到最小买单倍数 ----------
                total_sell = 0
                for coin, info in selected.items():
                    if coin == good_coin:
                        continue
                    unit = min_money_to_buy_amounts[coin]
                    adj = (info['prepared'] // unit) * unit  # 向下取整
                    if adj >= unit:  # 至少能下一单
                        sell_list.append((coin, adj, info['price']))
                        total_sell += adj

                if total_sell < good_min:  # 卖出后钱仍不足
                    continue

                # ---------- 再把买单金额离散化 ----------
                buy_amt = (total_sell // good_min) * good_min  # ≤ total_sell
                diff = total_sell - buy_amt  # 剩余差额

                # 若差额 ≥ 半个最小买单，就再加 1 单提高利用率
                if diff >= 0.5 * good_min:
                    buy_amt += good_min
                    diff = total_sell - buy_amt

                if buy_amt < good_min:  # 仍不够一笔，换下一个候选
                    continue

                # ---------- 更新参考价 & 文件 ----------
                # coinPrices_for_openPosition[good_coin] = now_price_for_all_coins[good_coin]
                for coin, _, price in sell_list:
                    coinPrices_for_openPosition[coin] = price
                coinPrices_for_openPosition['btc'] = btc_now_price
                save_para(coinPrices_for_openPosition, file_path)

                # ---------- 真正执行：卖 → 买 ----------
                for coin, adj, price in sell_list:
                    order_id, err_msg = engine.place_incremental_orders(adj * 1.02, coin, 'sell', soft=False)
                    if err_msg:
                        print(f"❌ 订单创建失败: {err_msg}")
                        continue
                    engine.monitor.record_operation("SellOther", '关税轮换', {"symbol": coin, "price": price, "money": adj, "order_id": order_id[0]})

                order_id, err_msg = engine.place_incremental_orders(buy_amt * 1.02, good_coin, 'buy', soft=False)
                if err_msg:
                    print(f"❌ 订单创建失败: {err_msg}")
                    continue
                engine.monitor.record_operation("BuyGood", '关税轮换', {"symbol": good_coin,  "price": now_price_for_all_coins[good_coin], "money": buy_amt, "order_id": order_id[0]})

                print(
                    f"✅✅✅✅✅✅[{BeijingTime()}] {cex_name.upper()}_{engine.account}轮换完成：买入 {good_coin.upper()}  {buy_amt:.2f} USDT； 卖出 {'-'.join(list([x for x in selected if x != good_coin]))} 个币合计 {total_sell:.2f} USDT，差额 {diff:.2f}!!!! ")
                time.sleep(3)
                break

        else:
            # 所有候选都买不起
            print("\r💡 good_pool 中无满足资金条件的币，本轮跳过", end='')
            time.sleep(1)


    def run_sniperTakeoffHedge(self):
        # 主循环
        balances = [engine.cex_driver.fetch_balance() for engine in self.engines]
        while True:
            # try:
            if True:
                for idx in range(len(self.engines)):
                    engine = self.engines[idx]
                    cex_name = self.cexes[idx]
                    account_id = self.account_ids[idx]
                    sanction_line = self.sanction_line[idx]
                    sanction_money = self.sanction_money[idx]
                    coinPrices_for_openPosition = self.coinPrices_for_openPositions[idx]
                    print(f"\r{BeijingTime()} 🔍 检查 {cex_name}-{account_id} 的飞升情况...", end='')
                    
                    # 获取该账户的关注币种
                    account_coins = self.coin_names_all.get(f"{cex_name}_{account_id}", self.coin_names_all[f"{cex_name}_{account_id}"])
                    
                    # 执行狙击飞升对冲策略
                    self.sniperTakeoffHedge(
                        engine=engine,
                        cex_name=cex_name,
                        coin_names=account_coins,
                        sanction_line=sanction_line,
                        sanction_money=sanction_money,
                        coinPrices_for_openPosition=coinPrices_for_openPosition  # 自动从文件加载或获取当前价格
                    )
                    # 更新余额信息      
                    current_balance = engine.cex_driver.fetch_balance()
                    balance_change = current_balance - balances[idx]
                    balances[idx] = current_balance
                time_to_sleep = self.sleep_duration
                while time_to_sleep > 0:
                    uptime = int(time.time() - self.start_time)
                    dd = uptime // 86400
                    hh = (uptime % 86400) // 3600
                    mm = (uptime % 3600) // 60
                    ss = uptime % 60
                    uptime_str = f"{dd}天{hh:02d}时{mm:02d}分"
                    output_string = f"{BeijingTime()} 💰 {cex_name}-{account_id} Watch {len(coinPrices_for_openPosition)} coins, 当前余额: {'-'.join(str(round(balance, 2)) for balance in balances)} USDT (变化: {balance_change:+.2f}) | 已运行: {uptime_str}"
                    if len(output_string) < 120:
                        output_string = output_string + ' ' * (120 - len(output_string))    
                    print(f"\r{output_string}", end='')
                    time.sleep(1)
                    time_to_sleep -= 1
                
            # except Exception as e:
            #     print(f"{BeijingTime()} ❌ 策略执行出错: {e}")
            #     time.sleep(10)  # 出错时等待更长时间
            
            # 主循环间隔
            # print(f"\r{BeijingTime()} ⏰ 等待下一轮检查...", end='')
            time.sleep(self.check_interval)  # 30秒检查一次


if __name__ == '__main__':
    strategy = SniperTakeoffHedge()
    strategy.run_sniperTakeoffHedge()