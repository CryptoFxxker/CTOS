# -*- coding: utf-8 -*-
# 均线策略：通过加载外部策略配置文件，对不同交易所、不同币种、不同周期的均线突破与击穿判断买卖点
# 均线数据来自 get_klines

import os
import sys
import time
import json
from pathlib import Path

def add_project_paths(project_name="ctos"):
    """自动查找项目根目录，并将其及常见子包路径添加到 sys.path"""
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

_PROJECT_ROOT = add_project_paths()

from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime

# 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(current_dir, "ma_strategy_config.json")
state_file = os.path.join(current_dir, "ma_strategy_state.json")


def load_strategy_config():
    """加载策略配置，支持从外部文件热更新"""
    default_config = {
        "check_interval": 60,
        "kline_limit": 200,
        "dry_run": True,
        "description": "均线策略：基于不同交易所、币种、周期的均线突破与击穿产生买卖信号",
        "rules": [],
    }
    default_rule = {
        "id": "",
        "exchange": "okx",
        "account_id": 0,
        "symbol": "btc",
        "timeframe": "1h",
        "ma_period": 20,
        "breakthrough_buy": True,
        "breakdown_sell": True,
        "order_amount": 100.0,
        "enabled": True,
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
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
    """加载均线状态（上根K线价格相对均线：above/below），用于检测突破/击穿"""
    default = {"last_relation": {}, "last_update": None}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_state(state):
    """保存均线状态"""
    try:
        state["last_update"] = int(time.time() * 1000)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"✗ 保存状态失败: {e}")


def klines_to_closes(raw):
    """
    将 get_klines 的 raw 转为从新到旧的 close 列表。
    支持: DataFrame (columns: trade_date, open, high, low, close, vol1, vol) 或 list[dict]。
    OKX okex.get_kline 返回 DataFrame，driver 直接透传。
    """
    if raw is None:
        return []
    # DataFrame（OKX driver 透传 okex.get_kline 的 DataFrame）
    if hasattr(raw, "columns") and hasattr(raw, "iloc"):
        if "close" in raw.columns:
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


def compute_ma(closes, period):
    """closes 从新到旧 [c0=最新, c1, ...]，返回 (当前MA, 上一根MA) 或 (None, None)"""
    if not closes or len(closes) < period + 1:
        return None, None
    # 当前: 最近 period 根
    curr = sum(closes[:period]) / period
    # 上一根: 从 closes[1] 开始的 period 根
    prev = sum(closes[1 : period + 1]) / period
    return curr, prev


def get_engine_for_rule(engines_cache, rule):
    """按 (exchange, account_id) 缓存 engine，供规则复用"""
    key = (rule["exchange"].lower(), int(rule.get("account_id", 0)))
    if key not in engines_cache:
        try:
            _, engine = pick_exchange(
                rule["exchange"],
                rule.get("account_id", 0),
                strategy="MA_STRATEGY",
                strategy_detail="COMMON",
            )
            engines_cache[key] = engine
        except Exception as e:
            print(f"{BeijingTime()} ✗ 初始化 {rule['exchange']}-{rule.get('account_id', 0)} 失败: {e}")
            return None
    return engines_cache[key]


def run_rule(engine, rule, config, state):
    """
    执行单条规则：get_klines -> 算均线 -> 判断突破/击穿 -> 可选下单，更新 state。
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
    period = int(rule.get("ma_period", 20))
    limit = max(int(config.get("kline_limit", 200)), period + 10)

    raw, err = driver.get_klines(symbol=symbol, timeframe=tf, limit=limit)
    if err:
        return None, f"get_klines({symbol},{tf}) 失败: {err}"
    closes = klines_to_closes(raw)
    curr_ma, prev_ma = compute_ma(closes, period)
    if curr_ma is None or prev_ma is None:
        return None, f"K线不足: need>{period}+1, got {len(closes)}"

    curr_close = closes[0]
    prev_close = closes[1]
    last_relation = state.get("last_relation", {})
    prev_relation = last_relation.get(rule_id)

    # 突破：上一根在均线下方，当前收在均线上方 -> 买
    # 击穿：上一根在均线上方，当前收在均线下方 -> 卖
    breakthrough = (
        rule.get("breakthrough_buy", True)
        and (prev_relation == "below" or prev_relation is None)
        and prev_close < prev_ma
        and curr_close > curr_ma
    )
    breakdown = (
        rule.get("breakdown_sell", True)
        and (prev_relation == "above" or prev_relation is None)
        and prev_close > prev_ma
        and curr_close < curr_ma
    )

    # 更新当前关系（用于下一轮判断，避免重复信号）
    if curr_close >= curr_ma:
        new_relation = "above"
    else:
        new_relation = "below"
    last_relation[rule_id] = new_relation
    state["last_relation"] = last_relation

    dry = config.get("dry_run", True)
    amount = float(rule.get("order_amount", 100.0))

    if breakthrough:
        side = "buy"
        sig = f"突破(买) {symbol} {tf} MA{period} | 现价{curr_close:.4f} 均线{curr_ma:.4f}"
        if not dry:
            oid, err = engine.place_incremental_orders(amount, symbol, side, soft=True)
            if err:
                return None, f"下单失败: {err}"
            return sig, None
        return f"[dry_run] {sig}", None

    if breakdown:
        side = "sell"
        sig = f"击穿(卖) {symbol} {tf} MA{period} | 现价{curr_close:.4f} 均线{curr_ma:.4f}"
        if not dry:
            oid, err = engine.place_incremental_orders(amount, symbol, side, soft=True)
            if err:
                return None, f"下单失败: {err}"
            return sig, None
        return f"[dry_run] {sig}", None

    return None, None


if __name__ == "__main__":
    default_strategy = "MA_STRATEGY"
    config = load_strategy_config()
    state = load_state()
    last_config_mtime = os.path.getmtime(config_file) if os.path.exists(config_file) else 0
    engines_cache = {}

    print("🚀 均线策略启动")
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
