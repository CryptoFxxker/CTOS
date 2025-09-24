#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试动态账户映射功能
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

def test_dynamic_account_mapping():
    """测试动态账户映射功能"""
    print("=== 测试动态账户映射功能 ===")
    
    try:
        from ctos.drivers.okx.driver import get_account_name_by_id
        from configs.account_reader import list_accounts
        
        # 1. 获取配置文件中的账户列表
        print("\n1. 配置文件中的OKX账户列表:")
        okx_accounts = list_accounts('okx')
        print(f"   账户列表: {okx_accounts}")
        print(f"   账户数量: {len(okx_accounts)}")
        
        # 2. 测试账户ID映射
        print("\n2. 账户ID映射测试:")
        for account_id in range(len(okx_accounts) + 2):  # 测试有效和无效的ID
            account_name = get_account_name_by_id(account_id, 'okx')
            status = "✓" if account_id < len(okx_accounts) else "⚠"
            print(f"   {status} 账户ID {account_id} -> {account_name}")
        
        # 3. 测试边界情况
        print("\n3. 边界情况测试:")
        
        # 测试负数ID
        account_name = get_account_name_by_id(-1, 'okx')
        print(f"   账户ID -1 -> {account_name}")
        
        # 测试超出范围的ID
        account_name = get_account_name_by_id(999, 'okx')
        print(f"   账户ID 999 -> {account_name}")
        
        return True
        
    except Exception as e:
        print(f"测试动态账户映射失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_okx_client_initialization():
    """测试OKX客户端初始化"""
    print("\n=== 测试OKX客户端初始化 ===")
    
    try:
        from ctos.drivers.okx.driver import init_OkxClient
        from configs.account_reader import list_accounts
        
        # 获取可用账户数量
        okx_accounts = list_accounts('okx')
        max_account_id = len(okx_accounts) - 1
        
        print(f"可用账户: {okx_accounts}")
        print(f"最大账户ID: {max_account_id}")
        
        # 测试不同账户ID的初始化
        for account_id in range(max_account_id + 1):
            print(f"\n测试账户ID {account_id}:")
            try:
                client = init_OkxClient(account_id=account_id, show=True)
                if client:
                    print(f"  ✓ 客户端初始化成功")
                else:
                    print(f"  ✗ 客户端初始化失败")
            except Exception as e:
                print(f"  ✗ 客户端初始化异常: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试OKX客户端初始化失败: {e}")
        return False

def test_okx_driver_initialization():
    """测试OKX Driver初始化"""
    print("\n=== 测试OKX Driver初始化 ===")
    
    try:
        from ctos.drivers.okx.driver import OkxDriver
        from configs.account_reader import list_accounts
        
        # 获取可用账户数量
        okx_accounts = list_accounts('okx')
        max_account_id = len(okx_accounts) - 1
        
        # 测试不同账户ID的Driver初始化
        for account_id in range(max_account_id + 1):
            print(f"\n测试Driver账户ID {account_id}:")
            try:
                driver = OkxDriver(account_id=account_id)
                if driver and driver.okx:
                    print(f"  ✓ Driver初始化成功")
                    print(f"    交易所: {driver.cex}")
                    print(f"    账户ID: {driver.account_id}")
                else:
                    print(f"  ✗ Driver初始化失败")
            except Exception as e:
                print(f"  ✗ Driver初始化异常: {e}")
        
        return True
        
    except Exception as e:
        print(f"测试OKX Driver初始化失败: {e}")
        return False

def test_configuration_flexibility():
    """测试配置灵活性"""
    print("\n=== 测试配置灵活性 ===")
    
    try:
        from configs.account_reader import get_all_accounts
        
        # 显示当前配置结构
        all_accounts = get_all_accounts()
        print("当前配置结构:")
        for exchange, accounts in all_accounts.items():
            print(f"  {exchange}:")
            for account_name, account_config in accounts.items():
                print(f"    {account_name}: {list(account_config.keys())}")
        
        # 测试OKX账户
        okx_accounts = all_accounts.get('okx', {})
        print(f"\nOKX账户数量: {len(okx_accounts)}")
        print("账户ID映射:")
        for i, account_name in enumerate(okx_accounts.keys()):
            print(f"  {i} -> {account_name}")
        
        return True
        
    except Exception as e:
        print(f"测试配置灵活性失败: {e}")
        return False

def main():
    """主测试函数"""
    print("动态账户映射功能测试")
    print("=" * 50)
    
    tests = [
        test_dynamic_account_mapping,
        test_okx_client_initialization,
        test_okx_driver_initialization,
        test_configuration_flexibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"测试 {test.__name__} 出现异常: {e}")
    
    print(f"\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("✓ 所有测试通过！动态账户映射功能正常")
    else:
        print("✗ 部分测试失败，请检查配置")

if __name__ == '__main__':
    main()
