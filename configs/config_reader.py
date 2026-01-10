#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置文件读取器
支持读取YAML格式的配置文件，并提供便捷的访问接口
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging

class ConfigReader:
    """配置文件读取器类"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化配置读取器
        
        Args:
            config_dir: 配置文件目录路径，默认为当前文件所在目录
        """
        if config_dir is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.config_dir = Path(config_dir)
        self._configs = {}
        self._logger = logging.getLogger(__name__)
    
    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        加载YAML配置文件
        
        Args:
            filename: 配置文件名（不包含路径）
            
        Returns:
            dict: 解析后的配置字典
            
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML解析错误
        """
        file_path = self.config_dir / filename
        
        if not file_path.exists():
            print(f"配置文件不存在: {file_path}")
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 缓存配置
            self._configs[filename] = config
            self._logger.info(f"成功加载配置文件: {filename}")
            return config
            
        except yaml.YAMLError as e:
            print(f"YAML解析错误 {filename}: {e}")
            self._logger.error(f"YAML解析错误 {filename}: {e}")
            return None
        except Exception as e:
            print(f"读取配置文件失败 {filename}: {e}")
            self._logger.error(f"读取配置文件失败 {filename}: {e}")
            return None
        
    def get_account_config(self, exchange: str = None, account: str = None) -> Dict[str, Any]:
        """
        获取账户配置
        
        Args:
            exchange: 交易所名称 (okx, backpack等)
            account: 账户名称 (main, sub1等)
            
        Returns:
            dict: 账户配置信息
            
        Examples:
            # 获取OKX主账户配置
            config = reader.get_account_config('okx', 'main')
            
            # 获取所有OKX账户配置
            config = reader.get_account_config('okx')
            
            # 获取所有账户配置
            config = reader.get_account_config()
        """
        if 'account.yaml' not in self._configs:
            self.load_yaml('account.yaml')
        
        accounts_config = self._configs['account.yaml']
        
        if exchange is None:
            return accounts_config.get('accounts', {})
        
        exchange_config = accounts_config.get('accounts', {}).get(exchange, {})
        
        if account is None:
            return exchange_config
        
        return exchange_config.get(account, {})
    
    def get_ctos_config(self) -> Dict[str, Any]:
        """
        获取CTOS系统配置
        
        Returns:
            dict: CTOS系统配置信息
        """
        if 'ctos.yaml' not in self._configs:
            x = self.load_yaml('ctos.yaml')
            if x is None:
                print(f"load_yaml ctos.yaml make some errors: {x}, BUT, u can still run normally, don't worry about it")
                return None
            else:
                print(f"load_yaml ctos.yaml success: {x}")
        
        return self._configs['ctos.yaml']
    
    def get_exchange_accounts(self, exchange: str) -> Dict[str, Dict[str, Any]]:
        """
        获取指定交易所的所有账户配置
        
        Args:
            exchange: 交易所名称
            
        Returns:
            dict: 该交易所的所有账户配置
        """
        return self.get_account_config(exchange)
    
    def get_account_credentials(self, exchange: str, account: str) -> Dict[str, str]:
        """
        获取指定账户的认证信息
        
        Args:
            exchange: 交易所名称
            account: 账户名称
            
        Returns:
            dict: 认证信息（API密钥等）
        """
        account_config = self.get_account_config(exchange, account)
        
        # 根据交易所类型返回相应的认证字段
        if exchange.lower() == 'okx':
            return {
                'api_key': account_config.get('api_key', ''),
                'api_secret': account_config.get('api_secret', ''),
                'passphrase': account_config.get('passphrase', '')
            }
        elif exchange.lower() == 'backpack':
            return {
                'public_key': account_config.get('public_key', ''),
                'secret_key': account_config.get('secret_key', '')
            }
        else:
            # 通用格式，返回所有字段
            return account_config
    
    def list_available_exchanges(self) -> list:
        """
        获取可用的交易所列表
        
        Returns:
            list: 交易所名称列表
        """
        accounts_config = self.get_account_config()
        return list(accounts_config.keys())
    
    def list_available_accounts(self, exchange: str) -> list:
        """
        获取指定交易所的可用账户列表
        
        Args:
            exchange: 交易所名称
            
        Returns:
            list: 账户名称列表
        """
        exchange_config = self.get_account_config(exchange)
        return list(exchange_config.keys())
    
    def validate_account_config(self, exchange: str, account: str) -> bool:
        """
        验证账户配置是否完整
        
        Args:
            exchange: 交易所名称
            account: 账户名称
            
        Returns:
            bool: 配置是否完整
        """
        try:
            credentials = self.get_account_credentials(exchange, account)
            
            if exchange.lower() == 'okx':
                required_fields = ['api_key', 'api_secret', 'passphrase']
            elif exchange.lower() == 'backpack':
                required_fields = ['public_key', 'secret_key']
            else:
                # 对于未知交易所，检查是否有非空值
                return any(credentials.values())
            
            return all(credentials.get(field) for field in required_fields)
            
        except Exception as e:
            self._logger.error(f"验证账户配置失败 {exchange}/{account}: {e}")
            return False
    
    def get_config(self, filename: str, key_path: str = None) -> Any:
        """
        获取配置文件中的指定值
        
        Args:
            filename: 配置文件名
            key_path: 键路径，用点分隔，如 'accounts.okx.main.api_key'
            
        Returns:
            配置值
            
        Examples:
            # 获取OKX主账户的API密钥
            api_key = reader.get_config('account.yaml', 'accounts.okx.main.api_key')
            
            # 获取CTOS配置的默认交易所
            default_exchange = reader.get_config('ctos.yaml', 'default_exchange')
        """
        if filename not in self._configs:
            self.load_yaml(filename)
        
        config = self._configs[filename]
        
        if key_path is None:
            return config
        
        # 按点分割键路径
        keys = key_path.split('.')
        value = config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            self._logger.warning(f"配置键不存在: {key_path}")
            return None
    
    def reload_config(self, filename: str = None):
        """
        重新加载配置文件
        
        Args:
            filename: 要重新加载的配置文件名，为None时重新加载所有配置
        """
        if filename:
            if filename in self._configs:
                del self._configs[filename]
            self.load_yaml(filename)
        else:
            self._configs.clear()
            # 重新加载所有配置文件
            for file_path in self.config_dir.glob('*.yaml'):
                if file_path.name != 'secrets.example.yaml':  # 跳过示例文件
                    self.load_yaml(file_path.name)


# 创建全局配置读取器实例
config_reader = ConfigReader()

# 便捷函数
def get_account_config(exchange: str = None, account: str = None) -> Dict[str, Any]:
    """获取账户配置的便捷函数"""
    return config_reader.get_account_config(exchange, account)

def get_ctos_config() -> Dict[str, Any]:
    """获取CTOS配置的便捷函数"""
    return config_reader.get_ctos_config()

def get_account_credentials(exchange: str, account: str) -> Dict[str, str]:
    """获取账户认证信息的便捷函数"""
    return config_reader.get_account_credentials(exchange, account)

def validate_account_config(exchange: str, account: str) -> bool:
    """验证账户配置的便捷函数"""
    return config_reader.validate_account_config(exchange, account)


if __name__ == '__main__':
    # 测试代码
    print("=== 配置文件读取器测试 ===")
    
    # 创建配置读取器
    reader = ConfigReader()
    
    # 测试获取账户配置
    print("\n1. 获取所有交易所配置:")
    all_exchanges = reader.get_account_config()
    for exchange, accounts in all_exchanges.items():
        print(f"  {exchange}: {list(accounts.keys())}")
    
    # 测试获取特定交易所配置
    print("\n2. 获取OKX配置:")
    okx_config = reader.get_account_config('okx')
    print(f"  OKX账户: {list(okx_config.keys())}")
    
    # 测试获取特定账户认证信息
    print("\n3. 获取OKX主账户认证信息:")
    okx_main_creds = reader.get_account_credentials('okx', 'main')
    print(f"  字段: {list(okx_main_creds.keys())}")
    
    # 测试配置验证
    print("\n4. 验证账户配置:")
    print(f"  OKX主账户: {reader.validate_account_config('okx', 'main')}")
    print(f"  Backpack主账户: {reader.validate_account_config('backpack', 'main')}")
    
    # 测试CTOS配置
    print("\n5. 获取CTOS配置:")
    ctos_config = reader.get_ctos_config()
    print(f"  默认交易所: {ctos_config.get('default_exchange')}")
    print(f"  模式: {ctos_config.get('mode')}")
    
    print("\n=== 测试完成 ===")
