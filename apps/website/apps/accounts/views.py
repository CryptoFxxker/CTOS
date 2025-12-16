from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import sys
import os

# 动态添加bpx包路径到sys.path
def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 添加项目根目录的bpx路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../../../'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

# 执行路径添加
_PROJECT_ROOT = _add_bpx_path()

from ctos.core.runtime.AccountManager import  ExchangeType, get_account_manager
from configs.account_reader import AccountReader

# 全局账户管理器初始化
def _init_global_account_manager():
    """初始化全局账户管理器，预创建指定账户的Driver"""
    try:
        # 获取AccountManager实例
        account_manager = get_account_manager()
        
        # 初始化Backpack账户 (0-5号)
        print("正在初始化Backpack账户...")
        for account_id in range(6):  # 0-5号账户
            try:
                driver = account_manager.get_driver(
                    ExchangeType('backpack'), 
                    account_id, 
                    auto_create=True
                )
                if driver:
                    print(f"Backpack账户 {account_id} 初始化成功")
                else:
                    print(f"Backpack账户 {account_id} 初始化失败")
            except Exception as e:
                print(f"Backpack账户 {account_id} 初始化异常: {e}")
        
        # 初始化OKX账户 (0-2号)
        print("正在初始化OKX账户...")
        for account_id in range(3):  # 0-2号账户
            try:
                driver = account_manager.get_driver(
                    ExchangeType('okx'), 
                    account_id, 
                    auto_create=True
                )
                if driver:
                    print(f"OKX账户 {account_id} 初始化成功")
                else:
                    print(f"OKX账户 {account_id} 初始化失败")
            except Exception as e:
                print(f"OKX账户 {account_id} 初始化异常: {e}")
        
        print("全局账户管理器初始化完成")
        return account_manager
        
    except Exception as e:
        print(f"全局账户管理器初始化失败: {e}")
        return None

# 全局账户管理器实例
_GLOBAL_ACCOUNT_MANAGER = _init_global_account_manager()

def account_list(request):
    """显示账户列表页面"""
    try:
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return render(request, "accounts/list.html", {
                "accounts": [],
                "exchanges": [],
                "error": "账户管理器初始化失败"
            })
        
        # 获取账户配置
        account_reader = AccountReader()
        all_accounts = account_reader.get_all_accounts()
        
        # 准备账户数据
        accounts_data = []
        
        for exchange, accounts in all_accounts.items():
            for account_name, credentials in accounts.items():
                # 解析账户ID（从账户名称中提取数字）
                account_id = 0
                if '_' in account_name:
                    try:
                        account_id = int(account_name.split('_')[0])
                    except ValueError:
                        account_id = 0
                
                # 尝试获取余额 - 参考ExecutionEngine的初始化方式
                balance = 0.0
                status = "未知"
                try:
                    # 直接使用全局账户管理器获取Driver
                    driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
                        ExchangeType(exchange), 
                        account_id, 
                        auto_create=False  # 不自动创建，因为已经预初始化了
                    )
                    
                    if driver:
                        # 获取余额
                        balance_result = driver.fetch_balance()
                        if isinstance(balance_result, (int, float)):
                            balance = float(balance_result)
                        else:
                            balance = 0.0
                        status = "正常"
                    else:
                        status = "Driver未找到"
                        
                except Exception as e:
                    status = f"错误: {str(e)[:50]}"
                
                accounts_data.append({
                    "exchange": exchange,
                    "account_name": account_name,
                    "account_id": account_id,
                    "balance": balance,
                    "status": status,
                    "credentials_configured": bool(credentials)
                })
        
        return render(request, "accounts/list.html", {
            "accounts": accounts_data,
            "exchanges": list(all_accounts.keys())
        })
        
    except Exception as e:
        return render(request, "accounts/list.html", {
            "accounts": [],
            "exchanges": [],
            "error": f"加载账户信息失败"
        })

