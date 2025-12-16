// 管理页面 JavaScript

// 标签页切换
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        const tabName = this.dataset.tab;
        
        // 更新按钮状态
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        
        // 更新内容显示
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');
    });
});

// 创建邀请码按钮
document.getElementById('create-invite-btn')?.addEventListener('click', function() {
    document.getElementById('modal-title').textContent = '创建邀请码';
    document.getElementById('invite-form').reset();
    document.getElementById('invite-id').value = '';
    document.getElementById('active-group').style.display = 'none';
    document.getElementById('invite-modal').style.display = 'block';
});

// 编辑邀请码
function editInviteCode(inviteId) {
    // 从表格中获取数据
    const row = document.querySelector(`tr[data-invite-id="${inviteId}"]`);
    if (!row) return;
    
    const cells = row.querySelectorAll('td');
    const code = cells[0].textContent.trim();
    const expiresText = cells[3].textContent.trim();
    const usesText = cells[4].textContent.trim();
    const note = cells[6].textContent.trim();
    
    // 解析使用次数
    const [used, maxUses] = usesText.split('/').map(s => parseInt(s.trim()));
    
    // 解析过期时间
    let days = null;
    if (expiresText !== '永不过期') {
        // 这里需要从后端获取准确的过期时间来计算天数
        // 暂时留空，让用户重新输入
    }
    
    document.getElementById('modal-title').textContent = `编辑邀请码: ${code}`;
    document.getElementById('invite-id').value = inviteId;
    document.getElementById('max-uses').value = maxUses;
    document.getElementById('days').value = days || '';
    document.getElementById('note').value = note === '-' ? '' : note;
    document.getElementById('active-group').style.display = 'block';
    
    // 检查状态
    const statusBadge = cells[5].querySelector('.status-badge');
    const isActive = !statusBadge.textContent.includes('已禁用');
    document.getElementById('is-active').checked = isActive;
    
    document.getElementById('invite-modal').style.display = 'block';
}

// 删除邀请码
function deleteInviteCode(inviteId, code) {
    if (!confirm(`确定要删除邀请码 "${code}" 吗？\n此操作不可恢复！`)) {
        return;
    }
    
    fetch(`/auth/api/invite-code/${inviteId}/delete/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('邀请码已删除');
            location.reload();
        } else {
            alert('删除失败: ' + data.error);
        }
    })
    .catch(error => {
        alert('删除失败: ' + error.message);
    });
}

// 查看邀请码使用者
function viewInviteUsers(inviteId) {
    document.getElementById('users-modal').style.display = 'block';
    document.getElementById('users-list').innerHTML = '<p>加载中...</p>';
    
    fetch(`/auth/api/invite-code/${inviteId}/users/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const users = data.users;
                if (users.length === 0) {
                    document.getElementById('users-list').innerHTML = '<p>暂无使用者</p>';
                } else {
                    let html = '<table class="data-table"><thead><tr><th>用户名</th><th>邮箱</th><th>注册时间</th><th>状态</th></tr></thead><tbody>';
                    users.forEach(user => {
                        html += `
                            <tr>
                                <td>${user.username}</td>
                                <td>${user.email || '-'}</td>
                                <td>${new Date(user.date_joined).toLocaleString('zh-CN')}</td>
                                <td>${user.is_active ? '<span class="status-badge status-active">✅ 活跃</span>' : '<span class="status-badge status-cancelled">❌ 禁用</span>'}</td>
                            </tr>
                        `;
                    });
                    html += '</tbody></table>';
                    document.getElementById('users-list').innerHTML = html;
                }
            } else {
                document.getElementById('users-list').innerHTML = '<p>加载失败: ' + data.error + '</p>';
            }
        })
        .catch(error => {
            document.getElementById('users-list').innerHTML = '<p>加载失败: ' + error.message + '</p>';
        });
}

// 提交表单
document.getElementById('invite-form')?.addEventListener('submit', function(e) {
    e.preventDefault();
    
    const inviteId = document.getElementById('invite-id').value;
    const maxUses = parseInt(document.getElementById('max-uses').value);
    const days = document.getElementById('days').value ? parseInt(document.getElementById('days').value) : null;
    const note = document.getElementById('note').value.trim();
    const isActive = document.getElementById('is-active').checked;
    
    const data = {
        max_uses: maxUses,
        days: days,
        note: note
    };
    
    if (inviteId) {
        // 编辑模式
        data.is_active = isActive;
        
        fetch(`/auth/api/invite-code/${inviteId}/update/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                alert('邀请码更新成功');
                location.reload();
            } else {
                alert('更新失败: ' + result.error);
            }
        })
        .catch(error => {
            alert('更新失败: ' + error.message);
        });
    } else {
        // 创建模式
        fetch('/auth/api/invite-code/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                alert(`邀请码创建成功！\n邀请码: ${result.invite_code.code}`);
                location.reload();
            } else {
                alert('创建失败: ' + result.error);
            }
        })
        .catch(error => {
            alert('创建失败: ' + error.message);
        });
    }
});

// 关闭模态框
function closeModal() {
    document.getElementById('invite-modal').style.display = 'none';
}

function closeUsersModal() {
    document.getElementById('users-modal').style.display = 'none';
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const inviteModal = document.getElementById('invite-modal');
    const usersModal = document.getElementById('users-modal');
    if (event.target === inviteModal) {
        closeModal();
    }
    if (event.target === usersModal) {
        closeUsersModal();
    }
}

// 获取 CSRF Token
function getCSRFToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') {
            return value;
        }
    }
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
        return metaToken.getAttribute('content');
    }
    return '';
}

