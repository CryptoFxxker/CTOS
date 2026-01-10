# -*- coding: utf-8 -*-
"""
quote_tg_bot.py
Public-only quote + Telegram alerts
- OKX: public REST ticker
- Backpack: existing BackpackDriver (public ticker)
"""

import os
import sys
import time
import io
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional, Tuple

import requests


# =============================================================================
# 1) 你要改的参数都放这里（集中配置）
# =============================================================================

# --- Telegram 配置（直接写死在程序里）---
TG_BOT_TOKEN = "8546519918:AAGL5Wq2yaHhQ2kRpKsLp9LNC2GLdo1zUnE"   # <- 替换成你的 token
TG_CHAT_ID = "-5096794764"                               # <- 私聊是正数；群一般是 -100xxxx

# --- 行情标的 ---
OKX_INST_ID = "XAUT-USDT-SWAP"
BP_SYMBOL = "PAXG_USDC_PERP"

# --- 轮询与网络 ---
INTERVAL_SEC = 5          # 每次拉取行情的间隔（秒）
TIMEOUT_SEC = 10          # HTTP 超时（秒）
DISABLE_PROXY = True      # 建议 True，避免你之前 socks/proxy 的坑

# --- 触发阈值（你要的“大于多少、小于多少推送”）---
SPREAD_HIGH_USD = 18.0    # 价差 > 18 触发
SPREAD_LOW_USD = 10.0     # 价差 < 10 触发

# --- 持续触发时重复推送间隔 ---
REPEAT_MIN = 10           # 持续 >18 或持续 <10，每 10 分钟再推一次


# =============================================================================
# 2) 基础工具
# =============================================================================

def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


# =============================================================================
# 3) OKX Public Client（绕开 OkxDriver / okex.py 的红字）
# =============================================================================

class OkxPublicClient:
    def __init__(self, timeout_sec: int = 10, disable_proxy: bool = True):
        self.timeout_sec = timeout_sec
        self.sess = requests.Session()
        if disable_proxy:
            self.sess.trust_env = False
            self.sess.proxies = {}

    def get_last(self, inst_id: str) -> float:
        url = "https://www.okx.com/api/v5/market/ticker"
        r = self.sess.get(url, params={"instId": inst_id}, timeout=self.timeout_sec)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0" or not j.get("data"):
            raise RuntimeError(f"OKX bad response: {j}")
        return float(j["data"][0]["last"])


# =============================================================================
# 4) Backpack Driver 初始化（静音，不改 driver）
# =============================================================================

def init_bp_driver_silent():
    from ctos.drivers.backpack.driver import BackpackDriver
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        bp = BackpackDriver(mode="perp", account_id=0)
    return bp


# =============================================================================
# 5) Telegram 推送
# =============================================================================

class TgNotifier:
    def __init__(self, token: str, chat_id: str, timeout_sec: int = 10, disable_proxy: bool = True):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip()
        self.timeout_sec = timeout_sec
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.sess = requests.Session()
        if disable_proxy:
            self.sess.trust_env = False
            self.sess.proxies = {}

    def send(self, text: str) -> Tuple[bool, Optional[str]]:
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            }
            r = self.sess.post(self.url, json=payload, timeout=self.timeout_sec)
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                return False, f"TG not ok: {j}"
            return True, None
        except Exception as e:
            return False, repr(e)


# =============================================================================
# 6) 告警状态机：首次触发立即推；持续触发每 10 分钟推一次
# =============================================================================

class AlertState:
    # condition: "HIGH" / "LOW" / None
    def __init__(self):
        self.condition: Optional[str] = None
        self.last_sent_ts: Optional[float] = None

    def reset(self):
        self.condition = None
        self.last_sent_ts = None

    def should_send(self, new_condition: Optional[str], repeat_sec: int, now: float) -> bool:
        # 回到正常区间：重置
        if new_condition is None:
            self.reset()
            return False

        # 新进入某个触发条件：立即推
        if self.condition != new_condition:
            self.condition = new_condition
            self.last_sent_ts = now
            return True

        # 同一条件持续：按 repeat_sec 间隔推
        if self.last_sent_ts is None:
            self.last_sent_ts = now
            return True

        if now - self.last_sent_ts >= repeat_sec:
            self.last_sent_ts = now
            return True

        return False


