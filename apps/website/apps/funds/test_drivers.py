#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
驱动测试脚本
用于测试环境变量配置和驱动初始化
"""
import os
import sys

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '../../../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("="*60)
print("驱动测试脚本")
print("="*60)

# 导入API密钥读取函数
try:
    from fund_data_manager import load_api_keys_from_file
    api_keys_from_file = load_api_keys_from_file()
    if api_keys_from_file:
        print(f"\n✓ 从api.txt文件读取到 {len(api_keys_from_file)} 个API密钥")
    else:
        print("\n⚠ 未从api.txt文件读取到API密钥（文件可能不存在或为空）")
except Exception as e:
    print(f"\n⚠ 无法导入load_api_keys_from_file: {e}")
    api_keys_from_file = {}

# 1. 检查环境变量和文件
print("\n[步骤1] 检查API密钥来源...")
print("-"*60)

# 合并文件和环境变量的值（文件优先）
def get_key_value(key_name, alt_names=None):
    """获取密钥值，优先从文件，其次从环境变量"""
    # 从文件读取
    if key_name in api_keys_from_file:
        return api_keys_from_file[key_name], '文件'
    if alt_names:
        for alt in alt_names:
            if alt in api_keys_from_file:
                return api_keys_from_file[alt], '文件'
    
    # 从环境变量读取
    value = os.getenv(key_name)
    if value:
        return value, '环境变量'
    if alt_names:
        for alt in alt_names:
            value = os.getenv(alt)
            if value:
                return value, '环境变量'
    
    return None, None

okx_keys = {
    'OKX_API_KEY': get_key_value('OKX_API_KEY', ['OKX_ACCESS_KEY']),
    'OKX_SECRET_KEY': get_key_value('OKX_SECRET_KEY', ['OKX_SECRET']),
    'OKX_PASSPHRASE': get_key_value('OKX_PASSPHRASE'),
}

backpack_keys = {
    'BP_PUBLIC_KEY': get_key_value('BP_PUBLIC_KEY', ['BACKPACK_PUBLIC_KEY']),
    'BP_SECRET_KEY': get_key_value('BP_SECRET_KEY', ['BACKPACK_SECRET_KEY']),
}

print("\n[OKX API密钥]")
for key, (value, source) in okx_keys.items():
    if value:
        print(f"  ✓ {key}: 已设置 (来源: {source}, 长度: {len(value)}, 前4位: {value[:4]}...)")
    else:
        print(f"  ✗ {key}: 未设置")

print("\n[Backpack API密钥]")
for key, (value, source) in backpack_keys.items():
    if value:
        print(f"  ✓ {key}: 已设置 (来源: {source}, 长度: {len(value)}, 前4位: {value[:4]}...)")
    else:
        print(f"  ✗ {key}: 未设置")

# 2. 检查驱动导入
print("\n[步骤2] 检查驱动导入...")
print("-"*60)

try:
    from ctos.drivers.okx.okex import OkexSpot
    print("✓ OKX驱动导入成功")
    okx_available = True
except ImportError as e:
    print(f"✗ OKX驱动导入失败: {e}")
    okx_available = False

try:
    try:
        from ctos.drivers.backpack.bpx.account import Account
        print("✓ Backpack驱动导入成功 (路径1)")
    except ImportError:
        try:
            from ctos.drivers.backpack.bpx.base.base_account import Account
            print("✓ Backpack驱动导入成功 (路径2)")
        except ImportError:
            from bpx.account import Account
            print("✓ Backpack驱动导入成功 (路径3)")
    backpack_available = True
except ImportError as e:
    print(f"✗ Backpack驱动导入失败: {e}")
    backpack_available = False

# 3. 测试驱动初始化
print("\n[步骤3] 测试驱动初始化...")
print("-"*60)

# 测试OKX
if okx_available:
    access_key, _ = get_key_value('OKX_API_KEY', ['OKX_ACCESS_KEY'])
    secret_key, _ = get_key_value('OKX_SECRET_KEY', ['OKX_SECRET'])
    passphrase, _ = get_key_value('OKX_PASSPHRASE')
    
    if access_key and secret_key and passphrase:
        try:
            print("\n[OKX] 尝试初始化...")
            okx_client = OkexSpot(
                symbol="ETH-USDT-SWAP",
                access_key=access_key,
                secret_key=secret_key,
                passphrase=passphrase,
                host=None
            )
            print("✓ OKX客户端创建成功")
            
            # 测试获取余额
            print("[OKX] 测试获取余额...")
            try:
                balance = okx_client.fetch_balance('USDT')
                print(f"✓ OKX余额获取成功: {balance}")
            except Exception as e:
                print(f"✗ OKX余额获取失败: {e}")
                import traceback
                print(traceback.format_exc())
        except Exception as e:
            print(f"✗ OKX客户端创建失败: {e}")
            import traceback
            print(traceback.format_exc())
    else:
        print("\n[OKX] 跳过测试（环境变量未配置）")

# 测试Backpack
if backpack_available:
    public_key, _ = get_key_value('BP_PUBLIC_KEY', ['BACKPACK_PUBLIC_KEY'])
    secret_key, _ = get_key_value('BP_SECRET_KEY', ['BACKPACK_SECRET_KEY'])
    
    if public_key and secret_key:
        try:
            print("\n[Backpack] 尝试初始化...")
            backpack_client = Account(public_key, secret_key, window=10000)
            print("✓ Backpack客户端创建成功")
            
            # 测试获取余额
            print("[Backpack] 测试获取余额...")
            try:
                if hasattr(backpack_client, 'get_collateral'):
                    collateral = backpack_client.get_collateral()
                    print(f"✓ Backpack余额获取成功，类型: {type(collateral)}")
                    if isinstance(collateral, dict):
                        print(f"  Collateral keys: {list(collateral.keys())}")
                else:
                    print("✗ Backpack Account缺少get_collateral方法")
            except Exception as e:
                print(f"✗ Backpack余额获取失败: {e}")
                import traceback
                print(traceback.format_exc())
        except Exception as e:
            print(f"✗ Backpack客户端创建失败: {e}")
            import traceback
            print(traceback.format_exc())
    else:
        print("\n[Backpack] 跳过测试（环境变量未配置）")

print("\n" + "="*60)
print("测试完成")
print("="*60)

