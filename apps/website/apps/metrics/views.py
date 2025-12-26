from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import os
from pathlib import Path

# 导入K线数据管理器
try:
    from .kline_data_manager import get_kline_manager
    KLINE_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"K线数据管理器导入失败: {e}")
    KLINE_MANAGER_AVAILABLE = False

def metrics_home(request):
    """指标可视化主页 - 显示所有可用指标"""
    # 定义可用指标
    indicators = [
        {
            "id": "topdogindex",
            "name": "TOPDOGINDEX 指标",
            "description": "多时间框架对比分析，包含6张comparison图片",
            "type": "multi_chart",
            "charts": 6,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        },
        {
            "id": "allcoin_trend",
            "name": "全币种趋势",
            "description": "所有币种的价格变化趋势图",
            "type": "single_chart",
            "charts": 1,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        },
        {
            "id": "kline",
            "name": "K线图",
            "description": "单个币种的K线图展示",
            "type": "kline",
            "charts": 1,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        },
        {
            "id": "gold_spread",
            "name": "黄金价差分析",
            "description": "XAUT 和 PAXG 的价差、价格和资金费率分析",
            "type": "multi_chart",
            "charts": 3,
            "timeframes": ["6h", "12h", "24h", "48h", "72h"]
        }
    ]
    
    return render(request, "metrics/home.html", {
        "indicators": indicators
    })

def indicator_detail(request, indicator_id):
    """指标详情页面"""
    if indicator_id == "topdogindex":
        return render(request, "metrics/topdogindex.html", {
            "indicator_id": indicator_id,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        })
    elif indicator_id == "allcoin_trend":
        return render(request, "metrics/allcoin_trend.html", {
            "indicator_id": indicator_id,
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]
        })
    elif indicator_id == "kline":
        # 定义主流币种列表（这些会显示在前面）
        mainstream_coins = ["btc", "eth", "sol", "xrp", "bnb", "ada", "doge", "trx", "ltc", "shib", 
                           "matic", "avax", "dot", "link", "uni"]
        
        # 尝试从K线管理器获取所有可用币种（主流币种在前）
        coins = mainstream_coins
        if KLINE_MANAGER_AVAILABLE:
            try:
                kline_manager = get_kline_manager()
                # 使用新的方法获取币种列表（已包含主流币种排序）
                coins = kline_manager.get_available_coins()
            except Exception as e:
                print(f"获取币种列表失败: {e}，使用默认主流币种")
                coins = mainstream_coins
        
        return render(request, "metrics/kline.html", {
            "indicator_id": indicator_id,
            "timeframes": json.dumps(["1m", "5m", "15m", "1h", "4h", "1d"]),
            "coins": json.dumps(coins)
        })
    elif indicator_id == "gold_spread":
        return render(request, "metrics/gold_spread.html", {
            "indicator_id": indicator_id,
            "timeframes": json.dumps(["6h", "12h", "24h", "48h", "72h"])
        })
    else:
        return render(request, "metrics/error.html", {
            "error": f"未知指标: {indicator_id}"
        })

