# router/packet.py
import json

class Packet:
    """
    简单的逻辑包:
    - src: 源“地址”（可以是 MAC/主机名/IP 字符串，随你定义）
    - dst: 目的“地址”
    - protocol: 协议类型字符串，比如 "L2" / "ICMP" / "DATA"
    - payload: 负载内容（字符串）
    """

    def __init__(self, src, dst, protocol, payload):
        self.src = src
        self.dst = dst
        self.protocol = protocol
        self.payload = payload

    def encode(self) -> bytes:
        data = {
            "src": self.src,
            "dst": self.dst,
            "protocol": self.protocol,
            "payload": self.payload,
        }
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def decode(raw: bytes):
        data = json.loads(raw.decode("utf-8"))
        return Packet(
            src=data["src"],
            dst=data["dst"],
            protocol=data["protocol"],
            payload=data["payload"],
        )
