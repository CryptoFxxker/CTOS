#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置文件读取器使用示例
演示如何在项目中使用account_reader
"""

import sys
import os
from pathlib import Path

def add_project_paths(project_name="ctos", subpackages=None):
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
PROJECT_ROOT = add_project_paths()

from configs.account_reader import (
    account_reader, 
    get_account, 
    get_okx_credentials, 
    get_backpack_credentials,
    get_credentials_for_driver,
    list_exchanges,
    list_accounts,
    is_account_valid
)

def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 1. 获取所有交易所
    exchanges = list_exchanges()
    print(f"可用交易所: {exchanges}")
    
    # 2. 获取OKX的所有账户
    okx_accounts = list_accounts('okx')
    print(f"OKX账户: {okx_accounts}")
    
    # 3. 获取OKX主账户配置
    okx_main = get_account('okx', 'main')
    print(f"OKX主账户配置字段: {list(okx_main.keys())}")
    
    # 4. 获取OKX认证信息
    okx_creds = get_okx_credentials('main')
    print(f"OKX认证信息: {list(okx_creds.keys())}")
    
    # 5. 验证账户有效性
    is_valid = is_account_valid('okx', 'main')
    print(f"OKX主账户是否有效: {is_valid}")

def example_driver_integration():
    """Driver集成示例"""
    print("\n=== Driver集成示例 ===")
    
    # 模拟创建OKX Driver
    try:
        okx_creds = get_credentials_for_driver('okx', 'main')
        print(f"OKX Driver认证信息: {list(okx_creds.keys())}")
        
        # 这里可以用于初始化OKX Driver
        # driver = OkxDriver(**okx_creds)
        
    except Exception as e:
        print(f"获取OKX认证信息失败: {e}")
    
    # 模拟创建Backpack Driver
    try:
        bp_creds = get_credentials_for_driver('backpack', 'main')
        print(f"Backpack Driver认证信息: {list(bp_creds.keys())}")
        
        # 这里可以用于初始化Backpack Driver
        # driver = BackpackDriver(**bp_creds)
        
    except Exception as e:
        print(f"获取Backpack认证信息失败: {e}")

def example_execution_engine_integration():
    """ExecutionEngine集成示例"""
    print("\n=== ExecutionEngine集成示例 ===")
    
    def create_driver(exchange: str, account: str = 'main'):
        """根据配置创建driver"""
        try:
            credentials = get_credentials_for_driver(exchange, account)
            
            if exchange == 'okx':
                # 模拟OKX Driver创建
                print(f"创建OKX Driver，账户: {account}")
                print(f"认证字段: {list(credentials.keys())}")
                return f"OKX_Driver_{account}"
                
            elif exchange == 'backpack':
                # 模拟Backpack Driver创建
                print(f"创建Backpack Driver，账户: {account}")
                print(f"认证字段: {list(credentials.keys())}")
                return f"Backpack_Driver_{account}"
                
            else:
                print(f"不支持的交易所: {exchange}")
                return None
                
        except Exception as e:
            print(f"创建{exchange} Driver失败: {e}")
            return None
    
    # 测试创建不同交易所的Driver
    okx_driver = create_driver('okx', 'main')
    bp_driver = create_driver('backpack', 'main')
    okx_sub_driver = create_driver('okx', 'sub1')

def example_configuration_validation():
    """配置验证示例"""
    print("\n=== 配置验证示例 ===")
    
    # 检查所有账户配置
    exchanges = list_exchanges()
    
    for exchange in exchanges:
        accounts = list_accounts(exchange)
        print(f"\n{exchange.upper()} 交易所:")
        
        for account in accounts:
            is_valid = is_account_valid(exchange, account)
            status = "✓ 有效" if is_valid else "✗ 无效"
            print(f"  {account}: {status}")
            
            if is_valid:
                # 获取认证信息（不显示真实值）
                creds = get_credentials_for_driver(exchange, account)
                print(f"    配置字段: {list(creds.keys())}")

def example_advanced_usage():
    """高级使用示例"""
    print("\n=== 高级使用示例 ===")
    
    # 1. 获取所有账户配置
    all_accounts = account_reader.get_all_accounts()
    print(f"所有账户配置结构: {list(all_accounts.keys())}")
    
    # 2. 遍历所有交易所和账户
    for exchange, accounts in all_accounts.items():
        print(f"\n{exchange.upper()}:")
        for account_name, account_config in accounts.items():
            print(f"  {account_name}: {list(account_config.keys())}")
    
    # 3. 动态选择账户
    def get_available_accounts(exchange: str):
        """获取指定交易所的可用账户"""
        accounts = list_accounts(exchange)
        valid_accounts = []
        
        for account in accounts:
            if is_account_valid(exchange, account):
                valid_accounts.append(account)
        
        return valid_accounts
    
    print(f"\nOKX可用账户: {get_available_accounts('okx')}")
    print(f"Backpack可用账户: {get_available_accounts('backpack')}")

if __name__ == '__main__':
    print("配置文件读取器使用示例")
    print("=" * 50)
    
    try:
        example_basic_usage()
        example_driver_integration()
        example_execution_engine_integration()
        example_configuration_validation()
        example_advanced_usage()
        
        print("\n" + "=" * 50)
        print("所有示例执行完成！")
        
    except Exception as e:
        print(f"示例执行失败: {e}")
        import traceback
        traceback.print_exc()
