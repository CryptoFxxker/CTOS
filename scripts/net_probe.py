#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import ssl
import time
import json
import os
import sys
from urllib.parse import urlparse
from datetime import datetime



# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)


from ctos.drivers.backpack.driver import BackpackDriver
from ctos.drivers.okx.driver import OkxDriver

try:
    import requests
except Exception:
    requests = None

# 导入驱动
try:
    from ctos.drivers.okx.driver import init_OkxClient
    from ctos.drivers.backpack.driver import init_BackpackClients
    OKX_AVAILABLE = True
    BACKPACK_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ OKX/Backpack驱动导入失败: {e}")
    OKX_AVAILABLE = False
    BACKPACK_AVAILABLE = False

try:
    from ctos.drivers.binance.driver import init_BinanceClient
    BINANCE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Binance驱动导入失败: {e}")
    BINANCE_AVAILABLE = False

DRIVERS_AVAILABLE = OKX_AVAILABLE or BACKPACK_AVAILABLE or BINANCE_AVAILABLE

EXCHANGES = [
    {
        "name": "OKX",
        "base": os.getenv("OKX_BASE_URL", "https://www.okx.com"),
        "check_paths": [
            "/api/v5/public/time",
            "/api/v5/public/instruments?instType=SWAP",
        ],
        "advice": {
            "zh": "若 DNS 解析失败或超时，尝试更换 DNS（如 1.1.1.1/8.8.8.8）；若 TLS 失败或 403，可能被风控或需要代理。",
            "en": "If DNS fails/timeouts, try alternate DNS (1.1.1.1/8.8.8.8). If TLS fails or 403, risk-control or proxy may be required.",
        },
    },
    {
        "name": "Backpack",
        "base": os.getenv("BP_BASE_URL", "https://api.backpack.exchange"),
        "check_paths": [
            "/api/v1/time",         # try a light endpoint (best-effort)
            "/api/v1/markets",      # common public endpoint
        ],
        "advice": {
            "zh": "若无法连接 api.backpack.exchange，请检查出口网络与代理；亦可尝试 curl 指定 --resolve 以绕过 DNS。",
            "en": "If api.backpack.exchange is unreachable, verify egress network/proxy; try curl with --resolve to bypass DNS.",
        },
    },
    {
        "name": "Binance",
        "base": os.getenv("BINANCE_BASE_URL", "https://api.binance.com"),
        "check_paths": [
            "/api/v3/time",
            "/api/v3/exchangeInfo",
        ],
        "advice": {
            "zh": "若无法连接 api.binance.com，请检查网络连接和防火墙设置。",
            "en": "If api.binance.com is unreachable, check network connection and firewall settings.",
        },
    },
]


def dns_lookup(host: str, timeout: float = 3.0):
    t0 = time.time()
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = list({info[4][0] for info in infos})
        return {"ok": True, "ips": ips, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "error": str(e), "ms": int((time.time() - t0) * 1000)}


def tcp_connect(host: str, port: int = 443, timeout: float = 3.0):
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "error": str(e), "ms": int((time.time() - t0) * 1000)}


def tls_handshake(host: str, port: int = 443, timeout: float = 5.0):
    t0 = time.time()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                _ = ssock.version()
                return {"ok": True, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "error": str(e), "ms": int((time.time() - t0) * 1000)}


def build_proxies_from_env():
    # Respect common conda/proxy env vars
    env = os.environ
    proxies = {}
    hp = env.get('http_proxy') or env.get('HTTP_PROXY')
    hps = env.get('https_proxy') or env.get('HTTPS_PROXY')
    if hp:
        proxies['http'] = hp
    if hps:
        proxies['https'] = hps
    no_proxy = env.get('no_proxy') or env.get('NO_PROXY')
    summary = {
        'http_proxy': hp,
        'https_proxy': hps,
        'no_proxy': no_proxy,
        'conda_env': env.get('CONDA_DEFAULT_ENV'),
        'requests_ca_bundle': env.get('REQUESTS_CA_BUNDLE'),
    }
    return proxies, summary


def http_get(url: str, timeout: float = 6.0, proxies: dict | None = None):
    if requests is None:
        return {"ok": False, "error": "requests not installed", "status": None, "ms": 0}
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout, proxies=proxies)
        return {
            "ok": (200 <= r.status_code < 400),
            "status": r.status_code,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "status": None, "ms": int((time.time() - t0) * 1000)}


