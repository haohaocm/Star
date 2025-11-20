
# 🧭 三层路由器说明文档（router_l3.py）

## 📘 项目简介

本项目实现了一个 **基于用户态的三层路由器（Layer 3 Router）**，  
完全使用 Python + Scapy + Flask 构建。  

它能够在 Linux 网络命名空间或虚拟接口之间实现 **IPv4 数据包的路由转发**，  
并提供完整的 **可视化 API、日志、嗅探与调试机制**。

该项目适用于：
- 🧪 网络实验 / 教学演示（L3 转发机制、ARP 解析、路由匹配）  
- 🧱 自定义虚拟网络测试平台  
- 🕵️‍♂️ 数据包嗅探、路径追踪、转发性能分析  

---

## ⚙️ 功能概述

| 功能模块 | 说明 |
|-----------|------|
| 🧩 **静态路由表管理** | 支持最长前缀匹配，自动排序，支持 next-hop 和 on-link 模式 |
| 🔁 **ARP 缓存与解析** | 动态维护 ARP 缓存表，超时自动刷新 |
| 🧠 **环路防御机制** | 支持 split-horizon + TTL 防环路机制 |
| 🔍 **报文嗅探与重建** | 使用 AsyncSniffer 抓取 IP 层数据包，重建 IP/TCP/UDP/ICMP 层并重新计算校验和 |
| 💬 **REST API 管理** | 支持动态添加/删除路由、接口控制、统计查询 |
| 📊 **实时统计与流量分析** | 统计 ICMP/TCP/UDP/丢包等；支持 5 元组流量统计（流量计数） |
| 🧰 **手动调试接口** | /debug/route、/arp、/flows 等便捷接口 |
| ⚡ **高可扩展性** | 模块化设计，可轻松扩展策略转发、防火墙或 NAT 模块 |

---

## 🧩 架构与模块说明

### 1️⃣ L3Router 主体类

负责核心逻辑，包括：
- 路由查找（Longest Prefix Match）
- TTL 递减、ICMP 超时响应
- 报文重建与校验和修正
- 通过 Scapy `sendp()` 发送二层帧

### 2️⃣ AsyncSniffer 嗅探模块

每个接口启动一个独立线程：
```python
AsyncSniffer(iface=iface.name, prn=cb, store=False, filter="ip")
```
回调函数 `cb(pkt)` 负责调用 `router.forward()` 进行用户态转发。

### 3️⃣ ARP 管理模块
- 自动解析目标 MAC 地址；
- 结果缓存 60 秒；
- 超时自动重新解析；
- 若无法解析则丢弃并记录 `DROP arp_unresolved`。

### 4️⃣ REST API 管理平面
基于 Flask 提供统一接口：
- `/routes` 路由管理
- `/interfaces` 接口状态
- `/sniffer` 控制嗅探
- `/settings` 修改运行参数
- `/stats` / `/flows` / `/arp` / `/debug/route` 提供运行状态

---

## 🚀 使用步骤

### 🧱 1. 环境准备

```bash
sudo apt update
sudo apt install python3-pip tcpdump net-tools netcat-traditional -y
pip install scapy flask cachetools netifaces
```

### 🧰 2. 创建测试网络拓扑（命名空间方式）

```bash
sudo ip netns add ns-a
sudo ip netns add ns-b

sudo ip link add veth1 type veth peer name veth0
sudo ip link add veth2 type veth peer name veth3

sudo ip link set veth0 netns ns-a
sudo ip link set veth3 netns ns-b

sudo ip addr add 10.0.1.1/24 dev veth1
sudo ip addr add 10.0.2.1/24 dev veth2

sudo ip netns exec ns-a ip addr add 10.0.1.10/24 dev veth0
sudo ip netns exec ns-b ip addr add 10.0.2.10/24 dev veth3

sudo ip link set veth1 up
sudo ip link set veth2 up
sudo ip netns exec ns-a ip link set veth0 up
sudo ip netns exec ns-b ip link set veth3 up
sudo ip netns exec ns-a ip link set lo up
sudo ip netns exec ns-b ip link set lo up

# 设置命名空间默认网关（指向路由器）
sudo ip netns exec ns-a ip route add default via 10.0.1.1
sudo ip netns exec ns-b ip route add default via 10.0.2.1
```

---

## 🚀 3. 启动路由器

```bash
sudo python3 router_l3.py --interfaces veth1 veth2 --api-port 8080
```

你将看到：
```
接口 veth1: IP=10.0.1.1 MAC=xx:xx:xx:xx:xx:xx
接口 veth2: IP=10.0.2.1 MAC=xx:xx:xx:xx:xx:xx
🎧 监听接口: veth1 (BPF: ip)
🎧 监听接口: veth2 (BPF: ip)
REST API 启动在 0.0.0.0:8080
```

---

## 🔧 4. 添加路由

