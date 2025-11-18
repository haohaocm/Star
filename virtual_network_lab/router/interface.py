# router/interface.py
import socket
from packet import EthernetFrame, ETH_HEADER_LEN

class Interface:
    """
    真实网络接口封装。
    使用 AF_PACKET 原始套接字，从指定网卡收发以太帧。
    注意：需要 root 权限。
    """

    def __init__(self, name: str):
        """
        name: Linux 中的接口名，如 "veth0", "eth0", "br0" 等
        """
        self.name = name

        # AF_PACKET + SOCK_RAW: 原始以太网帧
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
        # 绑定到具体网卡
        self.sock.bind((name, 0))
        self.sock.setblocking(False)

    def send_raw(self, raw_data: bytes):
        """直接发送一帧原始以太网帧（一般用在转发时）"""
        self.sock.send(raw_data)

    def send_frame(self, frame: EthernetFrame):
        """根据 EthernetFrame 发送数据"""
        self.send_raw(frame.to_bytes())

    def recv(self):
        """
        接收一帧（非阻塞）。
        返回 (frame, raw_data) 或 (None, None)
        raw_data 用于直接转发时不做修改。
        """
        try:
            raw, addr = self.sock.recvfrom(65535)
            # addr: (ifname, proto, pkttype, hatype, addr)
            frame = EthernetFrame.from_bytes(raw)
            return frame, raw
        except BlockingIOError:
            return None, None
