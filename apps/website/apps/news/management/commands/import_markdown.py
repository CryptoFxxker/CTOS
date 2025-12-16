"""
从 Markdown 文件导入文章的管理命令

使用方法:
    python manage.py import_markdown <markdown_file_path> [--author=username] [--update]
    
示例:
    python manage.py import_markdown articles/my_article.md --author=admin
    python manage.py import_markdown articles/my_article.md --author=admin --update
"""
import os
import re
import yaml
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from apps.news.models import Article

try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


class Command(BaseCommand):
    help = '从 Markdown 文件导入文章到资讯系统'

    def add_arguments(self, parser):
        parser.add_argument(
            'markdown_file',
            type=str,
            help='Markdown 文件路径'
        )
        parser.add_argument(
            '--author',
            type=str,
            default='admin',
            help='作者用户名（默认：admin）'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='如果文章已存在（通过slug判断），则更新而不是创建新文章'
        )

    def handle(self, *args, **options):
        markdown_file = options['markdown_file']
        author_username = options['author']
        update_mode = options['update']

        # 检查文件是否存在
        if not os.path.exists(markdown_file):
            raise CommandError(f'文件不存在: {markdown_file}')

        # 获取作者
        try:
            author = User.objects.get(username=author_username)
        except User.DoesNotExist:
            raise CommandError(f'用户不存在: {author_username}')

        # 解析 Markdown 文件
        try:
            article_data = self.parse_markdown(markdown_file)
        except Exception as e:
            raise CommandError(f'解析 Markdown 文件失败: {e}')

        # 生成 slug（如果没有提供）
        if not article_data.get('slug'):
            article_data['slug'] = slugify(article_data['title'])

        # 检查是否已存在
        existing_article = None
        try:
            existing_article = Article.objects.get(slug=article_data['slug'])
        except Article.DoesNotExist:
            pass

        # 创建或更新文章
        if existing_article and update_mode:
            # 更新现有文章
            for key, value in article_data.items():
                if key != 'slug':  # 不更新 slug
                    setattr(existing_article, key, value)
            existing_article.save()
            self.stdout.write(
                self.style.SUCCESS(f'✓ 文章已更新: {existing_article.title}')
            )
        elif existing_article:
            raise CommandError(
                f'文章已存在（slug: {article_data["slug"]}）。使用 --update 参数来更新现有文章。'
            )
        else:
            # 创建新文章
            article = Article.objects.create(
                author=author,
                **article_data
            )
            self.stdout.write(
                self.style.SUCCESS(f'✓ 文章已创建: {article.title} (slug: {article.slug})')
            )

    def parse_markdown(self, file_path):
        """解析 Markdown 文件，提取 front matter 和内容"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 front matter（YAML 格式）
        front_matter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(front_matter_pattern, content, re.DOTALL)

        if match:
            front_matter_text = match.group(1)
            markdown_content = match.group(2)
            
            try:
                front_matter = yaml.safe_load(front_matter_text) or {}
            except yaml.YAMLError as e:
                raise ValueError(f'Front matter YAML 解析错误: {e}')
        else:
            # 没有 front matter，使用文件名和内容
            front_matter = {}
            markdown_content = content
            # 从文件名提取标题
            filename = os.path.basename(file_path)
            front_matter['title'] = os.path.splitext(filename)[0]

        # 提取标题（优先使用 front matter，否则从内容第一行提取）
        title = front_matter.get('title')
        if not title:
            # 尝试从 Markdown 内容的第一行提取标题（# 开头的行）
            first_line = markdown_content.strip().split('\n')[0]
            if first_line.startswith('#'):
                title = first_line.lstrip('#').strip()
            else:
                title = os.path.splitext(os.path.basename(file_path))[0]

        # 提取摘要（优先使用 front matter，否则从内容前几行提取）
        excerpt = front_matter.get('excerpt', '')
        if not excerpt:
            # 从内容中提取前 200 个字符作为摘要
            text_content = re.sub(r'[#*`\[\]]', '', markdown_content).strip()
            excerpt = text_content[:200] + '...' if len(text_content) > 200 else text_content

        # 将 Markdown 转换为 HTML（简单转换，保留换行）
        html_content = self.markdown_to_html(markdown_content)

        # 解析发布时间
        published_at = timezone.now()
        if front_matter.get('published_at'):
            try:
                if isinstance(front_matter['published_at'], str):
                    published_at = datetime.fromisoformat(front_matter['published_at'].replace('Z', '+00:00'))
                    if timezone.is_naive(published_at):
                        published_at = timezone.make_aware(published_at)
                else:
                    published_at = front_matter['published_at']
            except (ValueError, TypeError):
                pass

        # 构建文章数据
        article_data = {
            'title': title,
            'slug': front_matter.get('slug', ''),
            'content': html_content,
            'excerpt': excerpt,
            'cover_image': front_matter.get('cover_image', ''),
            'category': front_matter.get('category', '未分类'),
            'tags': front_matter.get('tags', ''),
            'is_published': front_matter.get('is_published', True),
            'published_at': published_at,
        }

        return article_data

    def markdown_to_html(self, markdown_text):
        """将 Markdown 文本转换为 HTML"""
        if MARKDOWN_AVAILABLE:
            # 使用 markdown 库进行转换
            md = markdown.Markdown(extensions=['extra', 'codehilite', 'tables', 'nl2br'])
            html = md.convert(markdown_text)
            return html
        else:
            # 降级到简单实现
            return self._simple_markdown_to_html(markdown_text)
    
    def _simple_markdown_to_html(self, markdown_text):
        """简单的 Markdown 到 HTML 转换（备用方案）"""
        html = markdown_text
        
        # 标题转换
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # 粗体
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
        
        # 斜体
        html = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html)
        html = re.sub(r'(?<!_)_(?!_)(.*?)(?<!_)_(?!_)', r'<em>\1</em>', html)
        
        # 代码块
        html = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code>\2</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        
        # 链接
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)
        
        # 列表
        lines = html.split('\n')
        result = []
        in_list = False
        list_type = None
        
        for line in lines:
            if re.match(r'^[\*\-\+] ', line):
                if not in_list or list_type != 'ul':
                    if in_list:
                        result.append(f'</{list_type}>')
                    result.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                result.append(f'<li>{line[2:].strip()}</li>')
            elif re.match(r'^\d+\. ', line):
                if not in_list or list_type != 'ol':
                    if in_list:
                        result.append(f'</{list_type}>')
                    result.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                # 提取列表项内容（移除数字和点）
                list_content = re.sub(r'^\d+\. ', '', line).strip()
                result.append(f'<li>{list_content}</li>')
            else:
                if in_list:
                    result.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                if line.strip() and not line.strip().startswith('<'):
                    result.append(f'<p>{line}</p>')
                elif line.strip():
                    result.append(line)
                else:
                    result.append('')
        
        if in_list:
            result.append(f'</{list_type}>')
        
        html = '\n'.join(result)
        
        return html

