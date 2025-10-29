"""
AI 策略师模块
负责生成交易策略，使用 Ollama DeepSeek 模型
"""

from ollama_client import OllamaClient
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AIStrategist:
    """AI 策略师，使用大语言模型生成交易策略"""
    
    def __init__(self, client: Optional[OllamaClient] = None):
        """
        初始化 AI 策略师
        
        Args:
            client: OllamaClient 实例，如果为 None 则创建新实例
        """
        self.client = client or OllamaClient()
    
    def generate_strategy(
        self, 
        market_data: Dict[str, Any],
        market_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        基于市场数据生成交易策略
        
        Args:
            market_data: 市场数据字典，包含价格、指标等
            market_context: 市场背景信息（可选）
            
        Returns:
            Dict[str, Any]: 交易策略，包含以下字段：
                - action: 'buy', 'sell', 'hold'
                - amount: 交易金额
                - reason: 策略理由
                - confidence: 信心度 (0-1)
        """
        # 构建提示词
        prompt = self._build_prompt(market_data, market_context)
        
        try:
            # 调用 AI 生成策略
            response = self.client.chat(
                system=self._get_system_prompt(),
                prompt=prompt,
                stream=False
            )
            
            # 解析 AI 返回的策略
            strategy = self._parse_strategy(response)
            return strategy
            
        except Exception as e:
            logger.error(f"生成策略失败: {e}")
            return {
                'action': 'hold',
                'amount': 0,
                'reason': f'错误: {str(e)}',
                'confidence': 0
            }
    
    def _build_prompt(self, market_data: Dict[str, Any], context: Optional[str]) -> str:
        """
        构建 AI 提示词
        
        Args:
            market_data: 市场数据
            context: 市场背景
            
        Returns:
            str: 完整的提示词
        """
        prompt = f"""
请分析以下市场数据，并给出交易建议：

市场数据：
- 当前价格: {market_data.get('price', 'N/A')}
- 24h涨跌: {market_data.get('change_24h', 'N/A')}
- 成交量: {market_data.get('volume', 'N/A')}
- K线趋势: {market_data.get('trend', 'N/A')}
"""
        
        if context:
            prompt += f"\n市场背景: {context}"
        
        prompt += """

请用JSON格式返回，包含以下字段：
- action: 'buy', 'sell', 或 'hold'
- amount: 交易金额（USDT）
- reason: 简要说明理由
- confidence: 信心度（0-1的小数）

格式示例：
{"action": "buy", "amount": 100, "reason": "价格回调且成交量增加", "confidence": 0.75}
"""
        
        return prompt
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个专业的加密货币交易策略专家。你需要根据市场数据做出明智的交易决策。
请遵循以下原则：
1. 风险第一，不要过于激进
2. 考虑市场整体趋势
3. 给出具体的交易金额建议
4. 评估自己的信心度

请用JSON格式返回策略。"""
    
    def _parse_strategy(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 AI 返回的策略
        
        Args:
            response: AI 响应
            
        Returns:
            Dict[str, Any]: 解析后的策略
        """
        content = response.get('message', {}).get('content', '{}')
        
        try:
            import json
            strategy = json.loads(content.strip())
            
            # 验证必需字段
            required_fields = ['action', 'amount', 'reason', 'confidence']
            for field in required_fields:
                if field not in strategy:
                    strategy[field] = self._get_default_value(field)
            
            return strategy
        except json.JSONDecodeError:
            logger.error(f"解析策略失败，内容: {content}")
            return {
                'action': 'hold',
                'amount': 0,
                'reason': 'AI 返回格式错误',
                'confidence': 0
            }
    
    def _get_default_value(self, field: str) -> Any:
        """获取字段默认值"""
        defaults = {
            'action': 'hold',
            'amount': 0,
            'reason': '未知',
            'confidence': 0
        }
        return defaults.get(field, None)

