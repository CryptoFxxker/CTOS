"""
风险管理模块
控制交易风险，设置止损止盈
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """风险管理器"""
    
    def __init__(
        self, 
        max_position_size: float = 1000,
        max_daily_loss: float = 500,
        stop_loss_percent: float = 0.05,
        take_profit_percent: float = 0.10
    ):
        """
        初始化风险管理器
        
        Args:
            max_position_size: 最大单次持仓金额（USDT）
            max_daily_loss: 最大单日亏损（USDT）
            stop_loss_percent: 止损百分比
            take_profit_percent: 止盈百分比
        """
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        self.daily_pnl = 0.0
    
    def check_risk(
        self, 
        strategy: Dict[str, Any],
        current_position: float = 0
    ) -> Dict[str, Any]:
        """
        检查交易风险
        
        Args:
            strategy: 交易策略
            current_position: 当前持仓金额
            
        Returns:
            Dict[str, Any]: 风险评估结果
                - allowed: 是否允许交易
                - adjusted_amount: 调整后的交易金额
                - risk_level: 风险等级
                - message: 提示消息
        """
        action = strategy.get('action')
        amount = strategy.get('amount', 0)
        confidence = strategy.get('confidence', 0)
        
        # 检查信心度
        if confidence < 0.3:
            return {
                'allowed': False,
                'adjusted_amount': 0,
                'risk_level': 'high',
                'message': '信心度过低，拒绝交易'
            }
        
        # 调整交易金额
        adjusted_amount = min(amount, self.max_position_size)
        
        # 检查单日亏损
        if self.daily_pnl <= -self.max_daily_loss:
            return {
                'allowed': False,
                'adjusted_amount': 0,
                'risk_level': 'high',
                'message': f'已达单日亏损上限 {self.max_daily_loss} USDT'
            }
        
        # 根据信心度调整金额
        if confidence < 0.5:
            adjusted_amount *= 0.5
        elif confidence < 0.7:
            adjusted_amount *= 0.7
        
        risk_level = 'low' if confidence > 0.7 else 'medium'
        
        return {
            'allowed': True,
            'adjusted_amount': adjusted_amount,
            'risk_level': risk_level,
            'message': '风险检查通过'
        }
    
    def should_stop_loss(self, entry_price: float, current_price: float) -> bool:
        """判断是否触发止损"""
        if entry_price == 0:
            return False
        loss_percent = (current_price - entry_price) / entry_price
        return loss_percent <= -self.stop_loss_percent
    
    def should_take_profit(self, entry_price: float, current_price: float) -> bool:
        """判断是否触发止盈"""
        if entry_price == 0:
            return False
        profit_percent = (current_price - entry_price) / entry_price
        return profit_percent >= self.take_profit_percent
    
    def update_daily_pnl(self, pnl: float):
        """更新单日盈亏"""
        self.daily_pnl += pnl
        logger.info(f"更新单日盈亏: {self.daily_pnl} USDT")
    
    def reset_daily_pnl(self):
        """重置单日盈亏"""
        self.daily_pnl = 0.0

