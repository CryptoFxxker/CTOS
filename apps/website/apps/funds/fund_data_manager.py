# -*- coding: utf-8 -*-
"""
基金数据管理模块
提供余额获取、缓存、数据采集和走势数据读取功能
"""
import os
import sys
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import pytz

# 北京时间时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_beijing_time():
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)

def load_api_keys_from_file(file_path: Optional[str] = None) -> Dict[str, str]:
    """
    从文本文件读取API密钥（单账户版本，保持向后兼容）
    
    Args:
        file_path: 文件路径，如果为None则使用默认路径（funds文件夹下的api.txt）
        
    Returns:
        包含API密钥的字典
    """
    accounts = load_multiple_accounts_from_file(file_path)
    # 返回第一个账户的密钥（向后兼容）
    return accounts[0] if accounts else {}

def load_multiple_accounts_from_file(file_path: Optional[str] = None) -> List[Dict[str, str]]:
    """
    从文本文件读取多个账户的API密钥（空行分隔）
    
    Args:
        file_path: 文件路径，如果为None则使用默认路径（funds文件夹下的api.txt）
        
    Returns:
        账户列表，每个元素是一个包含API密钥的字典
    """
    accounts = []
    current_account = {}
    
    # 默认文件路径
    if file_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, 'api.txt')
    
    if not os.path.exists(file_path):
        return accounts
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 跳过注释
                if line.startswith('#'):
                    continue
                
                # 空行表示当前账户结束，开始下一个账户
                if not line:
                    if current_account:
                        accounts.append(current_account)
                        current_account = {}
                    continue
                
                # 解析 KEY="VALUE" 或 KEY=VALUE 格式
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    current_account[key] = value
        
        # 添加最后一个账户（如果文件末尾没有空行）
        if current_account:
            accounts.append(current_account)
        
        print(f"✓ 从文件读取账户: {file_path} (找到 {len(accounts)} 个账户)")
    except Exception as e:
        print(f"✗ 读取API密钥文件失败: {e}")
    
    return accounts

