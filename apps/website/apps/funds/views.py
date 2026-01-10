from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime, timedelta
import pytz
from .fund_data_manager import get_fund_manager, get_multi_account_manager

# 北京时间时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_beijing_time():
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)

# 获取多账户管理器
_multi_account_manager = None

def _init_multi_account_manager():
    """初始化多账户管理器"""
    global _multi_account_manager
    try:
        _multi_account_manager = get_multi_account_manager()
        print("多账户基金数据管理器初始化成功")
    except Exception as e:
        print(f"多账户基金数据管理器初始化失败: {e}")
        _multi_account_manager = None

def _get_multi_account_manager():
    """获取多账户管理器实例"""
    global _multi_account_manager
    if _multi_account_manager is None:
        _init_multi_account_manager()
    return _multi_account_manager

# 模块加载时初始化
_init_multi_account_manager()

def fund_trends(request):
    """基金趋势主页"""
    # 获取账户列表
    multi_manager = _get_multi_account_manager()
    accounts = []
    if multi_manager:
        accounts = multi_manager.get_account_info()
    
    return render(request, "funds/index.html", {
        "accounts": accounts
    })

@csrf_exempt
def get_accounts_list(request):
    """获取账户列表"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    try:
        multi_manager = _get_multi_account_manager()
        if multi_manager:
            accounts = multi_manager.get_account_info()
            return JsonResponse({
                "success": True,
                "accounts": accounts
            })
        else:
            return JsonResponse({
                "success": True,
                "accounts": [{"account_id": "default", "account_name": "默认账户"}]
            })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_fund_summary(request):
    """获取基金概览数据：当前余额和当日盈亏"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    try:
        # 获取账户ID参数
        account_id = request.GET.get('account_id', None)
        
        # 获取指定账户的管理器
        fund_manager = get_fund_manager(account_id)
        
        if fund_manager is None:
            return JsonResponse({
                "success": False,
                "error": f"账户 {account_id} 不存在"
            }, status=404)
        
        # 检查采集线程状态，如果停止则重启
        if not fund_manager.is_collector_running():
            print(f"⚠ 检测到账户 {account_id} 的采集线程已停止，正在重启...")
            fund_manager.restart_collector()
        
        # 获取当前余额（使用缓存）
        current_balance, error = fund_manager.get_total_balance(use_cache=True)
        
        if error:
            print(f"获取余额时出现警告: {error}")
        
        # 获取当日盈亏
        period_pnl, period_pnl_percent, start_value, current_value = fund_manager.get_period_pnl('1d')
        
        return JsonResponse({
            "success": True,
            "data": {
                "current_balance": current_balance,
                "today_pnl": period_pnl,
                "today_pnl_percent": period_pnl_percent,
                "last_updated": get_beijing_time().strftime("%Y-%m-%d %H:%M:%S"),
                "collector_running": fund_manager.is_collector_running()
            }
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_fund_trend(request):
    """获取基金走势数据"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    try:
        period = request.GET.get('period', '1d')  # 1d, 7d, 1m, 6m, all
        account_id = request.GET.get('account_id', None)  # 账户ID
        
        # 获取指定账户的管理器
        fund_manager = get_fund_manager(account_id)
        
        if fund_manager is None:
            return JsonResponse({
                "success": False,
                "error": f"账户 {account_id} 不存在"
            }, status=404)
        
        # 检查采集线程状态，如果停止则重启
        if not fund_manager.is_collector_running():
            print(f"⚠ 检测到账户 {account_id} 的采集线程已停止，正在重启...")
            fund_manager.restart_collector()
        
        # 从数据库获取走势数据
        trend_data = fund_manager.get_trend_data(period)
        
        # 如果数据库中没有数据，返回空数据
        if not trend_data:
            return JsonResponse({
                "success": True,
                "period": period,
                "data": [],
                "count": 0,
                "period_pnl": 0.0,
                "period_pnl_percent": 0.0,
                "start_value": 0.0,
                "current_value": 0.0,
                "message": "暂无数据，数据采集正在进行中..."
            })
        
        # 计算周期盈亏
        period_pnl, period_pnl_percent, start_value, current_value = fund_manager.get_period_pnl(period)
        
        return JsonResponse({
            "success": True,
            "period": period,
            "data": trend_data,
            "count": len(trend_data),
            "period_pnl": period_pnl,
            "period_pnl_percent": period_pnl_percent,
            "start_value": start_value,
            "current_value": current_value
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_collector_status(request):
    """获取采集线程状态诊断信息"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    try:
        multi_manager = _get_multi_account_manager()
        if not multi_manager:
            return JsonResponse({
                "success": False,
                "error": "多账户管理器未初始化"
            }, status=500)
        
        # 检查并重启停止的采集线程
        restarted = multi_manager.check_and_restart_collectors()
        
        # 获取状态
        status = multi_manager.get_collector_status()
        
        return JsonResponse({
            "success": True,
            "status": status,
            "restarted": restarted,
            "message": f"已重启 {len(restarted)} 个停止的采集线程" if restarted else "所有采集线程运行正常"
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def restart_collector(request):
    """强制重启指定账户的采集线程"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        account_id = request.GET.get('account_id') or request.POST.get('account_id')
        if not account_id:
            return JsonResponse({
                "success": False,
                "error": "缺少account_id参数"
            }, status=400)
        
        fund_manager = get_fund_manager(account_id)
        if fund_manager is None:
            return JsonResponse({
                "success": False,
                "error": f"账户 {account_id} 不存在"
            }, status=404)
        
        # 强制重启
        print(f"🔧 手动触发账户 {account_id} 的采集线程重启...")
        fund_manager.restart_collector()
        
        # 等待一下确保线程启动
        import time
        time.sleep(2)
        
        # 检查状态
        is_running = fund_manager.is_collector_running()
        
        return JsonResponse({
            "success": True,
            "account_id": account_id,
            "restarted": True,
            "running": is_running,
            "message": f"账户 {account_id} 的采集线程已{'成功重启' if is_running else '重启失败，请查看日志'}"
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

