from django.apps import AppConfig


class AuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auth'
    label = 'website_auth'  # 使用不同的标签避免与 django.contrib.auth 冲突
    verbose_name = '网站认证'

