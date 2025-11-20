#!/usr/bin/env bash
set -e

# ================= 基本配置 =================
H1_NS="ns-h1"
H2_NS="ns-h2"
SW_NS="ns-sw"

H1_IF="veth-h1"
H2_IF="veth-h2"
SW_IF1="veth-sw1"
SW_IF2="veth-sw2"

H1_IP="10.0.0.1/24"
H2_IP="10.0.0.2/24"

# 项目根目录（脚本所在目录）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "===== [1] 清理旧环境 ====="
ip netns del "$H1_NS" 2>/dev/null || true
ip netns del "$H2_NS" 2>/dev/null || true
ip netns del "$SW_NS" 2>/dev/null || true

ip link del "$H1_IF" 2>/dev/null || true
ip link del "$H2_IF" 2>/dev/null || true
ip link del "$SW_IF1" 2>/dev/null || true
ip link del "$SW_IF2" 2>/dev/null || true

echo "===== [2] 创建 namespace ====="
ip netns add "$H1_NS"
ip netns add "$H2_NS"
ip netns add "$SW_NS"

echo "===== [3] 创建 veth pair ====="
ip link add "$H1_IF" type veth peer name "$SW_IF1"
ip link add "$H2_IF" type veth peer name "$SW_IF2"

echo "===== [4] 把接口放入各自的 namespace ====="
ip link set "$H1_IF"  netns "$H1_NS"
ip link set "$H2_IF"  netns "$H2_NS"
ip link set "$SW_IF1" netns "$SW_NS"
ip link set "$SW_IF2" netns "$SW_NS"

echo "===== [5] 启用接口 ====="
ip netns exec "$H1_NS" ip link set lo up
ip netns exec "$H1_NS" ip link set "$H1_IF" up

ip netns exec "$H2_NS" ip link set lo up
ip netns exec "$H2_NS" ip link set "$H2_IF" up

ip netns exec "$SW_NS" ip link set lo up
ip netns exec "$SW_NS" ip link set "$SW_IF1" up
ip netns exec "$SW_NS" ip link set "$SW_IF2" up

echo "===== [6] 配置 IP 地址 ====="
ip netns exec "$H1_NS" ip addr add "$H1_IP" dev "$H1_IF"
ip netns exec "$H2_NS" ip addr add "$H2_IP" dev "$H2_IF"

echo "当前主机接口："
ip netns exec "$H1_NS" ip addr show "$H1_IF"
ip netns exec "$H2_NS" ip addr show "$H2_IF"

echo "===== [7] 启动 Python 交换机 (后台) ====="
SW_LOG="/tmp/sw1.log"
rm -f "$SW_LOG"

# 在交换机 namespace 中启动你的 router_daemon.py
ip netns exec "$SW_NS" bash -c "cd '$ROOT_DIR' && python3 router/router_daemon.py" > "$SW_LOG" 2>&1 &
SW_PID=$!
sleep 1

echo "交换机日志文件: $SW_LOG"
echo "交换机进程 PID: $SW_PID"

echo "===== [8] 测试 ICMP (ping) ====="
if ip netns exec "$H1_NS" ping -c 2 10.0.0.2 > /tmp/ping_result 2>&1; then
    echo "✅ ICMP (ping) 测试通过"
else
    echo "❌ ICMP (ping) 测试失败，详情如下："
    cat /tmp/ping_result
fi

echo "===== [9] 测试 TCP (nc) ====="
# 在 H2 上启动 TCP 服务器
ip netns exec "$H2_NS" bash -c "rm -f /tmp/tcp_result; nc -l 12345 > /tmp/tcp_result" &
TCP_SRV_PID=$!
sleep 1

# 在 H1 上作为客户端发送一行数据
echo "hello_tcp_from_h1" | ip netns exec "$H1_NS" nc 10.0.0.2 12345 || true
sleep 1

TCP_DATA=$(ip netns exec "$H2_NS" cat /tmp/tcp_result 2>/dev/null || true)
if [[ "$TCP_DATA" == "hello_tcp_from_h1" ]]; then
    echo "✅ TCP 测试通过，H2 收到: $TCP_DATA"
else
    echo "❌ TCP 测试失败，H2 收到内容: '$TCP_DATA'"
fi

# 关掉 TCP 服务器进程
kill "$TCP_SRV_PID" 2>/dev/null || true

echo "===== [10] 测试 UDP (nc -u) ====="
# 在 H2 上启动 UDP “服务器”
ip netns exec "$H2_NS" bash -c "rm -f /tmp/udp_result; nc -u -l 12346 > /tmp/udp_result" &
UDP_SRV_PID=$!
sleep 1

# 在 H1 上通过 UDP 发送一行
echo "hello_udp_from_h1" | ip netns exec "$H1_NS" nc -u 10.0.0.2 12346 || true
sleep 1

UDP_DATA=$(ip netns exec "$H2_NS" cat /tmp/udp_result 2>/dev/null || true)
if [[ "$UDP_DATA" == "hello_udp_from_h1" ]]; then
    echo "✅ UDP 测试通过，H2 收到: $UDP_DATA"
else
    echo "❌ UDP 测试失败，H2 收到内容: '$UDP_DATA'"
fi

kill "$UDP_SRV_PID" 2>/dev/null || true

echo "===== [11] 测试完成，可手动查看交换机日志 ====="
echo "tail -f $SW_LOG"

# 如需自动清理环境，可以取消下面注释：
# kill "$SW_PID" 2>/dev/null || true
# ip netns del "$H1_NS"
# ip netns del "$H2_NS"
# ip netns del "$SW_NS"

exit 0
