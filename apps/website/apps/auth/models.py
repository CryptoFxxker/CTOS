from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets


class InviteCode(models.Model):
    """邀请码模型"""
    code = models.CharField(max_length=32, unique=True, verbose_name='邀请码')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_invite_codes',
        verbose_name='创建者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')
    max_uses = models.IntegerField(default=1, verbose_name='最大使用次数')
    used_count = models.IntegerField(default=0, verbose_name='已使用次数')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
    used_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='used_invite_codes',
        blank=True,
        verbose_name='使用者'
    )
    note = models.CharField(max_length=200, blank=True, verbose_name='备注')

    class Meta:
        verbose_name = '邀请码'
        verbose_name_plural = '邀请码'
        ordering = ['-created_at']

    def __str__(self):
        status = '已过期' if self.is_expired() else ('已用完' if self.is_exhausted() else '可用')
        return f'{self.code} ({status})'

    @classmethod
    def generate_code(cls, length=16):
        """生成随机邀请码"""
        return secrets.token_urlsafe(length)[:length].upper().replace('-', '').replace('_', '')

    def is_expired(self):
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    def is_exhausted(self):
        """检查是否已用完"""
        return self.used_count >= self.max_uses

    def is_valid(self):
        """检查邀请码是否有效"""
        return self.is_active and not self.is_expired() and not self.is_exhausted()

    def use(self, user):
        """使用邀请码"""
        if not self.is_valid():
            return False
        self.used_count += 1
        self.used_by.add(user)
        self.save()
        return True

