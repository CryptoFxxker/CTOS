# -*- coding: utf-8 -*-
# MACD 策略：通过加载外部配置文件，对不同交易所、不同币种、不同周期计算 MACD，
# 以经典金叉（DIF 上穿 DEA）买入、死叉（DIF 下穿 DEA）卖出。K 线来自 get_klines。

import os
import sys
import time
import json

def add_project_paths(project_name="ctos"):
    """自动查找项目根目录并加入 sys.path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = current_dir
    while path != os.path.dirname(path):
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            if path not in sys.path:
                sys.path.insert(0, path)
            return path
        path = os.path.dirname(path)
    raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")

add_project_paths()

from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime

current_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(current_dir, "macd_strategy_config.json")
state_file = os.path.join(current_dir, "macd_strategy_state.json")


def load_strategy_config():
    """加载策略配置，支持热更新"""
    default_config = {
        "check_interval": 60,
        "kline_limit": 200,
        "dry_run": True,
        "description": "MACD策略：金叉买入、死叉卖出，支持多交易所、多币种、多周期",
        "rules": [],
    }
    default_rule = {
        "id": "",
        "exchange": "okx",
        "account_id": 0,
        "symbol": "btc",
        "timeframe": "1h",
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "golden_cross_buy": True,
        "death_cross_sell": True,
        "order_amount": 100.0,
        "enabled": True,
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            for k, v in default_config.items():
                if k not in config:
                    config[k] = v
            for r in config.get("rules", []):
                for k, v in default_rule.items():
                    if k not in r:
                        r[k] = v
            print(f"✓ 加载策略配置: {config_file}")
            return config
        except Exception as e:
            print(f"✗ 加载策略配置失败: {e}，使用默认配置")
            return default_config
    else:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        print(f"✓ 已创建默认配置: {config_file}")
        return default_config


def load_state():
    """加载 DIF/DEA 相对关系 (above/below)，用于去重"""
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_relation": {}, "last_update": None}


def save_state(state):
    try:
        state["last_update"] = int(time.time() * 1000)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"✗ 保存状态失败: {e}")


def klines_to_closes(raw):
    """将 get_klines 的 raw 转为 [最新, ..., 最旧] 的 close 列表。支持 DataFrame 或 list。"""
    if raw is None:
        return []
    if hasattr(raw, "columns") and hasattr(raw, "iloc") and "close" in raw.columns:
        try:
            return [float(x) for x in raw["close"]]
        except (TypeError, ValueError):
            pass
        return []
    if isinstance(raw, list):
        out = []
        for x in raw:
            if isinstance(x, dict):
                c = x.get("close") or x.get("c")
                if c is not None:
                    try:
                        out.append(float(c))
                    except (TypeError, ValueError):
                        pass
            elif isinstance(x, (list, tuple)) and len(x) >= 5:
                try:
                    out.append(float(x[4]))
                except (TypeError, ValueError, IndexError):
                    pass
        return out
    return []


def compute_ema(series, period):
    """
    series: [最旧, ..., 最新]，返回同长的 EMA 序列。
    EMA[i] = α * series[i] + (1-α) * EMA[i-1], α = 2/(period+1)
    """
    if not series or period < 1:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(series[0])]
    for i in range(1, len(series)):
        try:
            v = float(series[i])
        except (TypeError, ValueError):
            v = out[-1]
        out.append(alpha * v + (1.0 - alpha) * out[-1])
    return out


def compute_macd(closes_asc, fast=12, slow=26, signal=9):
    """
    closes_asc: [最旧, ..., 最新]
    返回 (dif_list, dea_list)，与 closes_asc 等长；不足时返回 ([], [])
    """
    if not closes_asc or len(closes_asc) < slow + signal:
        return [], []
    ema_fast = compute_ema(closes_asc, fast)
    ema_slow = compute_ema(closes_asc, slow)
    dif = [ema_fast[i] - ema_slow[i] for i in range(len(closes_asc))]
    dea = compute_ema(dif, signal)
    return dif, dea


def get_engine_for_rule(engines_cache, rule):
    key = (rule["exchange"].lower(), int(rule.get("account_id", 0)))
    if key not in engines_cache:
        try:
            _, engine = pick_exchange(
                rule["exchange"],
                rule.get("account_id", 0),
                strategy="MACD_STRATEGY",
                strategy_detail="COMMON",
            )
            engines_cache[key] = engine
        except Exception as e:
            print(f"{BeijingTime()} ✗ 初始化 {rule['exchange']}-{rule.get('account_id', 0)} 失败: {e}")
            return None
    return engines_cache[key]


def run_rule(engine, rule, config, state):
    """
    执行单条规则：get_klines -> 算 DIF/DEA -> 金叉/死叉 -> 可选下单。
    返回 (signal_str|None, error|None)
    """
    rule_id = rule.get("id") or f"{rule['exchange']}_{rule.get('account_id',0)}_{rule['symbol']}_{rule['timeframe']}"
    if not rule.get("enabled", True):
        return None, None

    driver = getattr(engine, "cex_driver", None)
    if not driver or not hasattr(driver, "get_klines"):
        return None, f"交易所 {rule['exchange']} 驱动不支持 get_klines"

    symbol = rule["symbol"]
    tf = rule["timeframe"]
    fast = int(rule.get("fast", 12))
    slow = int(rule.get("slow", 26))
    sig_per = int(rule.get("signal", 9))
    limit = max(int(config.get("kline_limit", 200)), slow + sig_per + 10)

    raw, err = driver.get_klines(symbol=symbol, timeframe=tf, limit=limit)
    if err:
        return None, f"get_klines({symbol},{tf}) 失败: {err}"

    closes = klines_to_closes(raw)
    # 转为 [最旧, ..., 最新] 以便 EMA 顺序计算
    closes_asc = list(reversed(closes))
    dif, dea = compute_macd(closes_asc, fast, slow, sig_per)
    if len(dif) < 2 or len(dea) < 2:
        return None, f"K线不足: need>{slow}+{sig_per}+2, got {len(closes)}"

    # 最新两根：当前、上一根
    dif_curr, dif_prev = dif[-1], dif[-2]
    dea_curr, dea_prev = dea[-1], dea[-2]
    last_relation = state.get("last_relation", {})
    prev_relation = last_relation.get(rule_id)

    # 金叉：上一根 DIF<DEA，当前 DIF>DEA -> 买
    golden = (
        rule.get("golden_cross_buy", True)
        and (prev_relation == "below" or prev_relation is None)
        and dif_prev < dea_prev
        and dif_curr > dea_curr
    )
    # 死叉：上一根 DIF>DEA，当前 DIF<DEA -> 卖
    death = (
        rule.get("death_cross_sell", True)
        and (prev_relation == "above" or prev_relation is None)
        and dif_prev > dea_prev
        and dif_curr < dea_curr
    )

    # 更新 DIF 相对 DEA 关系，避免同一根K线内重复信号
    if dif_curr >= dea_curr:
        new_relation = "above"
    else:
        new_relation = "below"
    last_relation[rule_id] = new_relation
    state["last_relation"] = last_relation

    dry = config.get("dry_run", True)
    amount = float(rule.get("order_amount", 100.0))
    curr_close = closes[0] if closes else 0.0

    if golden:
        side = "buy"
        msg = f"金叉(买) {symbol} {tf} MACD({fast},{slow},{sig_per}) | DIF={dif_curr:.6f} DEA={dea_curr:.6f} 价={curr_close:.4f}"
        if not dry:
            oid, err = engine.place_incremental_orders(amount, symbol, side, soft=True)
            if err:
                return None, f"下单失败: {err}"
            return msg, None
        return f"[dry_run] {msg}", None

    if death:
        side = "sell"
        msg = f"死叉(卖) {symbol} {tf} MACD({fast},{slow},{sig_per}) | DIF={dif_curr:.6f} DEA={dea_curr:.6f} 价={curr_close:.4f}"
        if not dry:
            oid, err = engine.place_incremental_orders(amount, symbol, side, soft=True)
            if err:
                return None, f"下单失败: {err}"
            return msg, None
        return f"[dry_run] {msg}", None

    return None, None


if __name__ == "__main__":
    config = load_strategy_config()
    state = load_state()
    last_config_mtime = os.path.getmtime(config_file) if os.path.exists(config_file) else 0
    engines_cache = {}

    print("🚀 MACD 策略启动")
    print(f"   配置: {config_file}")
    print(f"   dry_run: {config.get('dry_run', True)}")
    print(f"   规则数: {len([r for r in config.get('rules', []) if r.get('enabled', True)])}")

    try:
        while True:
            if os.path.exists(config_file):
                mtime = os.path.getmtime(config_file)
                if mtime != last_config_mtime:
                    print(f"{BeijingTime()} 🔄 检测到配置文件变更，重新加载...")
                    config = load_strategy_config()
                    last_config_mtime = mtime

            for rule in config.get("rules", []):
                if not rule.get("enabled", True):
                    continue
                engine = get_engine_for_rule(engines_cache, rule)
                if not engine:
                    continue
                sig, err = run_rule(engine, rule, config, state)
                if err:
                    print(f"{BeijingTime()} ⚠️ [{rule.get('id','')}] {err}")
                elif sig:
                    print(f"{BeijingTime()} 🎯 {sig}")
            save_state(state)

            interval = int(config.get("check_interval", 60))
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{BeijingTime()} ⏹️ 手动停止")
        save_state(state)
        sys.exit(0)
    except Exception as e:
        print(f"\n{BeijingTime()} ❌ 异常: {e}")
        import traceback

        traceback.print_exc()
        save_state(state)
        sys.exit(1)
