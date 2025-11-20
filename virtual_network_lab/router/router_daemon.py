# router_daemon.py
from router_core import RouterCore
from interface import Interface

if __name__ == "__main__":
    print("=== Real L2 Switch Daemon Start ===")

    sw = RouterCore(router_id="SW1")

    # 这里的名字是 ns-sw 这个 namespace 里存在的虚拟网卡
    iface1 = Interface("veth-sw1")  # 连接 ns-h1
    iface2 = Interface("veth-sw2")  # 连接 ns-h2

    sw.add_interface(iface1)
    sw.add_interface(iface2)

    sw.loop()
