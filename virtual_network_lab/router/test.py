from packet import Packet
import socket
import time
import threading


def send_packets(target_ip, target_port, count, interval):
    """发送指定数量的数据包，间隔时间为interval秒"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for i in range(count):
            # 构造数据包（源IP可根据需要修改）
            pkt = Packet("127.0.0.1", target_ip, "DATA", f"message {i + 1}: hello router")
            sock.sendto(pkt.encode(), (target_ip, target_port))
            print(f"已发送第 {i + 1}/{count} 个包，内容：{pkt.data}")
            if i < count - 1:  # 最后一个包不需要等待
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n发送被手动中断")
    finally:
        sock.close()
        print("发送完成，套接字已关闭")


def main():
    print("===== UDP数据包发送工具 =====")
    # 获取目标地址和端口
    target_ip = input("请输入目标IP地址（默认127.0.0.1）: ") or "127.0.0.1"
    target_port = int(input("请输入目标端口（默认10001）: ") or 10001)

    # 获取发送参数
    while True:
        try:
            send_count = int(input("请输入发送数量（正整数）: "))
            if send_count > 0:
                break
            print("请输入大于0的整数")
        except ValueError:
            print("请输入有效的整数")

    while True:
        try:
            interval = float(input("请输入发送间隔（秒，例如0.5）: "))
            if interval >= 0:
                break
            print("请输入非负的数字")
        except ValueError:
            print("请输入有效的数字")

    # 确认发送
    print(f"\n即将发送 {send_count} 个包到 {target_ip}:{target_port}，间隔 {interval} 秒")
    confirm = input("是否开始发送？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消发送")
        return

    # 启动发送线程（避免主线程阻塞导致无法中断）
    send_thread = threading.Thread(
        target=send_packets,
        args=(target_ip, target_port, send_count, interval)
    )
    send_thread.start()

    # 等待发送完成或手动中断
    try:
        while send_thread.is_alive():
            send_thread.join(0.1)  # 非阻塞等待
    except KeyboardInterrupt:
        print("\n检测到Ctrl+C，正在停止发送...")


if __name__ == "__main__":
    main()