@csrf_exempt
def get_account_balance(request):
    """AJAX接口：获取指定账户的余额"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        data = json.loads(request.body)
        exchange = data.get('exchange')
        account_id = int(data.get('account_id', 0))
        
        if not exchange:
            return JsonResponse({"error": "缺少交易所参数"}, status=400)
        
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return JsonResponse({
                "success": False,
                "error": "账户管理器未初始化"
            }, status=500)
        
        # 直接使用全局账户管理器获取Driver
        driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
            ExchangeType(exchange), 
            account_id, 
            auto_create=False
        )
        
        if not driver:
            return JsonResponse({
                "success": False,
                "error": f"未找到 {exchange} 账户 {account_id} 的Driver"
            }, status=404)
        
        # 获取余额
        balance_result = driver.fetch_balance()
        if isinstance(balance_result, (int, float)):
            balance = float(balance_result)
        else:
            balance = 0.0
        
        return JsonResponse({
            "success": True,
            "balance": balance,
            "exchange": exchange,
            "account_id": account_id
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def refresh_all_accounts(request):
    """AJAX接口：刷新所有账户信息"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return JsonResponse({
                "success": False,
                "error": "账户管理器未初始化"
            }, status=500)
        
        # 获取账户配置
        account_reader = AccountReader()
        all_accounts = account_reader.get_all_accounts()
        
        # 准备账户数据
        accounts_data = []
        
        for exchange, accounts in all_accounts.items():
            for account_name, credentials in accounts.items():
                # 解析账户ID
                account_id = 0
                if '_' in account_name:
                    try:
                        account_id = int(account_name.split('_')[0])
                    except ValueError:
                        account_id = 0
                
                # 尝试获取余额 - 参考ExecutionEngine的初始化方式
                balance = 0.0
                status = "未知"
                try:
                    # 直接使用全局账户管理器获取Driver
                    driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
                        ExchangeType(exchange), 
                        account_id, 
                        auto_create=False  # 不自动创建，因为已经预初始化了
                    )
                    
                    if driver:
                        # 获取余额
                        balance_result = driver.fetch_balance()
                        if isinstance(balance_result, (int, float)):
                            balance = float(balance_result)
                        else:
                            balance = 0.0
                        status = "正常"
                    else:
                        status = "Driver未找到"
                        
                except Exception as e:
                    status = f"错误: {str(e)[:50]}"
                
                accounts_data.append({
                    "exchange": exchange,
                    "account_name": account_name,
                    "account_id": account_id,
                    "balance": balance,
                    "status": status,
                    "credentials_configured": bool(credentials)
                })
        
        return JsonResponse({
            "success": True,
            "accounts": accounts_data
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

def account_detail(request, exchange, account_id):
    """账户详情页面 - 显示仓位和订单信息"""
    try:
        account_id = int(account_id)
        
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return render(request, "accounts/detail.html", {
                "exchange": exchange,
                "account_id": account_id,
                "error": "账户管理器未初始化"
            })
        
        # 获取Driver
        driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
            ExchangeType(exchange), 
            account_id, 
            auto_create=False
        )
        
        if not driver:
            return render(request, "accounts/detail.html", {
                "exchange": exchange,
                "account_id": account_id,
                "error": f"未找到 {exchange} 账户 {account_id} 的Driver"
            })
        
        # 获取账户基本信息
        account_info = {
            "exchange": exchange,
            "account_id": account_id,
            "balance": 0.0,
            "status": "正常"
        }
        
        try:
            balance_result = driver.fetch_balance()
            if isinstance(balance_result, (int, float)):
                account_info["balance"] = float(balance_result)
        except Exception as e:
            account_info["status"] = f"余额获取失败: {str(e)[:50]}"
        
        return render(request, "accounts/detail.html", {
            "account_info": account_info,
            "driver_available": True
        })
        
    except Exception as e:
        return render(request, "accounts/detail.html", {
            "exchange": exchange,
            "account_id": account_id,
            "error": f"加载账户详情失败: {str(e)}"
        })

@csrf_exempt
def get_account_positions(request, exchange, account_id):
    """AJAX接口：获取账户仓位信息"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        account_id = int(account_id)
        
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return JsonResponse({
                "success": False,
                "error": "账户管理器未初始化"
            }, status=500)
        
        # 获取Driver
        driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
            ExchangeType(exchange), 
            account_id, 
            auto_create=False
        )
        
        if not driver:
            return JsonResponse({
                "success": False,
                "error": f"未找到 {exchange} 账户 {account_id} 的Driver"
            }, status=404)
        
        # 获取仓位信息
        try:
            # 先获取原始数据（keep_origin=True）
            raw_positions_result = driver.get_position(keep_origin=True)
            print(f"DEBUG - {exchange} 账户 {account_id} 原始仓位数据:")
            print(f"  类型: {type(raw_positions_result)}")
            print(f"  内容: {raw_positions_result}")
            
            # 再获取统一格式数据（keep_origin=False）
            positions_result = driver.get_position(keep_origin=False)
            
            # 处理仓位数据
            positions = []
            if isinstance(positions_result, tuple):
                # 如果返回的是 (success, error) 格式
                success_data, error_data = positions_result
                if error_data:
                    return JsonResponse({
                        "success": False,
                        "error": str(error_data)
                    }, status=500)
                
                if isinstance(success_data, list):
                    positions = success_data
                elif isinstance(success_data, dict) and 'data' in success_data:
                    positions = success_data['data']
            elif isinstance(positions_result, list):
                positions = positions_result
            elif isinstance(positions_result, dict):
                if 'data' in positions_result:
                    positions = positions_result['data']
                else:
                    positions = [positions_result]
            
            
            # 添加调试信息（开发阶段）
            print(f"DEBUG - {exchange} 账户 {account_id} 仓位数据:")
            for i, pos in enumerate(positions):
                print(f"  仓位 {i}: {pos}")
            
            return JsonResponse({
                "success": True,
                "positions": positions,
                "exchange": exchange,
                "account_id": account_id
            })
            
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": f"获取仓位失败: {str(e)}"
            }, status=500)
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_account_orders(request, exchange, account_id):
    """AJAX接口：获取账户订单信息"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        account_id = int(account_id)
        
        # 使用全局账户管理器
        if _GLOBAL_ACCOUNT_MANAGER is None:
            return JsonResponse({
                "success": False,
                "error": "账户管理器未初始化"
            }, status=500)
        
        # 获取Driver
        driver = _GLOBAL_ACCOUNT_MANAGER.get_driver(
            ExchangeType(exchange), 
            account_id, 
            auto_create=False
        )
        
        if not driver:
            return JsonResponse({
                "success": False,
                "error": f"未找到 {exchange} 账户 {account_id} 的Driver"
            }, status=404)
        
        # 获取订单信息
        try:
            orders_result = driver.get_open_orders(onlyOrderId=False, keep_origin=False)
            
            # 处理订单数据
            orders = []
            if isinstance(orders_result, tuple):
                # 如果返回的是 (success, error) 格式
                success_data, error_data = orders_result
                if error_data:
                    return JsonResponse({
                        "success": False,
                        "error": str(error_data)
                    }, status=500)
                
                if isinstance(success_data, list):
                    orders = success_data
                elif isinstance(success_data, dict) and 'data' in success_data:
                    orders = success_data['data']
            elif isinstance(orders_result, list):
                orders = orders_result
            elif isinstance(orders_result, dict):
                if 'data' in orders_result:
                    orders = orders_result['data']
                else:
                    orders = [orders_result]
            
            # 添加调试信息（开发阶段）
            print(f"DEBUG - {exchange} 账户 {account_id} 订单数据:")
            for i, order in enumerate(orders):
                print(f"  订单 {i}: {order}")
            
            return JsonResponse({
                "success": True,
                "orders": orders,
                "exchange": exchange,
                "account_id": account_id
            })
            
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": f"获取订单失败: {str(e)}"
            }, status=500)
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

def debug_data(request):
    """调试数据格式页面"""
    return render(request, "accounts/debug.html")