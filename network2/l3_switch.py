#!/usr/bin/env python3
# l3_switch.py
#
# 用户态三层交换机：
# - 二层：学习 MAC，同子网内直接转发
# - 三层：不同子网间进行路由转发
# - 处理 ARP 请求/响应
# - 修改 IP 包的 TTL 和校验和
#
# 运行示例：
#   sudo ip netns exec sw1 python3 l3_switch.py \
#       --iface sw1-eth1 --ip 10.0.1.254/24 \
#       --iface sw1-eth2 --ip 10.0.2.254/24

import argparse
import socket
import struct
import time
import ipaddress
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
import select

ETH_HDR_LEN = 14
ETH_P_ALL = 0x0003
ETH_P_IP = 0x0800
ETH_P_ARP = 0x0806
MAC_AGING_TIME = 300.0

# ARP 操作码
ARP_REQUEST = 1
ARP_REPLY = 2

# IP 协议
IPPROTO_ICMP = 1
IPPROTO_TCP = 6
IPPROTO_UDP = 17


def mac_bytes_to_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def mac_str_to_bytes(s: str) -> bytes:
    return bytes(int(x, 16) for x in s.split(":"))


def ip_bytes_to_str(b: bytes) -> str:
    return ".".join(str(x) for x in b)


def ip_str_to_bytes(s: str) -> bytes:
    return bytes(int(x) for x in s.split("."))


@dataclass
class InterfaceConfig:
    """接口配置信息"""
    name: str
    ip: ipaddress.IPv4Interface
    mac: bytes


class MACLearningTable:
    """MAC 地址学习表"""

    def __init__(self, aging_time: float = MAC_AGING_TIME):
        self.table: Dict[str, Tuple[str, float]] = {}
        self.aging_time = aging_time

    def learn(self, mac: str, port: str) -> None:
        now = time.time()
        self.table[mac] = (port, now)

    def lookup(self, mac: str) -> Optional[str]:
        entry = self.table.get(mac)
        if not entry:
            return None
        port, ts = entry
        if time.time() - ts > self.aging_time:
            del self.table[mac]
            return None
        return port

    def age_out(self) -> None:
        now = time.time()
        to_delete = [mac for mac, (_, ts) in self.table.items() if now - ts > self.aging_time]
        for mac in to_delete:
            del self.table[mac]


class ARPCache:
    """ARP 缓存表"""

    def __init__(self, aging_time: float = 300.0):
        self.cache: Dict[str, Tuple[str, float]] = {}  # ip -> (mac, timestamp)
        self.aging_time = aging_time

    def add(self, ip: str, mac: str) -> None:
        self.cache[ip] = (mac, time.time())

    def lookup(self, ip: str) -> Optional[str]:
        entry = self.cache.get(ip)
        if not entry:
            return None
        mac, ts = entry
        if time.time() - ts > self.aging_time:
            del self.cache[ip]
            return None
        return mac

    def age_out(self) -> None:
        now = time.time()
        to_delete = [ip for ip, (_, ts) in self.cache.items() if now - ts > self.aging_time]
        for ip in to_delete:
            del self.cache[ip]


class SwitchPort:
    """交换机端口"""

    def __init__(self, config: InterfaceConfig):
        self.config = config
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        self.sock.bind((config.name, 0))

    def fileno(self) -> int:
        return self.sock.fileno()

    def recv(self, bufsize: int = 65535) -> bytes:
        return self.sock.recv(bufsize)

    def send(self, frame: bytes) -> None:
        self.sock.send(frame)

    def close(self) -> None:
        self.sock.close()