def probe_exchange(ex):
    base = ex["base"].rstrip('/')
    host = urlparse(base).hostname or base
    result = {"name": ex["name"], "base": base}

    # DNS
    result["dns"] = dns_lookup(host)

    # TCP
    result["tcp"] = tcp_connect(host)

    # TLS
    result["tls"] = tls_handshake(host)

    # HTTP(s) - consider proxy mode
    mode = (os.getenv('NET_PROBE_MODE') or 'both').lower()  # proxy|direct|both
    use_proxy = mode in ('proxy', 'both')
    use_direct = mode in ('direct', 'both')
    proxies, proxy_summary = build_proxies_from_env()
    result["proxy"] = proxy_summary
    result["http"] = []
    for p in ex.get("check_paths", []):
        url = base + p
        if use_proxy:
            res_p = {"url": url, "mode": "proxy", **http_get(url, proxies=proxies)}
            result["http"].append(res_p)
        if use_direct:
            res_d = {"url": url, "mode": "direct", **http_get(url, proxies={})}
            result["http"].append(res_d)

    # Analysis
    issues = []
    if not result["dns"]["ok"]:
        issues.append("DNS failed")
    if result["dns"].get("ms", 0) > 1500:
        issues.append("DNS slow")
    if not result["tcp"]["ok"]:
        issues.append("TCP connect failed")
    if not result["tls"]["ok"]:
        issues.append("TLS handshake failed")
    http_any_ok = any(h.get("ok") for h in result["http"])
    if not http_any_ok:
        issues.append("HTTP failed for all endpoints")

    result["summary"] = {
        "ok": (len(issues) == 0),
        "issues": issues,
        "advice_zh": ex.get("advice", {}).get("zh"),
        "advice_en": ex.get("advice", {}).get("en"),
        "mode": mode,
    }
    return result


def test_driver_initialization():
    """测试驱动初始化"""
    print("\n" + "="*50)
    print("🚀 驱动初始化测试")
    print("="*50)
    
    driver_tests = []
    
    # 测试OKX驱动
    if OKX_AVAILABLE:
        print("\n📊 测试 OKX 驱动...")
        try:
            client = OkxDriver(account_id=0)
            if client:
                # 测试基本功能
                test_results = {
                    "name": "OKX",
                    "init_ok": True,
                    "client_type": type(client).__name__,
                    "tests": {}
                }

                # 测试获取交易对
                try:
                    t0 = time.time()
                    symbols, _ = client.symbols(instType="SWAP")
                    test_results["tests"]["get_symbols"] = {
                        "ok": True,
                        "ms": int((time.time() - t0) * 1000),
                        "count": len(symbols) if symbols else 0
                    }
                except Exception as e:
                    test_results["tests"]["get_symbols"] = {"ok": False, "error": str(e)}
                
                # 测试获取价格
                try:
                    t0 = time.time()
                    price = client.get_price_now("eth")
                    test_results["tests"]["get_price"] = {
                        "ok": price is not None,
                        "ms": int((time.time() - t0) * 1000),
                        "price": price,
                        "symbol": "eth",
                    }
                except Exception as e:
                    test_results["tests"]["get_price"] = {"ok": False, "error": str(e)}
                    
            else:
                test_results = {"name": "OKX", "init_ok": False, "error": "Client initialization failed"}
                
        except Exception as e:
            test_results = {"name": "OKX", "init_ok": False, "error": str(e)}
        
        driver_tests.append(test_results)
    
    # 测试Backpack驱动
    if BACKPACK_AVAILABLE:
        print("\n📊 测试 Backpack 驱动...")
        try:
            bp = BackpackDriver(account_id=0)
            if bp:
                test_results = {
                    "name": "Backpack",
                    "init_ok": True,
                    "account_client": bp.__class__.__name__,
                    "tests": {}
                }
                # 测试获取市场信息
                try:
                    t0 = time.time()
                    markets, _ = bp.symbols()
                    test_results["tests"]["get_markets"] = {
                        "ok": True,
                        "ms": int((time.time() - t0) * 1000),
                        "count": len(markets) if markets else 0
                    }
                except Exception as e:
                    test_results["tests"]["get_markets"] = {"ok": False, "error": str(e)}
                
                # 测试获取价格
                try:
                    t0 = time.time()
                    ticker = bp.get_price_now("eth")
                    test_results["tests"]["get_price"] = {
                        "ok": ticker is not None,
                        "ms": int((time.time() - t0) * 1000),
                        "price": ticker if ticker else None,
                        "symbol": "eth",
                    }
                except Exception as e:
                    test_results["tests"]["get_price"] = {"ok": False, "error": str(e)}
                    
            else:
                test_results = {"name": "Backpack", "init_ok": False, "error": "Client initialization failed"}
                
        except Exception as e:
            test_results = {"name": "Backpack", "init_ok": False, "error": str(e)}
        
        driver_tests.append(test_results)
    
    # 测试Binance驱动
    if BINANCE_AVAILABLE:
        print("\n📊 测试 Binance 驱动...")
        try:
            client = init_BinanceClient()
            if client:
                test_results = {
                    "name": "Binance",
                    "init_ok": True,
                    "client_type": type(client).__name__,
                    "tests": {}
                }
                
                # 测试获取时间
                try:
                    t0 = time.time()
                    time_data = client.get_server_time()
                    test_results["tests"]["get_price_now"] = {
                        "ok": True,
                        "ms": int((time.time() - t0) * 1000),
                        "data": time_data
                    }
                except Exception as e:
                    test_results["tests"]["get_price_now"] = {"ok": False, "error": str(e)}
                
                # 测试获取交易对信息
                try:
                    t0 = time.time()
                    info = client.get_exchange_info()
                    test_results["tests"]["get_exchange_info"] = {
                        "ok": True,
                        "ms": int((time.time() - t0) * 1000),
                        "symbols_count": len(info.get("symbols", [])) if info else 0,
                        "symbol": "BTCUSDT",
                    }
                except Exception as e:
                    test_results["tests"]["get_exchange_info"] = {"ok": False, "error": str(e)}
                
                # 测试获取价格
                try:
                    t0 = time.time()
                    price = client.get_symbol_ticker(symbol="BTCUSDT")
                    test_results["tests"]["get_price"] = {
                        "ok": price is not None,
                        "ms": int((time.time() - t0) * 1000),
                        "price": price.get("price") if price else None,
                        "symbol": "BTCUSDT",
                    }
                except Exception as e:
                    test_results["tests"]["get_price"] = {"ok": False, "error": str(e)}
                    
            else:
                test_results = {"name": "Binance", "init_ok": False, "error": "Client initialization failed"}
                
        except Exception as e:
            test_results = {"name": "Binance", "init_ok": False, "error": str(e)}
        
        driver_tests.append(test_results)
    
    return driver_tests


