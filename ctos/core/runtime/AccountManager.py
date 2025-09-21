#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AccountManager - Driver实例管理器
负责管理不同交易所的Driver实例，为runtime组件提供统一的Driver访问接口

核心思路：
- Driver实例：具体交易所的适配器（负责和OKX/BP API通信）
- ExecutionEngine等runtime：策略友好的"场景层"，通过AccountManager获取driver
- 避免直接new driver，统一管理Driver生命周期
"""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Union, Any
from enum import Enum

# 确保项目根目录在sys.path中
def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bpx_path = os.path.join(current_dir, 'bpx')
    if bpx_path not in sys.path:
        sys.path.insert(0, bpx_path)
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
# 执行路径添加
_add_bpx_path()

import logging


class ExchangeType(Enum):
    """支持的交易所类型"""
    OKX = "okx"
    BACKPACK = "backpack"
    BINANCE = "binance"  # 预留


class DriverStatus(Enum):
    """Driver状态"""
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class DriverInfo:
    """Driver信息封装"""
    def __init__(self, driver, exchange_type: ExchangeType, account_id: int = 0, 
                 status: DriverStatus = DriverStatus.INITIALIZING):
        self.driver = driver
        self.exchange_type = exchange_type
        self.account_id = account_id
        self.status = status
        self.created_at = time.time()
        self.last_used = time.time()
        self.error_count = 0
        self.last_error = None

    def update_usage(self):
        """更新使用时间"""
        self.last_used = time.time()

    def mark_error(self, error_msg: str):
        """标记错误"""
        self.error_count += 1
        self.last_error = error_msg
        self.status = DriverStatus.ERROR

    def mark_ready(self):
        """标记为就绪"""
        self.status = DriverStatus.READY
        self.error_count = 0
        self.last_error = None

    def is_healthy(self, max_error_count: int = 5, timeout_seconds: int = 300) -> bool:
        """检查Driver是否健康"""
        if self.status == DriverStatus.ERROR and self.error_count >= max_error_count:
            return False
        if time.time() - self.last_used > timeout_seconds:
            return False
        return True


class AccountManager:
    """
    Driver实例管理器
    负责创建、管理和提供不同交易所的Driver实例
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化AccountManager
        
        Args:
            config: 配置字典，包含各交易所的配置信息
        """
        self.config = config or {}
        self._drivers: Dict[str, DriverInfo] = {}  # key: f"{exchange_type}_{account_id}"
        self._lock = threading.RLock()
        self.logger = self._setup_logger()
        
        # 默认配置
        self.default_config = {
            'okx': {
                'account_ids': [0],
                'auto_reconnect': True,
                'max_retries': 3,
                'timeout': 30
            },
            'backpack': {
                'account_ids': [0],
                'auto_reconnect': True,
                'max_retries': 3,
                'timeout': 30
            }
        }
        
        # 合并配置
        self._merge_config()
        
        self.logger.info("AccountManager initialized")

    def _setup_logger(self) -> logging.Logger:
        """设置日志器"""
        logger = logging.getLogger('AccountManager')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _merge_config(self):
        """合并配置"""
        for exchange, default_config in self.default_config.items():
            if exchange not in self.config:
                self.config[exchange] = default_config
            else:
                # 合并配置
                for key, value in default_config.items():
                    if key not in self.config[exchange]:
                        self.config[exchange][key] = value

    def _get_driver_key(self, exchange_type: ExchangeType, account_id: int = 0) -> str:
        """生成Driver的唯一标识"""
        return f"{exchange_type.value}_{account_id}"

    def _create_okx_driver(self, account_id: int = 0) -> Optional[Any]:
        """创建OKX Driver"""
        try:
            # 添加项目根目录到sys.path
            import sys
            from pathlib import Path
            _THIS_FILE = Path(__file__).resolve()
            _PROJECT_ROOT = _THIS_FILE.parents[2]
            if str(_PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(_PROJECT_ROOT))
            
            from ctos.drivers.okx.driver import OkxDriver, init_OkxClient
            
            # 初始化OKX客户端
            okx_client = init_OkxClient(account=account_id)
            if not okx_client:
                self.logger.error(f"Failed to initialize OKX client for account {account_id}")
                return None
                
            driver = OkxDriver(okx_client=okx_client)
            self.logger.info(f"OKX Driver created for account {account_id}")
            return driver
            
        except Exception as e:
            self.logger.error(f"Failed to create OKX Driver for account {account_id}: {e}")
            return None

    def _create_backpack_driver(self, account_id: int = 0) -> Optional[Any]:
        """创建Backpack Driver"""
        try:
            # 添加项目根目录到sys.path
            from ctos.drivers.backpack.driver import BackpackDriver
            driver = BackpackDriver(account_id=account_id)
            self.logger.info(f"Backpack Driver created for account {account_id}")
            return driver
            
        except Exception as e:
            self.logger.error(f"Failed to create Backpack Driver for account {account_id}: {e}")
            return None

    def _create_driver(self, exchange_type: ExchangeType, account_id: int = 0) -> Optional[Any]:
        """创建指定类型的Driver"""
        if exchange_type == ExchangeType.OKX:
            return self._create_okx_driver(account_id)
        elif exchange_type == ExchangeType.BACKPACK:
            return self._create_backpack_driver(account_id)
        else:
            self.logger.error(f"Unsupported exchange type: {exchange_type}")
            return None

    def get_driver(self, exchange_type: Union[ExchangeType, str], account_id: int = 0, 
                   auto_create: bool = True) -> Optional[Any]:
        """
        获取Driver实例
        
        Args:
            exchange_type: 交易所类型
            account_id: 账户ID
            auto_create: 是否自动创建Driver（如果不存在）
            
        Returns:
            Driver实例或None
        """
        if isinstance(exchange_type, str):
            try:
                exchange_type = ExchangeType(exchange_type.lower())
            except ValueError:
                self.logger.error(f"Invalid exchange type: {exchange_type}")
                return None

        driver_key = self._get_driver_key(exchange_type, account_id)
        
        with self._lock:
            # 检查是否已存在
            if driver_key in self._drivers:
                driver_info = self._drivers[driver_key]
                
                # 检查Driver是否健康
                if driver_info.is_healthy():
                    driver_info.update_usage()
                    return driver_info.driver
                else:
                    # Driver不健康，尝试重新创建
                    self.logger.warning(f"Driver {driver_key} is not healthy, attempting to recreate")
                    del self._drivers[driver_key]
            
            # 如果不存在且允许自动创建
            if auto_create:
                driver = self._create_driver(exchange_type, account_id)
                if driver:
                    driver_info = DriverInfo(driver, exchange_type, account_id, DriverStatus.READY)
                    self._drivers[driver_key] = driver_info
                    self.logger.info(f"Driver {driver_key} created and ready")
                    return driver
                else:
                    self.logger.error(f"Failed to create driver {driver_key}")
            
            return None

    def create_driver(self, exchange_type: Union[ExchangeType, str], account_id: int = 0) -> bool:
        """
        显式创建Driver实例
        
        Args:
            exchange_type: 交易所类型
            account_id: 账户ID
            
        Returns:
            是否创建成功
        """
        if isinstance(exchange_type, str):
            try:
                exchange_type = ExchangeType(exchange_type.lower())
            except ValueError:
                self.logger.error(f"Invalid exchange type: {exchange_type}")
                return False

        driver_key = self._get_driver_key(exchange_type, account_id)
        
        with self._lock:
            if driver_key in self._drivers:
                self.logger.warning(f"Driver {driver_key} already exists")
                return True
            
            driver = self._create_driver(exchange_type, account_id)
            if driver:
                driver_info = DriverInfo(driver, exchange_type, account_id, DriverStatus.READY)
                self._drivers[driver_key] = driver_info
                self.logger.info(f"Driver {driver_key} created successfully")
                return True
            else:
                self.logger.error(f"Failed to create driver {driver_key}")
                return False

    def remove_driver(self, exchange_type: Union[ExchangeType, str], account_id: int = 0) -> bool:
        """
        移除Driver实例
        
        Args:
            exchange_type: 交易所类型
            account_id: 账户ID
            
        Returns:
            是否移除成功
        """
        if isinstance(exchange_type, str):
            try:
                exchange_type = ExchangeType(exchange_type.lower())
            except ValueError:
                self.logger.error(f"Invalid exchange type: {exchange_type}")
                return False

        driver_key = self._get_driver_key(exchange_type, account_id)
        
        with self._lock:
            if driver_key in self._drivers:
                del self._drivers[driver_key]
                self.logger.info(f"Driver {driver_key} removed")
                return True
            else:
                self.logger.warning(f"Driver {driver_key} not found")
                return False

    def get_all_drivers(self) -> Dict[str, DriverInfo]:
        """获取所有Driver信息"""
        with self._lock:
            return self._drivers.copy()

    def get_driver_status(self, exchange_type: Union[ExchangeType, str], account_id: int = 0) -> Optional[DriverStatus]:
        """获取Driver状态"""
        if isinstance(exchange_type, str):
            try:
                exchange_type = ExchangeType(exchange_type.lower())
            except ValueError:
                return None

        driver_key = self._get_driver_key(exchange_type, account_id)
        
        with self._lock:
            if driver_key in self._drivers:
                return self._drivers[driver_key].status
            return None

    def mark_driver_error(self, exchange_type: Union[ExchangeType, str], account_id: int = 0, 
                         error_msg: str = "Unknown error") -> bool:
        """标记Driver错误"""
        if isinstance(exchange_type, str):
            try:
                exchange_type = ExchangeType(exchange_type.lower())
            except ValueError:
                return False

        driver_key = self._get_driver_key(exchange_type, account_id)
        
        with self._lock:
            if driver_key in self._drivers:
                self._drivers[driver_key].mark_error(error_msg)
                self.logger.warning(f"Driver {driver_key} marked with error: {error_msg}")
                return True
            return False

    def cleanup_unhealthy_drivers(self, max_error_count: int = 5, timeout_seconds: int = 300):
        """清理不健康的Driver"""
        with self._lock:
            to_remove = []
            for driver_key, driver_info in self._drivers.items():
                if not driver_info.is_healthy(max_error_count, timeout_seconds):
                    to_remove.append(driver_key)
            
            for driver_key in to_remove:
                del self._drivers[driver_key]
                self.logger.info(f"Removed unhealthy driver: {driver_key}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = {
                'total_drivers': len(self._drivers),
                'drivers_by_exchange': {},
                'drivers_by_status': {},
                'unhealthy_drivers': 0
            }
            
            for driver_info in self._drivers.values():
                # 按交易所统计
                exchange = driver_info.exchange_type.value
                if exchange not in stats['drivers_by_exchange']:
                    stats['drivers_by_exchange'][exchange] = 0
                stats['drivers_by_exchange'][exchange] += 1
                
                # 按状态统计
                status = driver_info.status.value
                if status not in stats['drivers_by_status']:
                    stats['drivers_by_status'][status] = 0
                stats['drivers_by_status'][status] += 1
                
                # 不健康Driver统计
                if not driver_info.is_healthy():
                    stats['unhealthy_drivers'] += 1
            
            return stats

    def shutdown(self):
        """关闭AccountManager，清理所有Driver"""
        with self._lock:
            self.logger.info(f"Shutting down AccountManager, cleaning up {len(self._drivers)} drivers")
            self._drivers.clear()
            self.logger.info("AccountManager shutdown complete")


# 全局AccountManager实例
_global_account_manager: Optional[AccountManager] = None


def get_account_manager(config: Optional[Dict[str, Any]] = None) -> AccountManager:
    """
    获取全局AccountManager实例（单例模式）
    
    Args:
        config: 配置字典，仅在首次创建时有效
        
    Returns:
        AccountManager实例
    """
    global _global_account_manager
    
    if _global_account_manager is None:
        _global_account_manager = AccountManager(config)
    
    return _global_account_manager


def reset_account_manager():
    """重置全局AccountManager实例"""
    global _global_account_manager
    
    if _global_account_manager:
        _global_account_manager.shutdown()
        _global_account_manager = None


if __name__ == '__main__':
    # 测试AccountManager
    print("=== AccountManager 测试 ===")
    
    # 创建AccountManager
    manager = AccountManager()
    
    # 测试创建Driver
    print("\n1. 测试创建OKX Driver:")
    okx_driver = manager.get_driver(ExchangeType.OKX, 0)
    if okx_driver:
        print("✓ OKX Driver创建成功")
    else:
        print("✗ OKX Driver创建失败")
    
    # 测试创建Backpack Driver
    print("\n2. 测试创建Backpack Driver:")
    bp_driver = manager.get_driver(ExchangeType.BACKPACK, 0)
    if bp_driver:
        print("✓ Backpack Driver创建成功")
    else:
        print("✗ Backpack Driver创建失败")
    
    # 测试获取统计信息
    print("\n3. 统计信息:")
    stats = manager.get_stats()
    print(f"总Driver数量: {stats['total_drivers']}")
    print(f"按交易所分布: {stats['drivers_by_exchange']}")
    print(f"按状态分布: {stats['drivers_by_status']}")
    
    # 测试重复获取
    print("\n4. 测试重复获取Driver:")
    okx_driver2 = manager.get_driver(ExchangeType.OKX, 0)
    print(f"是否为同一实例: {okx_driver is okx_driver2}")
    
    # 清理
    print("\n5. 清理测试:")
    manager.shutdown()
    print("AccountManager已关闭")
    
    print("\n=== 测试完成 ===")