# 动态添加项目路径
def _add_project_path():
    """添加项目路径到sys.path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '../../../../'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

_PROJECT_ROOT = _add_project_path()

# 导入驱动
OKX_AVAILABLE = False
BACKPACK_AVAILABLE = False

try:
    from ctos.drivers.okx.okex import OkexSpot
    OKX_AVAILABLE = True
    print("✓ OKX驱动导入成功")
except ImportError as e:
    print(f"✗ OKX驱动导入失败: {e}")

try:
    # 尝试多种导入路径
    try:
        from ctos.drivers.backpack.bpx.account import Account
    except ImportError:
        try:
            from ctos.drivers.backpack.bpx.base.base_account import Account
        except ImportError:
            from bpx.account import Account
    BACKPACK_AVAILABLE = True
    print("✓ Backpack驱动导入成功")
except ImportError as e:
    print(f"✗ Backpack驱动导入失败: {e}")


class FundDataManager:
    """基金数据管理器（单账户版本）"""
    
    def __init__(self, db_path: Optional[str] = None, account_id: str = "default", api_keys: Optional[Dict[str, str]] = None):
        """
        初始化基金数据管理器
        
        Args:
            db_path: 数据库文件路径，如果为None则使用默认路径
            account_id: 账户ID，用于区分不同账户
            api_keys: API密钥字典，如果为None则从文件读取
        """
        # 设置数据库路径
        if db_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(current_dir, 'fund_data.db')
        
        self.db_path = db_path
        self.account_id = account_id
        self.cache_balance = None
        self.cache_time = None
        self.cache_ttl = 10  # 缓存10秒
        
        # 初始化数据库
        self._init_database()
        
        # 初始化驱动实例（常驻维护）
        self.okx_client = None
        self.backpack_client = None
        self._init_drivers(api_keys)
        
        # 后台采集线程
        self.collector_thread = None
        self.collector_running = False
        
        # 启动后台采集线程
        self.start_collector()
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建数据表：存储不同周期的数据（添加account_id字段）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_balance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL DEFAULT 'default',
                timestamp DATETIME NOT NULL,
                balance REAL NOT NULL,
                period TEXT NOT NULL,
                UNIQUE(account_id, timestamp, period)
            )
        ''')
        
        # 如果表已存在但没有account_id字段，添加该字段
        try:
            cursor.execute('ALTER TABLE fund_balance ADD COLUMN account_id TEXT NOT NULL DEFAULT \'default\'')
        except sqlite3.OperationalError:
            # 字段已存在，忽略错误
            pass
        
        # 创建索引以提高查询速度
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_timestamp_period 
            ON fund_balance(account_id, timestamp, period)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON fund_balance(timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_id 
            ON fund_balance(account_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def _init_drivers(self, api_keys: Optional[Dict[str, str]] = None):
        """初始化并维护常驻驱动实例"""
        print("\n" + "="*60)
        print(f"开始初始化驱动 [账户: {self.account_id}]...")
        print("="*60)
        
        # 如果没有提供API密钥，从文件读取
        if api_keys is None:
            api_keys = load_api_keys_from_file()
        
        # 初始化OKX驱动
        if OKX_AVAILABLE:
            print("\n[OKX] 检查API密钥...")
            # 优先从文件读取，如果没有则从环境变量读取
            access_key = api_keys.get('OKX_API_KEY') or api_keys.get('OKX_ACCESS_KEY') or os.getenv('OKX_API_KEY') or os.getenv('OKX_ACCESS_KEY')
            secret_key = api_keys.get('OKX_SECRET_KEY') or api_keys.get('OKX_SECRET') or os.getenv('OKX_SECRET_KEY') or os.getenv('OKX_SECRET')
            passphrase = api_keys.get('OKX_PASSPHRASE') or os.getenv('OKX_PASSPHRASE')
            
            print(f"[OKX] OKX_API_KEY: {'已设置' if access_key else '未设置'} (长度: {len(access_key) if access_key else 0})")
            print(f"[OKX] OKX_SECRET_KEY: {'已设置' if secret_key else '未设置'} (长度: {len(secret_key) if secret_key else 0})")
            print(f"[OKX] OKX_PASSPHRASE: {'已设置' if passphrase else '未设置'} (长度: {len(passphrase) if passphrase else 0})")
            
            if access_key and secret_key and passphrase:
                try:
                    print("[OKX] 尝试创建OkexSpot实例...")
                    self.okx_client = OkexSpot(
                        symbol="ETH-USDT-SWAP",
                        access_key=access_key,
                        secret_key=secret_key,
                        passphrase=passphrase,
                        host=None
                    )
                    print("✓ OKX驱动初始化成功")
                    
                    # 测试连接
                    print("[OKX] 测试获取余额...")
                    try:
                        test_balance = self.okx_client.fetch_balance('USDT')
                        print(f"[OKX] 测试成功，余额: {test_balance}")
                    except Exception as test_e:
                        print(f"[OKX] 测试获取余额失败: {test_e}")
                except Exception as e:
                    print(f"✗ OKX驱动初始化失败: {e}")
                    import traceback
                    print(f"[OKX] 详细错误信息:\n{traceback.format_exc()}")
            else:
                missing = []
                if not access_key:
                    missing.append("OKX_API_KEY 或 OKX_ACCESS_KEY")
                if not secret_key:
                    missing.append("OKX_SECRET_KEY 或 OKX_SECRET")
                if not passphrase:
                    missing.append("OKX_PASSPHRASE")
                print(f"⚠ OKX API密钥未配置，缺少: {', '.join(missing)}")
        else:
            print("✗ OKX驱动不可用（导入失败）")
        
        # 初始化Backpack驱动
        if BACKPACK_AVAILABLE:
            print("\n[Backpack] 检查API密钥...")
            # 优先从文件读取，如果没有则从环境变量读取
            public_key = api_keys.get('BP_PUBLIC_KEY') or api_keys.get('BACKPACK_PUBLIC_KEY') or os.getenv('BP_PUBLIC_KEY') or os.getenv('BACKPACK_PUBLIC_KEY')
            secret_key = api_keys.get('BP_SECRET_KEY') or api_keys.get('BACKPACK_SECRET_KEY') or os.getenv('BP_SECRET_KEY') or os.getenv('BACKPACK_SECRET_KEY')
            
            print(f"[Backpack] BP_PUBLIC_KEY: {'已设置' if public_key else '未设置'} (长度: {len(public_key) if public_key else 0})")
            print(f"[Backpack] BP_SECRET_KEY: {'已设置' if secret_key else '未设置'} (长度: {len(secret_key) if secret_key else 0})")
            
            if public_key and secret_key:
                try:
                    print("[Backpack] 尝试创建Account实例...")
                    self.backpack_client = Account(public_key, secret_key, window=10000)
                    print("✓ Backpack驱动初始化成功")
                    
                    # 测试连接
                    print("[Backpack] 测试获取余额...")
                    try:
                        if hasattr(self.backpack_client, 'get_collateral'):
                            test_collateral = self.backpack_client.get_collateral()
                            print(f"[Backpack] 测试成功，collateral类型: {type(test_collateral)}")
                        else:
                            print("[Backpack] Account实例缺少get_collateral方法")
                    except Exception as test_e:
                        print(f"[Backpack] 测试获取余额失败: {test_e}")
                        import traceback
                        print(f"[Backpack] 详细错误信息:\n{traceback.format_exc()}")
                except Exception as e:
                    print(f"✗ Backpack驱动初始化失败: {e}")
                    import traceback
                    print(f"[Backpack] 详细错误信息:\n{traceback.format_exc()}")
            else:
                missing = []
                if not public_key:
                    missing.append("BP_PUBLIC_KEY 或 BACKPACK_PUBLIC_KEY")
                if not secret_key:
                    missing.append("BP_SECRET_KEY 或 BACKPACK_SECRET_KEY")
                print(f"⚠ Backpack API密钥未配置，缺少: {', '.join(missing)}")
        else:
            print("✗ Backpack驱动不可用（导入失败）")
        
        print("\n" + "="*60)
        print("驱动初始化完成")
        print("="*60 + "\n")
    
    def _reinit_okx_driver(self):
        """重新初始化OKX驱动（当驱动失效时）"""
        print("[OKX] 尝试重新初始化驱动...")
        try:
            # 优先从文件读取
            api_keys = load_api_keys_from_file()
            access_key = api_keys.get('OKX_API_KEY') or api_keys.get('OKX_ACCESS_KEY') or os.getenv('OKX_API_KEY') or os.getenv('OKX_ACCESS_KEY')
            secret_key = api_keys.get('OKX_SECRET_KEY') or api_keys.get('OKX_SECRET') or os.getenv('OKX_SECRET_KEY') or os.getenv('OKX_SECRET')
            passphrase = api_keys.get('OKX_PASSPHRASE') or os.getenv('OKX_PASSPHRASE')
            
            if not access_key:
                print("[OKX] 重新初始化失败: OKX_API_KEY 或 OKX_ACCESS_KEY 未设置")
                return False
            if not secret_key:
                print("[OKX] 重新初始化失败: OKX_SECRET_KEY 或 OKX_SECRET 未设置")
                return False
            if not passphrase:
                print("[OKX] 重新初始化失败: OKX_PASSPHRASE 未设置")
                return False
            
            self.okx_client = OkexSpot(
                symbol="ETH-USDT-SWAP",
                access_key=access_key,
                secret_key=secret_key,
                passphrase=passphrase,
                host=None
            )
            print("[OKX] 重新初始化成功")
            return True
        except Exception as e:
            print(f"[OKX] 重新初始化失败: {e}")
            import traceback
            print(f"[OKX] 详细错误:\n{traceback.format_exc()}")
        return False
    
    def _reinit_backpack_driver(self):
        """重新初始化Backpack驱动（当驱动失效时）"""
        print("[Backpack] 尝试重新初始化驱动...")
        try:
            # 优先从文件读取
            api_keys = load_api_keys_from_file()
            public_key = api_keys.get('BP_PUBLIC_KEY') or api_keys.get('BACKPACK_PUBLIC_KEY') or os.getenv('BP_PUBLIC_KEY') or os.getenv('BACKPACK_PUBLIC_KEY')
            secret_key = api_keys.get('BP_SECRET_KEY') or api_keys.get('BACKPACK_SECRET_KEY') or os.getenv('BP_SECRET_KEY') or os.getenv('BACKPACK_SECRET_KEY')
            
            if not public_key:
                print("[Backpack] 重新初始化失败: BP_PUBLIC_KEY 或 BACKPACK_PUBLIC_KEY 未设置")
                return False
            if not secret_key:
                print("[Backpack] 重新初始化失败: BP_SECRET_KEY 或 BACKPACK_SECRET_KEY 未设置")
                return False
            
            self.backpack_client = Account(public_key, secret_key, window=10000)
            print("[Backpack] 重新初始化成功")
            return True
        except Exception as e:
            print(f"[Backpack] 重新初始化失败: {e}")
            import traceback
            print(f"[Backpack] 详细错误:\n{traceback.format_exc()}")
        return False
    
    def _get_okx_balance(self) -> Tuple[float, Optional[str]]:
        """
        获取OKX账户余额（使用常驻驱动实例）
        只有在客户端已初始化时才调用此方法
        
        Returns:
            (balance, error_message)
        """
        if not OKX_AVAILABLE:
            return 0.0, "OKX驱动不可用（导入失败）"
        
        # 如果驱动未初始化，直接返回（不尝试初始化，由调用方决定）
        if self.okx_client is None:
            return 0.0, None  # 返回None表示未初始化，不是错误
        
        try:
            # 使用常驻驱动实例获取余额
            print("[OKX] 调用fetch_balance('USDT')...")
            balance_result = self.okx_client.fetch_balance('USDT')
            print(f"[OKX] fetch_balance返回: {balance_result} (类型: {type(balance_result)})")
            
            if balance_result is None:
                # 尝试使用其他方法获取余额
                print("[OKX] fetch_balance返回None，尝试使用get_zijin_asset...")
                try:
                    zijin_balance = self.okx_client.get_zijin_asset('USDT')
                    print(f"[OKX] get_zijin_asset返回: {zijin_balance}")
                    if zijin_balance is not None:
                        return float(zijin_balance), None
                except Exception as zijin_e:
                    print(f"[OKX] get_zijin_asset失败: {zijin_e}")
                
                # 尝试使用get_jiaoyi_asset
                print("[OKX] 尝试使用get_jiaoyi_asset...")
                try:
                    jiaoyi_balance = self.okx_client.get_jiaoyi_asset('USDT')
                    print(f"[OKX] get_jiaoyi_asset返回: {jiaoyi_balance}")
                    if jiaoyi_balance is not None:
                        return float(jiaoyi_balance), None
                except Exception as jiaoyi_e:
                    print(f"[OKX] get_jiaoyi_asset失败: {jiaoyi_e}")
                
                # 尝试直接调用get_asset查看原始返回
                print("[OKX] 尝试直接调用get_asset查看原始返回...")
                try:
                    asset_result = self.okx_client.get_asset('USDT')
                    print(f"[OKX] get_asset返回: {asset_result}")
                    if asset_result and len(asset_result) > 0:
                        response = asset_result[0]
                        print(f"[OKX] response code: {response.get('code')}, msg: {response.get('msg')}")
                        if response.get('code') == '0' and response.get('data'):
                            data = response['data'][0]
                            print(f"[OKX] data keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                            # 尝试提取总权益
                            if 'totalEq' in data:
                                total_eq = float(data['totalEq'])
                                print(f"[OKX] 找到totalEq: {total_eq}")
                                return total_eq, None
                except Exception as asset_e:
                    print(f"[OKX] get_asset失败: {asset_e}")
                    import traceback
                    print(f"[OKX] 详细错误:\n{traceback.format_exc()}")
                
                return 0.0, "OKX余额获取返回None，所有方法都失败"
            
            if isinstance(balance_result, (int, float)):
                return float(balance_result), None
            else:
                return 0.0, f"OKX余额返回格式错误: {type(balance_result)}"
                
        except Exception as e:
            # 如果出错，尝试重新初始化驱动
            error_msg = str(e)
            print(f"[OKX] 获取余额异常: {error_msg}")
            import traceback
            print(f"[OKX] 详细错误:\n{traceback.format_exc()}")
            
            if self._reinit_okx_driver():
                try:
                    # 重试一次
                    print("[OKX] 重新初始化后重试...")
                    balance_result = self.okx_client.fetch_balance('USDT')
                    if balance_result is None:
                        return 0.0, "OKX余额获取返回None（重试后）"
                    if isinstance(balance_result, (int, float)):
                        return float(balance_result), None
                except Exception as retry_e:
                    return 0.0, f"OKX获取余额失败（重试后）: {str(retry_e)}"
            return 0.0, f"OKX获取余额失败: {error_msg}"
    
    def _get_backpack_balance(self) -> Tuple[float, Optional[str]]:
        """
        获取Backpack账户余额（使用常驻驱动实例）
        只有在客户端已初始化时才调用此方法
        
        Returns:
            (balance, error_message)
        """
        if not BACKPACK_AVAILABLE:
            return 0.0, "Backpack驱动不可用（导入失败）"
        
        # 如果驱动未初始化，直接返回（不尝试初始化，由调用方决定）
        if self.backpack_client is None:
            return 0.0, None  # 返回None表示未初始化，不是错误
        
        try:
            # 使用常驻驱动实例获取余额
            if hasattr(self.backpack_client, 'get_collateral'):
                collateral_result = self.backpack_client.get_collateral()
                if isinstance(collateral_result, dict):
                    # 查找USDC余额
                    if 'collateral' in collateral_result:
                        for item in collateral_result['collateral']:
                            if item.get('symbol') == 'USDC':
                                return float(item.get('totalQuantity', 0)), None
                    # 如果没有找到USDC，返回总资产价值
                    if 'assetsValue' in collateral_result:
                        return float(collateral_result['assetsValue']), None
                    return 0.0, "Backpack未找到USDC余额"
                else:
                    return 0.0, f"Backpack余额返回格式错误: {type(collateral_result)}"
            else:
                return 0.0, "Backpack Account缺少get_collateral方法"
                
        except Exception as e:
            # 如果出错，尝试重新初始化驱动
            error_msg = str(e)
            print(f"Backpack获取余额出错，尝试重新初始化驱动: {error_msg}")
            if self._reinit_backpack_driver():
                try:
                    # 重试一次
                    if hasattr(self.backpack_client, 'get_collateral'):
                        collateral_result = self.backpack_client.get_collateral()
                        if isinstance(collateral_result, dict):
                            if 'collateral' in collateral_result:
                                for item in collateral_result['collateral']:
                                    if item.get('symbol') == 'USDC':
                                        return float(item.get('totalQuantity', 0)), None
                            if 'assetsValue' in collateral_result:
                                return float(collateral_result['assetsValue']), None
                except Exception as retry_e:
                    return 0.0, f"Backpack获取余额失败（重试后）: {str(retry_e)}"
            return 0.0, f"Backpack获取余额失败: {error_msg}"
    
    def get_total_balance(self, use_cache: bool = True) -> Tuple[float, Optional[str]]:
        """
        获取所有账户的总余额（带缓存）
        只使用已成功获取到API密钥的客户端
        
        Args:
            use_cache: 是否使用缓存
            
        Returns:
            (balance, error_message)
        """
        # 检查缓存
        if use_cache and self.cache_balance is not None and self.cache_time is not None:
            elapsed = time.time() - self.cache_time
            if elapsed < self.cache_ttl:
                return self.cache_balance, None
        
        try:
            total_balance = 0.0
            errors = []
            available_clients = []
            
            # 只尝试获取已初始化客户端的余额
            # OKX余额
            if self.okx_client is not None:
                try:
                    okx_balance, okx_error = self._get_okx_balance()
                    # okx_balance为None表示未初始化，跳过
                    if okx_balance is not None:
                        if okx_balance > 0:
                            total_balance += okx_balance
                        available_clients.append("OKX")
                    if okx_error:
                        errors.append(f"OKX: {okx_error}")
                except Exception as e:
                    errors.append(f"OKX获取余额异常: {str(e)}")
            else:
                # OKX客户端未初始化，跳过（不报错）
                pass
            
            # Backpack余额
            if self.backpack_client is not None:
                try:
                    bp_balance, bp_error = self._get_backpack_balance()
                    # bp_balance为None表示未初始化，跳过
                    if bp_balance is not None:
                        if bp_balance > 0:
                            total_balance += bp_balance
                        available_clients.append("Backpack")
                    if bp_error:
                        errors.append(f"Backpack: {bp_error}")
                except Exception as e:
                    errors.append(f"Backpack获取余额异常: {str(e)}")
            else:
                # Backpack客户端未初始化，跳过（不报错）
                pass
            
            # 更新缓存
            self.cache_balance = total_balance
            self.cache_time = time.time()
            
            # 构建返回信息
            if available_clients:
                info_msg = f"已使用客户端: {', '.join(available_clients)}"
            else:
                info_msg = "无可用客户端（请检查API密钥配置）"
            
            error_message = "; ".join(errors) if errors else None
            if error_message:
                error_message = f"{info_msg}; {error_message}"
            else:
                error_message = info_msg if not available_clients else None
            
            return total_balance, error_message
            
        except Exception as e:
            return 0.0, f"获取余额失败: {str(e)}"
    
    def save_balance(self, balance: float, period: str):
        """
        保存余额数据到数据库
        
        Args:
            balance: 余额值
            period: 周期标识 ('1m', '10m', '1h', '1d')
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            timestamp = get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT OR REPLACE INTO fund_balance (account_id, timestamp, balance, period)
                VALUES (?, ?, ?, ?)
            ''', (self.account_id, timestamp, balance, period))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[账户 {self.account_id}] 保存余额数据失败 (周期: {period}, 余额: {balance}): {e}")
            import traceback
            print(traceback.format_exc())
    
    def start_collector(self):
        """启动后台数据采集线程"""
        if self.collector_thread is not None and self.collector_thread.is_alive():
            print(f"[账户 {self.account_id}] 采集线程已在运行")
            return
        
        self.collector_running = True
        self.collector_thread = threading.Thread(target=self._collector_loop, daemon=True, name=f"Collector-{self.account_id}")
        self.collector_thread.start()
        print(f"[账户 {self.account_id}] 基金数据采集线程已启动 (线程ID: {self.collector_thread.ident})")
    
    def is_collector_running(self) -> bool:
        """检查采集线程是否在运行"""
        return self.collector_thread is not None and self.collector_thread.is_alive()
    
    def restart_collector(self):
        """重启采集线程"""
        print(f"[账户 {self.account_id}] 尝试重启采集线程...")
        # 先检查线程是否真的停止了
        if self.collector_thread and self.collector_thread.is_alive():
            print(f"[账户 {self.account_id}] 线程仍在运行，先停止...")
            self.stop_collector()
            time.sleep(2)  # 等待线程完全停止
        
        # 确保状态重置
        self.collector_running = False
        self.collector_thread = None
        time.sleep(1)
        
        # 重新启动
        self.start_collector()
        
        # 验证启动是否成功
        if self.is_collector_running():
            print(f"[账户 {self.account_id}] 采集线程重启成功")
        else:
            print(f"[账户 {self.account_id}] ⚠ 采集线程重启失败，请检查错误日志")
    
    def stop_collector(self):
        """停止后台数据采集线程"""
        self.collector_running = False
        if self.collector_thread:
            self.collector_thread.join(timeout=5)
        print(f"[账户 {self.account_id}] 基金数据采集线程已停止")
    
    def _collector_loop(self):
        """后台采集循环"""
        print(f"[账户 {self.account_id}] 采集线程启动")
        # 初始化各周期的上次采集时间
        last_collect = {
            '1m': None,   # 1分钟
            '10m': None,  # 10分钟
            '1h': None,   # 1小时
            '1d': None    # 1天
        }
        
        consecutive_errors = 0
        max_consecutive_errors = 10  # 连续错误10次后等待更长时间
        
        while self.collector_running:
            try:
                # 获取当前余额（不使用缓存，强制获取最新数据）
                balance, error = self.get_total_balance(use_cache=False)
                
                current_time = time.time()
                saved_periods = []
                
                # 即使有错误，如果余额>0也尝试保存（可能是部分错误）
                if error:
                    consecutive_errors += 1
                    print(f"[账户 {self.account_id}] 采集余额时出错 ({consecutive_errors}次): {error}")
                    
                    # 如果余额为0且连续错误，可能是真的有问题
                    if balance == 0 and consecutive_errors >= max_consecutive_errors:
                        print(f"[账户 {self.account_id}] 连续错误{consecutive_errors}次且余额为0，等待5分钟后重试...")
                        time.sleep(300)  # 等待5分钟
                        consecutive_errors = 0
                        continue
                    # 如果余额>0，即使有错误也继续保存（可能是警告性错误）
                    elif balance > 0:
                        print(f"[账户 {self.account_id}] 虽然有错误但余额>0 ({balance:.2f})，继续保存数据")
                        consecutive_errors = 0  # 重置错误计数（因为至少获取到了余额）
                else:
                    consecutive_errors = 0  # 重置错误计数
                
                # 1分钟周期
                if last_collect['1m'] is None or (current_time - last_collect['1m']) >= 60:
                    if balance > 0:  # 只保存有效余额
                        self.save_balance(balance, '1m')
                        last_collect['1m'] = current_time
                        saved_periods.append('1m')
                    else:
                        print(f"[账户 {self.account_id}] 余额为0，跳过1m数据保存")
                
                # 10分钟周期
                if last_collect['10m'] is None or (current_time - last_collect['10m']) >= 600:
                    if balance > 0:
                        self.save_balance(balance, '10m')
                        last_collect['10m'] = current_time
                        saved_periods.append('10m')
                
                # 1小时周期
                if last_collect['1h'] is None or (current_time - last_collect['1h']) >= 3600:
                    if balance > 0:
                        self.save_balance(balance, '1h')
                        last_collect['1h'] = current_time
                        saved_periods.append('1h')
                
                # 1天周期
                if last_collect['1d'] is None or (current_time - last_collect['1d']) >= 86400:
                    if balance > 0:
                        self.save_balance(balance, '1d')
                        last_collect['1d'] = current_time
                        saved_periods.append('1d')
                
                if saved_periods:
                    print(f"[账户 {self.account_id}] 已保存数据: {', '.join(saved_periods)}, 余额: {balance:.2f}")
                elif balance == 0:
                    print(f"[账户 {self.account_id}] 余额为0，未保存任何数据")
                
                # 每30秒检查一次
                time.sleep(30)
                
            except KeyboardInterrupt:
                print(f"[账户 {self.account_id}] 采集线程收到中断信号，退出")
                break
            except Exception as e:
                consecutive_errors += 1
                import traceback
                error_trace = traceback.format_exc()
                print(f"[账户 {self.account_id}] 采集循环出错 ({consecutive_errors}次): {e}")
                print(f"[账户 {self.account_id}] 错误详情:\n{error_trace}")
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"[账户 {self.account_id}] 连续错误{consecutive_errors}次，等待5分钟后重试...")
                    time.sleep(300)
                    consecutive_errors = 0
                else:
                    time.sleep(60)  # 出错后等待1分钟再继续
        
        print(f"[账户 {self.account_id}] 采集线程退出")
    
    def get_trend_data(self, period: str) -> List[Dict]:
        """
        获取走势数据，自适应前端展示需求
        
        Args:
            period: 周期 ('1d', '7d', '1m', '6m', 'all')
            
        Returns:
            走势数据列表，每个元素包含 timestamp, value, pnl
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 根据周期选择合适的数据源和采样策略
            if period == '1d':
                # 1天：使用1分钟数据，最多1440个点（24小时*60分钟）
                # 如果数据点太多，每10分钟采样一次
                period_source = '1m'
                hours_back = 24
                start_time = (get_beijing_time() - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    SELECT timestamp, balance 
                    FROM fund_balance 
                    WHERE account_id = ? AND period = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (self.account_id, period_source, start_time))
                
                rows = cursor.fetchall()
                original_count = len(rows)
                
                # 如果数据点太多（>144），采样到144个点
                # 重要：保留最新的数据点，而不是只保留前面的
                if len(rows) > 144:
                    # 计算采样步长
                    step = len(rows) // 144
                    if step > 1:
                        # 使用步长采样，但确保最后一个数据点被包含
                        sampled = rows[::step]
                        # 如果最后一个数据点不在采样结果中，添加它
                        if sampled[-1] != rows[-1]:
                            sampled.append(rows[-1])
                        rows = sampled
                    else:
                        # 如果步长为1，保留最后144个数据点（包含最新的）
                        rows = rows[-144:]
                    print(f"[1天周期] 数据点从 {original_count} 采样到 {len(rows)} 个，保留最新数据点: {rows[-1][0] if rows else 'N/A'}")
                elif len(rows) > 0:
                    print(f"[1天周期] 使用所有 {len(rows)} 个数据点（未采样），最新数据点: {rows[-1][0]}")
                
            elif period == '7d':
                # 7天：使用10分钟数据，最多1008个点（7天*24小时*6个10分钟）
                # 如果数据点太多，每天采样一次
                period_source = '10m'
                days_back = 7
                start_time = (get_beijing_time() - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    SELECT timestamp, balance 
                    FROM fund_balance 
                    WHERE account_id = ? AND period = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (self.account_id, period_source, start_time))
                
                rows = cursor.fetchall()
                
                # 如果数据点太多，采样到168个点（7天*24小时）
                # 重要：保留最新的数据点
                if len(rows) > 168:
                    step = len(rows) // 168
                    if step > 1:
                        sampled = rows[::step]
                        # 确保最后一个数据点被包含
                        if sampled[-1] != rows[-1]:
                            sampled.append(rows[-1])
                        rows = sampled
                    else:
                        # 保留最后168个数据点（包含最新的）
                        rows = rows[-168:]
                
            elif period == '1m':
                # 1月：优先使用1小时数据，如果都是0或不足则使用1天数据
                days_back = 30
                start_time = (get_beijing_time() - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")
                
                # 先尝试使用1小时数据
                period_source = '1h'
                cursor.execute('''
                    SELECT timestamp, balance 
                    FROM fund_balance 
                    WHERE account_id = ? AND period = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (self.account_id, period_source, start_time))
                
                rows = cursor.fetchall()
                
                # 检查1小时数据是否有效（过滤掉0值，检查是否有有效数据）
                rows_valid = [row for row in rows if float(row[1]) > 0]
                
                # 如果1小时数据不足或都是0，尝试使用1天数据
                if len(rows_valid) < 5:
                    print(f"[1月周期] 1小时数据不足({len(rows)}个点，有效数据{len(rows_valid)}个)，尝试使用1天数据...")
                    period_source_fallback = '1d'
                    cursor.execute('''
                        SELECT timestamp, balance 
                        FROM fund_balance 
                        WHERE account_id = ? AND period = ? AND timestamp >= ? AND balance > 0
                        ORDER BY timestamp ASC
                    ''', (self.account_id, period_source_fallback, start_time))
                    rows_fallback = cursor.fetchall()
                    if len(rows_fallback) > len(rows_valid):
                        rows = rows_fallback
                        print(f"[1月周期] 使用1天数据，找到 {len(rows)} 个有效数据点")
                    else:
                        # 如果1天数据也不足，使用1小时数据（即使有0值）
                        rows = rows if len(rows) > 0 else rows_fallback
                        print(f"[1月周期] 使用1小时数据，找到 {len(rows)} 个数据点（包含0值）")
                else:
                    # 使用有效的1小时数据
                    rows = rows_valid
                    print(f"[1月周期] 使用1小时数据，找到 {len(rows)} 个有效数据点")
                
                # 如果数据点太多，采样到30个点（每天一个）
                if len(rows) > 30:
                    step = len(rows) // 30
                    rows = rows[::step] if step > 1 else rows[:30]
                    print(f"[1月周期] 采样后保留 {len(rows)} 个数据点")
                elif len(rows) > 0:
                    # 如果数据点较少，直接使用所有数据
                    print(f"[1月周期] 使用 {len(rows)} 个数据点（未采样）")
                else:
                    print(f"[1月周期] 警告：没有找到数据")
                
                # 调试：打印前几个和后几个数据点的值
                if len(rows) > 0:
                    print(f"[1月周期] 前3个数据点: {rows[:3]}")
                    print(f"[1月周期] 后3个数据点: {rows[-3:]}")
                    # 检查是否有值变化
                    values = [float(row[1]) for row in rows]
                    unique_values = len(set(values))
                    print(f"[1月周期] 唯一值数量: {unique_values}/{len(values)}")
                    if unique_values == 1:
                        print(f"[1月周期] 警告：所有数据点的值都相同 ({values[0]})，这会导致图表显示为直线")
                
            elif period == '6m':
                # 半年：使用1天数据，最多180个点（6个月*30天）
                period_source = '1d'
                days_back = 180
                start_time = (get_beijing_time() - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    SELECT timestamp, balance 
                    FROM fund_balance 
                    WHERE account_id = ? AND period = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (self.account_id, period_source, start_time))
                
                rows = cursor.fetchall()
                
            else:  # all
                # 全部：使用1天数据，获取所有可用数据
                period_source = '1d'
                
                cursor.execute('''
                    SELECT timestamp, balance 
                    FROM fund_balance 
                    WHERE account_id = ? AND period = ?
                    ORDER BY timestamp ASC
                ''', (self.account_id, period_source))
                
                rows = cursor.fetchall()
            
            conn.close()
            
            # 转换为前端需要的格式
            if not rows:
                print(f"[{period}周期] 没有找到数据")
                return []
            
            print(f"[{period}周期] 找到 {len(rows)} 个数据点")
            
            trend_data = []
            start_value = float(rows[0][1]) if rows else 0.0
            
            for row in rows:
                timestamp = row[0]
                value = float(row[1])
                pnl = value - start_value
                
                trend_data.append({
                    "timestamp": timestamp,
                    "value": round(value, 2),
                    "pnl": round(pnl, 2)
                })
            
            return trend_data
            
        except Exception as e:
            print(f"获取走势数据失败: {e}")
            return []
    
    def get_period_pnl(self, period: str) -> Tuple[float, float, float, float]:
        """
        计算周期盈亏
        
        Args:
            period: 周期 ('1d', '7d', '1m', '6m', 'all')
            
        Returns:
            (period_pnl, period_pnl_percent, start_value, current_value)
        """
        trend_data = self.get_trend_data(period)
        
        if not trend_data:
            return 0.0, 0.0, 0.0, 0.0
        
        start_value = trend_data[0]["value"]
        current_value = trend_data[-1]["value"]
        period_pnl = current_value - start_value
        period_pnl_percent = (period_pnl / start_value * 100) if start_value > 0 else 0.0
        
        return (
            round(period_pnl, 2),
            round(period_pnl_percent, 2),
            round(start_value, 2),
            round(current_value, 2)
        )


