import sys
import os
import time
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# 项目路径
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 工具函数
from ctos.drivers.backpack.util import align_decimal_places, round_dynamic, round_to_two_digits, rate_price2order

def pick_exchange(from_arg: str | None = None):
    ex = (from_arg or os.getenv('GRID_EX') or '').strip().lower()
    if ex not in ('okx', 'bp'):
        ex = input("选择交易所 exchange [okx/bp] (默认 okx): ").strip().lower() or 'okx'
    if ex == 'bp':
        from ctos.drivers.backpack.driver import BackpackDriver as Driver
        return 'bp', Driver()
    else:
        from ctos.drivers.okx.driver import OkxDriver as Driver
        return 'okx', Driver()

class HourlyLongShortStrategy:
    def __init__(self, driver, coins, capital_per_side=10000):
        """
        :param driver: 交易驱动 (OkxDriver / BackpackDriver)
        :param coins: 监控的币种列表，例如 ['BTC', 'ETH', 'SOL']
        :param capital_per_side: 多/空各分配的总资金
        """
        self.driver = driver
        self.coins = coins
        self.capital_per_side = capital_per_side
        self.positions = {}  # 记录开仓价格 {coin: {'side': str, 'entry': float}}

    def get_last_hour_returns(self):
        """获取上一小时的涨跌幅"""
        returns = {}
        for coin in self.coins:
            symbol, _, _ = self.driver._norm_symbol(f"{coin}-USDT-SWAP")
            df, err = self.driver.get_klines(symbol, timeframe='1m', limit=60)
            if err or df is None or len(df) < 2:
                continue
            if isinstance(df, pd.DataFrame):
                open_price = float(df.iloc[0]['open'])
                close_price = float(df.iloc[-1]['close'])
            else:  # 兼容 list 格式
                open_price = float(df[0]['open'])
                close_price = float(df[-1]['close'])
            returns[coin] = (close_price - open_price) / open_price
        return returns

    def rebalance(self):
        """每小时第一秒：决定开仓方向"""
        returns = self.get_last_hour_returns()
        if not returns:
            print("⚠️ 未能获取行情数据")
            return
        # 按涨幅排序
        sorted_coins = sorted(returns.items(), key=lambda x: x[1], reverse=True)
        n = len(sorted_coins)
        if n < 2:
            print("⚠️ 币种不足，跳过本轮")
            return
        half = n // 2
        longs = sorted_coins[:half]
        shorts = sorted_coins[half:]

        # 每个币分配资金
        long_cap = self.capital_per_side / max(1, len(longs))
        short_cap = self.capital_per_side / max(1, len(shorts))

        print(f"\n[{datetime.now()}] 开始新一轮调仓")
        # print("涨幅排名:", sorted_coins)

        # 多头
        for coin, ret in longs:
            price = self.driver.get_price_now(f"{coin}-USDT-SWAP")
            print(f"\r➡️ 做多 {coin}: {long_cap} USDT @ {price}", end='')
            self.positions[coin] = {"side": "long", "entry": price}

        # 空头
        for coin, ret in shorts:
            price = self.driver.get_price_now(f"{coin}-USDT-SWAP")
            print(f"\r⬅️ 做空 {coin}: {short_cap} USDT @ {price}", end='')
            self.positions[coin] = {"side": "short", "entry": price}

    def evaluate(self):
        """每小时最后10秒：评估盈亏"""
        print(f"\n[{datetime.now()}] 本小时结束，评估仓位表现")
        results = {}
        total_pnl = 0.0
        n = 0

        for coin, info in self.positions.items():
            side = info['side']
            entry = info['entry']
            now_price = self.driver.get_price_now(f"{coin}-USDT-SWAP")
            pnl_ratio = (now_price - entry) / entry if side == 'long' else (entry - now_price) / entry
            results[coin] = {"side": side, "entry": entry, "now": now_price, "pnl_ratio": pnl_ratio}
            print(f"\r📊 {coin:<6} {side:<5} 入场 {entry:.4f} → 现价 {now_price:.4f}, 收益 {pnl_ratio*100:.4f}%", end='')

            total_pnl += pnl_ratio
            n += 1

        avg_pnl = total_pnl / n if n > 0 else 0.0
        print(f"\n📈 本小时总体平均收益率: {avg_pnl*100:.4f}%")

        return results, avg_pnl
def main():
    ex_name, driver = pick_exchange()
    coins = [x.upper() for x in rate_price2order.keys()]  # 示例
    strat = HourlyLongShortStrategy(driver, coins)

    while True:
        now = datetime.now()
        # 整点 + 1 秒：开仓
        if now.minute == 0 and now.second >50:
            strat.rebalance()
        # 整点 - 10 秒：评估
        if now.minute == 59 and now.second >= 50:
            strat.evaluate()
            time.sleep(15)  # 避免重复触发
        time.sleep(1)

if __name__ == "__main__":
    main()
