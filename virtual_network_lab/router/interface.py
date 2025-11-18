# router/interface.py
import socket
from packet import Packet

class Interface:
    """
    一个逻辑接口:
    - 用 UDP 套接字监听 (ip, port)
    - peers: 这个端口“连出去”的对端列表，用于模拟连接的设备/链路
    """

    def __init__(self, name, ip, port):
        self.name = name
        self.ip = ip
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.sock.setblocking(False)

        # list[(peer_ip, peer_port)]
        self.peers = []

    def add_peer(self, ip, port):
        """为此接口添加一个可以发送的对端"""
        self.peers.append((ip, port))

    def send(self, dst_ip, dst_port, packet: Packet):
        self.sock.sendto(packet.encode(), (dst_ip, dst_port))

    def send_to_all_peers(self, packet: Packet):
        """Flood：向该接口所有对端发送"""
        for ip, port in self.peers:
            self.sock.sendto(packet.encode(), (ip, port))

    def recv(self):
        """非阻塞接收一个包，返回 (Packet, addr) 或 (None, None)"""
        try:
            raw, addr = self.sock.recvfrom(4096)
            pkt = Packet.decode(raw)
            return pkt, addr  # addr = (ip, port)
        except BlockingIOError:
            return None, None
