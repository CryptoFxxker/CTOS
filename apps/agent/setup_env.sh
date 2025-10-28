#!/bin/bash
# Ollama Client 环境变量设置脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}===================================================${NC}"
echo -e "${GREEN}    Ollama Client 环境变量设置${NC}"
echo -e "${GREEN}===================================================${NC}"
echo ""

# 提示用户输入服务器地址
echo -e "${YELLOW}请输入你的 Ollama 服务器地址（例如：http://localhost:11434）：${NC}"
read -p "OLLAMA_BASE_URL [默认: http://localhost:11434]: " ollama_url

# 如果未输入，使用默认值
if [ -z "$ollama_url" ]; then
    ollama_url="http://localhost:11434"
fi

# 提示用户输入模型名称
echo -e "${YELLOW}请输入模型名称：${NC}"
read -p "OLLAMA_MODEL [默认: deepseek-r1:32b]: " ollama_model

# 如果未输入，使用默认值
if [ -z "$ollama_model" ]; then
    ollama_model="deepseek-r1:32b"
fi

# 显示设置
echo ""
echo -e "${GREEN}环境变量设置如下：${NC}"
echo "OLLAMA_BASE_URL=$ollama_url"
echo "OLLAMA_MODEL=$ollama_model"
echo ""

# 询问是否写入 .bashrc 或 .zshrc
echo -e "${YELLOW}是否要将这些设置写入配置文件中？(y/n)${NC}"
read -p "输入选择: " write_config

if [ "$write_config" = "y" ] || [ "$write_config" = "Y" ]; then
    # 检测 shell 类型
    if [ -n "$ZSH_VERSION" ]; then
        config_file="$HOME/.zshrc"
    else
        config_file="$HOME/.bashrc"
    fi
    
    echo ""
    echo -e "${YELLOW}将写入到: $config_file${NC}"
    
    # 添加环境变量
    cat >> "$config_file" << EOF

# Ollama Client 环境变量设置
export OLLAMA_BASE_URL="$ollama_url"
export OLLAMA_MODEL="$ollama_model"
EOF
    
    echo -e "${GREEN}✓ 已写入配置文件！${NC}"
    echo -e "${YELLOW}请运行以下命令使配置生效：${NC}"
    echo "source $config_file"
    echo ""
    echo -e "${GREEN}或者运行以下命令直接在当前会话中使用：${NC}"
    echo "export OLLAMA_BASE_URL=\"$ollama_url\""
    echo "export OLLAMA_MODEL=\"$ollama_model\""
else
    echo ""
    echo -e "${GREEN}手动设置环境变量命令：${NC}"
    echo "export OLLAMA_BASE_URL=\"$ollama_url\""
    echo "export OLLAMA_MODEL=\"$ollama_model\""
    echo ""
    echo -e "${YELLOW}或者在当前会话中直接运行上面的命令。${NC}"
fi

echo ""
echo -e "${GREEN}设置完成！${NC}"

