# router/router_daemon.py
from router_core import RouterCore
from interface import Interface

if __name__ == "__main__":
    print("=== L2 Switch Daemon (UDP模拟) Start ===")

    sw = RouterCore(router_id="SW1")

    # 在本机用不同 UDP 端口模拟两个接口
    # 监听端口：10001, 10002
    iface0 = Interface("eth0", "127.0.0.1", 10001)
    iface1 = Interface("eth1", "127.0.0.1", 10002)

    # eth0 下挂一个“主机 A”：127.0.0.1:11001
    iface0.add_peer("127.0.0.1", 11001)

    # eth1 下挂一个“主机 B”：127.0.0.1:11002
    iface1.add_peer("127.0.0.1", 11002)

    sw.add_interface(iface0)
    sw.add_interface(iface1)

    sw.loop()
