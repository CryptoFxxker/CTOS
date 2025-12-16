// TOPDOGINDEX 指标页面 JavaScript

class TopdogindexManager {
    constructor() {
        this.config = window.topdogindexConfig;
        this.timeframes = this.config.timeframes;
        this.currentTimeframe = 'all';
        this.currentDisplayMode = 'grid'; // 'grid' 或 'single'
        this.autoRefreshInterval = null;
        this.refreshInterval = 10000; // 10秒
        // 定义时间框架的顺序（从短到长）
        this.timeframeOrder = {
            '1m': 1,
            '5m': 2,
            '15m': 3,
            '1h': 4,
            '4h': 5,
            '1d': 6
        };
        this.sortTimeout = null; // 用于防抖排序
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadAllCharts(false); // false 表示首次加载，不是刷新
        this.startAutoRefresh();
    }

    bindEvents() {
        // 时间框架选择器
        const timeframeSelect = document.getElementById('timeframe-select');
        if (timeframeSelect) {
            timeframeSelect.addEventListener('change', (e) => {
                this.currentTimeframe = e.target.value;
                this.loadAllCharts(false); // false 表示切换时间框架，不是刷新
            });
        }

        // 展示模式选择器
        const displayModeSelect = document.getElementById('display-mode-select');
        if (displayModeSelect) {
            displayModeSelect.addEventListener('change', (e) => {
                this.currentDisplayMode = e.target.value;
                this.updateDisplayMode();
            });
        }

        // 手动刷新按钮
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadAllCharts(true); // true 表示刷新模式
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

    async loadAllCharts(isRefresh = true) {
        // 不显示全屏loading，使用渐进式刷新
        const chartsContainer = document.getElementById('charts-container');
        
        // 如果是首次加载，清空容器
        if (!isRefresh) {
            chartsContainer.innerHTML = '';
        }
        
        const timeframesToLoad = this.currentTimeframe === 'all' 
            ? this.timeframes 
            : [this.currentTimeframe];
        
        // 并行加载所有图片，使用 Promise.all
        const loadPromises = timeframesToLoad.map((timeframe, i) => {
            const index = this.currentTimeframe === 'all' ? i : this.timeframes.indexOf(timeframe);
            return this.loadChart(timeframe, index, isRefresh); // isRefresh 表示是否使用渐进式刷新
        });
        
        try {
            await Promise.all(loadPromises);
            // 按照时间顺序排序图表卡片
            this.sortChartsByTimeframe();
            this.updateDisplayMode();
            if (isRefresh) {
                this.showNotification('图表刷新完成', 'success');
            }
        } catch (error) {
            this.showNotification(`部分图表加载失败`, 'warning');
        }
    }

    async loadChart(timeframe, index, progressive = false) {
        try {
            // 添加时间戳防止缓存
            const timestamp = new Date().getTime();
            const response = await fetch(`/metrics/${this.config.indicatorId}/api/chart/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    timeframe: timeframe,
                    _t: timestamp // 时间戳参数
                })
            });

            const data = await response.json();
            
            if (data.success) {
                // 渐进式刷新：如果卡片已存在，更新图片；否则创建新卡片
                if (progressive) {
                    this.updateChartCard(timeframe, data.image_path, index);
                } else {
                    this.createChartCard(timeframe, data.image_path, index);
                }
            } else {
                if (progressive) {
                    this.updateChartCardError(timeframe, data.error, index);
                } else {
                    this.createErrorCard(timeframe, data.error, index);
                }
            }
        } catch (error) {
            if (progressive) {
                this.updateChartCardError(timeframe, error.message, index);
            } else {
                this.createErrorCard(timeframe, error.message, index);
            }
        }
    }

    createChartCard(timeframe, imagePath, index) {
        const chartsContainer = document.getElementById('charts-container');
        
        const chartCard = document.createElement('div');
        chartCard.className = 'chart-card';
        chartCard.setAttribute('data-timeframe', timeframe);
        chartCard.setAttribute('data-index', index);
        chartCard.innerHTML = `
            <div class="chart-header">
                <h3>TOPDOGINDEX - ${timeframe.toUpperCase()}</h3>
                <span class="chart-index">#${index + 1}</span>
            </div>
            <div class="chart-content">
                <div class="chart-loading-indicator">
                    <div class="mini-spinner"></div>
                    <span>加载中...</span>
                </div>
                <img src="${imagePath}" alt="TOPDOGINDEX ${timeframe}" 
                     class="chart-image" 
                     style="opacity: 0;"
                     onload="this.style.opacity='1'; this.parentElement.querySelector('.chart-loading-indicator').style.display='none';"
                     onerror="this.parentElement.innerHTML='<div class=\\'error-message\\'>图片加载失败</div>'">
            </div>
            <div class="chart-footer">
                <span class="chart-timeframe">${timeframe.toUpperCase()}</span>
                <span class="chart-timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        
        chartsContainer.appendChild(chartCard);
    }

    updateChartCard(timeframe, imagePath, index) {
        // 查找已存在的卡片
        const chartsContainer = document.getElementById('charts-container');
        let chartCard = chartsContainer.querySelector(`[data-timeframe="${timeframe}"]`);
        
        if (!chartCard) {
            // 如果卡片不存在，创建新卡片
            this.createChartCard(timeframe, imagePath, index);
            return;
        }
        
        // 卡片已存在，更新图片（渐进式刷新）
        const chartContent = chartCard.querySelector('.chart-content');
        const oldImage = chartCard.querySelector('.chart-image');
        
        // 显示加载指示器
        let loadingIndicator = chartContent.querySelector('.chart-loading-indicator');
        if (!loadingIndicator) {
            loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'chart-loading-indicator';
            loadingIndicator.innerHTML = '<div class="mini-spinner"></div><span>刷新中...</span>';
            chartContent.insertBefore(loadingIndicator, oldImage);
        }
        loadingIndicator.style.display = 'flex';
        
        // 创建新图片（在后台加载）
        const newImage = new Image();
        newImage.className = 'chart-image';
        newImage.alt = `TOPDOGINDEX ${timeframe}`;
        newImage.style.opacity = '0';
        newImage.style.transition = 'opacity 0.5s ease-in-out';
        
        // 图片加载完成后替换
        newImage.onload = () => {
            // 淡入新图片
            newImage.style.opacity = '1';
            // 淡出旧图片
            if (oldImage) {
                oldImage.style.opacity = '0';
                setTimeout(() => {
                    if (oldImage.parentNode) {
                        oldImage.remove();
                    }
                }, 500);
            }
            // 隐藏加载指示器
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            // 更新时间戳
            const timestampEl = chartCard.querySelector('.chart-timestamp');
            if (timestampEl) {
                timestampEl.textContent = new Date().toLocaleTimeString();
            }
            // 更新后重新排序（确保顺序正确）
            this.sortChartsByTimeframe();
        };
        
        newImage.onerror = () => {
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            this.updateChartCardError(timeframe, '图片加载失败', index);
        };
        
        // 添加时间戳防止缓存
        newImage.src = imagePath + (imagePath.includes('?') ? '&' : '?') + '_t=' + new Date().getTime();
        
        // 将新图片添加到容器（在旧图片后面）
        chartContent.appendChild(newImage);
    }

    updateChartCardError(timeframe, error, index) {
        const chartsContainer = document.getElementById('charts-container');
        const chartCard = chartsContainer.querySelector(`[data-timeframe="${timeframe}"]`);
        
        if (chartCard) {
            const chartContent = chartCard.querySelector('.chart-content');
            const loadingIndicator = chartContent.querySelector('.chart-loading-indicator');
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            // 如果图片加载失败，显示错误信息（但不替换整个卡片）
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.innerHTML = `<div class="error-icon">⚠️</div><p>刷新失败</p><small>${error}</small>`;
            errorDiv.style.position = 'absolute';
            errorDiv.style.top = '50%';
            errorDiv.style.left = '50%';
            errorDiv.style.transform = 'translate(-50%, -50%)';
            errorDiv.style.background = 'rgba(255, 255, 255, 0.9)';
            errorDiv.style.padding = '1rem';
            errorDiv.style.borderRadius = '5px';
            
            // 移除旧的错误信息
            const oldError = chartContent.querySelector('.error-message');
            if (oldError) {
                oldError.remove();
            }
            
            chartContent.appendChild(errorDiv);
            
            // 3秒后自动移除错误信息
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.style.opacity = '0';
                    errorDiv.style.transition = 'opacity 0.3s';
                    setTimeout(() => errorDiv.remove(), 300);
                }
            }, 3000);
        } else {
            // 如果卡片不存在，创建错误卡片
            this.createErrorCard(timeframe, error, index);
        }
    }

