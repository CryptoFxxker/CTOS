"""
批量从 Markdown 文件导入文章的管理命令

使用方法:
    python manage.py import_all_markdown [--dir=articles] [--author=admin] [--update]
    
示例:
    python manage.py import_all_markdown
    python manage.py import_all_markdown --dir=/path/to/articles --author=admin --update
    
注意:
    - 如果不指定 --dir，将使用 settings.py 中的 ARTICLES_DIR 配置
    - 可以通过环境变量 ARTICLES_DIR 设置文章目录
"""
import os
import glob
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings


class Command(BaseCommand):
    help = '批量从目录中导入所有 Markdown 文件到资讯系统'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            type=str,
            default=None,
            help='Markdown 文件所在目录（如果不指定，将使用 settings.ARTICLES_DIR）'
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
            help='如果文章已存在，则更新而不是跳过'
        )

    def handle(self, *args, **options):
        # 获取文章目录：优先使用命令行参数，否则使用 settings 配置
        articles_dir = options['dir']
        if articles_dir is None:
            articles_dir = getattr(settings, 'ARTICLES_DIR', 'articles')
            self.stdout.write(
                self.style.SUCCESS(f'使用配置的文章目录: {articles_dir}')
            )
        
        author = options['author']
        update = options['update']

        # 检查目录是否存在
        if not os.path.exists(articles_dir):
            raise CommandError(f'目录不存在: {articles_dir}')

        # 查找所有 .md 文件
        md_files = glob.glob(os.path.join(articles_dir, '*.md'))
        
        # 排除 README.md
        md_files = [f for f in md_files if not os.path.basename(f).upper().startswith('README')]

        if not md_files:
            self.stdout.write(
                self.style.WARNING(f'在目录 {articles_dir} 中没有找到 Markdown 文件')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f'找到 {len(md_files)} 个 Markdown 文件，开始导入...\n')
        )

        success_count = 0
        error_count = 0

        for md_file in sorted(md_files):
            filename = os.path.basename(md_file)
            self.stdout.write(f'正在导入: {filename}...', ending=' ')
            
            try:
                # 调用 import_markdown 命令
                call_command(
                    'import_markdown',
                    md_file,
                    author=author,
                    update=update
                )
                success_count += 1
                self.stdout.write(self.style.SUCCESS('✓'))
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'✗ 错误: {e}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'\n完成！成功导入 {success_count} 篇文章，失败 {error_count} 篇。'
            )
        )

