#!/usr/bin/env python
"""
创建超级用户的脚本
使用方法: python create_superuser.py
"""
import os
import sys
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'website.settings')
django.setup()

from django.contrib.auth.models import User

def create_superuser(username, email, password):
    """创建超级用户"""
    if User.objects.filter(username=username).exists():
        print(f"⚠ 用户 {username} 已存在")
        user = User.objects.get(username=username)
        if not user.is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save()
            print(f"✓ 已将用户 {username} 设置为超级用户")
        else:
            print(f"✓ 用户 {username} 已经是超级用户")
        return user
    
    try:
        user = User.objects.create_superuser(username, email, password)
        print(f"✓ 超级用户 {username} 创建成功")
        return user
    except Exception as e:
        print(f"✗ 创建超级用户失败: {e}")
        return None

if __name__ == '__main__':
    print("=" * 60)
    print("创建 Django 超级用户")
    print("=" * 60)
    
    # 默认配置（可以修改）
    username = 'admin'
    email = 'admin@ctos.com'
    password = 'admin123'  # ⚠️ 请修改为强密码！
    
    print(f"\n将创建以下超级用户：")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")
    print(f"  密码: {password}")
    print(f"\n⚠️  警告：默认密码不安全，请在生产环境中修改！")
    
    # 确认
    confirm = input("\n是否继续？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        sys.exit(0)
    
    create_superuser(username, email, password)
    
    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)
    print(f"\n现在可以使用以下信息登录 Django Admin：")
    print(f"  URL: http://你的服务器IP:8000/admin/")
    print(f"  用户名: {username}")
    print(f"  密码: {password}")
    print(f"\n⚠️  重要：登录后请立即修改密码！")

