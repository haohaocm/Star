#!/usr/bin/env python3
# labctl.py
#
# 简单的实验网络管理工具：
# - 使用 ip netns / ip link / ip addr 命令管理 namespace 和 veth
# - 用 argparse 做子命令：create-node / delete-node / create-link / delete-link / link-set / assign-ip / exec
#
# 运行示例：
#   sudo python3 labctl.py create-node sw1
#   sudo python3 labctl.py create-node sw2
#   sudo python3 labctl.py create-link sw1 sw1-eth1 sw2 sw2-eth1
#   sudo python3 labctl.py exec sw1 -- python3 userspace_switch.py --iface sw1-eth1
#
# 注意：需要 root 权限。

import argparse
import subprocess
import sys
from typing import List


class CommandError(RuntimeError):
    pass


def run_cmd(cmd: List[str], check: bool = True) -> None:
    """运行 shell 命令并可选地检查返回值."""
    # print(f"[DEBUG] run: {' '.join(cmd)}")  # 调试时可以打开
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        raise CommandError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


class NetLab:
    """封装 ip netns / ip link 操作，方便调用."""

    def create_node(self, name: str) -> None:
        """创建一个 network namespace，代表一台虚拟设备."""
        run_cmd(["ip", "netns", "add", name])
        print(f"Created node (netns) {name}")

    def delete_node(self, name: str) -> None:
        """删除一个 network namespace."""
        run_cmd(["ip", "netns", "del", name])
        print(f"Deleted node (netns) {name}")

    def create_link(self, node1: str, if1: str, node2: str, if2: str) -> None:
        """
        创建一对 veth，分别放入 node1/if1 与 node2/if2 中。
        """
        # 创建 veth pair（先用临时名字）
        temp1 = f"{if1}-temp"
        temp2 = f"{if2}-temp"
        run_cmd(["ip", "link", "add", temp1, "type", "veth", "peer", "name", temp2])

        # 把两端移动到对应 namespace
        run_cmd(["ip", "link", "set", temp1, "netns", node1])
        run_cmd(["ip", "link", "set", temp2, "netns", node2])

        # 在 namespace 内重命名
        run_cmd(["ip", "netns", "exec", node1, "ip", "link", "set", temp1, "name", if1])
        run_cmd(["ip", "netns", "exec", node2, "ip", "link", "set", temp2, "name", if2])

        # 设置接口 up
        run_cmd(["ip", "netns", "exec", node1, "ip", "link", "set", if1, "up"])
        run_cmd(["ip", "netns", "exec", node2, "ip", "link", "set", if2, "up"])

        print(f"Created link: {node1}:{if1} <--> {node2}:{if2}")

    def delete_link(self, node: str, ifname: str) -> None:
        """
        删除某个接口所在的 veth pair.
        注意：删除一端即可，另一端会自动消失。
        """
        run_cmd(["ip", "netns", "exec", node, "ip", "link", "del", ifname])
        print(f"Deleted link (via {node}:{ifname})")

    def set_link_state(self, node: str, ifname: str, up: bool) -> None:
        """把某个 namespace 内的接口 up 或 down，用于模拟断网."""
        state = "up" if up else "down"
        run_cmd(["ip", "netns", "exec", node, "ip", "link", "set", ifname, state])
        print(f"Set {node}:{ifname} {state}")

    def assign_ip(self, node: str, ifname: str, cidr: str) -> None:
        """给某个接口配置 IP（管理 IP 或 host IP）."""
        run_cmd(["ip", "netns", "exec", node, "ip", "addr", "add", cidr, "dev", ifname])
        print(f"Assigned {cidr} to {node}:{ifname}")

    def exec_in(self, node: str, cmd: List[str]) -> None:
        """
        在指定 namespace 内执行命令。
        示例：
          lab.exec_in("sw1", ["python3", "userspace_switch.py", "--iface", "sw1-eth1"])
        """
        full_cmd = ["ip", "netns", "exec", node] + cmd
        os_exec(full_cmd)


def os_exec(cmd: List[str]) -> None:
    """用 exec 替换当前进程（适合 exec 子命令）."""
    import os
    print(f"Executing in current process: {' '.join(cmd)}")
    os.execvp(cmd[0], cmd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple network lab controller")
    # ⚠️ 这里用 subcmd 而不是 cmd，避免和 exec 子命令的参数冲突
    sub = parser.add_subparsers(dest="subcmd", required=True)

    # create-node
    p_cn = sub.add_parser("create-node", help="Create a network namespace node")
    p_cn.add_argument("name")

    # delete-node
    p_dn = sub.add_parser("delete-node", help="Delete a network namespace node")
    p_dn.add_argument("name")

    # create-link
    p_cl = sub.add_parser("create-link", help="Create a veth link between two nodes")
    p_cl.add_argument("node1")
    p_cl.add_argument("if1")
    p_cl.add_argument("node2")
    p_cl.add_argument("if2")

    # delete-link
    p_dl = sub.add_parser("delete-link", help="Delete a veth link via one side")
    p_dl.add_argument("node")
    p_dl.add_argument("ifname")

    # link-set
    p_ls = sub.add_parser("link-set", help="Set link up/down within a node")
    p_ls.add_argument("node")
    p_ls.add_argument("ifname")
    p_ls.add_argument("state", choices=["up", "down"])

    # assign-ip
    p_ai = sub.add_parser("assign-ip", help="Assign IP to interface in node")
    p_ai.add_argument("node")
    p_ai.add_argument("ifname")
    p_ai.add_argument("cidr", help="IP/CIDR, e.g. 192.168.1.1/24")

    # exec
    p_ex = sub.add_parser("exec", help="Execute a command inside a node")
    p_ex.add_argument("node")
    # ⚠️ 这里用 command，nargs=REMAINDER，用来接所有后续参数
    p_ex.add_argument("command", nargs=argparse.REMAINDER, help="Command to run (after --)")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lab = NetLab()

    try:
        if args.subcmd == "create-node":
            lab.create_node(args.name)
        elif args.subcmd == "delete-node":
            lab.delete_node(args.name)
        elif args.subcmd == "create-link":
            lab.create_link(args.node1, args.if1, args.node2, args.if2)
        elif args.subcmd == "delete-link":
            lab.delete_link(args.node, args.ifname)
        elif args.subcmd == "link-set":
            lab.set_link_state(args.node, args.ifname, args.state == "up")
        elif args.subcmd == "assign-ip":
            lab.assign_ip(args.node, args.ifname, args.cidr)
        elif args.subcmd == "exec":
            if not args.command:
                print("You must provide a command after --", file=sys.stderr)
                sys.exit(1)
            lab.exec_in(args.node, args.command)
        else:
            raise ValueError(f"Unknown subcommand {args.subcmd}")
    except CommandError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
