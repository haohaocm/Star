# test_hosts.py
import socket
from virtual_network_lab.router.packet import Packet

def make_host(name, local_port, sw_port):
    """
    name: 主机名，用作 MAC（src）
    local_port: 主机监听端口
    sw_port: 交换机端口（eth0/eth1 那个 UDP 端口）
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", local_port))

    def send(dst_mac):
        pkt = Packet(src=name, dst=dst_mac, protocol="L2",
                     payload=f"hello from {name}")
        sock.sendto(pkt.encode(), ("127.0.0.1", sw_port))

    def recv_once():
        sock.settimeout(1)
        try:
            raw, addr = sock.recvfrom(4096)
            p = Packet.decode(raw)
            print(f"[{name}] 收到: {p.src} -> {p.dst}, payload={p.payload}")
        except:
            pass

    return send, recv_once

if __name__ == "__main__":
    # HostA 连在 SW1.eth0（交换机本地端口 10001）
    send_A, recv_A = make_host("HostA", 11001, 10001)

    # HostB 连在 SW1.eth1（交换机本地端口 10002）
    send_B, recv_B = make_host("HostB", 11002, 10002)

    # 1. A 给 B 发送（第一次，交换机还不认识 B，应该 Flood）
    print("HostA -> HostB 第一次发送（未知 MAC，将 Flood）")
    send_A("HostB")
    recv_A()
    recv_B()

    # 2. B 再给 A 回复，此时交换机已经学习了 A 和 B 的 MAC，
    #    应该走单播，而不是 Flood
    print("HostB -> HostA 第二次发送（已学习，单播）")
    send_B("HostA")
    recv_A()
    recv_B()