class MultiAccountFundManager:
    """多账户基金数据管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化多账户管理器
        
        Args:
            db_path: 数据库文件路径，如果为None则使用默认路径
        """
        if db_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(current_dir, 'fund_data.db')
        
        self.db_path = db_path
        self.managers: Dict[str, FundDataManager] = {}
        self.account_names: Dict[str, str] = {}  # account_id -> display_name
        
        # 从文件加载所有账户
        self._load_accounts()
    
    def _load_accounts(self):
        """从api.txt文件加载所有账户"""
        accounts = load_multiple_accounts_from_file()
        
        if not accounts:
            print("⚠ 未找到账户配置，使用默认账户")
            # 创建默认账户
            default_manager = FundDataManager(self.db_path, account_id="default")
            self.managers["default"] = default_manager
            self.account_names["default"] = "默认账户"
            return
        
        print(f"✓ 找到 {len(accounts)} 个账户配置")
        
        for idx, api_keys in enumerate(accounts):
            account_id = f"account_{idx + 1}"
            # 尝试从API密钥中提取账户名称（如果有ACCOUNT_NAME字段）
            account_name = api_keys.get('ACCOUNT_NAME', f"账户 {idx + 1}")
            
            try:
                manager = FundDataManager(
                    db_path=self.db_path,
                    account_id=account_id,
                    api_keys=api_keys
                )
                self.managers[account_id] = manager
                self.account_names[account_id] = account_name
                print(f"✓ 账户 {account_id} ({account_name}) 初始化成功")
            except Exception as e:
                print(f"✗ 账户 {account_id} ({account_name}) 初始化失败: {e}")
    
    def get_account_ids(self) -> List[str]:
        """获取所有账户ID列表"""
        return list(self.managers.keys())
    
    def get_account_info(self) -> List[Dict[str, str]]:
        """获取所有账户信息"""
        return [
            {
                "account_id": account_id,
                "account_name": self.account_names.get(account_id, account_id)
            }
            for account_id in self.managers.keys()
        ]
    
    def get_manager(self, account_id: str) -> Optional[FundDataManager]:
        """获取指定账户的管理器"""
        return self.managers.get(account_id)
    
    def get_default_manager(self) -> Optional[FundDataManager]:
        """获取默认账户管理器（第一个账户）"""
        if self.managers:
            return list(self.managers.values())[0]
        return None
    
    def check_and_restart_collectors(self):
        """检查所有账户的采集线程状态，如果停止则重启"""
        restarted = []
        for account_id, manager in self.managers.items():
            if not manager.is_collector_running():
                print(f"⚠ 检测到账户 {account_id} 的采集线程已停止，正在重启...")
                manager.restart_collector()
                restarted.append(account_id)
        return restarted
    
    def get_collector_status(self) -> Dict[str, Dict]:
        """获取所有账户的采集线程状态"""
        status = {}
        for account_id, manager in self.managers.items():
            status[account_id] = {
                "running": manager.is_collector_running(),
                "thread_alive": manager.collector_thread.is_alive() if manager.collector_thread else False,
                "thread_id": manager.collector_thread.ident if manager.collector_thread else None
            }
        return status


