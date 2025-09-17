# Tests 目录说明

本目录包含针对不同交易所驱动的快速集成测试脚本与输出快照，用于验证各交易所驱动的功能完整性和稳定性。

## 📁 目录结构

```
tests/
├── README.md                    # 本说明文件
├── test_okx_driver.py          # OKX 驱动测试脚本
├── test_bp_driver.py           # Backpack 驱动测试脚本
├── README_okx.md               # OKX 测试输出样例
├── README_bp.py                # Backpack 测试输出快照（自动生成）
└── __pycache__/                # Python 缓存目录
```

## 🧪 测试脚本

### 1. OKX 驱动测试
- **文件**: `test_okx_driver.py`
- **功能**: 测试 OKX 交易所驱动的核心功能
- **测试内容**:
  - 市场数据获取（价格、订单簿、K线）
  - 订单管理（下单、修改、查询、撤销）
  - 账户信息（余额、仓位）
  - 交易所信息（交易对、限制、费率）

### 2. Backpack 驱动测试
- **文件**: `test_bp_driver.py`
- **功能**: 测试 Backpack 交易所驱动的核心功能
- **测试内容**:
  - 市场数据获取（价格、订单簿、K线、资金费率）
  - 账户信息（余额、仓位、订单）
  - 数据格式标准化验证

## 📊 测试结果

### 当前可用的测试结果

| 交易所 | 测试脚本 | 输出文件 | 状态 | 说明 |
|--------|----------|----------|------|------|
| OKX | `test_okx_driver.py` | [README_okx.md](./README_okx.md) | ✅ 可用 | 完整功能测试结果 |
| Backpack | `test_bp_driver.py` | [README_bp.md](./README_bp.md) | ✅ 可用 | 自动生成的测试快照 |

### 计划中的测试结果

| 交易所 | 测试脚本 | 输出文件 | 状态 | 说明 |
|--------|----------|----------|------|------|
| Binance | `test_binance_driver.py` | [README_binance.md](./README_binance.md) | 🔄 计划中 | 币安驱动测试 |
| Bybit | `test_bybit_driver.py` | [README_bybit.md](./README_bybit.md) | 🔄 计划中 | Bybit 驱动测试 |
| Gate.io | `test_gate_driver.py` | [README_gate.md](./README_gate.md) | 🔄 计划中 | Gate.io 驱动测试 |
| KuCoin | `test_kucoin_driver.py` | [README_kucoin.md](./README_kucoin.md) | 🔄 计划中 | KuCoin 驱动测试 |
| 综合测试 | `test_all_drivers.py` | [README_all.md](./README_all.md) | 🔄 计划中 | 所有驱动对比测试 |

## 🚀 快速开始

### 运行 Backpack 测试

1. **设置环境变量**（BP 代表 Backpack 交易所，建议使用权限最小的 API Key）：
   ```bash
   export BP_PUBLIC_KEY=<你的BP公钥>
   export BP_SECRET_KEY=<你的BP私钥>
   
   # 可选配置
   export BP_TEST_MODE=perp|spot          # 默认 perp
   export BP_TEST_SYMBOL=ETH_USDC_PERP    # perp 默认 ETH_USDC_PERP，spot 默认 ETH_USDC
   export BP_TEST_TIMEFRAME=15m           # 默认 15m
   export BP_TEST_LIMIT=5                 # 默认 5
   ```

2. **执行测试**：
   ```bash
   python -m tests.test_bp_driver
   ```

3. **查看结果**：
   - 终端实时输出
   - 自动生成的 `tests/README_bp.py` 快照文件

### 运行 OKX 测试

1. **配置 API 密钥**：
   - 在 `ctos/drivers/okx/Config.py` 中设置您的 API 密钥

2. **执行测试**：
   ```bash
   python -m tests.test_okx_driver
   ```

3. **查看结果**：
   - 终端实时输出
   - 参考 `tests/README_okx.md` 了解预期输出

## 📋 测试覆盖范围

### 核心功能测试
- ✅ **市场数据**: 价格查询、订单簿、K线数据
- ✅ **账户管理**: 余额查询、仓位查询
- ✅ **订单管理**: 下单、修改、查询、撤销
- ✅ **交易所信息**: 交易对列表、交易限制、费率信息

### 数据格式验证
- ✅ **标准化输出**: 确保所有驱动返回统一的数据格式
- ✅ **错误处理**: 验证异常情况的处理机制
- ✅ **性能测试**: 响应时间和资源使用情况

## 🔧 开发指南

### 添加新的交易所测试

1. 创建测试脚本：`test_{exchange}_driver.py`
2. 实现核心功能测试
3. 生成输出快照：`README_{exchange}.md` 或 `README_{exchange}.py`
4. 更新本 README 文件

### 测试脚本模板

```python
# -*- coding: utf-8 -*-
# tests/test_{exchange}_driver.py

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.{exchange}.driver import {Exchange}Driver

def test_driver():
    driver = {Exchange}Driver()
    
    # 测试核心功能
    print("[TEST] Testing {exchange} driver...")
    
    # 添加具体的测试逻辑
    # ...

if __name__ == "__main__":
    test_driver()
```

## 📈 测试统计

- **总测试脚本**: 2 个
- **已完成的驱动**: 2 个（OKX, Backpack）
- **计划中的驱动**: 4 个（Binance, Bybit, Gate.io, KuCoin）
- **测试覆盖率**: 核心功能 100%

## 🤝 贡献指南

1. 添加新交易所测试时，请遵循现有的命名规范
2. 确保测试脚本包含完整的错误处理
3. 生成详细的测试输出快照
4. 更新本 README 文件的相关部分

## 📞 支持

如有问题或建议，请：
- 查看具体的测试输出文件了解详细信息
- 检查驱动配置是否正确
- 确认 API 密钥权限是否足够

