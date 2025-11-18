# router/router_core.py
import time
from packet import Packet

class RouterCore:
    """
    现在它就是一个 L2 交换机核心：
    - MAC 学习：src -> 接口
    - L2 转发：已知单播 → 单播；未知 / 广播 → Flood
    """

    def __init__(self, router_id):
        self.router_id = router_id

        # {iface_name: Interface}
        self.interfaces = {}

        # L2 转发表: mac(字符串) -> iface_name
        self.mac_table = {}

        # 预留：协议插件（暂时不用）
        self.algorithms = []

    def add_interface(self, iface):
        self.interfaces[iface.name] = iface

    def add_algorithm(self, algo):
        self.algorithms.append(algo)

    # ---------- L2 核心逻辑 ----------

    def learn_mac(self, src_mac, iface_name):
        old = self.mac_table.get(src_mac)
        if old != iface_name:
            self.mac_table[src_mac] = iface_name
            print(f"[{self.router_id}] 学习 MAC: {src_mac} -> {iface_name}")

    def l2_forward(self, pkt: Packet, in_iface_name: str):
        dst_mac = pkt.dst

        # 简单广播判断：你可以约定一个特殊地址，例如 "FF:FF:FF:FF:FF:FF" 或 "BROADCAST"
        is_broadcast = (dst_mac == "FF:FF:FF:FF:FF:FF" or dst_mac == "BROADCAST")

        if (not is_broadcast) and (dst_mac in self.mac_table):
            # 已知单播
            out_iface_name = self.mac_table[dst_mac]
            if out_iface_name == in_iface_name:
                # 不从同一个接口再发回去
                return

            out_iface = self.interfaces.get(out_iface_name)
            if not out_iface:
                print(f"[{self.router_id}] 找不到出接口 {out_iface_name}，丢包")
                return

            # 这里用接口的 peers 模拟“对端设备”
            out_iface.send_to_all_peers(pkt)
            print(f"[{self.router_id}] L2 单播: {pkt.src} -> {pkt.dst} via {out_iface_name}")
        else:
            # Flood
            print(f"[{self.router_id}] L2 Flood: {pkt.src} -> {pkt.dst}")
            for name, iface in self.interfaces.items():
                if name == in_iface_name:
                    continue
                iface.send_to_all_peers(pkt)

    # ---------- 收包处理 ----------

    def process_packet(self, pkt: Packet, iface, addr):
        # 这里只做 L2 交换机行为：只处理 protocol == "L2" 的帧
        if pkt.protocol == "L2":
            self.learn_mac(pkt.src, iface.name)
            self.l2_forward(pkt, iface.name)
            return

        # 其它协议（例如你自定义 "ICMP" / "DATA"）这里暂时不处理
        print(f"[{self.router_id}] 收到非 L2 协议包: proto={pkt.protocol}, 丢弃")

    # ---------- 事件循环 ----------

    def loop(self):
        print(f"[{self.router_id}] L2 Switch loop start")

        while True:
            for iface in self.interfaces.values():
                pkt, addr = iface.recv()
                if pkt:
                    print(f"[{self.router_id}] 收到: src={pkt.src}, dst={pkt.dst}, proto={pkt.protocol}, via={iface.name}")
                    self.process_packet(pkt, iface, addr)

            time.sleep(0.01)
