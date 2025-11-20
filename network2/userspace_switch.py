#!/usr/bin/env python3
# userspace_switch.py
#
# 简单用户态二层交换机：
# - 使用 AF_PACKET 原始套接字绑定多个接口
# - 学习源 MAC，构建 MAC 表
# - 对已知单播 MAC 转发到对应端口，对未知或广播 MAC 进行 flood
# - 上层协议（ARP, IP/TCP/UDP/ICMP）不做修改，只做二层转发
#
# 运行示例（在某个 netns 中）：
#   sudo ip netns exec sw1 python3 userspace_switch.py --iface sw1-eth1 --iface sw1-eth2
#
# 注意：需要 root 权限。

import argparse
import socket
import struct
import time
from typing import Dict, Tuple, List, Optional

ETH_ALEN = 6
ETH_HDR_LEN = 14
ETH_P_ALL = 0x0003  # for AF_PACKET
MAC_AGING_TIME = 300.0  # seconds


def mac_bytes_to_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


class MACLearningTable:
    """管理 MAC -> (port_name, last_seen_time) 的转发表."""

    def __init__(self, aging_time: float = MAC_AGING_TIME):
        self.table: Dict[str, Tuple[str, float]] = {}
        self.aging_time = aging_time

    def learn(self, mac: str, port: str) -> None:
        now = time.time()
        self.table[mac] = (port, now)

    def lookup(self, mac: str) -> Optional[str]:
        """返回 port_name 或 None（过期或不存在）."""
        entry = self.table.get(mac)
        if not entry:
            return None
        port, ts = entry
        if time.time() - ts > self.aging_time:
            # aging
            del self.table[mac]
            return None
        return port

    def age_out(self) -> None:
        """周期性调用以清理老的条目."""
        now = time.time()
        to_delete = [mac for mac, (_, ts) in self.table.items() if now - ts > self.aging_time]
        for mac in to_delete:
            del self.table[mac]


class SwitchPort:
    """封装一个二层端口（接口 + AF_PACKET 套接字）."""

    def __init__(self, ifname: str):
        self.ifname = ifname
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        # 第 2 个参数是 protocol，0 表示所有
        self.sock.bind((ifname, 0))

    def fileno(self) -> int:
        return self.sock.fileno()

    def recv(self, bufsize: int = 65535) -> bytes:
        return self.sock.recv(bufsize)

    def send(self, frame: bytes) -> None:
        self.sock.send(frame)

    def close(self) -> None:
        self.sock.close()


class SwitchCore:
    """用户态交换机核心逻辑."""

    def __init__(self, ifaces: List[str], verbose: bool = True):
        self.ports: Dict[int, SwitchPort] = {}
        self.mac_table = MACLearningTable()
        self.verbose = verbose
        for name in ifaces:
            port = SwitchPort(name)
            self.ports[port.fileno()] = port
            if self.verbose:
                print(f"[INFO] Port up: {name} (fd={port.fileno()})")

    def _parse_eth_header(self, frame: bytes) -> Tuple[bytes, bytes, int]:
        """返回 (dst_mac_bytes, src_mac_bytes, ether_type)."""
        if len(frame) < ETH_HDR_LEN:
            raise ValueError("Frame too short")
        dst, src, eth_type = struct.unpack("!6s6sH", frame[:ETH_HDR_LEN])
        return dst, src, eth_type

    def _is_broadcast(self, mac: bytes) -> bool:
        return mac == b"\xff\xff\xff\xff\xff\xff"

    def _is_multicast(self, mac: bytes) -> bool:
        # LSB of first octet
        return bool(mac[0] & 0x01)

    def run(self) -> None:
        """事件主循环：收包 -> 学习 MAC -> 查表 -> 转发."""
        import select

        try:
            while True:
                # aging
                self.mac_table.age_out()

                rlist, _, _ = select.select(list(self.ports.keys()), [], [], 1.0)
                if not rlist:
                    continue

                for fd in rlist:
                    in_port = self.ports[fd]
                    frame = in_port.recv()

                    try:
                        dst_mac_b, src_mac_b, eth_type = self._parse_eth_header(frame)
                    except ValueError:
                        continue

                    src_mac = mac_bytes_to_str(src_mac_b)
                    dst_mac = mac_bytes_to_str(dst_mac_b)

                    # 学习源 MAC
                    self.mac_table.learn(src_mac, in_port.ifname)

                    if self.verbose:
                        print(
                            f"[FRAME] in={in_port.ifname} "
                            f"src={src_mac} dst={dst_mac} eth_type=0x{eth_type:04x} len={len(frame)}"
                        )

                    # 判断广播/组播/未知单播
                    out_ports: List[SwitchPort] = []

                    if self._is_broadcast(dst_mac_b) or self._is_multicast(dst_mac_b):
                        # 直接 flood
                        out_ports = [p for f, p in self.ports.items() if p is not in_port]
                    else:
                        out_port_name = self.mac_table.lookup(dst_mac)
                        if out_port_name is None or out_port_name == in_port.ifname:
                            # 未知 MAC 或 环回：flood
                            out_ports = [p for f, p in self.ports.items() if p is not in_port]
                        else:
                            # 单播转发
                            for p in self.ports.values():
                                if p.ifname == out_port_name:
                                    out_ports = [p]
                                    break

                    for p in out_ports:
                        try:
                            p.send(frame)
                            if self.verbose:
                                print(f"[FWD] {in_port.ifname} -> {p.ifname} dst={dst_mac}")
                        except OSError as e:
                            print(f"[WARN] Failed to send on {p.ifname}: {e}")
        finally:
            for p in self.ports.values():
                p.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple userspace L2 switch")
    parser.add_argument(
        "--iface",
        "-i",
        action="append",
        required=True,
        help="Interface to attach as a switch port (can be repeated)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less verbose logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    core = SwitchCore(args.iface, verbose=not args.quiet)
    core.run()


if __name__ == "__main__":
    main()
