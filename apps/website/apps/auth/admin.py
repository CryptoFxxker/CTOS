from django.contrib import admin
from .models import InviteCode


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'created_by', 'created_at', 'expires_at', 'used_count', 'max_uses', 'is_active', 'is_valid_display']
    list_filter = ['is_active', 'created_at', 'expires_at']
    search_fields = ['code', 'note', 'created_by__username']
    readonly_fields = ['code', 'created_at', 'used_count', 'used_by_list']
    fieldsets = (
        ('基本信息', {
            'fields': ('code', 'created_by', 'created_at', 'note')
        }),
        ('使用限制', {
            'fields': ('max_uses', 'used_count', 'expires_at', 'is_active')
        }),
        ('使用记录', {
            'fields': ('used_by_list',),
            'classes': ('collapse',)
        }),
    )

    def is_valid_display(self, obj):
        """显示邀请码是否有效"""
        if not obj.is_active:
            return '❌ 已禁用'
        if obj.is_expired():
            return '❌ 已过期'
        if obj.is_exhausted():
            return '❌ 已用完'
        return '✅ 可用'
    is_valid_display.short_description = '状态'

    def used_by_list(self, obj):
        """显示使用该邀请码的用户列表"""
        users = obj.used_by.all()
        if users:
            return ', '.join([user.username for user in users])
        return '暂无'
    used_by_list.short_description = '使用者'

    def save_model(self, request, obj, form, change):
        """保存时自动设置创建者"""
        if not change:  # 新建时
            if not obj.code:
                obj.code = InviteCode.generate_code()
            if not obj.created_by:
                obj.created_by = request.user
        super().save_model(request, obj, form, change)

