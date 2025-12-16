from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    # 管理页面
    path('admin/manage/', views.admin_manage_view, name='admin_manage'),
    # API 接口
    path('api/invite-code/create/', views.api_create_invite_code, name='api_create_invite_code'),
    path('api/invite-code/<int:invite_id>/update/', views.api_update_invite_code, name='api_update_invite_code'),
    path('api/invite-code/<int:invite_id>/delete/', views.api_delete_invite_code, name='api_delete_invite_code'),
    path('api/invite-code/<int:invite_id>/users/', views.api_get_invite_code_users, name='api_get_invite_code_users'),
    # 也可以使用 Django 内置的视图
    # path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    # path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

