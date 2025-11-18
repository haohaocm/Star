#!/usr/bin/env python3
import socket
import struct
import fcntl
import time

ETH_P_ALL = 0x0003
PACKET_HOST = 0
PACKET_OUTGOING = 4

def mac_addr(raw):
    return ':'.join('%02x' % b for b in raw)

class Interface:
    def __init__(self, name):
        self.name = name
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        self.sock.bind((name, 0))
        # 增大收包缓存，避免截断 TCP 大帧
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2**20)

    def recv_frame(self):
        pkt, addr = self.sock.recvfrom(65535)
        return pkt, addr

    def send_frame(self, frame):
        self.sock.send(frame)

class L2Switch:
    def __init__(self, name, interfaces):
        self.name = name
        self.interfaces = interfaces
        self.mac_table = {}

    def flood(self, in_if, frame):
        for iface in self.interfaces:
            if iface is not in_if:
                iface.send_frame(frame)

    def run(self):
        print(f"=== Real L2 Switch Daemon Start ({self.name}) ===")
        print("[SW] L2 Switch loop start")

        while True:
            # 监听多个接口
            readable_socks = [iface.sock for iface in self.interfaces]
            import select
            rs, _, _ = select.select(readable_socks, [], [], 0.1)

            for sock in rs:
                iface = next(x for x in self.interfaces if x.sock == sock)
                frame, addr_info = iface.recv_frame()

                # ========== 必须跳过 outgoing 包（核心修复点）==========
                if addr_info[2] == PACKET_OUTGOING:
                    continue

                # 解析源/目的 MAC
                dst_mac = mac_addr(frame[0:6])
                src_mac = mac_addr(frame[6:12])
                eth_type = struct.unpack("!H", frame[12:14])[0]

                # 忽略 IPv6 噪声
                if eth_type == 0x86DD:
                    continue

                # 忽略 LLDP，多播 01:80:c2 等控制帧
                if dst_mac.startswith("01:80:c2"):
                    continue

                # 学习 MAC → 接口
                self.mac_table[src_mac] = iface

                # 单播
                if dst_mac in self.mac_table:
                    out_iface = self.mac_table[dst_mac]
                    if out_iface is not iface:  # 避免回送
                        out_iface.send_frame(frame)
                    continue

                # 广播 / 未知单播 → Flood
                self.flood(iface, frame)


if __name__ == "__main__":
    iface1 = Interface("veth-sw1")
    iface2 = Interface("veth-sw2")

    sw = L2Switch("SW1", [iface1, iface2])
    sw.run()
