import logging, json, time, sys, threading, atexit, queue, os
from logging.handlers import RotatingFileHandler
# 确保项目根目录在sys.path中
import os
import sys
from datetime import datetime, timedelta

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
        log_dir = os.path.join(PROJECT_ROOT, 'core', 'io', 'logging')
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成带交易所名称的文件名
        base_name = f"{cex_name}_Account{execution_engine.account}_{strategy_name}"

        # 监控日志：滚动文件，记录时间改为北京时间

        class BeijingTimeFormatter(logging.Formatter):
            def formatTime(self, record, datefmt=None):
                # 获取UTC时间戳，转为北京时间
                dt = datetime.fromtimestamp(record.created) + timedelta(hours=8)
                if datefmt:
                    s = dt.strftime(datefmt)
                else:
                    s = dt.strftime("%Y-%m-%d %H:%M:%S")
                # 加上毫秒
                s = f"{s},{int(record.msecs):03d}"
                return s

        self.logger = logging.getLogger("SystemMonitor-" + strategy_name)
        self.logger.setLevel(logging.INFO)
        log_file = os.path.join(log_dir, f"{base_name}_system_monitor.log")
        print('log_file path: ', log_file)
        rh = RotatingFileHandler(
            log_file,
            maxBytes=self.LOG_MAX_MB * 1024 * 1024,
            backupCount=self.LOG_BACKUP,
            encoding="utf8"
        )
        # 使用自定义Formatter，时间为北京时间
        rh.setFormatter(BeijingTimeFormatter(
            '%(asctime)s - %(levelname)s - %(message)s'))
        if not any(isinstance(h, RotatingFileHandler) for h in self.logger.handlers):
            self.logger.addHandler(rh)

        # ---------- 操作日志：队列 + 后台 flush ----------
        op_file_path = os.path.join(log_dir, f"{base_name}_operation_log.log")
        self.op_file = open(op_file_path, "a", buffering=1)
        print('op_file_path path: ', op_file_path)
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



    def check_api_status(self, symbol="ETH"):
        """
        调用执行引擎的 get_price_now 接口检查 API 状态，
        并记录当前价格，如果异常，则记录错误。
        """
        try:
            symbol = self.execution_engine._norm_symbol(symbol)
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

    def monitor_positions(self, symbols=None, tolerance_threshold=20, 
                         pos_change_pct_thresh=10, upl_change_thresh=100,
                         price_change_thresh=5, auto_correct=True):
        """
        增强的仓位监控系统：
        1. 获取全部仓位信息并建立备份
        2. 监控仓位异常变化并自动纠正
        3. 监控价格异常波动
        4. 维护下单记录和预期仓位
        5. 生成详细的异常报告
        Args:
            symbols: 要监控的币种列表，None表示监控所有仓位
            tolerance_threshold: 风险容忍阈值
            pos_change_pct_thresh: 仓位变化百分比阈值
            upl_change_thresh: 未实现收益变化阈值
            price_change_thresh: 价格变化百分比阈值
            auto_correct: 是否自动纠正异常仓位
        """

        # 初始化监控数据
        if not hasattr(self, "last_positions"):
            self.last_positions = {}
        if not hasattr(self, "order_expectations"):
            self.order_expectations = {}  # 记录下单预期
        if not hasattr(self, "position_backup"):
            self.position_backup = {}
        
        # 获取交易所和账户信息
        exchange = self.execution_engine.exchange_type
        account_id = self.execution_engine.account
        
        # 1. 获取全部仓位信息
        try:
            all_positions, err = self.execution_engine.cex_driver.get_position(symbol=None, keep_origin=False)
            if err:
                self.logger.error(f"获取全部仓位失败: {err}")
                return
            
            if not all_positions:
                self.logger.info("当前无持仓")
                return
                
        except Exception as e:
            self.logger.error(f"获取仓位信息异常: {e}")
            return
        
        # 2. 加载或创建仓位备份
        backup_file = self._get_position_backup_path(exchange, account_id)
        self._load_position_backup(backup_file)
        
        # 3. 保存当前仓位备份
        self._save_position_backup(backup_file, all_positions)
        
        # 4. 处理每个仓位
        for pos in all_positions:
            try:
                self._process_position(pos, symbols, tolerance_threshold, 
                                     pos_change_pct_thresh, upl_change_thresh,
                                     price_change_thresh, auto_correct)
            except Exception as e:
                self.logger.error(f"处理仓位异常 {pos.get('symbol', 'unknown')}: {e}")
                self._record_anomaly("Position Processing Error", {
                    "symbol": pos.get('symbol', 'unknown'),
                    "error": str(e)
                })
    
    def _get_position_backup_path(self, exchange, account_id):
        """获取仓位备份文件路径"""
        import os
        logging_dir = os.path.join(os.path.dirname(__file__), '../io/logging')
        os.makedirs(logging_dir, exist_ok=True)
        return os.path.join(logging_dir, f'{exchange}_account{account_id}_position_backup.json')
    
    def _load_position_backup(self, backup_file):
        """加载仓位备份"""
        if not os.path.exists(backup_file):
            return
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 检查时间戳
            backup_time = datetime.fromisoformat(backup_data.get('timestamp', ''))
            if datetime.now() - backup_time < timedelta(minutes=10):
                self.position_backup = backup_data.get('positions', {})
                self.logger.info(f"加载仓位备份成功 (时间: {backup_time.strftime('%Y-%m-%d %H:%M:%S')})")
            else:
                self.logger.info("仓位备份已过期，将重新建立")
                
        except Exception as e:
            self.logger.warning(f"加载仓位备份失败: {e}")
    
    def _save_position_backup(self, backup_file, positions):
        """保存仓位备份"""
        try:
            backup_data = {
                'timestamp': datetime.now().isoformat(),
                'exchange': self.execution_engine.exchange_type,
                'account_id': self.execution_engine.account,
                'positions': {pos.get('symbol'): pos for pos in positions}
            }
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存仓位备份失败: {e}")
    
    def _process_position(self, pos, symbols, tolerance_threshold, 
                         pos_change_pct_thresh, upl_change_thresh,
                         price_change_thresh, auto_correct):
        """处理单个仓位"""
        symbol = pos.get('symbol', '')
        
        # 如果指定了symbols，只处理指定的币种
        if symbols:
            coin = symbol.split('-')[0].lower() if '-' in symbol else symbol.lower()
            if coin not in [s.lower() for s in symbols]:
                return
        
        # 提取仓位信息
        current_qty = float(pos.get('quantity', 0))
        current_upl = float(pos.get('pnlUnrealized', 0))
        current_realized = float(pos.get('pnlRealized', 0))
        mark_price = float(pos.get('markPrice', 0))
        entry_price = float(pos.get('entryPrice', 0))
        side = pos.get('side', '')
        leverage = float(pos.get('leverage', 1))
        quantity_usd = float(pos.get('quantityUSD', 0))
        

        # 检查仓位是否为空
        if current_qty == 0:
            return
        
        # 1. 检查价格异常波动
        self._check_price_anomaly(symbol, mark_price, price_change_thresh)
        
        # 2. 检查仓位异常变化
        self._check_position_anomaly(symbol, pos, pos_change_pct_thresh, 
                                   upl_change_thresh, auto_correct)
        
        # 3. 检查风险指标
        self._check_risk_metrics(symbol, pos, tolerance_threshold)
        
        # 4. 更新监控数据
        from datetime import datetime
        self.last_positions[symbol] = {
            'quantity': current_qty,
            'pnlUnrealized': current_upl,
            'pnlRealized': current_realized,
            'markPrice': mark_price,
            'entryPrice': entry_price,
            'side': side,
            'leverage': leverage,
            'quantityUSD': quantity_usd, 
            'timestamp': datetime.now().isoformat()
        }
    
    def _check_price_anomaly(self, symbol, current_price, threshold):
        """检查价格异常波动"""
        if symbol in self.last_positions:
            last_price = self.last_positions[symbol].get('markPrice', current_price)
            if last_price > 0:
                price_change_pct = abs(current_price - last_price) / last_price * 100
                if price_change_pct > threshold:
                    self._record_anomaly("Price Anomaly", {
                        "symbol": symbol,
                        "last_price": last_price,
                        "current_price": current_price,
                        "change_pct": price_change_pct,
                        "threshold": threshold
                    })
                    self.logger.warning(f"{symbol} 价格异常波动: {last_price:.4f} -> {current_price:.4f} ({price_change_pct:.2f}%)")
    
    def _check_position_anomaly(self, symbol, pos, pos_change_pct_thresh, 
                               upl_change_thresh, auto_correct):
        """检查仓位异常变化"""
        # 获取仓位金额，根据side添加正负号
        current_qty_usd = float(pos.get('quantityUSD', 0))
        side = pos.get('side', '')
        if side == 'short':
            current_qty_usd = -current_qty_usd  # 空头仓位为负值
        
        current_upl = float(pos.get('pnlUnrealized', 0))
        
        if symbol in self.last_positions:
            last_data = self.last_positions[symbol]
            if last_data.get('side', '') :
                last_qty_usd = last_data.get('quantityUSD', current_qty_usd) if last_data.get('side', '') == 'long' else -last_data.get('quantityUSD', current_qty_usd)
            last_upl = last_data.get('pnlUnrealized', current_upl)
            
            # 检查仓位金额变化
            if last_qty_usd != 0:
                qty_change_pct = abs(current_qty_usd - last_qty_usd) / abs(last_qty_usd) * 100
                if qty_change_pct > pos_change_pct_thresh:
                    self._record_anomaly("Position Value Anomaly", {
                        "symbol": symbol,
                        "last_quantity_usd": last_qty_usd,
                        "current_quantity_usd": current_qty_usd,
                        "change_pct": qty_change_pct,
                        "threshold": pos_change_pct_thresh,
                        "side": side
                    })
                    if auto_correct:
                        self._auto_correct_position_usd(symbol, last_qty_usd, current_qty_usd)
            
            # 检查未实现收益变化
            upl_change = abs(current_upl - last_upl)
            if upl_change > upl_change_thresh:
                self._record_anomaly("PnL Anomaly", {
                    "symbol": symbol,
                    "last_upl": last_upl,
                    "current_upl": current_upl,
                    "change": upl_change,
                    "threshold": upl_change_thresh
                })
                self.logger.warning(f"{symbol} 未实现收益异常变化: {last_upl:.2f} -> {current_upl:.2f} (变化: {upl_change:.2f})")
    
    def _auto_correct_position_usd(self, symbol, expected_qty_usd, actual_qty_usd):
        """基于USD金额自动纠正异常仓位"""
        try:
            diff_usd = expected_qty_usd - actual_qty_usd
            if abs(diff_usd) < 20:  # 忽略微小差异（1美元以下）
                return
            
            side = 'buy' if diff_usd > 0 else 'sell'
            abs_diff_usd = abs(diff_usd)
            self.logger.warning(f"自动纠正仓位 {symbol}: 预期金额 ${expected_qty_usd:.2f}, 实际金额 ${actual_qty_usd:.2f}, 差异 ${diff_usd:.2f}")
            
            # 使用ExecutionEngine下单纠正，直接使用USD金额
            result, err = self.execution_engine.place_incremental_orders(
                abs_diff_usd,
                symbol.split('-')[0],
                side,
                soft=False, # 妈的，有超出预计的变化？给爷死！ 直接打回去！去你妈的，煞笔人类不要干涉代码操作！
            )
            
            if result:
                self._record_anomaly("Auto Correction USD", {
                    "symbol": symbol,
                    "expected_quantity_usd": expected_qty_usd,
                    "actual_quantity_usd": actual_qty_usd,
                    "correction_diff_usd": diff_usd,
                    "correction_side": side,
                    "order_result": result
                })
                self.logger.info(f"仓位纠正订单已提交: {symbol} {side} ${abs_diff_usd:.2f}")
            else:
                self.logger.error(f"仓位纠正订单提交失败: {symbol}")
                
        except Exception as e:
            self.logger.error(f"自动纠正仓位失败 {symbol}: {e}")
            self._record_anomaly("Auto Correction Failed", {
                            "symbol": symbol,
                "error": str(e)
            })
    
    def _check_risk_metrics(self, symbol, pos, tolerance_threshold):
        """检查风险指标"""
        current_qty = float(pos.get('quantity', 0))
        current_upl = float(pos.get('pnlUnrealized', 0))
        mark_price = float(pos.get('markPrice', 0))
        leverage = float(pos.get('leverage', 1))
        quantity_usd = float(pos.get('quantityUSD', 0))
        side = pos.get('side', '')
        
        # 根据side添加正负号到quantityUSD
        if side == 'short':
            quantity_usd = -quantity_usd  # 空头仓位为负值
        
        # 计算风险指标
        risk_metrics = {
            "symbol": symbol,
            "quantity": current_qty,
            "pnl_unrealized": current_upl,
            "mark_price": mark_price,
            "leverage": leverage,
            "quantity_usd": quantity_usd,  # 带正负号的仓位金额
            "side": side,
            "risk_ratio": abs(current_upl) / abs(quantity_usd) if quantity_usd != 0 else 0
        }
        
        # 检查风险阈值
        if risk_metrics["risk_ratio"] > tolerance_threshold / 100:
            self._record_anomaly("Risk Threshold Exceeded", risk_metrics)
            self.logger.warning(f"{symbol} 风险比例过高: {risk_metrics['risk_ratio']:.2%} (仓位金额: ${quantity_usd:.2f})")
        

        # 检查仓位价值风险
        if abs(quantity_usd) > self.execution_engine.cex_driver.fetch_balance('USDT') * 0.5:  # 大仓位警告
            self._record_anomaly("Large Position Warning", risk_metrics)
            self.logger.warning(f"{symbol} 大仓位警告: ${quantity_usd:.2f}")
    
    def _record_anomaly(self, anomaly_type, data):
        """记录异常信息"""
        import os
        import json
        from datetime import datetime
        
        try:
            # 创建异常记录文件
            logging_dir = os.path.join(os.path.dirname(__file__), '../io/logging')
            os.makedirs(logging_dir, exist_ok=True)
            
            exchange = self.execution_engine.exchange_type
            account_id = self.execution_engine.account
            anomaly_file = os.path.join(logging_dir, f'{exchange}_account{account_id}_anomaly_report.json')
            
            # 读取现有记录
            anomalies = []
            if os.path.exists(anomaly_file):
                with open(anomaly_file, 'r', encoding='utf-8') as f:
                    anomalies = json.load(f)
            
            # 添加新记录
            anomaly_record = {
                'timestamp': datetime.now().isoformat(),
                'type': anomaly_type,
                'data': data,
                'exchange': exchange,
                'account_id': account_id
            }
            anomalies.append(anomaly_record)
            
            # 保存记录（保留最近1000条）
            if len(anomalies) > 1000:
                anomalies = anomalies[-1000:]
            
            with open(anomaly_file, 'w', encoding='utf-8') as f:
                json.dump(anomalies, f, ensure_ascii=False, indent=2)
            
            # 记录到操作日志
            self.record_operation("Anomaly Detected", "PositionMonitor", {
                "anomaly_type": anomaly_type,
                "data": data
            })
            
        except Exception as e:
            self.logger.error(f"记录异常信息失败: {e}")
    
    def get_anomaly_summary(self, hours=24):
        """获取异常汇总报告"""
        import os
        import json
        from datetime import datetime, timedelta
        
        try:
            logging_dir = os.path.join(os.path.dirname(__file__), '../io/logging')
            exchange = self.execution_engine.exchange_type
            account_id = self.execution_engine.account
            anomaly_file = os.path.join(logging_dir, f'{exchange}_account{account_id}_anomaly_report.json')
            
            if not os.path.exists(anomaly_file):
                return {"message": "无异常记录"}
            
            with open(anomaly_file, 'r', encoding='utf-8') as f:
                anomalies = json.load(f)
            
            # 筛选时间范围内的异常
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_anomalies = [
                a for a in anomalies 
                if datetime.fromisoformat(a['timestamp']) > cutoff_time
            ]
            
            # 统计异常类型
            anomaly_counts = {}
            for anomaly in recent_anomalies:
                anomaly_type = anomaly['type']
                anomaly_counts[anomaly_type] = anomaly_counts.get(anomaly_type, 0) + 1
            
            return {
                "time_range_hours": hours,
                "total_anomalies": len(recent_anomalies),
                "anomaly_types": anomaly_counts,
                "recent_anomalies": recent_anomalies[-10:]  # 最近10条
            }
            
        except Exception as e:
            self.logger.error(f"获取异常汇总失败: {e}")
            return {"error": str(e)}
    
    def start_position_monitoring(self, symbols=None, interval_minutes=1, **kwargs):
        """启动仓位监控定时任务"""
        import threading
        import time
        
        def monitoring_loop():
            while True:
                try:
                    self.logger.info("开始执行仓位监控...")
                    self.monitor_positions(symbols=symbols, **kwargs)
                    self.logger.info("仓位监控完成")
                except Exception as e:
                    self.logger.error(f"仓位监控异常: {e}")
                
                # 等待下次监控
                time.sleep(interval_minutes * 60)
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        self.logger.info(f"仓位监控已启动，监控间隔: {interval_minutes}分钟")
        return monitor_thread
    
    def stop_position_monitoring(self):
        """停止仓位监控（通过设置标志位）"""
        if hasattr(self, 'monitoring_active'):
            self.monitoring_active = False
            self.logger.info("仓位监控已停止")
    
    def get_position_summary(self):
        """获取当前仓位汇总"""
        try:
            all_positions, err = self.execution_engine.cex_driver.get_position(symbol=None, keep_origin=False)
            if err:
                return {"error": f"获取仓位失败: {err}"}
            
            if not all_positions:
                return {"message": "当前无持仓"}
            
            summary = {
                "total_positions": len(all_positions),
                "total_quantity_usd": 0,
                "total_pnl_unrealized": 0,
                "total_pnl_realized": 0,
                "positions": []
            }
            
            for pos in all_positions:
                qty_usd = float(pos.get('quantityUSD', 0))
                pnl_unrealized = float(pos.get('pnlUnrealized', 0))
                pnl_realized = float(pos.get('pnlRealized', 0))
                
                summary["total_quantity_usd"] += qty_usd
                summary["total_pnl_unrealized"] += pnl_unrealized
                summary["total_pnl_realized"] += pnl_realized
                
                summary["positions"].append({
                    "symbol": pos.get('symbol'),
                    "side": pos.get('side'),
                    "quantity": float(pos.get('quantity', 0)),
                    "quantity_usd": qty_usd,
                    "pnl_unrealized": pnl_unrealized,
                    "pnl_realized": pnl_realized,
                    "mark_price": float(pos.get('markPrice', 0)),
                    "entry_price": float(pos.get('entryPrice', 0)),
                    "leverage": float(pos.get('leverage', 1))
                })
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取仓位汇总失败: {e}")
            return {"error": str(e)}


    def handle_error(self, error_msg, context=""):
        """
        错误处理：记录错误日志及详细信息
        """
        self.logger.error(f"Error in {context}: {error_msg}")
        self.record_operation("Error", context, {"error": error_msg})



if __name__ == '__main__':
    # from ExecutionEngine import ExecutionEngine
    pass

