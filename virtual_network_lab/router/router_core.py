# router/router_core.py
import time
from packet import EthernetFrame

class RouterCore:
    """
    现在更像一个“L2 交换机核心”：
    - MAC 学习
    - L2 转发（基于真实 MAC + 接口）
    """

    def __init__(self, router_id):
        self.router_id = router_id

        # 接口集合： {ifname: Interface}
        self.interfaces = {}

        # L2 MAC 转发表: mac -> iface_name
        self.mac_table = {}

        # 预留：协议插件（L3/控制平面用）
        self.algorithms = []

    # ---------- 管理接口 ----------
    def add_interface(self, iface):
        self.interfaces[iface.name] = iface

    def add_algorithm(self, algo):
        self.algorithms.append(algo)

    # ---------- L2：MAC 学习与转发 ----------
    def learn_mac(self, src_mac, iface_name):
        old = self.mac_table.get(src_mac)
        if old != iface_name:
            self.mac_table[src_mac] = iface_name
            print(f"[{self.router_id}] 学习 MAC: {src_mac} -> {iface_name}")

    def l2_forward(self, frame: EthernetFrame, in_iface_name: str, raw_data: bytes):
        dst_mac = frame.dst_mac

        # 简单广播判断：全 FF
        is_broadcast = (dst_mac.lower() == "ff:ff:ff:ff:ff:ff")

        if (not is_broadcast) and (dst_mac in self.mac_table):
            out_iface_name = self.mac_table[dst_mac]
            if out_iface_name == in_iface_name:
                # 目的 MAC 在同一端口上，无需发回去
                return
            out_iface = self.interfaces.get(out_iface_name)
            if out_iface:
                out_iface.send_raw(raw_data)
                print(f"[{self.router_id}] 单播转发: {frame.src_mac} -> {frame.dst_mac} via {out_iface_name}")
            else:
                print(f"[{self.router_id}] 转发表中接口 {out_iface_name} 不存在，丢弃")
        else:
            # Flood: 发到所有非入口端口
            print(f"[{self.router_id}] Flood 帧: {frame.src_mac} -> {frame.dst_mac}")
            for name, iface in self.interfaces.items():
                if name == in_iface_name:
                    continue
                iface.send_raw(raw_data)

    # ---------- 主事件循环 ----------
    def loop(self):
        print(f"[{self.router_id}] L2 Switch loop start")
        while True:
            for ifname, iface in self.interfaces.items():
                frame, raw = iface.recv()
                if frame is not None:
                    # 学习源 MAC
                    self.learn_mac(frame.src_mac, ifname)
                    # 转发
                    self.l2_forward(frame, ifname, raw)

            # 后续可以在这里调度算法的 periodic
            for algo in self.algorithms:
                algo.periodic()

            time.sleep(0.001)