    createErrorCard(timeframe, error, index) {
        const chartsContainer = document.getElementById('charts-container');
        
        const errorCard = document.createElement('div');
        errorCard.className = 'chart-card error-card';
        errorCard.innerHTML = `
            <div class="chart-header">
                <h3>TOPDOGINDEX - ${timeframe.toUpperCase()}</h3>
                <span class="chart-index">#${index + 1}</span>
            </div>
            <div class="chart-content">
                <div class="error-message">
                    <div class="error-icon">⚠️</div>
                    <p>加载失败</p>
                    <small>${error}</small>
                </div>
            </div>
            <div class="chart-footer">
                <span class="chart-timeframe">${timeframe.toUpperCase()}</span>
                <span class="chart-timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        
        chartsContainer.appendChild(errorCard);
    }

    sortChartsByTimeframe() {
        // 使用防抖，避免频繁排序
        if (this.sortTimeout) {
            clearTimeout(this.sortTimeout);
        }
        
        this.sortTimeout = setTimeout(() => {
            // 按照时间框架顺序对图表卡片进行排序
            const chartsContainer = document.getElementById('charts-container');
            const chartCards = Array.from(chartsContainer.querySelectorAll('.chart-card'));
            
            // 按照时间框架顺序排序
            chartCards.sort((a, b) => {
                const timeframeA = a.getAttribute('data-timeframe');
                const timeframeB = b.getAttribute('data-timeframe');
                const orderA = this.timeframeOrder[timeframeA] || 999;
                const orderB = this.timeframeOrder[timeframeB] || 999;
                return orderA - orderB;
            });
            
            // 重新插入排序后的卡片
            chartCards.forEach(card => {
                chartsContainer.appendChild(card);
            });
            
            this.sortTimeout = null;
        }, 100); // 100ms 防抖延迟
    }

    updateDisplayMode() {
        const chartsContainer = document.getElementById('charts-container');
        const pageContainer = document.querySelector('.topdogindex-container');
        const chartCards = chartsContainer.querySelectorAll('.chart-card');
        
        // 移除所有现有的样式类
        chartsContainer.classList.remove('charts-grid', 'charts-single');
        chartCards.forEach(card => {
            card.classList.remove('chart-card-grid', 'chart-card-single');
        });
        
        if (this.currentDisplayMode === 'single') {
            // 单页展示模式：6张图在一页
            chartsContainer.classList.add('charts-single');
            chartCards.forEach(card => {
                card.classList.add('chart-card-single');
            });
            // 添加单页模式类到页面容器
            if (pageContainer) {
                pageContainer.classList.add('single-mode');
            }
        } else {
            // 网格布局模式：竖排放置
            chartsContainer.classList.add('charts-grid');
            chartCards.forEach(card => {
                card.classList.add('chart-card-grid');
            });
            // 移除单页模式类
            if (pageContainer) {
                pageContainer.classList.remove('single-mode');
            }
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh(); // 确保没有重复的定时器
        this.autoRefreshInterval = setInterval(() => {
            this.loadAllCharts(true); // true 表示自动刷新模式
        }, this.refreshInterval);
        
        this.showNotification(`自动刷新已启动 (${this.refreshInterval/1000}秒间隔)`, 'info');
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
            this.showNotification('自动刷新已停止', 'info');
        }
    }

    showLoading() {
        // 不再使用全屏loading，改为每个卡片独立显示加载状态
        // 保留方法以兼容性，但不执行任何操作
    }

    hideLoading() {
        // 不再使用全屏loading
        // 保留方法以兼容性，但不执行任何操作
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
    new TopdogindexManager();
});