def format_alert(ts: str, xaut: float, paxg: float, spread: float, cond: str) -> str:
    # 只推你要的 3 个参数：XAUT、PAXG、Spread
    tag = "🔺" if cond == "HIGH" else "🔻"
    return (
        f"{tag} Spread Alert  [{ts}]\n"
        f"XAUT: {xaut:.4f}\n"
        f"PAXG: {paxg:.4f}\n"
        f"SPREAD (PAXG - XAUT): {spread:.4f}"
    )


# =============================================================================
# 7) 主程序
# =============================================================================

def main():
    # ---- 基本保护：你忘了填 token/chat_id 就直接报错退出 ----
    if "xxxxxxxx" in TG_BOT_TOKEN or not TG_BOT_TOKEN.strip():
        print("请在程序开头把 TG_BOT_TOKEN 替换成你自己的 token", flush=True)
        return
    if not str(TG_CHAT_ID).strip():
        print("请在程序开头把 TG_CHAT_ID 替换成你自己的 chat id", flush=True)
        return

    # ---- proxy off（再保险）----
    if DISABLE_PROXY:
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
            os.environ.pop(k, None)

    # ---- 确保能 import ctos ----
    THIS = Path(__file__).resolve()
    PROJECT_ROOT = THIS.parents[1]  # if located in CTOS/tests/
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    repeat_sec = REPEAT_MIN * 60

    print(f">>> RUNNING: {__file__}", flush=True)
    print(f"Monitor: OKX({OKX_INST_ID}) vs BP({BP_SYMBOL}) | poll={INTERVAL_SEC}s", flush=True)
    print(f"Rules: spread > {SPREAD_HIGH_USD} OR spread < {SPREAD_LOW_USD} | repeat={REPEAT_MIN}min", flush=True)
    print("=" * 80, flush=True)

    okx = OkxPublicClient(timeout_sec=TIMEOUT_SEC, disable_proxy=DISABLE_PROXY)
    bp = init_bp_driver_silent()
    tg = TgNotifier(token=TG_BOT_TOKEN, chat_id=TG_CHAT_ID, timeout_sec=TIMEOUT_SEC, disable_proxy=DISABLE_PROXY)

    state = AlertState()

    # 启动提示（可删）
    ok, err = tg.send(f"✅ Quote bot started\nOKX={OKX_INST_ID}\nBP={BP_SYMBOL}\nHIGH>{SPREAD_HIGH_USD} LOW<{SPREAD_LOW_USD} repeat={REPEAT_MIN}min")
    if not ok:
        print("TG startup send failed:", err, flush=True)

    while True:
        t0 = time.time()
        ts = now_ts()

        # --- fetch OKX ---
        okx_px = None
        try:
            okx_px = okx.get_last(OKX_INST_ID)
        except Exception as e:
            print(f"[{ts}] OKX fetch error: {repr(e)}", flush=True)

        # --- fetch BP ---
        bp_px = None
        try:
            bp_px = safe_float(bp.get_price_now(BP_SYMBOL))
            if bp_px is None:
                print(f"[{ts}] BP price None (check symbol={BP_SYMBOL})", flush=True)
        except Exception as e:
            print(f"[{ts}] BP fetch error: {repr(e)}", flush=True)

        if okx_px is None or bp_px is None:
            time.sleep(INTERVAL_SEC)
            continue

        spread = bp_px - okx_px

        # 条件判断（严格按你说的“大于18/小于10”）
        cond = None
        if spread > SPREAD_HIGH_USD:
            cond = "HIGH"
        elif spread < SPREAD_LOW_USD:
            cond = "LOW"

        # 控制台打印心跳（你不想看可以注释）
        print(f"[{ts}] XAUT={okx_px:.4f} | PAXG={bp_px:.4f} | spread={spread:.4f} | cond={cond}", flush=True)

        # 推送策略：首次触发立即推；持续触发每 repeat_sec 推一次
        if state.should_send(cond, repeat_sec=repeat_sec, now=t0):
            msg = format_alert(ts, okx_px, bp_px, spread, cond)
            ok, err = tg.send(msg)
            if not ok:
                print(f"[{ts}] TG send failed: {err}", flush=True)

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
