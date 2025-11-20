# interface.py
import socket
from ethernet import EthernetFrame, ETH_HEADER_LEN

class Interface:
    def __init__(self, name: str):
        self.name = name
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW,
                                  socket.ntohs(0x0003))
        self.sock.bind((name, 0))
        self.sock.setblocking(False)

    def recv(self):
        try:
            raw, addr = self.sock.recvfrom(65535)
            # addr: (ifname, proto, pkttype, hatype, addr)
            print(f"------[{self.name}] ✅ 真正收到一帧: addr={addr}, len={len(raw)}")

            # 过滤本机发出的 OUTGOING 帧
            # pkttype == 4 (PACKET_OUTGOING)
            if len(addr) >= 3 and addr[2] == 4:
                print(f"[{self.name}] ✅ 过滤了 OUTGOING 包")
                return None, None

            print(f"[{self.name}] ✅ 处理正常包")
            frame = EthernetFrame.from_bytes(raw)
            return frame, raw

        except BlockingIOError:
            # 这里什么也不打印，避免刷屏
            return None, None

    def send_raw(self, raw: bytes):
        print(f"------向[{self.name}] ✅ 发送包，len={len(raw)}")
        self.sock.send(raw)

    def send_frame(self, frame: EthernetFrame):
        print(f"------向[{self.name}] ✅ 发送帧")
        self.send_raw(frame.to_bytes())
