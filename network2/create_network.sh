#!/bin/bash

# 确保脚本以root权限运行
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用sudo或root权限运行此脚本"
    exit 1
fi

# 定义labctl.py的路径（根据实际路径修改，这里使用当前目录）
LABCTL="./labctl.py"

# 检查labctl.py是否存在
if [ ! -f "$LABCTL" ]; then
    echo "未找到labctl.py，请检查路径是否正确"
    exit 1
fi

# 创建节点（netns）
echo "创建节点..."
python3 "$LABCTL" create-node sw1
python3 "$LABCTL" create-node sw2
python3 "$LABCTL" create-node h1
python3 "$LABCTL" create-node h2

# 创建链路
echo "创建链路..."
python3 "$LABCTL" create-link h1 h1-eth1 sw1 sw1-eth1
python3 "$LABCTL" create-link sw1 sw1-eth2 sw2 sw2-eth1
python3 "$LABCTL" create-link sw2 sw2-eth2 h2 h2-eth1

# 分配IP地址
echo "分配IP地址..."
python3 "$LABCTL" assign-ip h1 h1-eth1 10.0.0.1/24
python3 "$LABCTL" assign-ip h2 h2-eth1 10.0.0.2/24

echo "网络环境创建完成"
