// K线图页面 JavaScript

class KlineManager {
    constructor() {
        this.config = window.klineConfig || {};
        // 解析JSON字符串（如果后端传递的是字符串）
        this.timeframes = typeof this.config.timeframes === 'string' 
            ? JSON.parse(this.config.timeframes) 
            : (this.config.timeframes || ['1m', '5m', '15m', '1h', '4h', '1d']);
        this.coins = typeof this.config.coins === 'string' 
            ? JSON.parse(this.config.coins) 
            : (this.config.coins || ['btc', 'eth', 'xrp', 'bnb', 'sol', 'ada', 'doge', 'trx', 'ltc', 'shib']);
        this.currentCoin = 'btc';
        this.currentTimeframe = '1h';
        this.autoRefreshInterval = null;
        this.refreshInterval = 10000; // 10秒
        this.chart = null; // Chart.js实例
        this.isInitialLoad = true; // 标记是否为首次加载
        this.isLoading = false; // 标记是否正在加载
        this.init();
    }

    init() {
        this.initSelectors();
        this.bindEvents();
        this.loadChart();
        this.startAutoRefresh();
    }
    
    initSelectors() {
        // 初始化币种选择器
        const coinSelect = document.getElementById('coin-select');
        if (coinSelect && this.coins && this.coins.length > 0) {
            coinSelect.innerHTML = '';
            
            // 定义主流币种（用于添加分隔符）
            const mainstreamCoins = ['btc', 'eth', 'sol', 'xrp', 'bnb', 'ada', 'doge', 'trx', 'ltc', 'shib', 
                                    'matic', 'avax', 'dot', 'link', 'uni'];
            let mainstreamEnded = false;
            
            this.coins.forEach((coin, index) => {
                const coinLower = coin.toLowerCase();
                
                // 如果当前币种不是主流币种，且主流币种部分已结束，添加分隔符
                if (!mainstreamEnded && !mainstreamCoins.includes(coinLower)) {
                    // 添加分隔符选项
                    const separator = document.createElement('option');
                    separator.disabled = true;
                    separator.textContent = '────────── 其他币种 ──────────';
                    separator.style.fontWeight = 'bold';
                    coinSelect.appendChild(separator);
                    mainstreamEnded = true;
                }
                
                const option = document.createElement('option');
                option.value = coinLower;
                option.textContent = coin.toUpperCase();
                if (coinLower === 'btc') {
                    option.selected = true;
                    this.currentCoin = coinLower;
                }
                coinSelect.appendChild(option);
            });
        }
        
        // 初始化时间框架选择器
        const timeframeSelect = document.getElementById('timeframe-select');
        if (timeframeSelect && this.timeframes && this.timeframes.length > 0) {
            timeframeSelect.innerHTML = '';
            this.timeframes.forEach(timeframe => {
                const option = document.createElement('option');
                option.value = timeframe.toLowerCase();
                option.textContent = timeframe.toUpperCase();
                if (timeframe.toLowerCase() === '1h') {
                    option.selected = true;
                    this.currentTimeframe = timeframe.toLowerCase();
                }
                timeframeSelect.appendChild(option);
            });
        }
    }