@csrf_exempt
def get_chart_image(request, indicator_id):
    """获取图表图片的AJAX接口 - 从 static/images 目录读取"""
    if request.method != 'POST':
        return JsonResponse({"error": "只支持POST请求"}, status=405)
    
    try:
        data = json.loads(request.body)
        timeframe = data.get('timeframe', '1m')
        coin = data.get('coin', 'btc')
        
        # 从 static/images 目录读取图片
        # BASE_DIR 是 apps/website 目录
        base_dir = Path(__file__).resolve().parent.parent.parent
        images_dir = base_dir / "static" / "images"
        
        if indicator_id == "topdogindex":
            # TOPDOGINDEX的comparison图片
            # 文件名格式: comparison_chart_all_coin-{index}_{timeframe}.png
            # index: 0->1m, 1->5m, 2->15m, 3->1h, 4->4h, 5->1d
            timeframe_list = ['1m', '5m', '15m', '1h', '4h', '1d']
            if timeframe not in timeframe_list:
                return JsonResponse({
                    "success": False,
                    "error": f"不支持的时间框架: {timeframe}"
                }, status=400)
            
            index = timeframe_list.index(timeframe)
            image_filename = f"comparison_chart_all_coin-{index}_{timeframe}.png"
            image_path = images_dir / image_filename
            
        elif indicator_id == "allcoin_trend":
            # 全币种趋势图
            image_filename = f"allcoin_trend_{timeframe}.png"
            image_path = images_dir / image_filename
            
        elif indicator_id == "kline":
            # K线图（这里需要根据实际实现调整）
            image_filename = f"kline_{coin}_{timeframe}.png"
            image_path = images_dir / image_filename
        elif indicator_id == "gold_spread":
            # 黄金价差分析图
            # 文件名格式: gold_spread_chart.png, gold_price_chart.png, gold_funding_chart.png
            chart_type = data.get('chart_type', 'spread')  # spread, price, funding
            if chart_type == "spread":
                image_filename = "gold_spread_chart.png"
            elif chart_type == "price":
                image_filename = "gold_price_chart.png"
            elif chart_type == "funding":
                image_filename = "gold_funding_chart.png"
            else:
                return JsonResponse({
                    "success": False,
                    "error": f"未知图表类型: {chart_type}"
                }, status=400)
            image_path = images_dir / image_filename
        else:
            return JsonResponse({
                "success": False,
                "error": f"未知指标: {indicator_id}"
            }, status=404)
        
        # 检查图片是否存在
        if not image_path.exists():
            return JsonResponse({
                "success": False,
                "error": f"图片不存在: {image_filename}",
                "searched_path": str(image_path)
            }, status=404)
        
        # 返回图片的静态文件路径（Django会自动处理 /static/ 路径）
        relative_path = f"/static/images/{image_filename}"
        
        return JsonResponse({
            "success": True,
            "image_path": relative_path,
            "indicator_id": indicator_id,
            "timeframe": timeframe,
            "coin": coin
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_kline_data(request):
    """获取K线数据的API接口"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    if not KLINE_MANAGER_AVAILABLE:
        return JsonResponse({
            "success": False,
            "error": "K线数据管理器不可用"
        }, status=500)
    
    try:
        symbol = request.GET.get('symbol', 'btc')
        timeframe = request.GET.get('timeframe', '1H')
        limit = int(request.GET.get('limit', 200))
        
        # 限制limit范围
        if limit < 1 or limit > 1000:
            limit = 200
        
        kline_manager = get_kline_manager()
        kline_data, error = kline_manager.get_kline_data(symbol, timeframe, limit)
        
        if error:
            return JsonResponse({
                "success": False,
                "error": error
            }, status=500)
        
        return JsonResponse({
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "data": kline_data,
            "count": len(kline_data) if kline_data else 0
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_available_symbols(request):
    """获取可用交易对列表的API接口"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    if not KLINE_MANAGER_AVAILABLE:
        return JsonResponse({
            "success": False,
            "error": "K线数据管理器不可用"
        }, status=500)
    
    try:
        kline_manager = get_kline_manager()
        symbols = kline_manager.get_available_symbols()
        
        return JsonResponse({
            "success": True,
            "symbols": symbols
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
def get_gold_spread_data(request):
    """获取黄金价差数据的API接口"""
    if request.method != 'GET':
        return JsonResponse({"error": "只支持GET请求"}, status=405)
    
    if not KLINE_MANAGER_AVAILABLE:
        return JsonResponse({
            "success": False,
            "error": "K线数据管理器不可用"
        }, status=500)
    
    try:
        hours = int(request.GET.get('hours', 24))
        # 限制hours范围
        if hours < 1 or hours > 168:  # 最多7天
            hours = 24
        
        kline_manager = get_kline_manager()
        data, error = kline_manager.get_gold_spread_data(hours=hours)
        
        if error:
            return JsonResponse({
                "success": False,
                "error": error
            }, status=500)
        
        return JsonResponse({
            "success": True,
            "hours": hours,
            "data": data,
            "count": len(data) if data else 0
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)
