from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta
import json
from .models import InviteCode

def login_view(request):
    """用户登录视图"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'欢迎回来，{user.username}！')
                # 重定向到之前访问的页面，如果没有则重定向到主页
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            else:
                messages.error(request, '用户名或密码错误')
        else:
            messages.error(request, '请填写用户名和密码')
    
    return render(request, 'auth/login.html')

def register_view(request):
    """用户注册视图（需要邀请码）"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        invite_code = request.POST.get('invite_code', '').strip().upper()
        
        # 验证必填字段
        if not all([username, email, password, password_confirm, invite_code]):
            messages.error(request, '请填写所有必填字段')
            return render(request, 'auth/register.html')
        
        # 验证密码匹配
        if password != password_confirm:
            messages.error(request, '两次输入的密码不一致')
            return render(request, 'auth/register.html')
        
        # 验证密码长度
        if len(password) < 8:
            messages.error(request, '密码长度至少为8个字符')
            return render(request, 'auth/register.html')
        
        # 验证用户名是否已存在
        if User.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在，请选择其他用户名')
            return render(request, 'auth/register.html')
        
        # 验证邮箱是否已存在
        if User.objects.filter(email=email).exists():
            messages.error(request, '该邮箱已被注册')
            return render(request, 'auth/register.html')
        
        # 验证邀请码
        try:
            invite = InviteCode.objects.get(code=invite_code)
            if not invite.is_valid():
                if invite.is_expired():
                    messages.error(request, '邀请码已过期')
                elif invite.is_exhausted():
                    messages.error(request, '邀请码已被使用完')
                else:
                    messages.error(request, '邀请码无效')
                return render(request, 'auth/register.html')
        except InviteCode.DoesNotExist:
            messages.error(request, '邀请码不存在')
            return render(request, 'auth/register.html')
        
        # 创建用户
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            # 使用邀请码
            invite.use(user)
            messages.success(request, f'注册成功！欢迎，{user.username}！')
            # 自动登录
            login(request, user)
            return redirect('home')
        except Exception as e:
            messages.error(request, f'注册失败：{str(e)}')
            return render(request, 'auth/register.html')
    
    return render(request, 'auth/register.html')

@login_required
def logout_view(request):
    """用户登出视图"""
    logout(request)
    messages.success(request, '您已成功退出登录')
    return redirect('home')

def is_superuser(user):
    """检查用户是否为超级用户"""
    return user.is_authenticated and user.is_superuser

@login_required
@user_passes_test(is_superuser)
def admin_manage_view(request):
    """超级用户管理页面"""
    # 获取所有邀请码
    invite_codes = InviteCode.objects.all().order_by('-created_at')
    
    # 获取所有用户
    users = User.objects.all().order_by('-date_joined')
    
    # 统计信息
    stats = {
        'total_invite_codes': InviteCode.objects.count(),
        'active_invite_codes': InviteCode.objects.filter(is_active=True).count(),
        'total_users': User.objects.count(),
        'recent_users': User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count(),
    }
    
    return render(request, 'auth/admin_manage.html', {
        'invite_codes': invite_codes,
        'users': users,
        'stats': stats
    })

@csrf_exempt
@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def api_create_invite_code(request):
    """API: 创建邀请码"""
    try:
        data = json.loads(request.body)
        max_uses = int(data.get('max_uses', 1))
        days = data.get('days', None)
        note = data.get('note', '').strip()
        
        # 计算过期时间
        expires_at = None
        if days:
            expires_at = timezone.now() + timedelta(days=int(days))
        
        # 创建邀请码
        invite = InviteCode.objects.create(
            code=InviteCode.generate_code(),
            created_by=request.user,
            max_uses=max_uses,
            expires_at=expires_at,
            note=note,
            is_active=True
        )
        
        return JsonResponse({
            'success': True,
            'message': '邀请码创建成功',
            'invite_code': {
                'id': invite.id,
                'code': invite.code,
                'max_uses': invite.max_uses,
                'expires_at': invite.expires_at.isoformat() if invite.expires_at else None,
                'note': invite.note,
                'is_valid': invite.is_valid(),
                'created_at': invite.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

@csrf_exempt
@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def api_update_invite_code(request, invite_id):
    """API: 更新邀请码"""
    try:
        invite = InviteCode.objects.get(id=invite_id)
        data = json.loads(request.body)
        
        # 更新字段
        if 'max_uses' in data:
            invite.max_uses = int(data['max_uses'])
        if 'days' in data:
            days = data['days']
            if days:
                invite.expires_at = timezone.now() + timedelta(days=int(days))
            else:
                invite.expires_at = None
        if 'note' in data:
            invite.note = data['note'].strip()
        if 'is_active' in data:
            invite.is_active = bool(data['is_active'])
        
        invite.save()
        
        return JsonResponse({
            'success': True,
            'message': '邀请码更新成功',
            'invite_code': {
                'id': invite.id,
                'code': invite.code,
                'max_uses': invite.max_uses,
                'expires_at': invite.expires_at.isoformat() if invite.expires_at else None,
                'note': invite.note,
                'is_active': invite.is_active,
                'is_valid': invite.is_valid(),
            }
        })
    except InviteCode.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '邀请码不存在'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

@csrf_exempt
@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def api_delete_invite_code(request, invite_id):
    """API: 删除邀请码"""
    try:
        invite = InviteCode.objects.get(id=invite_id)
        code = invite.code
        invite.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'邀请码 {code} 已删除'
        })
    except InviteCode.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '邀请码不存在'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

@login_required
@user_passes_test(is_superuser)
@require_http_methods(["GET"])
def api_get_invite_code_users(request, invite_id):
    """API: 获取使用邀请码的用户列表"""
    try:
        invite = InviteCode.objects.get(id=invite_id)
        users = invite.used_by.all()
        
        return JsonResponse({
            'success': True,
            'users': [{
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat(),
                'is_active': user.is_active,
            } for user in users]
        })
    except InviteCode.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '邀请码不存在'
        }, status=404)