    bindEvents() {
        // 币种选择器
        const coinSelect = document.getElementById('coin-select');
        if (coinSelect) {
            coinSelect.addEventListener('change', (e) => {
                this.currentCoin = e.target.value;
                this.loadChart();
            });
        }

        // 时间框架选择器
        const timeframeSelect = document.getElementById('timeframe-select');
        if (timeframeSelect) {
            timeframeSelect.addEventListener('change', (e) => {
                this.currentTimeframe = e.target.value;
                this.loadChart();
            });
        }

        // 手动刷新按钮
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadChart();
            });
        }

        // 自动刷新复选框
        const autoRefreshCheckbox = document.getElementById('auto-refresh-checkbox');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }
    }

    async loadChart() {
        // 如果正在加载，忽略新的请求
        if (this.isLoading) {
            return;
        }
        
        this.isLoading = true;
        
        // 只在首次加载时显示全屏loading
        if (this.isInitialLoad) {
            this.showLoading();
        } else {
            // 刷新时只显示小的加载指示器
            this.showRefreshIndicator();
        }
        
        try {
            // 使用新的K线数据API
            const response = await fetch(`/metrics/api/kline/data/?symbol=${this.currentCoin}&timeframe=${this.currentTimeframe}&limit=200`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            
            if (data.success && data.data) {
                // 先准备好数据，再更新图表
                await this.updateChart(data.data);
                
                // 隐藏loading
                if (this.isInitialLoad) {
                    this.hideLoading();
                    this.isInitialLoad = false;
                } else {
                    this.hideRefreshIndicator();
                }
                
                // 只在首次加载或手动刷新时显示通知
                if (this.isInitialLoad) {
                    // 首次加载不显示通知，避免干扰
                }
            } else {
                this.showError(data.error || '获取K线数据失败');
                if (this.isInitialLoad) {
                    this.hideLoading();
                    this.isInitialLoad = false;
                } else {
                    this.hideRefreshIndicator();
                }
                this.showNotification(`加载失败: ${data.error || '获取K线数据失败'}`, 'error');
            }
        } catch (error) {
            this.showError(error.message);
            if (this.isInitialLoad) {
                this.hideLoading();
                this.isInitialLoad = false;
            } else {
                this.hideRefreshIndicator();
            }
            this.showNotification(`加载失败: ${error.message}`, 'error');
        } finally {
            this.isLoading = false;
        }
    }

    async updateChart(klineData) {
        const chartCanvas = document.getElementById('kline-chart');
        const chartTitle = document.getElementById('chart-title');
        const lastUpdate = document.getElementById('last-update');
        
        if (!chartCanvas) {
            console.error('找不到K线图表canvas元素');
            return;
        }
        
        // 更新标题和时间戳
        chartTitle.textContent = `K线图 - ${this.currentCoin.toUpperCase()} ${this.currentTimeframe.toUpperCase()}`;
        lastUpdate.textContent = new Date().toLocaleTimeString();
        
        // 转换数据格式为Chart.js Financial需要的格式
        // 确保时间戳是毫秒数
        const chartData = klineData.map(item => {
            let timestamp = item.timestamp;
            
            // 确保时间戳是数字类型
            if (typeof timestamp === 'string') {
                // 尝试直接转换为数字
                const numTimestamp = parseInt(timestamp, 10);
                if (!isNaN(numTimestamp)) {
                    timestamp = numTimestamp;
                } else {
                    // 如果不是数字字符串，尝试解析为日期
                    timestamp = new Date(timestamp).getTime();
                }
            }
            
            // 如果时间戳看起来是秒（小于10000000000），转换为毫秒
            if (timestamp < 10000000000) {
                timestamp = timestamp * 1000;
            }
            
            return {
                x: timestamp,  // 毫秒时间戳
                o: parseFloat(item.open) || 0,
                h: parseFloat(item.high) || 0,
                l: parseFloat(item.low) || 0,
                c: parseFloat(item.close) || 0
            };
        }).filter(item => item.x > 0 && item.o > 0); // 过滤无效数据
        
        if (chartData.length === 0) {
            this.showError('没有有效的K线数据');
            return;
        }
        
        // 计算数据的时间范围，用于自动调整时间单位
        const timeRange = chartData.length > 0 
            ? chartData[chartData.length - 1].x - chartData[0].x 
            : 0;
        
        // 根据时间范围和当前时间框架确定合适的时间单位
        const timeConfig = this._getTimeConfig(this.currentTimeframe, timeRange);
        
        // 如果图表已存在，更新数据而不是重新创建
        if (this.chart) {
            try {
                // 更新图表数据
                this.chart.data.datasets[0].data = chartData;
                this.chart.data.datasets[0].label = `${this.currentCoin.toUpperCase()} ${this.currentTimeframe.toUpperCase()}`;
                
                // 更新时间单位配置
                this.chart.options.scales.x.time.unit = timeConfig.unit;
                
                // 平滑更新图表
                this.chart.update('none'); // 'none'模式避免动画，更快
            } catch (e) {
                console.warn('更新图表时出错，尝试重新创建:', e);
                // 如果更新失败，销毁并重新创建
                this.chart.destroy();
                this.chart = null;
                this._createNewChart(chartCanvas, chartData, timeConfig);
            }
        } else {
            // 首次创建图表
            this._createNewChart(chartCanvas, chartData, timeConfig);
        }
    }
    
    _createNewChart(chartCanvas, chartData, timeConfig) {
        // 创建新图表
        const ctx = chartCanvas.getContext('2d');
        
        this.chart = new Chart(ctx, {
            type: 'candlestick',
            data: {
                datasets: [{
                    label: `${this.currentCoin.toUpperCase()} ${this.currentTimeframe.toUpperCase()}`,
                    data: chartData
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: this.isInitialLoad ? 800 : 0 // 首次加载有动画，刷新时无动画
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: timeConfig.unit,
                            displayFormats: {
                                minute: 'HH:mm',
                                hour: 'MM-dd HH:mm',
                                day: 'MM-dd',
                                week: 'MM-dd',
                                month: 'YYYY-MM'
                            }
                        },
                        ticks: {
                            source: 'auto',
                            maxRotation: 45,
                            autoSkip: true,
                            maxTicksLimit: 15
                        }
                    },
                    y: {
                        position: 'right',
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                const point = context.raw;
                                return [
                                    `开盘: $${point.o.toFixed(2)}`,
                                    `最高: $${point.h.toFixed(2)}`,
                                    `最低: $${point.l.toFixed(2)}`,
                                    `收盘: $${point.c.toFixed(2)}`
                                ];
                            }
                        }
                    }
                }
            }
        });
    }
    
    _getTimeConfig(timeframe, timeRangeMs = 0) {
        // 根据时间框架和时间范围返回时间配置（只返回单位，不设置stepSize）
        const tf = timeframe.toLowerCase();
        
        // 如果提供了时间范围，根据范围自动选择合适单位
        if (timeRangeMs > 0) {
            const days = timeRangeMs / (1000 * 60 * 60 * 24);
            const hours = timeRangeMs / (1000 * 60 * 60);
            
            // 根据时间范围智能选择单位（让Chart.js自动计算步长）
            if (days > 90) {
                return { unit: 'day' };
            } else if (days > 30) {
                return { unit: 'day' };
            } else if (days > 7) {
                return { unit: 'day' };

            } else if (days > 1) {
                return { unit: 'hour' };
            } else if (hours > 12) {
                return { unit: 'hour' };
            } else if (hours > 6) {
                return { unit: 'hour' };
            } else if (hours > 2) {
                return { unit: 'minute' };
            } else {
                return { unit: 'minute' };
            }
        }
        
        // 根据时间框架返回默认配置
        if (tf === '1m' || tf === '5m' || tf === '15m' || tf === '30m') {
            return { unit: 'minute' };
        } else if (tf === '1h' || tf === '2h' || tf === '4h' || tf === '6h' || tf === '12h') {
            return { unit: 'hour' };
        } else if (tf === '1d') {
            return { unit: 'day' };
        } else if (tf === '1w') {
            return { unit: 'week' };
        }
        
        return { unit: 'hour' }; // 默认
    }
    
    _getTimeUnit(timeframe, timeRangeMs = 0) {
        // 兼容方法，返回时间单位
        return this._getTimeConfig(timeframe, timeRangeMs).unit;
    }
    
    _getTimeDisplayFormat(timeframe) {
        // 根据时间框架返回时间显示格式
        const tf = timeframe.toLowerCase();
        if (tf === '1m' || tf === '5m' || tf === '15m' || tf === '30m') {
            return 'HH:mm';
        } else if (tf === '1h' || tf === '2h' || tf === '4h' || tf === '6h' || tf === '12h') {
            return 'MM-dd HH:mm';
        } else if (tf === '1d') {
            return 'MM-dd';
        } else if (tf === '1w') {
            return 'MM-dd';
        }
        return 'MM-dd HH:mm'; // 默认
    }

    showError(error) {
        const chartCanvas = document.getElementById('kline-chart');
        if (!chartCanvas) return;
        
        const chartContent = chartCanvas.parentElement;
        chartContent.innerHTML = `
            <div class="error-message" style="padding: 2rem; text-align: center; color: #dc3545;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                <p style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem;">加载失败</p>
                <small style="color: #666;">${error}</small>
            </div>
        `;
    }

    startAutoRefresh() {
        this.stopAutoRefresh(); // 确保没有重复的定时器
        
        // 首次加载完成后才启动自动刷新
        if (this.isInitialLoad) {
            // 等待首次加载完成
            const checkInitialLoad = setInterval(() => {
                if (!this.isInitialLoad) {
                    clearInterval(checkInitialLoad);
                    this.autoRefreshInterval = setInterval(() => {
                        this.loadChart();
                    }, this.refreshInterval);
                }
            }, 100);
        } else {
            this.autoRefreshInterval = setInterval(() => {
                this.loadChart();
            }, this.refreshInterval);
        }
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    showLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'flex';
            loadingOverlay.style.opacity = '1';
        }
    }

    hideLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            // 使用淡出动画
            loadingOverlay.style.opacity = '0';
            setTimeout(() => {
                if (loadingOverlay) {
                    loadingOverlay.style.display = 'none';
                }
            }, 300);
        }
    }
    
    showRefreshIndicator() {
        // 在图表标题旁边显示小的刷新指示器
        const chartTitle = document.getElementById('chart-title');
        if (chartTitle && !chartTitle.querySelector('.refresh-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'refresh-indicator';
            indicator.innerHTML = ' ⟳';
            indicator.style.cssText = 'display: inline-block; animation: spin 1s linear infinite; margin-left: 0.5rem; color: #667eea;';
            chartTitle.appendChild(indicator);
        }
    }
    
    hideRefreshIndicator() {
        // 移除刷新指示器
        const chartTitle = document.getElementById('chart-title');
        if (chartTitle) {
            const indicator = chartTitle.querySelector('.refresh-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
    }

    showNotification(message, type = 'info') {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // 添加样式
        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '1rem 1.5rem',
            borderRadius: '5px',
            color: 'white',
            fontWeight: '500',
            zIndex: '1000',
            maxWidth: '300px',
            wordWrap: 'break-word',
            opacity: '0',
            transform: 'translateX(100%)',
            transition: 'all 0.3s ease'
        });

        // 根据类型设置背景色
        const colors = {
            success: '#28a745',
            error: '#dc3545',
            info: '#17a2b8',
            warning: '#ffc107'
        };
        notification.style.backgroundColor = colors[type] || colors.info;

        // 添加到页面
        document.body.appendChild(notification);

        // 显示动画
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        }, 100);

        // 自动移除
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    getCSRFToken() {
        // 尝试从cookie中获取CSRF token
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        
        // 如果cookie中没有，尝试从meta标签获取
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        
        return '';
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    new KlineManager();
});
