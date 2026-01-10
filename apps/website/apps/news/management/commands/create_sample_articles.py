"""
创建示例文章的管理命令

使用方法:
    python manage.py create_sample_articles
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from apps.news.models import Article


class Command(BaseCommand):
    help = '创建示例文章到资讯系统'

    def handle(self, *args, **options):
        # 获取或创建默认作者
        try:
            author = User.objects.get(username='admin')
        except User.DoesNotExist:
            # 如果没有 admin 用户，使用第一个超级用户
            author = User.objects.filter(is_superuser=True).first()
            if not author:
                self.stdout.write(
                    self.style.ERROR('错误：没有找到可用的作者用户。请先创建超级用户。')
                )
                return

        # 示例文章数据
        sample_articles = [
            {
                'title': 'CTOS 量化交易管理系统介绍',
                'slug': 'ctos-introduction',
                'content': '''
<h1>CTOS 量化交易管理系统介绍</h1>

<h2>系统概述</h2>
<p>CTOS 量化交易管理系统是一个专为加密货币交易设计的 Web 应用，集成了多个主流交易所（OKX、Backpack），提供实时账户监控、策略管理、技术指标分析等功能。</p>

<h2>核心功能</h2>
<h3>🏦 账户管理</h3>
<ul>
<li><strong>多交易所支持</strong>：集成 OKX、Backpack 等主流交易所</li>
<li><strong>实时余额监控</strong>：自动刷新账户余额和持仓信息</li>
<li><strong>账户详情页面</strong>：查看详细的仓位和订单信息</li>
<li><strong>健康状态监控</strong>：实时监控 Driver 连接状态</li>
</ul>

<h3>📊 指标分析</h3>
<ul>
<li><strong>TOPDOGINDEX 指标</strong>：自定义技术指标，支持多时间周期</li>
<li><strong>全币种趋势</strong>：市场整体趋势分析</li>
<li><strong>K线图表</strong>：支持多种币种和时间间隔的 K 线展示</li>
<li><strong>实时刷新</strong>：指标数据自动更新</li>
</ul>
                ''',
                'excerpt': 'CTOS 是一个专为加密货币交易设计的量化交易管理系统，集成了多个主流交易所，提供实时账户监控、策略管理、技术指标分析等功能。',
                'category': '系统介绍',
                'tags': '系统,量化交易,介绍',
                'cover_image': 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80',
                'published_at': timezone.now() - timedelta(days=5),
            },
            {
                'title': '账户管理功能使用指南',
                'slug': 'account-management-guide',
                'content': '''
<h1>账户管理功能使用指南</h1>

<h2>功能概述</h2>
<p>账户管理是 CTOS 系统的核心功能之一，它允许您实时监控和管理多个交易所的账户信息。</p>

<h2>主要功能</h2>
<h3>1. 账户列表</h3>
<p>在账户列表页面，您可以：</p>
<ul>
<li>查看所有已配置的交易所账户</li>
<li>实时查看账户余额</li>
<li>查看账户健康状态</li>
<li>快速跳转到账户详情页面</li>
</ul>

<h3>2. 账户详情</h3>
<p>点击"查看详情"按钮，您可以查看：</p>
<ul>
<li><strong>账户概览</strong>：账户基本信息、总资产价值</li>
<li><strong>持仓信息</strong>：当前持仓列表、盈亏情况</li>
<li><strong>订单信息</strong>：历史订单、订单状态</li>
</ul>
                ''',
                'excerpt': '详细介绍 CTOS 系统中账户管理功能的使用方法，包括如何查看账户信息、监控余额变化、查看持仓和订单等。',
                'category': '使用指南',
                'tags': '账户管理,使用指南,教程',
                'cover_image': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&q=80',
                'published_at': timezone.now() - timedelta(days=4),
            },
            {
                'title': '技术指标分析功能详解',
                'slug': 'metrics-analysis-details',
                'content': '''
<h1>技术指标分析功能详解</h1>

<h2>功能简介</h2>
<p>CTOS 系统提供了强大的技术指标分析功能，帮助您更好地理解市场趋势和做出交易决策。</p>

<h2>核心指标</h2>
<h3>TOPDOGINDEX 指标</h3>
<p>TOPDOGINDEX 是 CTOS 系统的核心自定义指标，它通过多维度分析来评估市场趋势。</p>

<h3>特点</h3>
<ul>
<li><strong>多时间框架</strong>：支持 1m、5m、15m、1h、4h、1d 等多个时间周期</li>
<li><strong>多币种对比</strong>：可以同时查看多个币种的指标情况</li>
<li><strong>可视化展示</strong>：通过图表直观展示指标变化</li>
</ul>
                ''',
                'excerpt': '深入解析 CTOS 系统中的技术指标分析功能，包括 TOPDOGINDEX 指标、全币种趋势分析、K 线图表等高级功能的使用方法。',
                'category': '技术分析',
                'tags': '技术指标,分析,TOPDOGINDEX',
                'cover_image': 'https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=1200&q=80',
                'published_at': timezone.now() - timedelta(days=3),
            },
        ]

        created_count = 0
        updated_count = 0

        for article_data in sample_articles:
            slug = article_data['slug']
            
            # 检查是否已存在
            article, created = Article.objects.get_or_create(
                slug=slug,
                defaults={
                    'author': author,
                    **article_data
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ 创建文章: {article.title}')
                )
            else:
                # 更新现有文章
                for key, value in article_data.items():
                    if key != 'slug':
                        setattr(article, key, value)
                article.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'⚠ 更新文章: {article.title}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n完成！创建 {created_count} 篇文章，更新 {updated_count} 篇文章。'
            )
        )

