# -*- coding: utf-8 -*-
# SimpleMartinSystem.py
# 简化版单币种马丁策略系统 - 集成策略执行、管理、监控

import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

def add_project_paths(project_name="ctos"):
    """自动查找项目根目录"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    path = current_dir
    while path != os.path.dirname(path):
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

_PROJECT_ROOT = add_project_paths()
from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime

class SimpleMartinSystem:
    """简化版单币种马丁策略系统"""
    
    def __init__(self, config_file="simple_martin_config.json"):
        self.config_file = os.path.join(os.path.dirname(__file__), config_file)
        self.config = self.load_config()
        self.engines = {}  # 按交易所+账户存储引擎
        self.running = False
        self.monitor_thread = None
        self.initialized = False
        self.last_status_print = 0  # 上次打印状态的时间戳
        self.status_print_counter = 0  # 状态打印计数器
        
    def load_config(self):
        """加载配置文件"""
        default_config = {
            "strategies": [
                {
                    "coin": "ETH",
                    "exchange": "bp",
                    "account_id": 0,
                    "base_amount": 50.0,
                    "martin_multiplier": 1.5,
                    "max_positions": 8,
                    "add_position_rate": 0.05,
                    "reduce_position_rate": 0.1,
                    "stop_loss_rate": 0.3,
                    "enabled": True,
                    "positions": [],
                    "total_pnl": 0.0,
                    "last_price": 0.0
                }
            ],
            "global_settings": {
                "monitor_interval": 30,
                "status_print_interval": 3,  # 每3次循环打印一次状态
                "emergency_stop": False,
                "log_level": "INFO"
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"❌ 加载配置失败: {e}")
                return default_config
        else:
            self.save_config(default_config)
            return default_config
    
    def save_config(self, config=None):
        """保存配置文件"""
        if config is None:
            config = self.config
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            return False
    
    def initialize_engines(self):
        """初始化所有需要的引擎"""
        if self.initialized:
            return True
            
        print("🔧 初始化执行引擎...")
        
        # 收集所有需要的交易所+账户组合
        engine_keys = set()
        for strategy in self.config["strategies"]:
            if strategy["enabled"]:
                key = f"{strategy['exchange']}_{strategy['account_id']}"
                engine_keys.add(key)
        
        # 初始化所有引擎
        success_count = 0
        for key in engine_keys:
            exchange, account_id = key.split('_')
            account_id = int(account_id)
            
            try:
                exch, engine = pick_exchange(
                    cex=exchange, 
                    account=account_id, 
                    strategy="SimpleMartin", 
                    strategy_detail="COMMON"
                )
                self.engines[key] = engine
                print(f"✅ 初始化引擎: {exchange}-{account_id}")
                success_count += 1
            except Exception as e:
                print(f"❌ 初始化引擎失败: {exchange}-{account_id} - {e}")
                # 禁用使用该引擎的策略
                for strategy in self.config["strategies"]:
                    if (strategy["exchange"] == exchange and 
                        strategy["account_id"] == account_id):
                        strategy["enabled"] = False
                        print(f"⚠️ 禁用策略: {strategy['coin']} (引擎初始化失败)")
        
        self.initialized = True
        print(f"🎯 引擎初始化完成: {success_count}/{len(engine_keys)} 成功")
        return success_count > 0
    
    def get_engine(self, exchange, account_id):
        """获取已初始化的引擎"""
        key = f"{exchange}_{account_id}"
        return self.engines.get(key)
    
    def get_current_price(self, engine, coin):
        """获取当前价格"""
        try:
            price = engine.cex_driver.get_price_now(coin)
            return float(price) if price else None
        except Exception as e:
            print(f"❌ 获取价格失败 {coin}: {e}")
            return None
    
    def place_martin_order(self, engine, coin, direction, amount, price=None):
        """下马丁订单"""
        try:
            if price is None:
                price = self.get_current_price(engine, coin)
                if price is None:
                    return None, "无法获取价格"
            print(f"place_martin_order: {coin}, {direction}, {amount}, {price}")
            orders, err = engine.place_incremental_orders(
                usdt_amount=amount,
                coin=coin.lower(),
                direction=direction,
                soft=True,
                price=price
            )
            
            if err:
                return None, err
            
            return orders[0] if orders else None, None
        except Exception as e:
            return None, str(e)
    
    def calculate_position_size(self, strategy, position_level):
        """计算持仓大小"""
        base_amount = strategy["base_amount"]
        martin_multiplier = strategy["martin_multiplier"]
        return base_amount * (martin_multiplier ** position_level)
    
    def should_add_position(self, strategy, current_price):
        """判断是否应该加仓"""
        if not strategy["positions"]:
            return True, 0  # 首次建仓
        
        last_position = strategy["positions"][-1]
        last_price = last_position["price"]
        price_change = (current_price - last_price) / last_price
        
        if (price_change < -strategy["add_position_rate"] and len(strategy["positions"]) < strategy["max_positions"]):
            return True, len(strategy["positions"])
        return False, 0
    
    def should_reduce_position(self, strategy, current_price):
        """判断是否应该减仓"""
        if not strategy["positions"]:
            return False, 0
        
        total_pnl = sum(pos["pnl"] for pos in strategy["positions"])
        total_invested = sum(pos["amount"] for pos in strategy["positions"])
        
        if total_invested > 0 and (total_pnl / total_invested) > strategy["reduce_position_rate"]:
            return True, len(strategy["positions"]) - 1
        
        return False, 0
    
    def should_stop_loss(self, strategy, current_price):
        """判断是否应该止损"""
        if not strategy["positions"]:
            return False
        
        total_pnl = sum(pos["pnl"] for pos in strategy["positions"])
        total_invested = sum(pos["amount"] for pos in strategy["positions"])
        
        if total_invested > 0 and (total_pnl / total_invested) < -strategy["stop_loss_rate"]:
            return True
        
        return False
    
    def update_position_pnl(self, strategy, current_price):
        """更新持仓盈亏"""
        for position in strategy["positions"]:
            if position["direction"] == "buy":
                position["pnl"] = (current_price - position["price"]) * (position["amount"] / position["price"])
            else:
                position["pnl"] = (position["price"] - current_price) * (position["amount"] / position["price"])
        
        strategy["total_pnl"] = sum(pos["pnl"] for pos in strategy["positions"])
    
    def execute_strategy(self, strategy):
        """执行单个策略"""
        coin = strategy["coin"]
        exchange = strategy["exchange"]
        account_id = strategy["account_id"]
        
        if not strategy["enabled"]:
            return
        
        engine = self.get_engine(exchange, account_id)
        if not engine:
            return
        
        try:
            current_price = self.get_current_price(engine, coin)
            if current_price is None:
                return
            
            strategy["last_price"] = current_price
            self.update_position_pnl(strategy, current_price)
            
            # 检查止损
            if self.should_stop_loss(strategy, current_price):
                print(f"🚨 {BeijingTime()} | [{coin}] 触发止损，禁用策略")
                strategy["enabled"] = False
                self.save_config()  # 立即保存配置
                return
            
            # 检查减仓
            should_reduce, reduce_level = self.should_reduce_position(strategy, current_price)
            if should_reduce:
                print(f"💰 {BeijingTime()} | [{coin}] 触发减仓，减少 {reduce_level} 层")
                strategy["positions"] = strategy["positions"][:-reduce_level]
                self.save_config()  # 立即保存配置
                return
            
            # 检查加仓
            should_add, add_level = self.should_add_position(strategy, current_price)
            if should_add:
                position_amount = self.calculate_position_size(strategy, add_level)
                direction = "buy"
                
                print(f"📈 {BeijingTime()} | [{coin}] 触发加仓，第 {add_level + 1} 层，金额: {position_amount}")
                
                order_id, err = self.place_martin_order(engine, coin, direction, position_amount, current_price)
                if order_id:
                    position = {
                        "coin": coin,
                        "direction": direction,
                        "amount": position_amount,
                        "price": current_price,
                        "order_id": order_id,
                        "timestamp": time.time(),
                        "pnl": 0.0
                    }
                    strategy["positions"].append(position)
                    print(f"✅ {BeijingTime()} | [{coin}] 加仓成功，订单ID: {order_id}")
                    self.save_config()  # 立即保存配置
                else:
                    print(f"❌ {BeijingTime()} | [{coin}] 加仓失败: {err}")
            
        except Exception as e:
            print(f"❌ {BeijingTime()} | [{coin}] 策略执行异常: {e}")
    
    def print_strategies_status(self):
        """轮动打印所有策略的状态"""
        print(f"\n{'='*80}")
        print(f"📊 策略状态报告 - {BeijingTime()}")
        print('='*80)
        
        for strategy in self.config["strategies"]:
            if strategy["enabled"]:
                coin = strategy["coin"]
                positions_count = len(strategy["positions"])
                total_pnl = strategy["total_pnl"]
                last_price = strategy["last_price"]
                total_invested = sum(pos["amount"] for pos in strategy["positions"])
                
                status_symbol = "🟢" if positions_count > 0 else "⚪"
                pnl_symbol = "📈" if total_pnl >= 0 else "📉"
                
                print(f"\n{status_symbol} [{coin}] [{strategy['exchange']}-{strategy['account_id']}]")
                print(f"   当前价格: {last_price:10.4f} | 持仓层数: {positions_count:2d}/{strategy['max_positions']:2d}")
                print(f"   投入资金: {total_invested:10.2f} USDT")
                print(f"   {pnl_symbol} 总盈亏: {total_pnl:+10.2f} USDT ({total_pnl/total_invested*100 if total_invested > 0 else 0:+.2f}%)")
                
                if positions_count > 0:
                    print(f"   持仓详情:")
                    for i, pos in enumerate(strategy["positions"], 1):
                        pnl_pct = (pos["pnl"] / pos["amount"]) * 100 if pos["amount"] > 0 else 0
                        print(f"      第{i}层: 价格={pos['price']:10.4f}, 金额={pos['amount']:7.2f}, 盈亏={pos['pnl']:+8.2f} ({pnl_pct:+6.2f}%)")
        
        print(f"\n{'='*80}\n")
    
    def run_strategies(self):
        """运行所有策略"""
        print(f"🚀 {BeijingTime()} | 启动策略执行")
        
        while self.running:
            try:
                if self.config["global_settings"]["emergency_stop"]:
                    print(f"🚨 {BeijingTime()} | 紧急停止触发")
                    break
                
                # 执行所有策略
                for strategy in self.config["strategies"]:
                    if strategy["enabled"]:
                        self.execute_strategy(strategy)
                
                # 保存配置（确保订单等信息持久化）
                self.save_config()
                
                # 定期打印策略状态
                self.status_print_counter += 1
                status_interval = self.config["global_settings"].get("status_print_interval", 3)
                if self.status_print_counter >= status_interval:
                    self.print_strategies_status()
                    self.status_print_counter = 0
                
                time.sleep(self.config["global_settings"]["monitor_interval"])
                
            except KeyboardInterrupt:
                print(f"\n⏹️ {BeijingTime()} | 手动停止策略")
                break
            except Exception as e:
                print(f"❌ {BeijingTime()} | 策略运行异常: {e}")
                time.sleep(5)
        
        # 退出前保存配置
        self.save_config()
        self.running = False
        print(f"🏁 {BeijingTime()} | 策略执行结束")
    
    def start(self):
        """启动系统"""
        if self.running:
            print("⚠️ 系统已在运行中")
            return
        
        # 初始化引擎
        if not self.initialize_engines():
            print("❌ 引擎初始化失败，无法启动系统")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self.run_strategies, daemon=True)
        self.monitor_thread.start()
        print("✅ 系统已启动")
    
    def stop(self):
        """停止系统"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("⏹️ 系统已停止")
    
    def add_strategy(self, coin, exchange, account_id, base_amount=50.0, martin_multiplier=1.5, max_positions=8):
        """添加策略"""
        strategy = {
            "coin": coin.upper(),
            "exchange": exchange.lower(),
            "account_id": account_id,
            "base_amount": base_amount,
            "martin_multiplier": martin_multiplier,
            "max_positions": max_positions,
            "add_position_rate": 0.05,
            "reduce_position_rate": 0.1,
            "stop_loss_rate": 0.3,
            "enabled": True,
            "positions": [],
            "total_pnl": 0.0,
            "last_price": 0.0
        }
        
        self.config["strategies"].append(strategy)
        self.save_config()
        
        # 如果系统已初始化，需要为新策略初始化引擎
        if self.initialized:
            key = f"{exchange.lower()}_{account_id}"
            if key not in self.engines:
                try:
                    exch, engine = pick_exchange(
                        cex=exchange.lower(), 
                        account=account_id, 
                        strategy="SimpleMartin", 
                        strategy_detail="COMMON"
                    )
                    self.engines[key] = engine
                    print(f"✅ 为新策略初始化引擎: {exchange}-{account_id}")
                except Exception as e:
                    print(f"❌ 为新策略初始化引擎失败: {exchange}-{account_id} - {e}")
                    strategy["enabled"] = False
                    print(f"⚠️ 策略 {coin} 已禁用 (引擎初始化失败)")
        
        print(f"✅ 策略 {coin} 添加成功")
    
    def remove_strategy(self, coin):
        """删除策略"""
        self.config["strategies"] = [s for s in self.config["strategies"] if s["coin"].upper() != coin.upper()]
        self.save_config()
        print(f"✅ 策略 {coin} 删除成功")
    
    def toggle_strategy(self, coin):
        """启用/禁用策略"""
        for strategy in self.config["strategies"]:
            if strategy["coin"].upper() == coin.upper():
                strategy["enabled"] = not strategy["enabled"]
                status = "启用" if strategy["enabled"] else "禁用"
                print(f"✅ 策略 {coin} 已{status}")
                self.save_config()
                return
        print(f"❌ 未找到策略 {coin}")
    
    def list_strategies(self):
        """列出所有策略"""
        print(f"\n📊 策略列表 ({BeijingTime()})")
        print("=" * 80)
        
        for i, strategy in enumerate(self.config["strategies"]):
            status = "✅ 启用" if strategy["enabled"] else "❌ 禁用"
            positions_count = len(strategy["positions"])
            total_pnl = strategy["total_pnl"]
            
            print(f"{i+1:2d}. {strategy['coin']:4s} | {strategy['exchange']:4s}-{strategy['account_id']} | {status}")
            print(f"    基础金额: {strategy['base_amount']:6.1f} | 马丁倍数: {strategy['martin_multiplier']:4.1f} | 最大层数: {strategy['max_positions']:2d}")
            print(f"    持仓层数: {positions_count:2d} | 总盈亏: {total_pnl:8.2f} | 最新价格: {strategy['last_price']:10.4f}")
            print()
    
    def show_status(self):
        """显示系统状态"""
        print(f"\n📈 系统状态 ({BeijingTime()})")
        print("=" * 60)
        
        total_strategies = len(self.config["strategies"])
        enabled_strategies = sum(1 for s in self.config["strategies"] if s["enabled"])
        total_positions = sum(len(s["positions"]) for s in self.config["strategies"])
        total_pnl = sum(s["total_pnl"] for s in self.config["strategies"])
        
        print(f"总策略数: {total_strategies} | 启用: {enabled_strategies} | 禁用: {total_strategies - enabled_strategies}")
        print(f"总持仓层数: {total_positions} | 总盈亏: {total_pnl:.2f}")
        print(f"系统状态: {'运行中' if self.running else '已停止'}")
        print(f"紧急停止: {'是' if self.config['global_settings']['emergency_stop'] else '否'}")
        print(f"监控间隔: {self.config['global_settings']['monitor_interval']} 秒")
    
    def emergency_stop(self):
        """紧急停止"""
        self.config["global_settings"]["emergency_stop"] = True
        for strategy in self.config["strategies"]:
            strategy["enabled"] = False
        self.save_config()
        print("🚨 紧急停止已触发")
    
    def reset_emergency_stop(self):
        """重置紧急停止"""
        self.config["global_settings"]["emergency_stop"] = False
        self.save_config()
        print("✅ 紧急停止已重置")
    
    def reinitialize_engines(self):
        """重新初始化引擎（当配置发生变化时）"""
        print("🔄 重新初始化引擎...")
        self.engines.clear()
        self.initialized = False
        return self.initialize_engines()
    
    def get_engine_status(self):
        """获取引擎状态"""
        print(f"\n🔧 引擎状态 ({BeijingTime()})")
        print("=" * 60)
        
        if not self.engines:
            print("❌ 没有已初始化的引擎")
            return
        
        for key, engine in self.engines.items():
            exchange, account_id = key.split('_')
            print(f"✅ {exchange.upper()}-{account_id}: 已初始化")
        
        print(f"\n📊 引擎统计: {len(self.engines)} 个引擎已初始化")

