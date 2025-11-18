#!/bin/bash
set -e

echo "===== 清理旧环境 ====="
ip netns del ns-h1 2>/dev/null || true
ip netns del ns-h2 2>/dev/null || true
ip netns del ns-sw 2>/dev/null || true

echo "===== 创建 namespace ====="
ip netns add ns-h1
ip netns add ns-h2
ip netns add ns-sw

echo "===== 创建 veth pair ====="
ip link add veth-h1 type veth peer name veth-sw1
ip link add veth-h2 type veth peer name veth-sw2

echo "===== 移动接口到 namespace ====="
ip link set veth-h1 netns ns-h1
ip link set veth-h2 netns ns-h2
ip link set veth-sw1 netns ns-sw
ip link set veth-sw2 netns ns-sw

echo "===== 启动接口 ====="
ip netns exec ns-h1 ip link set lo up
ip netns exec ns-h1 ip link set veth-h1 up

ip netns exec ns-h2 ip link set lo up
ip netns exec ns-h2 ip link set veth-h2 up

ip netns exec ns-sw ip link set lo up
ip netns exec ns-sw ip link set veth-sw1 up
ip netns exec ns-sw ip link set veth-sw2 up

echo "===== 配置 IP 地址 ====="
ip netns exec ns-h1 ip addr add 10.0.0.1/24 dev veth-h1
ip netns exec ns-h2 ip addr add 10.0.0.2/24 dev veth-h2

echo "===== 启动 Python 交换机 (后台) ====="
ip netns exec ns-sw bash -c "python3 router/router_daemon.py &"
sleep 1

echo "===== 测试 Ping ====="
ip netns exec ns-h1 ping -c 2 10.0.0.2 || {
    echo "Ping 不通，交换机可能未转发"
    exit 1
}



echo "===== 在 ns-h2 启动 TCP 服务器 (后台) ====="
ip netns exec ns-h2 bash -c "nc -l 12345 > /tmp/tcp_result &"
sleep 1

echo "===== 在 ns-h1 自动发送 TCP 请求 ====="
echo "hello_from_h1" | ip netns exec ns-h1 nc 10.0.0.2 12345

sleep 1

echo "===== 检查 ns-h2 是否收到数据 ====="
DATA=$(ip netns exec ns-h2 cat /tmp/tcp_result || true)

if [[ "$DATA" == "hello_from_h1" ]]; then
    echo "🎉 TCP 测试成功！交换机正确转发数据！"
else
    echo "❌ TCP 测试失败，未收到正确数据"
    echo "收到内容：$DATA"
fi

echo "===== 测试完成 ====="

