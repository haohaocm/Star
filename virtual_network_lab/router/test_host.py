# test_hosts.py
import socket
from router.packet import Packet

def make_host(name, local_port, sw_port):
    """
    name: 主机名（这里直接当成“MAC 地址”用）
    local_port: 这个主机本地监听端口
    sw_port: 交换机对应接口的 UDP 端口 (10001 或 10002)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", local_port))

    def send(dst_name):
        pkt = Packet(src=name, dst=dst_name, protocol="L2",
                     payload=f"hello from {name}")
        sock.sendto(pkt.encode(), ("127.0.0.1", sw_port))

    def recv_once():
        sock.settimeout(1)
        try:
            raw, addr = sock.recvfrom(4096)
            p = Packet.decode(raw)
            print(f"[{name}] 收到: {p.src} -> {p.dst}, proto={p.protocol}, payload={p.payload}")
        except Exception:
            pass

    return send, recv_once

if __name__ == "__main__":
    # HostA 接在 SW1.eth0（交换机端口 10001）
    send_A, recv_A = make_host("HostA", 11001, 10001)

    # HostB 接在 SW1.eth1（交换机端口 10002）
    send_B, recv_B = make_host("HostB", 11002, 10002)

    print("HostA -> HostB 第一次发送（未知 MAC，将 Flood）")
    send_A("HostB")
    recv_A()
    recv_B()

    print("HostB -> HostA 第二次发送（应单播）")
    send_B("HostA")
    recv_A()
    recv_B()
