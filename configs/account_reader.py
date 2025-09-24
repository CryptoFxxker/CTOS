#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账户配置文件读取器
专门用于读取account.yaml配置文件，提供简洁的接口
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

class AccountReader:
    """账户配置读取器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化账户配置读取器
        
        Args:
            config_dir: 配置文件目录，默认为当前文件所在目录
        """
        if config_dir is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.config_dir = Path(config_dir)
        self.account_file = self.config_dir / 'account.yaml'
        self._config = None
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is not None:
            return self._config
        
        if not self.account_file.exists():
            raise FileNotFoundError(f"账户配置文件不存在: {self.account_file}")
        
        try:
            with open(self.account_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            return self._config
        except yaml.YAMLError as e:
            raise ValueError(f"YAML解析错误: {e}")
        except Exception as e:
            raise RuntimeError(f"读取配置文件失败: {e}")
    
    def get_all_accounts(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        获取所有账户配置
        
        Returns:
            dict: 格式为 {exchange: {account: {credentials}}}
            
        Example:
            {
                'okx': {
                    'main': {'api_key': '...', 'api_secret': '...', 'passphrase': '...'},
                    'sub1': {'api_key': '...', 'api_secret': '...', 'passphrase': '...'}
                },
                'backpack': {
                    'main': {'public_key': '...', 'secret_key': '...'},
                    'arb_bot': {'public_key': '...', 'secret_key': '...'}
                }
            }
        """
        config = self._load_config()
        return config.get('accounts', {})
    
    def get_exchange_accounts(self, exchange: str) -> Dict[str, Dict[str, Any]]:
        """
        获取指定交易所的所有账户
        
        Args:
            exchange: 交易所名称 (okx, backpack等)
            
        Returns:
            dict: 格式为 {account: {credentials}}
            
        Example:
            get_exchange_accounts('okx')
            # 返回: {'main': {'api_key': '...', ...}, 'sub1': {'api_key': '...', ...}}
        """
        all_accounts = self.get_all_accounts()
        return all_accounts.get(exchange, {})
    
    def get_account(self, exchange: str, account: str) -> Dict[str, Any]:
        """
        获取指定账户的配置
        
        Args:
            exchange: 交易所名称
            account: 账户名称
            
        Returns:
            dict: 账户配置信息
            
        Example:
            get_account('okx', 'main')
            # 返回: {'api_key': '...', 'api_secret': '...', 'passphrase': '...'}
        """
        exchange_accounts = self.get_exchange_accounts(exchange)
        return exchange_accounts.get(account, {})
    
    def get_okx_credentials(self, account: str = 'main') -> Dict[str, str]:
        """
        获取OKX账户认证信息
        
        Args:
            account: 账户名称，默认为'main'
            
        Returns:
            dict: 包含api_key, api_secret, passphrase的字典
        """
        account_config = self.get_account('okx', account)
        return {
            'api_key': account_config.get('api_key', ''),
            'api_secret': account_config.get('api_secret', ''),
            'passphrase': account_config.get('passphrase', '')
        }
    
    def get_backpack_credentials(self, account: str = 'main') -> Dict[str, str]:
        """
        获取Backpack账户认证信息
        
        Args:
            account: 账户名称，默认为'main'
            
        Returns:
            dict: 包含public_key, secret_key的字典
        """
        account_config = self.get_account('backpack', account)
        return {
            'public_key': account_config.get('public_key', ''),
            'secret_key': account_config.get('secret_key', '')
        }
    
    def list_exchanges(self) -> List[str]:
        """
        获取所有可用的交易所列表
        
        Returns:
            list: 交易所名称列表
        """
        all_accounts = self.get_all_accounts()
        return list(all_accounts.keys())
    
    def list_accounts(self, exchange: str) -> List[str]:
        """
        获取指定交易所的账户列表
        
        Args:
            exchange: 交易所名称
            
        Returns:
            list: 账户名称列表
        """
        exchange_accounts = self.get_exchange_accounts(exchange)
        return list(exchange_accounts.keys())
    
    def is_account_valid(self, exchange: str, account: str) -> bool:
        """
        检查账户配置是否有效（非空）
        
        Args:
            exchange: 交易所名称
            account: 账户名称
            
        Returns:
            bool: 配置是否有效
        """
        account_config = self.get_account(exchange, account)
        
        if not account_config:
            return False
        
        # 检查是否有非空值
        return any(str(value).strip() for value in account_config.values() if value is not None)
    
    def get_credentials_for_driver(self, exchange: str, account: str = 'main') -> Dict[str, str]:
        """
        获取适合driver使用的认证信息
        
        Args:
            exchange: 交易所名称
            account: 账户名称
            
        Returns:
            dict: 适合driver的认证信息
        """
        if exchange.lower() == 'okx':
            return self.get_okx_credentials(account)
        elif exchange.lower() == 'backpack':
            return self.get_backpack_credentials(account)
        else:
            # 对于其他交易所，返回原始配置
            return self.get_account(exchange, account)
    
    def reload(self):
        """重新加载配置文件"""
        self._config = None
        self._load_config()


# 创建全局实例
account_reader = AccountReader()

# 便捷函数
def get_account(exchange: str, account: str = 'main') -> Dict[str, Any]:
    """获取账户配置的便捷函数"""
    return account_reader.get_account(exchange, account)

def get_okx_credentials(account: str = 'main') -> Dict[str, str]:
    """获取OKX认证信息的便捷函数"""
    return account_reader.get_okx_credentials(account)

def get_backpack_credentials(account: str = 'main') -> Dict[str, str]:
    """获取Backpack认证信息的便捷函数"""
    return account_reader.get_backpack_credentials(account)

def get_credentials_for_driver(exchange: str, account: str = 'main') -> Dict[str, str]:
    """获取driver认证信息的便捷函数"""
    return account_reader.get_credentials_for_driver(exchange, account)

def list_exchanges() -> List[str]:
    """获取交易所列表的便捷函数"""
    return account_reader.list_exchanges()

def list_accounts(exchange: str) -> List[str]:
    """获取账户列表的便捷函数"""
    return account_reader.list_accounts(exchange)

def is_account_valid(exchange: str, account: str) -> bool:
    """检查账户有效性的便捷函数"""
    return account_reader.is_account_valid(exchange, account)


if __name__ == '__main__':
    # 测试代码
    print("=== 账户配置读取器测试 ===")
    
    try:
        # 测试获取所有交易所
        print("\n1. 可用交易所:")
        exchanges = list_exchanges()
        for exchange in exchanges:
            print(f"  - {exchange}")
        
        # 测试获取OKX配置
        print("\n2. OKX账户:")
        okx_accounts = list_accounts('okx')
        for account in okx_accounts:
            print(f"  - {account}")
        
        # 测试获取OKX主账户认证信息
        print("\n3. OKX主账户认证信息:")
        okx_creds = get_okx_credentials('main')
        for key, value in okx_creds.items():
            print(f"  {key}: {'已配置' if value else '未配置'}")
        
        # 测试获取Backpack配置
        print("\n4. Backpack账户:")
        bp_accounts = list_accounts('backpack')
        for account in bp_accounts:
            print(f"  - {account}")
        
        # 测试获取Backpack主账户认证信息
        print("\n5. Backpack主账户认证信息:")
        bp_creds = get_backpack_credentials('main')
        for key, value in bp_creds.items():
            print(f"  {key}: {'已配置' if value else '未配置'}")
        
        # 测试账户有效性检查
        print("\n6. 账户有效性检查:")
        for exchange in exchanges:
            accounts = list_accounts(exchange)
            for account in accounts:
                is_valid = is_account_valid(exchange, account)
                print(f"  {exchange}/{account}: {'有效' if is_valid else '无效'}")
        
        print("\n=== 测试完成 ===")
        
    except Exception as e:
        print(f"测试失败: {e}")
