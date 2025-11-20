
# l3lab 快速多路由器实验环境

本工具脚本 `l3lab.sh` 使用 **Linux netns + veth**，配合 `router_l3.py`，一键创建多台用户态路由器并快速连通两端主机。适合批量实验与集中管理。

## 功能
- 一条命令创建 **N 台路由器链路**（r1..rN）
- 自动布线：相邻路由器之间使用 `/30` 子网 `10.200.X.0/30`
- 两端自动接入主机：hL(10.0.1.10) 与 hR(10.0.2.10)
- 自动启动每台路由器并下发静态路由
- 提供批量 `status / stats / ping / stop / destroy` 管理命令

## 依赖
```bash
sudo apt-get install -y iproute2 tcpdump netcat-traditional
pip install scapy flask cachetools netifaces
```

## 使用
```bash
chmod +x l3lab.sh
# 在包含 router_l3.py 的目录里执行：
sudo ./l3lab.sh chain 5     # 创建 5 台路由器的链
sudo ./l3lab.sh start       # 启动所有路由器进程
sudo ./l3lab.sh status      # 查看命名空间与 API 端口
sudo ./l3lab.sh ping        # 从左主机 ping 右主机
sudo ./l3lab.sh stats       # 查看每台路由器 /stats
sudo ./l3lab.sh stop        # 停止路由器进程（保留拓扑）
sudo ./l3lab.sh destroy     # 清理所有命名空间与状态
```

> 路由器 API 端口范围：`r1 -> 9001`，`rN -> 9000+N`。日志与状态保存在 `/tmp/l3lab/`。

## 说明
- 路由器自动添加 on-link 路由（接口直连子网），并在所有中间路由器上下发到两端 LAN 的静态路由：
  - `10.0.1.0/24` 指向左邻居
  - `10.0.2.0/24` 指向右邻居
- 如需调整 IP 规划或 API 端口，请修改 `l3lab.sh` 顶部变量。

## 常见问题
- **报权限错误**：需使用 `sudo` 运行。
- **router_l3.py 找不到**：设置环境变量 `ROUTER_PY=/绝对路径/router_l3.py`。
- **宿主机已有 10.200.0.0/16**：请在脚本中更换链路地址段前缀。
