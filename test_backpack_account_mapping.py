#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试Backpack Driver动态账户映射功能
验证账户ID根据配置文件动态映射到账户名称
"""

import sys
import os
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

# 执行路径添加
PROJECT_ROOT = add_project_paths()

def test_backpack_dynamic_account_mapping():
    """测试Backpack动态账户映射功能"""
    print("=== 测试Backpack动态账户映射功能 ===")
    
    try:
        from ctos.drivers.backpack.driver import get_account_name_by_id
        from configs.account_reader import list_accounts
        
        # 1. 获取配置文件中的账户列表
        print("\n1. 配置文件中的Backpack账户列表:")
        bp_accounts = list_accounts('backpack')
        print(f"   账户列表: {bp_accounts}")
        print(f"   账户数量: {len(bp_accounts)}")
        
        # 2. 测试账户ID映射
        print("\n2. 账户ID映射测试:")
        for account_id in range(len(bp_accounts) + 2):  # 测试有效和无效的ID
            account_name = get_account_name_by_id(account_id, 'backpack')
            status = "✓" if account_id < len(bp_accounts) else "⚠"
            print(f"   {status} 账户ID {account_id} -> {account_name}")
        
        # 3. 测试边界情况
        print("\n3. 边界情况测试:")
        
        # 测试负数ID
        account_name = get_account_name_by_id(-1, 'backpack')
        print(f"   账户ID -1 -> {account_name}")
        
        # 测试超出范围的ID
        account_name = get_account_name_by_id(999, 'backpack')
        print(f"   账户ID 999 -> {account_name}")
        
        return True
        
    except Exception as e:
        print(f"测试Backpack动态账户映射失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_backpack_client_initialization():
    """测试Backpack客户端初始化"""
    print("\n=== 测试Backpack客户端初始化 ===")
    
    try:
        from ctos.drivers.backpack.driver import init_BackpackClients
        from configs.account_reader import list_accounts
        
        # 获取可用账户数量
        bp_accounts = list_accounts('backpack')
        max_account_id = len(bp_accounts) - 1
        
        print(f"可用账户: {bp_accounts}")
        print(f"最大账户ID: {max_account_id}")
        
        # 测试不同账户ID的初始化
        for account_id in range(max_account_id + 1):
            print(f"\n测试账户ID {account_id}:")
            try:
                account, public = init_BackpackClients(account_id=account_id)
                if account and public:
                    print(f"  ✓ 客户端初始化成功")
                    print(f"  Account类型: {type(account).__name__}")
                    print(f"  Public类型: {type(public).__name__}")
                else:
                    print(f"  ✗ 客户端初始化失败")
            except Exception as e:
                print(f"  ✗ 客户端初始化异常: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试Backpack客户端初始化失败: {e}")
        return False

def test_backpack_driver_initialization():
    """测试Backpack Driver初始化"""
    print("\n=== 测试Backpack Driver初始化 ===")
    
    try:
        from ctos.drivers.backpack.driver import BackpackDriver
        from configs.account_reader import list_accounts
        
        # 获取可用账户数量
        bp_accounts = list_accounts('backpack')
        max_account_id = len(bp_accounts) - 1
        
        # 测试不同账户ID的Driver初始化
        for account_id in range(max_account_id + 1):
            print(f"\n测试Driver账户ID {account_id}:")
            try:
                driver = BackpackDriver(account_id=account_id)
                if driver and driver.account and driver.public:
                    print(f"  ✓ Driver初始化成功")
                    print(f"  交易所: {driver.cex}")
                    print(f"  账户ID: {driver.account_id}")
                    print(f"  Account类型: {type(driver.account).__name__}")
                    print(f"  Public类型: {type(driver.public).__name__}")
                else:
                    print(f"  ✗ Driver初始化失败")
            except Exception as e:
                print(f"  ✗ Driver初始化异常: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试Backpack Driver初始化失败: {e}")
        return False

def test_backpack_credentials():
    """测试Backpack认证信息获取"""
    print("\n=== 测试Backpack认证信息获取 ===")
    
    try:
        from configs.account_reader import get_backpack_credentials, list_accounts
        
        # 获取账户列表
        bp_accounts = list_accounts('backpack')
        print(f"Backpack账户列表: {bp_accounts}")
        
        # 测试每个账户的认证信息
        for account_name in bp_accounts:
            print(f"\n测试账户 {account_name}:")
            try:
                credentials = get_backpack_credentials(account_name)
                print(f"  字段: {list(credentials.keys())}")
                print(f"  Public Key: {'已配置' if credentials.get('public_key') else '未配置'}")
                print(f"  Secret Key: {'已配置' if credentials.get('secret_key') else '未配置'}")
            except Exception as e:
                print(f"  ✗ 获取认证信息失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试Backpack认证信息获取失败: {e}")
        return False

def test_execution_engine_integration():
    """测试与ExecutionEngine的集成"""
    print("\n=== 测试与ExecutionEngine的集成 ===")
    
    try:
        from ctos.core.runtime.ExecutionEngine import ExecutionEngine
        from configs.account_reader import list_accounts
        
        # 获取可用账户数量
        bp_accounts = list_accounts('backpack')
        max_account_id = len(bp_accounts) - 1
        
        # 测试不同账户ID的ExecutionEngine
        for account_id in range(max_account_id + 1):
            print(f"\n测试ExecutionEngine账户ID {account_id}:")
            try:
                engine = ExecutionEngine(account=account_id, exchange_type='backpack')
                if engine and engine.cex_driver:
                    print(f"  ✓ ExecutionEngine初始化成功")
                    print(f"  交易所: {engine.exchange_type}")
                    print(f"  账户ID: {engine.account}")
                    print(f"  Driver类型: {type(engine.cex_driver).__name__}")
                    
                    # 检查driver的account_id
                    if hasattr(engine.cex_driver, 'account_id'):
                        print(f"  Driver账户ID: {engine.cex_driver.account_id}")
                else:
                    print(f"  ✗ ExecutionEngine初始化失败")
            except Exception as e:
                print(f"  ✗ ExecutionEngine初始化异常: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试ExecutionEngine集成失败: {e}")
        return False

def main():
    """主测试函数"""
    print("Backpack Driver动态账户映射功能测试")
    print("=" * 60)
    
    tests = [
        test_backpack_dynamic_account_mapping,
        test_backpack_credentials,
        test_backpack_client_initialization,
        test_backpack_driver_initialization,
        test_execution_engine_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"测试 {test.__name__} 出现异常: {e}")
    
    print(f"\n" + "=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("✓ 所有测试通过！Backpack Driver动态账户映射功能正常")
    else:
        print("✗ 部分测试失败，请检查配置")

if __name__ == '__main__':
    main()
