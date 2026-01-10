# DataHandler 数据处理器服务

规范化数据处理器服务，支持数据抓取和 HTTP API 服务两种模式。

## 功能特性

1. **数据同步模式**: 自动检查缺失数据，下载并更新到数据库
2. **HTTP API 服务模式**: 提供 RESTful API 接口，支持外部程序查询数据
3. **规范化存储**: 所有数据文件存储在 `storage` 文件夹下
4. **命令行参数**: 支持灵活的命令行参数配置

## 安装依赖

```bash
pip install mysql-connector-python pandas tqdm requests flask
```

## 使用方法

### 1. 数据同步模式

#### 完整同步（检查缺失 -> 下载 -> 插入）

```bash
python DataHandler.py sync --coins btc eth --intervals 1d 1h
```

#### 仅下载数据

```bash
python DataHandler.py download --coins btc eth
```

#### 仅插入数据

```bash
python DataHandler.py insert --coins btc eth
```

#### 修复表数据（补缺）

```bash
python DataHandler.py repair --coins btc eth --intervals 1m 15m 1h
```

#### 导出数据到 CSV

```bash
python DataHandler.py export --export-path ~/data/exported
```

### 2. HTTP API 服务模式

#### 启动服务

```bash
python DataHandler.py server --host 0.0.0.0 --port 5000
```

#### API 接口说明

**健康检查**
```bash
GET /health
```

**获取K线数据**
```bash
# 获取最近100条数据
GET /api/data?symbol=ETHUSDT&interval=1d&limit=100

# 获取指定日期范围的数据
GET /api/data?symbol=ETHUSDT&interval=1d&start_date=2024-01-01&end_date=2024-01-31

# 从指定日期开始获取100条数据
GET /api/data?symbol=ETHUSDT&interval=1d&start_date=2024-01-01&limit=100
```

**检查缺失数据**
```bash
GET /api/missing?coins=btc&coins=eth&intervals=1d&intervals=1h
```

**获取支持的交易对列表**
```bash
GET /api/symbols
```

## 命令行参数说明

### 同步模式参数

- `--host`: 数据库主机地址（默认: 从配置读取）
- `--database`: 数据库名（默认: TradingData）
- `--user`: 数据库用户名（默认: 从配置读取）
- `--password`: 数据库密码（默认: 从配置读取）
- `--coins`: 币种列表，如: `btc eth xrp`
- `--intervals`: 时间周期列表，如: `1m 15m 1h 4h 1d`
- `--start-date`: 起始日期，格式: YYYY-MM-DD
- `--missing-days`: 缺失日期列表
- `--export-path`: 导出数据的目标路径

### 服务模式参数

- `--host`: 服务监听地址（默认: 0.0.0.0）
- `--port`: 服务端口（默认: 5000）
- `--db-host`: 数据库主机地址
- `--db-database`: 数据库名
- `--db-user`: 数据库用户名
- `--db-password`: 数据库密码
- `--debug`: 开启调试模式

## 存储结构

所有文件存储在 `storage` 文件夹下：

```
storage/
├── data/           # 下载的原始数据文件
│   ├── 1m/
│   ├── 15m/
│   ├── 1h/
│   └── 1d/
├── cache/          # 缓存文件
│   └── start_date_cache.json
└── exported_data/  # 导出的数据（可选）
```

## 示例

### 示例1: 同步 BTC 和 ETH 的日线数据

```bash
python DataHandler.py sync sync --coins btc eth --intervals 1d
```

### 示例2: 启动 API 服务并查询数据

```bash
# 终端1: 启动服务
python DataHandler.py server --port 5000

# 终端2: 查询数据
curl "http://localhost:5000/api/data?symbol=BTCUSDT&interval=1d&limit=10"
```

### 示例3: 修复所有币种的1小时数据

```bash
python DataHandler.py sync repair --coins btc eth xrp --intervals 1h
```

## 注意事项

1. 首次运行需要确保数据库连接配置正确
2. 下载数据时会自动创建必要的目录结构
3. API 服务模式需要安装 Flask: `pip install flask`
4. 大量数据同步可能需要较长时间，请耐心等待
5. 建议在同步模式下使用后台运行或定时任务

