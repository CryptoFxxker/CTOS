#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import ssl
import time
import json
import os
from urllib.parse import urlparse

try:
    import requests
except Exception:
    requests = None


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


def main():
    reports = []
    for ex in EXCHANGES:
        reports.append(probe_exchange(ex))

    # Pretty print bilingual report
    for r in reports:
        print("\n==============================")
        print(f"Exchange: {r['name']}  Base: {r['base']}")
        print("- Proxy env:", json.dumps(r.get('proxy', {}), ensure_ascii=False))
        print("- DNS:", json.dumps(r['dns'], ensure_ascii=False))
        print("- TCP:", json.dumps(r['tcp'], ensure_ascii=False))
        print("- TLS:", json.dumps(r['tls'], ensure_ascii=False))
        print("- HTTP checks:")
        for h in r['http']:
            print("  *", json.dumps(h, ensure_ascii=False))
        ok = r['summary']['ok']
        print(f"- SUMMARY(EN): {'OK' if ok else 'ISSUES: ' + ', '.join(r['summary']['issues'])} (mode={r['summary']['mode']})")
        print(f"  Advice: {r['summary']['advice_en']}")
        print(f"- 总结(中文): {'正常' if ok else '问题: ' + ', '.join(r['summary']['issues'])} (模式={r['summary']['mode']})")
        print(f"  建议: {r['summary']['advice_zh']}")

    print("\nTip: set OKX_BASE_URL / BP_BASE_URL to override defaults if needed.")
    print("Tip: set NET_PROBE_MODE=proxy|direct|both to control HTTP probing mode (default both).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


