"""
配置管理模块
管理交易策略的配置参数
"""

from typing import Dict, Any, Optional
import os
import json


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file or 'ai_trading_config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置失败: {e}")
        
        # 默认配置
        return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            'symbol': 'BTC/USDT',
            'exchange': 'okx',
            'account_id': 0,
            'risk': {
                'max_position_size': 1000,
                'max_daily_loss': 500,
                'stop_loss_percent': 0.05,
                'take_profit_percent': 0.10
            },
            'ai': {
                'model': 'deepseek-r1:32b',
                'temperature': 0.7
            },
            'trading': {
                'enabled': True,
                'min_confidence': 0.5
            }
        }
    
    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"配置已保存到 {self.config_file}")
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            value = value.get(k, default)
            if value == default:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value


def load_env_config() -> Dict[str, Any]:
    """从环境变量加载配置"""
    return {
        'ollama_base_url': os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
        'ollama_model': os.getenv('OLLAMA_MODEL', 'deepseek-r1:32b'),
        'exchange': os.getenv('EXCHANGE', 'okx'),
        'account_id': int(os.getenv('ACCOUNT_ID', '0')),
        'symbol': os.getenv('SYMBOL', 'BTC/USDT')
    }

