from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from apps.auth.models import InviteCode


class Command(BaseCommand):
    help = '创建邀请码'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=1,
            help='要创建的邀请码数量（默认：1）'
        )
        parser.add_argument(
            '--max-uses',
            type=int,
            default=1,
            help='每个邀请码的最大使用次数（默认：1）'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='邀请码有效期（天数），不指定则永不过期'
        )
        parser.add_argument(
            '--creator',
            type=str,
            default=None,
            help='创建者用户名（可选）'
        )
        parser.add_argument(
            '--note',
            type=str,
            default='',
            help='备注信息'
        )

    def handle(self, *args, **options):
        count = options['count']
        max_uses = options['max_uses']
        days = options['days']
        creator_username = options['creator']
        note = options['note']

        # 获取创建者
        creator = None
        if creator_username:
            try:
                creator = User.objects.get(username=creator_username)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'警告：用户 "{creator_username}" 不存在，将不设置创建者')
                )

        # 计算过期时间
        expires_at = None
        if days:
            expires_at = timezone.now() + timedelta(days=days)

        # 创建邀请码
        created_codes = []
        for i in range(count):
            code = InviteCode.generate_code()
            invite = InviteCode.objects.create(
                code=code,
                created_by=creator,
                max_uses=max_uses,
                expires_at=expires_at,
                note=note
            )
            created_codes.append(invite)

        # 输出结果
        self.stdout.write(self.style.SUCCESS(f'\n成功创建 {count} 个邀请码：\n'))
        for invite in created_codes:
            expires_info = ''
            if invite.expires_at:
                expires_info = f'，过期时间：{invite.expires_at.strftime("%Y-%m-%d %H:%M:%S")}'
            else:
                expires_info = '，永不过期'
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'  邀请码：{invite.code} '
                    f'（最大使用次数：{invite.max_uses}{expires_info}）'
                )
            )
        
        self.stdout.write(self.style.SUCCESS('\n邀请码已创建完成！'))