```bash
curl -X POST http://127.0.0.1:8080/routes   -H "Content-Type: application/json"   -d '{"network":"10.0.1.0","netmask":"255.255.255.0","next_hop":"0.0.0.0","interface":"veth1"}'

curl -X POST http://127.0.0.1:8080/routes   -H "Content-Type: application/json"   -d '{"network":"10.0.2.0","netmask":"255.255.255.0","next_hop":"0.0.0.0","interface":"veth2"}'
```

---

## 🧪 5. 功能测试

### ✅ ICMP 连通性（Ping 测试）
```bash
sudo ip netns exec ns-a ping -c 3 10.0.2.10
sudo ip netns exec ns-b ping -c 3 10.0.1.10
```
正常输出：
```
64 bytes from 10.0.2.10: icmp_seq=1 ttl=63 time=0.5 ms
```

---

### ✅ TCP 转发测试（前台交互）

**B 端：**
```bash
sudo ip netns exec ns-b nc -l 10.0.2.10 9999
```

**A 端：**
```bash
sudo ip netns exec ns-a nc 10.0.2.10 9999
```

输入文字后双方均可看到内容，表示转发成功。

---

### ✅ UDP 转发测试（前台交互）

**B 端：**
```bash
sudo ip netns exec ns-b nc -u -l 10.0.2.10 8888
```

**A 端：**
```bash
sudo ip netns exec ns-a nc -u 10.0.2.10 8888
```

输入任意字符串，B 端应立即显示收到的内容。

---

## 🧠 6. REST API 手册（简版）

| API 路径 | 方法 | 功能说明 |
|-----------|--------|-------------|
| `/health` | GET | 查看当前接口状态 |
| `/routes` | GET/POST/DELETE | 查看/添加/删除 路由条目 |
| `/interfaces` | GET | 查看接口信息 |
| `/interfaces/<if>/enable` | POST | 启用接口 |
| `/interfaces/<if>/disable` | POST | 禁用接口 |
| `/sniffer/start` | POST | 启动嗅探线程 |
| `/sniffer/stop` | POST | 停止嗅探线程 |
| `/settings` | POST | 动态调整参数（如关闭 split-horizon） |
| `/stats` | GET | 查看统计信息 |
| `/flows` | GET | 查看最近流量统计 |
| `/arp` | GET | 查看 ARP 缓存表 |
| `/debug/route?dst=<IP>` | GET | 查看指定 IP 的路由匹配情况 |

---

## 🧰 7. 调试与排错

| 日志关键字 | 说明 |
|-------------|------|
| `FORWARD ok` | 成功转发一个包 |
| `DROP ttl_expired` | TTL <= 1 被丢弃 |
| `DROP no_route` | 未命中路由表 |
| `DROP split_horizon` | 入/出接口相同，被防环机制丢弃 |
| `DROP arp_unresolved` | ARP 未解析成功 |
| `DROP loop_guard` | 检测到重复转发（环路） |
| `DROP iface_disabled` | 出接口未启用 |

---

## 📊 8. 统计与监控示例

查看统计：
```bash
curl -s http://127.0.0.1:8080/stats | python3 -m json.tool
```

示例输出：
```json
{
  "rx_packets": 540,
  "tx_packets": 538,
  "icmp_packets": 240,
  "tcp_packets": 12,
  "udp_packets": 14,
  "dropped_packets": 2
}
```

查看当前流量前 10：
```bash
curl -s "http://127.0.0.1:8080/flows?top=10" | python3 -m json.tool
```

---

## 🧩 9. 典型用例

| 用例 | 操作 |
|------|------|
| 手动禁用接口 | `curl -X POST http://127.0.0.1:8080/interfaces/veth2/disable` |
| 删除一条路由 | `curl -X DELETE http://127.0.0.1:8080/routes -d '{"network":"10.0.2.0","netmask":"255.255.255.0"}' -H "Content-Type: application/json"` |
| 临时关闭 split-horizon | `curl -X POST http://127.0.0.1:8080/settings -H "Content-Type: application/json" -d '{"split_horizon": false}'` |

---

## 🧩 10. 代码扩展建议

- 🧱 **添加 NAT 功能**：可在 `forward()` 中识别特定端口并修改 `src/dst` 地址。  
- 🔐 **访问控制列表 (ACL)**：在转发前插入规则匹配逻辑（白名单/黑名单）。  
- 🧠 **动态路由协议**：可增加 RIP/OSPF 协议线程，周期性更新路由表。  
- 📡 **性能优化**：使用原生 `socket(AF_PACKET)` + zero-copy 或 DPDK 接口加速。

---

## ✅ 总结

**router_l3.py** 是一个教学级但功能完整的三层路由器原型。  
它具有真实路由器的核心行为：**路由匹配 → TTL 检查 → ARP 解析 → 数据包重建 → 二层发送**。  

同时，它提供 **实时统计、API 控制、嗅探与可调策略机制**，  
是学习路由器内部工作机制的绝佳实验平台。

---
