# -*- coding: utf-8 -*-
# tests/test_round_like.py
# 测试round_like函数的修复

import os
import sys
from pathlib import Path

# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.okx.util import round_like


def test_round_like():
    """测试round_like函数"""
    print("测试 round_like 函数:")
    print("=" * 50)
    
    test_cases = [
        (1e-6, 0.0223456, "科学计数法精度"),
        (0.01, 0.0223456, "两位小数精度"),
        (0.0001, 0.0223456, "四位小数精度"),
        (1.0, 0.0223456, "整数精度"),
        (0.1, 0.0223456, "一位小数精度"),
        (1e-8, 0.000123456789, "极小精度"),
        (100, 123.456789, "大整数精度"),
    ]
    
    for ref, x, description in test_cases:
        try:
            result = round_like(ref, x)
            print(f"✓ {description}: round_like({ref}, {x}) = {result}")
        except Exception as e:
            print(f"❌ {description}: round_like({ref}, {x}) 失败 - {e}")
    
    print("=" * 50)
    print("测试完成!")


if __name__ == '__main__':
    test_round_like()
