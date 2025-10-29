"""
AI 交易系统主程序
整合所有模块，实现自动化交易
"""

import time
import logging
from typing import Dict, Any
from ai_strategist import AIStrategist
from data_fetcher import DataFetcher, create_mock_data
from executor import Executor
from risk_manager import RiskManager
from config_manager import ConfigManager, load_env_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AITradingSystem:
    """AI 交易系统"""
    
    def __init__(self):
        """初始化系统"""
        # 加载配置
        self.config = ConfigManager()
        self.env_config = load_env_config()
        
        # 初始化各个模块
        self.ai = AIStrategist()
        self.data_fetcher = DataFetcher(exchange=self.config.get('exchange', 'okx'))
        self.executor = Executor(
            exchange=self.config.get('exchange', 'okx'),
            account_id=self.config.get('account_id', 0)
        )
        self.risk_manager = RiskManager(
            max_position_size=self.config.get('risk.max_position_size', 1000),
            max_daily_loss=self.config.get('risk.max_daily_loss', 500),
            stop_loss_percent=self.config.get('risk.stop_loss_percent', 0.05),
            take_profit_percent=self.config.get('risk.take_profit_percent', 0.10)
        )
        
        # 运行状态
        self.running = False
        self.position = {}  # 当前持仓
        
    def start(self):
        """启动交易系统"""
        logger.info("=" * 60)
        logger.info("AI 交易系统启动")
        logger.info("=" * 60)
        
        symbol = self.config.get('symbol', 'BTC/USDT')
        logger.info(f"监控币种: {symbol}")
        logger.info(f"交易所: {self.config.get('exchange', 'okx')}")
        
        self.running = True
        
        try:
            while self.running:
                self.run_cycle()
                time.sleep(60)  # 每分钟执行一次
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭...")
            self.stop()
    
    def run_cycle(self):
        """执行一个交易周期"""
        symbol = self.config.get('symbol', 'BTC/USDT')
        
        logger.info("-" * 60)
        logger.info(f"开始新的交易周期 - {symbol}")
        
        try:
            # 1. 获取市场数据
            logger.info("步骤 1: 获取市场数据")
            market_data = self.data_fetcher.get_market_data(symbol)
            logger.info(f"市场数据: {market_data}")
            
            # 2. 检查风险
            logger.info("步骤 2: 检查风险限制")
            # TODO: 检查当前持仓
            
            # 3. AI 生成策略
            logger.info("步骤 3: AI 生成交易策略")
            strategy = self.ai.generate_strategy(market_data)
            logger.info(f"AI 策略: {strategy}")
            
            # 4. 风险审核
            logger.info("步骤 4: 风险审核")
            risk_check = self.risk_manager.check_risk(strategy)
            logger.info(f"风险检查: {risk_check}")
            
            # 5. 执行交易
            if risk_check['allowed'] and strategy['action'] != 'hold':
                logger.info("步骤 5: 执行交易")
                adjusted_amount = risk_check['adjusted_amount']
                
                if adjusted_amount > 0:
                    result = self.executor.execute_order(
                        symbol=symbol,
                        action=strategy['action'],
                        amount=adjusted_amount,
                        strategy_info=strategy
                    )
                    logger.info(f"执行结果: {result}")
            else:
                logger.info(f"跳过交易: {strategy['action']} - {risk_check.get('message', '')}")
            
            # 6. 更新持仓
            self.update_position(symbol)
            
        except Exception as e:
            logger.error(f"交易周期执行失败: {e}", exc_info=True)
    
    def update_position(self, symbol: str):
        """更新持仓信息"""
        position = self.executor.get_position(symbol)
        self.position[symbol] = position
    
    def stop(self):
        """停止系统"""
        self.running = False
        logger.info("AI 交易系统已停止")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("AI 加密货币交易系统")
    print("=" * 60)
    
    # 检查配置
    env_config = load_env_config()
    print(f"\n配置信息:")
    print(f"  Ollama 服务器: {env_config['ollama_base_url']}")
    print(f"  Ollama 模型: {env_config['ollama_model']}")
    print(f"  交易所: {env_config['exchange']}")
    print(f"  账户ID: {env_config['account_id']}")
    print(f"  交易对: {env_config['symbol']}")
    
    # 创建并启动系统
    system = AITradingSystem()
    
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n程序已停止")
    except Exception as e:
        logger.error(f"系统运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()

