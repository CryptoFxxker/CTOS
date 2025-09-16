# -*- coding: utf-8 -*-
# tests/test_bp_driver.py

import os
import sys
from pathlib import Path
from datetime import datetime

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.backpack.driver import BackpackDriver


def append_log(buf, *parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    buf.append(line)


def main():
    out_lines = []
    append_log(out_lines, "[BP] Test start:", datetime.utcnow().isoformat())

    mode = os.getenv("BP_TEST_MODE", "perp")
    symbol = os.getenv("BP_TEST_SYMBOL", "ETH_USDC_PERP" if mode == "perp" else "ETH_USDC")

    bp = BackpackDriver(mode=mode)

    append_log(out_lines, "[TEST] symbols()")
    syms, err = bp.symbols()
    append_log(out_lines, "  error:", err)
    append_log(out_lines, "  count:", len(syms) if syms else 0)
    append_log(out_lines, "  sample:", (syms or [])[:10])

    append_log(out_lines, "[TEST] get_price_now()")
    try:
        price = bp.get_price_now(symbol)
        append_log(out_lines, "  price:", price)
    except Exception as e:
        append_log(out_lines, "  error:", e)
        price = None

    append_log(out_lines, "[TEST] get_orderbook()")
    try:
        ob = bp.get_orderbook(symbol, level=5)
        append_log(out_lines, "  bids/asks:", len(ob.get('bids', [])), len(ob.get('asks', [])))
    except Exception as e:
        append_log(out_lines, "  error:", e)

    append_log(out_lines, "[TEST] get_klines()")
    k, kerr = bp.get_klines(symbol, timeframe=os.getenv("BP_TEST_TIMEFRAME", "15m"), limit=int(os.getenv("BP_TEST_LIMIT", "5")))
    append_log(out_lines, "  error:", kerr)
    try:
        import pandas as pd  # noqa
        if hasattr(k, "head"):
            append_log(out_lines, "  head:\n" + str(k.head()))
        else:
            append_log(out_lines, "  first:", (k or [])[:2])
    except Exception:
        append_log(out_lines, "  first:", (k or [])[:2] if isinstance(k, list) else k)

    append_log(out_lines, "[TEST] fees()")
    fees, ferr = bp.fees(symbol)
    append_log(out_lines, "  error:", ferr)
    append_log(out_lines, "  latest:", (fees or {}).get('latest'))

    append_log(out_lines, "[TEST] fetch_balance()")
    bal = bp.fetch_balance('USDC')
    append_log(out_lines, "  USDC:", bal)

    append_log(out_lines, "[TEST] get_open_orders()")
    oo, oerr = bp.get_open_orders(symbol)
    append_log(out_lines, "  error:", oerr)
    append_log(out_lines, "  type:", type(oo))
    append_log(out_lines, "  ", str(oo)[:300])

    append_log(out_lines, "[TEST] get_position()")
    pos_all, perr = bp.get_position()
    append_log(out_lines, "  all error:", perr)
    append_log(out_lines, "  all sample:", str(pos_all)[:300])
    pos_one, perr2 = bp.get_position(symbol)
    append_log(out_lines, "  one error:", perr2)
    append_log(out_lines, "  one:", str(pos_one)[:300])

    # 写入 README_bp.py
    readme_path = _PROJECT_ROOT / "tests" / "README_bp.py"
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write("\n")
            f.write("""
                    BP Driver Test Output Snapshot
                    --------------------------------
                    """
                    )
            for line in out_lines:
                f.write(str(line) + "\n")
        append_log(out_lines, "[BP] Wrote:", str(readme_path))
    except Exception as e:
        append_log(out_lines, "[BP] Write README_bp.py failed:", e)


if __name__ == "__main__":
    main()