def main():
    """主函数"""
    system = SimpleMartinSystem()
    
    while True:
        print("\n" + "=" * 50)
        print("🎯 简化版单币种马丁策略系统")
        print("=" * 50)
        print("1. 启动策略")
        print("2. 停止策略")
        print("3. 查看策略列表")
        print("4. 添加策略")
        print("5. 删除策略")
        print("6. 启用/禁用策略")
        print("7. 查看系统状态")
        print("8. 查看引擎状态")
        print("9. 重新初始化引擎")
        print("10. 紧急停止")
        print("11. 重置紧急停止")
        print("0. 退出")
        print("-" * 50)
        
        choice = input("请选择操作 (0-11): ").strip()
        
        if choice == '1':
            system.start()
        elif choice == '2':
            system.stop()
        elif choice == '3':
            system.list_strategies()
        elif choice == '4':
            coin = input("币种 (如 ETH): ").upper()
            exchange = input("交易所 (bp/okx): ").lower()
            account_id = int(input("账户ID: "))
            base_amount = float(input("基础金额 (USDT): "))
            system.add_strategy(coin, exchange, account_id, base_amount)
        elif choice == '5':
            coin = input("币种: ").upper()
            system.remove_strategy(coin)
        elif choice == '6':
            coin = input("币种: ").upper()
            system.toggle_strategy(coin)
        elif choice == '7':
            system.show_status()
        elif choice == '8':
            system.get_engine_status()
        elif choice == '9':
            system.reinitialize_engines()
        elif choice == '10':
            system.emergency_stop()
        elif choice == '11':
            system.reset_emergency_stop()
        elif choice == '0':
            system.stop()
            print("👋 再见！")
            break
        else:
            print("❌ 无效选择，请重试")
        
        if choice in ['1', '2']:
            input("\n按回车键继续...")

if __name__ == '__main__':
    main()