class L3Switch:
    """三层交换机核心逻辑"""

    def __init__(self, interfaces: List[Tuple[str, str]], verbose: bool = True):
        self.ports: Dict[int, SwitchPort] = {}
        self.port_by_name: Dict[str, SwitchPort] = {}
        self.mac_table = MACLearningTable()
        self.arp_cache = ARPCache()
        self.verbose = verbose

        # 初始化接口
        for ifname, ip_cidr in interfaces:
            config = InterfaceConfig(
                name=ifname,
                ip=ipaddress.IPv4Interface(ip_cidr),
                mac=self._get_interface_mac(ifname)
            )
            port = SwitchPort(config)
            self.ports[port.fileno()] = port
            self.port_by_name[ifname] = port

            if self.verbose:
                print(f"[INFO] Interface {ifname}: IP={config.ip}, MAC={mac_bytes_to_str(config.mac)}")

    def _get_interface_mac(self, ifname: str) -> bytes:
        """获取接口的 MAC 地址"""
        import fcntl
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', ifname[:15].encode()))
        s.close()
        return info[18:24]

    def _parse_ethernet(self, frame: bytes) -> Tuple[bytes, bytes, int, bytes]:
        """解析以太网帧，返回 (dst_mac, src_mac, ethertype, payload)"""
        if len(frame) < ETH_HDR_LEN:
            raise ValueError("Frame too short")
        dst, src, eth_type = struct.unpack("!6s6sH", frame[:ETH_HDR_LEN])
        return dst, src, eth_type, frame[ETH_HDR_LEN:]

    def _build_ethernet(self, dst_mac: bytes, src_mac: bytes, eth_type: int, payload: bytes) -> bytes:
        """构建以太网帧"""
        return struct.pack("!6s6sH", dst_mac, src_mac, eth_type) + payload

    def _parse_arp(self, payload: bytes) -> dict:
        """解析 ARP 包"""
        if len(payload) < 28:
            raise ValueError("ARP packet too short")

        htype, ptype, hlen, plen, oper = struct.unpack("!HHBBH", payload[:8])
        sha = payload[8:14]  # Sender hardware address
        spa = payload[14:18]  # Sender protocol address
        tha = payload[18:24]  # Target hardware address
        tpa = payload[24:28]  # Target protocol address

        return {
            "oper": oper,
            "sha": sha,
            "spa": spa,
            "tha": tha,
            "tpa": tpa
        }

    def _build_arp(self, oper: int, sha: bytes, spa: bytes, tha: bytes, tpa: bytes) -> bytes:
        """构建 ARP 包"""
        return struct.pack(
            "!HHBBH6s4s6s4s",
            1,  # Hardware type (Ethernet)
            0x0800,  # Protocol type (IPv4)
            6,  # Hardware address length
            4,  # Protocol address length
            oper,
            sha, spa, tha, tpa
        )

    def _handle_arp(self, in_port: SwitchPort, arp: dict) -> Optional[bytes]:
        """处理 ARP 请求，返回 ARP 响应帧或 None"""
        spa_str = ip_bytes_to_str(arp["spa"])
        tpa_str = ip_bytes_to_str(arp["tpa"])
        sha_str = mac_bytes_to_str(arp["sha"])

        # 学习 ARP 映射
        self.arp_cache.add(spa_str, sha_str)

        if self.verbose:
            print(f"[ARP] {['', 'REQUEST', 'REPLY'][arp['oper']]} from {spa_str} ({sha_str}) for {tpa_str}")

        # 检查是否是询问我们的 IP
        for port in self.ports.values():
            if str(port.config.ip.ip) == tpa_str:
                if arp["oper"] == ARP_REQUEST:
                    # 构造 ARP 响应
                    arp_reply = self._build_arp(
                        ARP_REPLY,
                        port.config.mac,  # 我们的 MAC
                        arp["tpa"],  # 我们的 IP
                        arp["sha"],  # 请求者的 MAC
                        arp["spa"]  # 请求者的 IP
                    )
                    reply_frame = self._build_ethernet(
                        arp["sha"],  # 目标 MAC
                        port.config.mac,  # 源 MAC
                        ETH_P_ARP,
                        arp_reply
                    )
                    if self.verbose:
                        print(f"[ARP] Sending REPLY to {spa_str}")
                    return reply_frame
                break

        return None

    def _calculate_ip_checksum(self, header: bytes) -> int:
        """计算 IP 头部校验和"""
        if len(header) % 2 == 1:
            header += b'\x00'

        checksum = 0
        for i in range(0, len(header), 2):
            word = (header[i] << 8) + header[i + 1]
            checksum += word

        checksum = (checksum >> 16) + (checksum & 0xffff)
        checksum += checksum >> 16
        return (~checksum) & 0xffff

    def _parse_ip(self, payload: bytes) -> dict:
        """解析 IP 包头"""
        if len(payload) < 20:
            raise ValueError("IP packet too short")

        version_ihl = payload[0]
        ihl = (version_ihl & 0x0F) * 4
        ttl = payload[8]
        protocol = payload[9]
        src_ip = payload[12:16]
        dst_ip = payload[16:20]

        return {
            "ihl": ihl,
            "ttl": ttl,
            "protocol": protocol,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "header": payload[:ihl],
            "data": payload[ihl:]
        }

    def _route_packet(self, in_port: SwitchPort, ip_packet: dict) -> Optional[Tuple[SwitchPort, bytes]]:
        """路由 IP 包，返回 (出端口, 新的以太网帧) 或 None"""
        dst_ip_str = ip_bytes_to_str(ip_packet["dst_ip"])
        src_ip_str = ip_bytes_to_str(ip_packet["src_ip"])

        # 检查 TTL
        if ip_packet["ttl"] <= 1:
            if self.verbose:
                print(f"[IP] TTL expired for packet to {dst_ip_str}")
            return None

        # 查找出接口
        out_port = None
        for port in self.ports.values():
            if ipaddress.IPv4Address(dst_ip_str) in port.config.ip.network:
                out_port = port
                break

        if not out_port:
            if self.verbose:
                print(f"[IP] No route to {dst_ip_str}")
            return None

        # 查找下一跳 MAC 地址
        next_hop_mac_str = self.arp_cache.lookup(dst_ip_str)
        if not next_hop_mac_str:
            if self.verbose:
                print(f"[IP] No ARP entry for {dst_ip_str}, dropping packet")
            # TODO: 可以实现 ARP 请求队列
            return None

        # 修改 IP 包：递减 TTL，重新计算校验和
        new_header = bytearray(ip_packet["header"])
        new_header[8] = ip_packet["ttl"] - 1  # 递减 TTL
        new_header[10:12] = b'\x00\x00'  # 清空校验和
        new_checksum = self._calculate_ip_checksum(bytes(new_header))
        new_header[10:12] = struct.pack("!H", new_checksum)

        # 构建新的 IP 包
        new_ip_packet = bytes(new_header) + ip_packet["data"]

        # 构建新的以太网帧
        new_frame = self._build_ethernet(
            mac_str_to_bytes(next_hop_mac_str),  # 目标 MAC
            out_port.config.mac,  # 源 MAC（使用出接口的 MAC）
            ETH_P_IP,
            new_ip_packet
        )

        if self.verbose:
            print(f"[ROUTE] {src_ip_str} -> {dst_ip_str} via {out_port.config.name}")

        return out_port, new_frame

    def _is_broadcast(self, mac: bytes) -> bool:
        return mac == b"\xff\xff\xff\xff\xff\xff"

    def _is_multicast(self, mac: bytes) -> bool:
        return bool(mac[0] & 0x01)

    def run(self) -> None:
        """主事件循环"""
        try:
            while True:
                self.mac_table.age_out()
                self.arp_cache.age_out()

                rlist, _, _ = select.select(list(self.ports.keys()), [], [], 1.0)
                if not rlist:
                    continue

                for fd in rlist:
                    in_port = self.ports[fd]
                    frame = in_port.recv()

                    try:
                        dst_mac, src_mac, eth_type, payload = self._parse_ethernet(frame)
                    except ValueError:
                        continue

                    src_mac_str = mac_bytes_to_str(src_mac)
                    dst_mac_str = mac_bytes_to_str(dst_mac)

                    # 学习源 MAC
                    self.mac_table.learn(src_mac_str, in_port.config.name)

                    # 处理 ARP
                    if eth_type == ETH_P_ARP:
                        try:
                            arp = self._parse_arp(payload)
                            reply_frame = self._handle_arp(in_port, arp)
                            if reply_frame:
                                in_port.send(reply_frame)
                        except ValueError:
                            pass
                        continue

                    # 处理 IP 包
                    if eth_type == ETH_P_IP:
                        try:
                            ip_packet = self._parse_ip(payload)
                            dst_ip_str = ip_bytes_to_str(ip_packet["dst_ip"])

                            # 检查是否是发给交换机自己的
                            is_for_us = False
                            for port in self.ports.values():
                                if str(port.config.ip.ip) == dst_ip_str:
                                    is_for_us = True
                                    break

                            if is_for_us:
                                # TODO: 处理发给交换机的包（ICMP ping 等）
                                if self.verbose:
                                    print(f"[IP] Packet for us: {dst_ip_str}")
                                continue

                            # 检查是否需要路由
                            src_network = None
                            dst_network = None

                            for port in self.ports.values():
                                src_ip = ipaddress.IPv4Address(ip_bytes_to_str(ip_packet["src_ip"]))
                                dst_ip = ipaddress.IPv4Address(dst_ip_str)

                                if src_ip in port.config.ip.network:
                                    src_network = port.config.ip.network
                                if dst_ip in port.config.ip.network:
                                    dst_network = port.config.ip.network

                            if src_network and dst_network and src_network != dst_network:
                                # 需要路由
                                result = self._route_packet(in_port, ip_packet)
                                if result:
                                    out_port, new_frame = result
                                    out_port.send(new_frame)
                                continue

                        except ValueError:
                            pass

                    # 二层转发（同一子网内）
                    if self._is_broadcast(dst_mac) or self._is_multicast(dst_mac):
                        # Flood
                        for port in self.ports.values():
                            if port != in_port:
                                port.send(frame)
                    else:
                        out_port_name = self.mac_table.lookup(dst_mac_str)
                        if out_port_name and out_port_name != in_port.config.name:
                            self.port_by_name[out_port_name].send(frame)
                        else:
                            # Flood
                            for port in self.ports.values():
                                if port != in_port:
                                    port.send(frame)

        finally:
            for port in self.ports.values():
                port.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Layer 3 Switch")
    parser.add_argument(
        "--iface",
        "-i",
        action="append",
        nargs=2,
        metavar=("INTERFACE", "IP/MASK"),
        required=True,
        help="Interface and IP address (e.g., --iface sw1-eth1 10.0.1.254/24)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less verbose logging"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    interfaces = [(iface, ip) for iface, ip in args.iface]
    switch = L3Switch(interfaces, verbose=not args.quiet)
    switch.run()


if __name__ == "__main__":
    main()
