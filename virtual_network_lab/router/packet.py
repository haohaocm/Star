# router/packet.py
import struct

ETH_HEADER_LEN = 14

def mac_bytes_to_str(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02x}" for b in mac_bytes)

def mac_str_to_bytes(mac_str: str) -> bytes:
    return bytes(int(part, 16) for part in mac_str.split(":"))

class EthernetFrame:
    """
    以太网帧格式:
    +-----------------+-----------------+------------+----------+
    | 6B dst_mac      | 6B src_mac      | 2B type    | payload  |
    +-----------------+-----------------+------------+----------+
    """

    def __init__(self, dst_mac: str, src_mac: str, eth_type: int, payload: bytes):
        self.dst_mac = dst_mac
        self.src_mac = src_mac
        self.eth_type = eth_type  # 0x0800 = IPv4, 0x86DD = IPv6, 0x0806 = ARP, etc.
        self.payload = payload

    def to_bytes(self) -> bytes:
        dst = mac_str_to_bytes(self.dst_mac)
        src = mac_str_to_bytes(self.src_mac)
        header = dst + src + struct.pack("!H", self.eth_type)
        return header + self.payload

    @staticmethod
    def from_bytes(data: bytes):
        if len(data) < ETH_HEADER_LEN:
            return None
        dst = mac_bytes_to_str(data[0:6])
        src = mac_bytes_to_str(data[6:12])
        eth_type = struct.unpack("!H", data[12:14])[0]
        payload = data[14:]
        frame = EthernetFrame(dst, src, eth_type, payload)
        return frame