def main():
    print("🌐 CTOS 网络连接与驱动测试")
    print("="*50)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 网络连接测试
    print("\n🔗 网络连接测试")
    print("-" * 30)
    reports = []
    for ex in EXCHANGES:
        reports.append(probe_exchange(ex))

    # 驱动测试
    driver_tests = []
    if DRIVERS_AVAILABLE:
        driver_tests = test_driver_initialization()
    else:
        print("\n⚠️ 驱动不可用，跳过驱动测试")

    # 生成综合报告
    print("\n" + "="*50)
    print("📋 综合测试报告")
    print("="*50)
    
    # 网络连接报告
    print("\n🌐 网络连接状态:")
    for r in reports:
        ok = r['summary']['ok']
        status = "✅ 正常" if ok else "❌ 异常"
        print(f"  {r['name']}: {status}")
        if not ok:
            print(f"    问题: {', '.join(r['summary']['issues'])}")
    
    # 驱动测试报告
    if driver_tests:
        print("\n🚀 驱动测试状态:")
        for test in driver_tests:
            if test.get("init_ok"):
                print(f"  {test['name']}: ✅ 初始化成功")
                for test_name, result in test.get("tests", {}).items():
                    status = "✅" if result.get("ok") else "❌"
                    ms = result.get("ms", 0)
                    print(f"    {test_name}: {status} ({ms}ms)")
            else:
                print(f"  {test['name']}: ❌ 初始化失败 - {test.get('error', 'Unknown error')}")
    
    # 详细报告
    print("\n" + "="*50)
    print("📊 详细测试结果")
    print("="*50)
    
    # 网络连接详细结果
    for r in reports:
        print(f"\n🌐 {r['name']} 网络测试:")
        print(f"  DNS: {r['dns']}")
        print(f"  TCP: {r['tcp']}")
        print(f"  TLS: {r['tls']}")
        print(f"  HTTP测试:")
        for h in r['http']:
            print(f"    {h['url']} ({h['mode']}): {h}")
    
    # 驱动测试详细结果
    if driver_tests:
        for test in driver_tests:
            print(f"\n🚀 {test['name']} 驱动测试:")
            if test.get("init_ok"):
                print(f"  初始化: ✅ 成功")
                print(f"  客户端类型: {test.get('client_type', test.get('account_client', 'Unknown'))}")
                for test_name, result in test.get("tests", {}).items():
                    print(f"  {test_name}: {result}")
            else:
                print(f"  初始化: ❌ 失败 - {test.get('error', 'Unknown error')}")

    print("\n💡 提示:")
    print("  - 设置环境变量 OKX_BASE_URL / BP_BASE_URL / BINANCE_BASE_URL 可覆盖默认URL")
    print("  - 设置 NET_PROBE_MODE=proxy|direct|both 可控制HTTP探测模式")
    print("  - 确保已正确配置各交易所的API密钥")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


