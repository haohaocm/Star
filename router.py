#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
软件路由器（教学版）—— Python 3.8.10 可运行
提供功能：
  - 路由表（最长前缀匹配）
  - ARP 缓存
  - 模拟收包与转发
"""

import ipaddress


class RouteEntry:
    def __init__(self, network, next_hop, interface):
        self.network = ipaddress.ip_network(network)
        self.next_hop = next_hop  # str, IP
        self.interface = interface  # str

    def match(self, ip):
        return ip in self.network


class SoftwareRouter:
    def __init__(self):
        self.routes = []  # routing table
        self.arp_table = {}  # next_hop_ip -> MAC address

    def add_route(self, network, next_hop, interface):
        self.routes.append(RouteEntry(network, next_hop, interface))

    def add_arp(self, ip, mac):
        self.arp_table[ip] = mac

    # 最长前缀匹配
    def lookup_route(self, dst_ip):
        dst = ipaddress.ip_address(dst_ip)
        matches = []

        for r in self.routes:
            if r.match(dst):
                matches.append((r.network.prefixlen, r))

        if not matches:
            return None  # no route

        # 选 prefix 最大的（最长前缀匹配）
        matches.sort(reverse=True, key=lambda x: x[0])
        return matches[0][1]

    def forward_packet(self, src_ip, dst_ip, payload):
        print(f"\n收到数据包：{src_ip} → {dst_ip}, payload={payload}")

        # Step1: 查路由
        route = self.lookup_route(dst_ip)
        if not route:
            print("❌ 无路由，丢弃")
            return

        print(f"匹配路由：{route.network} via {route.next_hop} on {route.interface}")

        # Step2: 查 ARP
        next_mac = self.arp_table.get(route.next_hop)
        if not next_mac:
            print(f"❌ 无 ARP 项：无法找到 {route.next_hop} 的 MAC，丢弃")
            return

        # Step3: "转发"
        print(f"✔️ 通过接口 {route.interface} 发出：")
        print(f"   目的MAC={next_mac}, 下一跳={route.next_hop}")
        print(f"   Payload：{payload}")

        return {
            "interface": route.interface,
            "next_hop": route.next_hop,
            "next_mac": next_mac,
            "payload": payload,
        }


if __name__ == "__main__":
    router = SoftwareRouter()

    # 添加路由（示例）
    router.add_route("10.0.0.0/24", "10.0.0.1", "eth0")
    router.add_route("192.168.1.0/24", "192.168.1.1", "eth1")
    router.add_route("0.0.0.0/0", "203.0.113.1", "eth2")  # 默认路由

    # 添加 ARP 表
    router.add_arp("10.0.0.1", "AA:AA:AA:AA:AA:AA")
    router.add_arp("192.168.1.1", "BB:BB:BB:BB:BB:BB")
    router.add_arp("203.0.113.1", "CC:CC:CC:CC:CC:CC")

    # 测试转发
    router.forward_packet("10.0.0.100", "192.168.1.55", "Hello LAN")
    router.forward_packet("10.0.0.100", "8.8.8.8", "Hello Internet")