# 全局实例
_global_fund_manager: Optional[FundDataManager] = None
_global_multi_account_manager: Optional[MultiAccountFundManager] = None


def get_fund_manager(account_id: Optional[str] = None) -> FundDataManager:
    """
    获取基金数据管理器实例
    
    Args:
        account_id: 账户ID，如果为None则返回默认账户或第一个账户
    
    Returns:
        FundDataManager实例
    """
    global _global_fund_manager, _global_multi_account_manager
    
    # 如果指定了account_id，使用多账户管理器
    if account_id:
        if _global_multi_account_manager is None:
            _global_multi_account_manager = MultiAccountFundManager()
        manager = _global_multi_account_manager.get_manager(account_id)
        if manager:
            return manager
        # 如果找不到指定账户，返回默认账户
        return _global_multi_account_manager.get_default_manager() or FundDataManager()
    
    # 如果没有指定account_id，使用单账户管理器（向后兼容）
    if _global_fund_manager is None:
        _global_fund_manager = FundDataManager()
    return _global_fund_manager


def get_multi_account_manager() -> MultiAccountFundManager:
    """获取多账户管理器实例"""
    global _global_multi_account_manager
    if _global_multi_account_manager is None:
        _global_multi_account_manager = MultiAccountFundManager()
    return _global_multi_account_manager

