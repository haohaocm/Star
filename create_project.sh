#!/bin/bash

# L3 Switch Project Setup Script
# 用于在Ubuntu中自动创建项目目录结构

set -e  # 遇到错误立即退出

PROJECT_NAME="l3_switch"
BASE_DIR=$(pwd)/$PROJECT_NAME

echo "======================================"
echo "Creating L3 Switch Project Structure"
echo "======================================"

# 创建项目根目录
echo "Creating project directory: $BASE_DIR"
mkdir -p "$BASE_DIR"

# 创建目录结构
echo "Creating directory structure..."

# 核心模块
mkdir -p "$BASE_DIR/core"
mkdir -p "$BASE_DIR/layer2"
mkdir -p "$BASE_DIR/layer3"
mkdir -p "$BASE_DIR/protocols"
mkdir -p "$BASE_DIR/utils"

# 测试目录
mkdir -p "$BASE_DIR/tests"
mkdir -p "$BASE_DIR/tests/unit"
mkdir -p "$BASE_DIR/tests/integration"

# 配置和日志目录
mkdir -p "$BASE_DIR/config"
mkdir -p "$BASE_DIR/logs"

# 文档目录
mkdir -p "$BASE_DIR/docs"

# 创建 __init__.py 文件
echo "Creating __init__.py files..."
touch "$BASE_DIR/__init__.py"
touch "$BASE_DIR/core/__init__.py"
touch "$BASE_DIR/layer2/__init__.py"
touch "$BASE_DIR/layer3/__init__.py"
touch "$BASE_DIR/protocols/__init__.py"
touch "$BASE_DIR/utils/__init__.py"
touch "$BASE_DIR/tests/__init__.py"
touch "$BASE_DIR/tests/unit/__init__.py"
touch "$BASE_DIR/tests/integration/__init__.py"

# 创建空的源文件
echo "Creating source files..."

# Core
touch "$BASE_DIR/core/switch_core.py"
touch "$BASE_DIR/core/port.py"

# Layer 2
touch "$BASE_DIR/layer2/mac_table.py"
touch "$BASE_DIR/layer2/vlan.py"
touch "$BASE_DIR/layer2/stp.py"

# Layer 3
touch "$BASE_DIR/layer3/arp_table.py"
touch "$BASE_DIR/layer3/routing.py"
touch "$BASE_DIR/layer3/ip_handler.py"

# Protocols
touch "$BASE_DIR/protocols/ethernet.py"
touch "$BASE_DIR/protocols/arp.py"
touch "$BASE_DIR/protocols/ip.py"
touch "$BASE_DIR/protocols/icmp.py"

# Utils
touch "$BASE_DIR/utils/logger.py"
touch "$BASE_DIR/utils/config.py"

# Main
touch "$BASE_DIR/main.py"

# 创建配置文件
echo "Creating configuration files..."

cat > "$BASE_DIR/config/switch.yaml" << 'EOF'
# L3 Switch Configuration

switch:
  name: "L3-Switch-01"
  mac_aging_time: 300
  arp_timeout: 1200

vlans:
  - id: 1
    name: "default"
    description: "Default VLAN"
  - id: 10
    name: "vlan10"
    description: "Management VLAN"
  - id: 20
    name: "vlan20"
    description: "Data VLAN"

interfaces:
  - name: "eth0"
    mode: "access"
    access_vlan: 1
    ip: "192.168.1.1"
    netmask: "255.255.255.0"
  
  - name: "eth1"
    mode: "trunk"
    native_vlan: 1
    allowed_vlans: [1, 10, 20]
    ip: "192.168.10.1"
    netmask: "255.255.255.0"

routes:
  - network: "0.0.0.0"
    netmask: "0.0.0.0"
    next_hop: "192.168.1.254"
    interface: "eth0"
    metric: 1

logging:
  level: "INFO"
  file: "logs/switch.log"
  max_size: 10485760  # 10MB
  backup_count: 5
EOF

# 创建 requirements.txt
cat > "$BASE_DIR/requirements.txt" << 'EOF'
pyyaml>=6.0
scapy>=2.5.0
pytest>=7.4.0
pytest-cov>=4.1.0
EOF

# 创建 setup.py
cat > "$BASE_DIR/setup.py" << 'EOF'
from setuptools import setup, find_packages

setup(
    name="l3_switch",
    version="0.1.0",
    description="User-space Layer 3 Switch Implementation",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        'pyyaml>=6.0',
        'scapy>=2.5.0',
    ],
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'l3switch=main:main',
        ],
    },
)
EOF

# 创建 README.md
cat > "$BASE_DIR/README.md" << 'EOF'
# L3 Switch - User-space Layer 3 Switch

## 项目简介

i这是一个用Python实现的用户态三层交换机，支持完整的L2/L3功能。

## 功能特性

### Layer 2 功能
- MAC地址学习和转发
- VLAN支持（Access/Trunk/Hybrid模式）
- 生成树协议(STP)
- 端口聚合

### Layer 3 功能
- IP路由转发
- ARP协议处理
- ICMP协议支持
- 静态路由配置

## 项目结构

l3_switch/
├── core/ # 核心模块
├── layer2/ # 二层功能
├── layer3/ # 三层功能
├── protocols/ # 协议实现
├── utils/ # 工具模块
├── tests/ # 测试用例
├── config/ # 配置文件
├── logs/ # 日志文件
└── docs/ # 文档

shell
复制

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 安装项目
pip install -e .
