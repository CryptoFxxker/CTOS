#!/usr/bin/env python
"""
批量创建用户的脚本
使用方法: python create_users.py
"""
import os
import sys
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'website.settings')
django.setup()

from django.contrib.auth.models import User

def create_user(username, email, password, is_superuser=False, is_staff=False):
    """
    创建用户
    
    Args:
        username: 用户名
        email: 邮箱
        password: 密码
        is_superuser: 是否为超级用户
        is_staff: 是否可以访问 Admin 后台
    """
    if User.objects.filter(username=username).exists():
        print(f"⚠ 用户 {username} 已存在，跳过")
        return None
    
    try:
        if is_superuser:
            user = User.objects.create_superuser(username, email, password)
            print(f"✓ 超级用户 {username} 创建成功")
        else:
            user = User.objects.create_user(username, email, password)
            if is_staff:
                user.is_staff = True
                user.save()
            print(f"✓ 用户 {username} 创建成功")
        return user
    except Exception as e:
        print(f"✗ 创建用户 {username} 失败: {e}")
        return None

def list_users():
    """列出所有用户"""
    users = User.objects.all()
    if not users:
        print("当前没有用户")
        return
    
    print("\n当前用户列表:")
    print("-" * 60)
    print(f"{'用户名':<20} {'邮箱':<30} {'超级用户':<10} {'Staff':<10}")
    print("-" * 60)
    for user in users:
        print(f"{user.username:<20} {user.email or 'N/A':<30} {'是' if user.is_superuser else '否':<10} {'是' if user.is_staff else '否':<10}")
    print("-" * 60)

if __name__ == '__main__':
    print("=" * 60)
    print("CTOS 网站用户管理脚本")
    print("=" * 60)
    
    # 显示当前用户
    list_users()
    
    print("\n开始创建用户...")
    print("-" * 60)
    
    # 创建默认管理员（如果不存在）
    # 注意：请修改密码！
    create_user(
        username='admin',
        email='admin@ctos.com',
        password='admin123',  # ⚠️ 请修改为强密码！
        is_superuser=True,
        is_staff=True
    )
    
    # 可以在这里添加更多用户
    # create_user('user1', 'user1@ctos.com', 'user123')
    # create_user('user2', 'user2@ctos.com', 'user123', is_staff=True)
    
    print("\n" + "=" * 60)
    print("用户创建完成！")
    print("=" * 60)
    
    # 再次显示用户列表
    list_users()
    
    print("\n⚠️  重要提示:")
    print("1. 请立即修改默认密码！")
    print("2. 使用命令: python manage.py changepassword admin")
    print("3. 或访问 Admin 后台修改: http://服务器IP:8000/admin/")

