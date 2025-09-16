#!/bin/bash

echo "🚀 Git 自动提交助手 (Conventional Commit 规范)"
echo "--------------------------------------------"

# 1. 是否手动选择文件，还是默认全部
read -p "是否手动选择文件? (y/N): " choose_file
if [[ "$choose_file" == "y" || "$choose_file" == "Y" ]]; then
    read -p "请输入要提交的文件或目录(用空格分隔): " files
    git add $files
else
    git add .
fi

# 2. 选择 commit 类型
echo "请选择 commit 类型:"
options=(
  "feat     → ✨ 新功能 (feature)"
  "fix      → 🐛 修复 bug"
  "docs     → 📚 文档修改"
  "style    → 💅 格式调整（不影响逻辑，如缩进、空格）"
  "refactor → ♻️ 代码重构（非新增功能或修 bug）"
  "perf     → ⚡ 性能优化"
  "test     → ✅ 增加或修改测试"
  "chore    → 🔧 构建/工具相关的改动（无源码影响）"
  "ci       → 🤖 CI/CD 配置修改"
)
select type in "${options[@]}"; do
    if [[ -n "$type" ]]; then
        break
    fi
done

# 3. 输入 scope（可选）
read -p "请输入 scope（模块/目录，可选，回车跳过）: " scope
if [[ -n "$scope" ]]; then
    scope="($scope)"
fi

# 4. 简短描述
read -p "请输入简短描述: " desc

# 5. 提交正文（可多行，Ctrl+D 结束输入）
echo "请输入详细描述（可选，多行，结束请按 Ctrl+D）:"
body=$(</dev/stdin)

# 6. footer（比如 BREAKING CHANGE 或 issue 关联）
read -p "请输入 footer（可选，比如 Closes #123）: " footer

# 7. 拼接 commit message
commit_msg="$type$scope: $desc"
if [[ -n "$body" ]]; then
    commit_msg="$commit_msg\n\n$body"
fi
if [[ -n "$footer" ]]; then
    commit_msg="$commit_msg\n\n$footer"
fi

# 8. 执行 commit
echo -e "最终提交信息如下：\n--------------------------------"
echo -e "$commit_msg"
echo "--------------------------------"
read -p "确认提交? (Y/n): " confirm
if [[ "$confirm" != "n" && "$confirm" != "N" ]]; then
    git commit -m "$type$scope: $desc" -m "$body" -m "$footer"
    git push
    echo "✅ 已完成提交并推送"
else
    echo "❌ 已取消提交"
fi
	
