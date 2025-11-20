# router_core.py
import time
from ethernet import EthernetFrame

class RouterCore:
    def __init__(self, router_id):
        self.router_id = router_id
        self.interfaces = {}      # name -> Interface
        self.mac_table = {}       # mac -> iface_name

    def add_interface(self, iface):
        self.interfaces[iface.name] = iface

    def learn_mac(self, src_mac: str, iface_name: str):
        old = self.mac_table.get(src_mac)
        if old != iface_name:
            self.mac_table[src_mac] = iface_name
            print(f"[{self.router_id}] 学习 MAC: {src_mac} -> {iface_name}")

    def l2_forward(self, frame: EthernetFrame, in_iface_name: str, raw: bytes):
        dst = frame.dst_mac
        is_broadcast = (dst == "ff:ff:ff:ff:ff:ff")

        # 已知单播
        if (not is_broadcast) and (dst in self.mac_table):
            out_iface_name = self.mac_table[dst]
            if out_iface_name == in_iface_name:
                return

            out_iface = self.interfaces.get(out_iface_name)
            if out_iface:
                out_iface.send_raw(raw)
                print(f"[{self.router_id}] 单播转发: {frame.src_mac} -> {frame.dst_mac} via {out_iface_name}")
            else:
                print(f"[{self.router_id}] 转发表指向不存在接口 {out_iface_name}，丢弃")
        else:
            # Flood 未知单播、广播（包括 ARP 请求、初始 TCP SYN 等）
            print(f"[{self.router_id}] Flood 帧: {frame.src_mac} -> {frame.dst_mac}")
            for name, iface in self.interfaces.items():
                if name == in_iface_name:
                    continue
                iface.send_raw(raw)

    def loop(self):
        print(f"[{self.router_id}] L2 Switch loop start")
        while True:
            for iface in self.interfaces.values():
                frame, raw = iface.recv()
                if frame is None:
                    continue

                # 学习源 MAC
                self.learn_mac(frame.src_mac, iface.name)

                # 可选：过滤 IPv6 噪声（但不要过滤 IPv4）
                if frame.eth_type == 0x86DD:  # IPv6
                    continue

                # 🚫 不要在这里区分 TCP/UDP/ICMP
                # L2 交换机只按 MAC 转发整个帧
                self.l2_forward(frame, iface.name, raw)

            time.sleep(0.001)
