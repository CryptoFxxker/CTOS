import logging, json, time, sys, threading, atexit, queue, os
from logging.handlers import RotatingFileHandler
# 确保项目根目录在sys.path中
import os
import sys
def add_project_paths(project_name="ctos"):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    :param project_name: 项目根目录标识（默认 'ctos'）
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    # 向上回溯，找到项目根目录
    path = current_dir
    while path != os.path.dirname(path):  # 一直回溯到根目录
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")
    # 添加根目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
PROJECT_ROOT = add_project_paths()
print('PROJECT_ROOT: ', PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))


from ctos.drivers.okx.util import BeijingTime

class SystemMonitor:
    # ---------- 参数 ----------
    BATCH_SIZE   = 200       # 满 N 条落盘
    FLUSH_SEC    = 3         # 或每隔 T 秒落盘
    LOG_MAX_MB   = 5
    LOG_BACKUP   = 5

    def __init__(self, execution_engine, strategy_name='Classical'):
        self.execution_engine = execution_engine
        
        # 获取交易所名称
        cex_name = getattr(execution_engine.cex_driver, 'cex', 'UNKNOWN')
        # 创建logging目录
        log_dir = os.path.join(PROJECT_ROOT, 'ctos', 'core', 'io', 'logging')
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成带交易所名称的文件名
        base_name = f"{cex_name}_{strategy_name}"
        
        # 监控日志：滚动文件
        self.logger = logging.getLogger("SystemMonitor-" + strategy_name)
        self.logger.setLevel(logging.INFO)
        log_file = os.path.join(log_dir, f"{base_name}_system_monitor.log")
        rh = RotatingFileHandler(
            log_file,
            maxBytes=self.LOG_MAX_MB * 1024 * 1024,
            backupCount=self.LOG_BACKUP,
            encoding="utf8"
        )
        rh.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'))
        if not any(isinstance(h, RotatingFileHandler) for h in self.logger.handlers):
            self.logger.addHandler(rh)

        # ---------- 操作日志：队列 + 后台 flush ----------
        op_file_path = os.path.join(log_dir, f"{base_name}_operation_log.log")
        self.op_file = open(op_file_path, "a", buffering=1)
        self.q   = queue.Queue()
        self._stop = threading.Event()
        self.worker = threading.Thread(target=self._flush_loop, daemon=True)
        self.worker.start()
        atexit.register(self._shutdown)

    # ---------- 后台线程 ----------
    def _flush_loop(self):
        buf, last_flush = [], time.time()
        while not self._stop.is_set():
            try:
                item = self.q.get(timeout=0.5)
                buf.append(item)
            except queue.Empty:
                pass

            now = time.time()
            if len(buf) >= self.BATCH_SIZE or (buf and now - last_flush > self.FLUSH_SEC):
                self._write_batch(buf)
                buf.clear()
                last_flush = now

        # flush remaining
        if buf:
            self._write_batch(buf)

    def _write_batch(self, batch):
        try:
            self.op_file.writelines(line + "\n" for line in batch)
            self.op_file.flush()
            os.fsync(self.op_file.fileno())   # 保证落盘
        except Exception as e:
            self.logger.error("Failed batch write: %s", e)

    def _shutdown(self):
        self._stop.set()
        self.worker.join()
        self.op_file.close()

    # ---------- 对外 API ----------
    def record_operation(self, operation, source_strategy, details):
        log_entry = {
            "ts":   BeijingTime(),
            "op":   operation,
            "src":  source_strategy,
            "det":  details
        }
        # 快速入队；失败也不要阻塞
        try:
            self.q.put_nowait(json.dumps(log_entry))
        except queue.Full:
            self.logger.warning("Operation queue full; drop record")

        # 同步写监控日志（小流量）
        self.logger.info("OP %s | %s", operation, details)



    def check_api_status(self, symbol="ETH-USDT-SWAP"):
        """
        调用执行引擎的 get_price_now 接口检查 API 状态，
        并记录当前价格，如果异常，则记录错误。
        """
        try:
            price = self.execution_engine.cex_driver.get_price_now(symbol)
            if price is not None:
                msg = f"API Status OK. {symbol} 当前价格：{price}"
                self.logger.info(msg)
                return True
            else:
                msg = f"API Status Error: {symbol} 返回价格为 None"
                self.logger.error(msg)
                self.record_operation("API Status Check", "HealthMonitor", {"symbol": symbol, "price": None})
                return False
        except Exception as e:
            self.logger.error(f"API Status check exception: {e}")
            self.record_operation("API Status Exception", "HealthMonitor", {"symbol": symbol, "error": str(e)})
            return False

    def monitor_market(self, symbol="ETH-USDT-SWAP", threshold=5):
        """
        监控市场价格变化：调用执行引擎获取当前价格，
        如果与上一次记录的价格相比变化超过 threshold（百分比），则记录报警信息。
        """
        try:
            price = self.execution_engine.cex_driver.get_price_now(symbol)
            if price is None:
                self.logger.error(f"monitor_market: 无法获取 {symbol} 当前价格")
                return
            if self.last_price is None:
                self.last_price = price
                self.logger.info(f"初始 {symbol} 价格: {price}")
            else:
                change_pct = ((price - self.last_price) / self.last_price) * 100
                if abs(change_pct) >= threshold:
                    alert_msg = (f"Significant market movement for {symbol}: {change_pct:.2f}% "
                                 f"(从 {self.last_price} 到 {price})")
                    self.logger.warning(alert_msg)
                    self.record_operation("Market Movement Alert", "MarketMonitor",
                                          {"symbol": symbol, "old_price": self.last_price, "new_price": price, "change_pct": change_pct})
                # 更新 last_price
                self.last_price = price
        except Exception as e:
            self.logger.error(f"Error in monitor_market: {e}")
            self.record_operation("Market Monitor Exception", "MarketMonitor", {"symbol": symbol, "error": str(e)})

    def monitor_positions(self, symbols=['eth', 'btc'],
                          tolerance_threshold=5, pos_change_pct_thresh=50, upl_change_thresh=500):
        """
        监控多个币种的仓位：
          1. 对每个币种，通过 get_positions 获取当前仓位信息；
          2. 若与上次记录相比，持仓数量或未实现收益变化超过预设阈值（例如持仓数量变化超过 10% 或未实现收益变化超过 500），则发出异常波动警告；
          3. 同时，根据 tolerance_threshold、杠杆、最新标记价格及持仓数量计算风险，
             如果绝对未实现收益 (upl) 超过 loss_limit，则视为风险超出容忍值并记录警告。
          4. 更新 self.last_positions 保存最新监控数据。
        """
        # 初始化上次仓位记录字典
        if not hasattr(self, "last_positions"):
            self.last_positions = {}

        for coin in symbols:
            symbol = f'{coin.upper()}-USDT-SWAP'
            try:
                # 获取当前仓位信息
                pos_info = self.execution_engine.cex_driver.get_positions(symbol, show=False)
                if not pos_info:
                    self.logger.error(f"monitor_positions: 获取 {symbol} 持仓信息失败")
                    continue

                # 提取关键字段（请根据实际字段名称做相应调整）
                current_pos = float(pos_info.get("持仓数量", 0))
                current_upl = float(pos_info.get("未实现收益", 0))
                lever = float(pos_info.get("杠杆倍数", 1))
                mark_px = float(pos_info.get("最新标记价格", 0))

                # 异常波动检测：比较当前与上一次监控结果
                if symbol in self.last_positions:
                    last_record = self.last_positions[symbol]
                    last_pos = last_record.get("持仓数量", current_pos)
                    last_upl = last_record.get("未实现收益", current_upl)
                    pos_change_pct = abs(current_pos - last_pos) / (last_pos if last_pos != 0 else 1) * 100
                    upl_change = current_upl - last_upl
                    if pos_change_pct > pos_change_pct_thresh or abs(upl_change) > upl_change_thresh:
                        alert_msg = (f"{symbol} 仓位异常变动：持仓数量从 {last_pos} 变为 {current_pos} "
                                     f"(变化 {pos_change_pct:.2f}%)，未实现收益从 {last_upl} 变为 {current_upl} "
                                     f"(变化 {upl_change:.2f})")
                        self.logger.warning(alert_msg)
                        self.record_operation("Position Alert", "PositionMonitor", {
                            "symbol": symbol,
                            "last_持仓数量": last_pos,
                            "current_持仓数量": current_pos,
                            "last_未实现收益": last_upl,
                            "current_未实现收益": current_upl
                        })

                # 保存当前监控数据
                self.last_positions[symbol] = {"持仓数量": current_pos, "未实现收益": current_upl}

                # 基于 tolerance_threshold 检查风险
                risk_factor = tolerance_threshold * lever
                if risk_factor <= 100:
                    loss_limit = tolerance_threshold * 0.01 * mark_px * current_pos
                    if abs(current_upl) > loss_limit:
                        risk_msg = (f"{symbol} 风险超出容忍度：未实现收益 {current_upl} 超过损失限额 {loss_limit:.2f}")
                        self.logger.warning(risk_msg)
                        self.record_operation("Risk Alert", "PositionMonitor", {
                            "symbol": symbol,
                            "未实现收益": current_upl,
                            "损失限额": loss_limit
                        })
                        # 此处可补充自动止损操作，如调用 self.execution_engine.place_order("stop", ...)
                    else:
                        self.logger.info(f"{symbol} 持仓风险在容忍范围内。")
                else:
                    err_msg = (f"{symbol} 风险管理错误：tolerance_threshold * 杠杆 = {risk_factor} 超过允许上限")
                    self.logger.error(err_msg)
                    self.record_operation("Risk Alert", "PositionMonitor",
                                          {"symbol": symbol, "risk_factor": risk_factor})
            except Exception as e:
                self.logger.error(f"Error in monitor_positions for {symbol}: {e}")
                self.record_operation("Position Monitor Exception", "PositionMonitor",
                                      {"symbol": symbol, "error": str(e)})


    def handle_error(self, error_msg, context=""):
        """
        错误处理：记录错误日志及详细信息
        """
        self.logger.error(f"Error in {context}: {error_msg}")
        self.record_operation("Error", context, {"error": error_msg})



if __name__ == '__main__':
    # from ExecutionEngine import ExecutionEngine
    pass

