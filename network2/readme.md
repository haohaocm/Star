# 🧠 Userspace L2 Switch Emulator

本项目提供一个基于 **Linux Network Namespace** 的用户态二层交换机模拟实验环境。你可以通过该项目构建网络拓扑、运行交换机程序，并观察转发表学习、报文转发等行为，适合用于网络协议学习与测试。

---

## 📁 项目结构

| 文件 | 说明 |
|------|------|
| `labctl.py` | 启动器脚本，用于创建和控制虚拟网络设备 |
| `create_network.sh` | 创建命名空间与虚拟链路，构建实验拓扑 |
| `clean_network.sh` | 清理网络环境 |
| `userspace_switch.py` | 用户态二层交换机程序 |

---

## ⚙️ 使用步骤

### 1️⃣ 创建实验网络拓扑

运行以下脚本以初始化命名空间和虚拟接口：

```bash
sudo ./create_network.sh
```
### 2️⃣ 启动用户态交换机

分别在两个交换机命名空间中运行交换机程序：

```bash
# 启动 sw1
sudo ip netns exec sw1 python3 userspace_switch.py --iface sw1-eth1 --iface sw1-eth2

# 启动 sw2
sudo ip netns exec sw2 python3 userspace_switch.py --iface sw2-eth1 --iface sw2-eth2
```
### 3️⃣ 关闭网卡校验和（为抓包或调试做准备）

关闭主机接口校验和卸载，防止干扰转发行为：

```bash
# 关闭 h1 校验和
sudo ip netns exec h1 ethtool -K h1-eth1 tx off rx off

# 关闭 h2 校验和
sudo ip netns exec h2 ethtool -K h2-eth1 tx off rx off

# 交换机接口（通常已执行过）
sudo ip netns exec sw1 ethtool -K sw1-eth1 tx off rx off
sudo ip netns exec sw1 ethtool -K sw1-eth2 tx off rx off
```


### 4️⃣ 校验是否成功关闭校验和

使用以下命令验证校验和是否已关闭：
```bash
# 检查 h1
sudo ip netns exec h1 ethtool -k h1-eth1 | grep checksumming

# 检查 h2
sudo ip netns exec h2 ethtool -k h2-eth1 | grep checksumming
```



### 5️⃣ 运行功能测试

你可以在 h1 和 h2 中执行如下操作进行测试：
```bash
# 在 h1 中发送 UDP 数据包,在h2 中接收 UDP 数据包
sudo ip netns exec h2 nc -u -l -p 9999
sudo ip netns exec h1 nc -u 10.0.0.2 9999
# 在 h1 中发送 TCP 数据包,在h2 中接收 TCP 数据包
sudo ip netns exec h2 nc -l 8888
sudo ip netns exec h1 nc 10.0.0.2 8888
```

# 在 h1 中 ping h2
sudo ip netns exec h1 ping <h2_IP地址>


你也可以使用 tcpdump 进行抓包，观察 MAC 学习与帧转发行为：

sudo ip netns exec sw1 tcpdump -i sw1-eth1 -n -e

### 6️⃣ 清理环境

实验完成后，运行以下脚本清除命名空间和接口：

```bash
sudo ./clean_network.sh
```

