#!/bin/bash

# 确保脚本以root权限运行
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用sudo或root权限运行此脚本"
    exit 1
fi

# 定义labctl.py的路径（与创建脚本保持一致）
LABCTL="./labctl.py"

# 检查labctl.py是否存在
if [ ! -f "$LABCTL" ]; then
    echo "未找到labctl.py，请检查路径是否正确"
    exit 1
fi

# 清除节点（netns）
echo "清除节点..."
python3 "$LABCTL" delete-node sw1 2>/dev/null  # 忽略不存在的错误
python3 "$LABCTL" delete-node sw2 2>/dev/null
python3 "$LABCTL" delete-node h1 2>/dev/null
python3 "$LABCTL" delete-node h2 2>/dev/null

# （可选）如果labctl有单独的清除链路命令，可在此添加
# 若delete-node已自动清除关联链路，则无需额外操作

echo "网络环境已清除"
