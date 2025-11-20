# ethernet.py
import struct

ETH_HEADER_LEN = 14

def mac_bytes_to_str(b: bytes) -> str:
    return ':'.join(f'{x:02x}' for x in b)

def mac_str_to_bytes(s: str) -> bytes:
    return bytes(int(x, 16) for x in s.split(':'))

class EthernetFrame:
    def __init__(self, dst_mac: str, src_mac: str, eth_type: int, payload: bytes):
        self.dst_mac = dst_mac.lower()
        self.src_mac = src_mac.lower()
        self.eth_type = eth_type      # 0x0800 IPv4, 0x86dd IPv6, 0x0806 ARP, ...
        self.payload = payload        # 里面就是 IP / ARP / 其它协议

    @classmethod
    def from_bytes(cls, raw: bytes):
        if len(raw) < ETH_HEADER_LEN:
            raise ValueError("frame too short")
        dst = mac_bytes_to_str(raw[0:6])
        src = mac_bytes_to_str(raw[6:12])
        eth_type = struct.unpack("!H", raw[12:14])[0]
        payload = raw[14:]
        return cls(dst, src, eth_type, payload)

    def to_bytes(self) -> bytes:
        dst_b = mac_str_to_bytes(self.dst_mac)
        src_b = mac_str_to_bytes(self.src_mac)
        header = dst_b + src_b + struct.pack("!H", self.eth_type)
        return header + self.payload
