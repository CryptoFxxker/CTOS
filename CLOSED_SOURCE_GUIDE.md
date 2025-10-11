# 闭源处理完整指南

## 🎯 目标
将 `apps/strategies/hedge/` 和 `apps/strategies/grid/` 目录从开源项目中完全移除。

## 📋 处理方案

### 方案1：基础清理（推荐先执行）
**脚本**: `complete_cleanup.sh`
**作用**: 删除本地敏感目录，更新.gitignore，提交更改

```bash
# 执行基础清理
./complete_cleanup.sh
```

**结果**:
- ✅ 删除本地敏感目录
- ✅ 更新.gitignore防止未来提交
- ✅ 创建备份分支
- ✅ 提交更改到Git

### 方案2：历史清理（如果需要完全移除历史）
**脚本**: `clean_history.sh`
**作用**: 从Git历史中完全移除敏感目录

```bash
# 执行历史清理
./clean_history.sh
```

**结果**:
- ✅ 从所有Git提交中移除敏感目录
- ✅ 重写Git历史
- ✅ 需要强制推送
- ✅ 协作者需要重新克隆

## 🚀 执行步骤

### 第一步：基础清理
```bash
# 1. 执行基础清理
./complete_cleanup.sh

# 2. 检查结果
git status
git log --oneline -3

# 3. 推送到远程
git push origin main
```

### 第二步：检查是否需要历史清理
```bash
# 检查敏感目录是否在历史中
git log --oneline --name-only | grep -E "apps/strategies/(hedge|grid)"
```

**如果输出为空**：说明敏感目录不在历史中，清理完成！

**如果有输出**：需要执行历史清理

### 第三步：历史清理（可选）
```bash
# 1. 执行历史清理
./clean_history.sh

# 2. 强制推送到远程
git push --force-with-lease origin main

# 3. 通知协作者重新克隆
```

## 🔍 验证清理结果

### 检查本地文件
```bash
# 检查敏感目录是否已删除
ls -la apps/strategies/
# 应该只看到其他目录，不包含hedge和grid
```

### 检查Git状态
```bash
# 检查Git状态
git status
# 应该显示"working tree clean"

# 检查提交历史
git log --oneline -5
# 应该看到清理相关的提交
```

### 检查.gitignore
```bash
# 检查.gitignore是否包含敏感目录
grep -A 5 "敏感策略目录" .gitignore
# 应该看到hedge和grid目录被忽略
```

### 检查历史记录
```bash
# 检查敏感目录是否还在历史中
git log --oneline --name-only | grep -E "apps/strategies/(hedge|grid)"
# 如果执行了历史清理，应该没有输出
```

## 🛡️ 预防措施

### 1. 本地忽略配置
创建 `.git/info/exclude` 文件：
```
# 本地忽略文件（不提交到仓库）
apps/strategies/hedge/
apps/strategies/grid/
```

### 2. Git钩子检查
创建 `.git/hooks/pre-commit`：
```bash
#!/bin/bash
# 检查是否包含敏感目录
if git diff --cached --name-only | grep -E "apps/strategies/(hedge|grid)"; then
    echo "❌ 错误：检测到敏感目录文件，请检查后再提交"
    exit 1
fi
```

### 3. 定期检查
```bash
# 定期检查是否有敏感文件被跟踪
git ls-files | grep -E "apps/strategies/(hedge|grid)"
# 应该没有输出
```

## 📊 清理前后对比

### 清理前
```
apps/strategies/
├── hedge/                    # 敏感目录
│   ├── MartingHedgeGrid.py
│   ├── ProgressiveHedgeGrid.py
│   └── ...
└── grid/                     # 敏感目录
    ├── Grid_with_more_gap.py
    └── ...
```

### 清理后
```
apps/strategies/
└── (其他非敏感目录)
```

## ⚠️ 重要提醒

1. **备份确认**: 确保敏感文件已备份到安全位置
2. **协作者通知**: 如果执行历史清理，需要通知所有协作者
3. **测试验证**: 在推送前验证清理结果
4. **持续监控**: 定期检查是否意外提交敏感文件

## 🔄 恢复方法

如果需要恢复敏感目录：
```bash
# 切换到备份分支
git checkout backup-before-cleanup-YYYYMMDD_HHMMSS

# 复制敏感目录到新位置
cp -r apps/strategies/hedge /path/to/safe/location/
cp -r apps/strategies/grid /path/to/safe/location/
```

## 📞 技术支持

如果遇到问题：
1. 检查Git状态：`git status`
2. 查看提交历史：`git log --oneline`
3. 恢复备份分支：`git checkout backup-*`
4. 重置到清理前：`git reset --hard HEAD~1`
