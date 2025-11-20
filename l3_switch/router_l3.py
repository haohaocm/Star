#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
router_l3.py
A userspace L3 router with:
- Longest-prefix routing (on-link or next-hop)
- ARP cache & resolution
- Robust L3/L4 rebuild (TTL-1, checksum re-calc)
- Loop prevention (split-horizon + per-packet signature cache)
- Flow accounting (5-tuple)
- REST control plane (routes, ifaces, sniffer, settings, stats, flows, arp)
- Stable sniffing using AsyncSniffer

Deps:
  pip install scapy flask cachetools netifaces
Run:
  sudo python3 router_l3.py --interfaces veth1 veth2 --api-port 8080
"""

import argparse
import ipaddress
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from flask import Flask, request, jsonify
from cachetools import TTLCache
import netifaces

from scapy.all import (
    AsyncSniffer, sniff, sendp, srp1,
    Ether, ARP, IP, ICMP, TCP, UDP, Raw,
    get_if_hwaddr, get_if_addr, conf
)

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] L3Router: %(message)s"
)
log = logging.getLogger("L3Router")

# ---------------- Models -----------------
@dataclass
class RouteEntry:
    network: str
    netmask: str
    next_hop: str      # "0.0.0.0" means on-link
    interface: str
    metric: int = 1

    def net(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(f"{self.network}/{self.netmask}", strict=False)

@dataclass
class IfaceInfo:
    name: str
    ip: str
    mac: str
    enabled: bool = True


# --------------- Core Router --------------
class L3Router:
    def __init__(self, interfaces: List[str]):
        # Scapy performance
        conf.sniff_promisc = True
        conf.verb = 0

        # Interfaces
        self.ifaces: Dict[str, IfaceInfo] = {}
        for ifn in interfaces:
            ip = get_if_addr(ifn)
            mac = get_if_hwaddr(ifn)
            self.ifaces[ifn] = IfaceInfo(name=ifn, ip=ip, mac=mac, enabled=True)
            log.info(f"接口 {ifn}: IP={ip} MAC={mac}")

        # Routes
        self.routes: List[RouteEntry] = []

        # ARP cache (IPv4 -> MAC)
        self.arp_cache: TTLCache[str, str] = TTLCache(maxsize=4096, ttl=60)

        # Loop guard: (src,dst,proto,id,in_if,out_if) -> seen_ts
        self.loop_guard: TTLCache[Tuple, float] = TTLCache(maxsize=8192, ttl=1.0)

        # Flow accounting: (src,dst,proto,sport,dport) -> stats
        self.flows: Dict[Tuple, Dict] = {}
        self.flows_lock = threading.Lock()

        # Stats
        self.stats = {
            "rx_packets": 0,
            "tx_packets": 0,
            "dropped_packets": 0,
            "icmp_packets": 0,
            "tcp_packets": 0,
            "udp_packets": 0,
            "no_route": 0,
            "ttl_expired": 0,
            "arp_miss": 0,
            "arp_sent": 0,
            "loop_suppressed": 0
        }

        # Settings (runtime switchable via /settings)
        self.settings = {
            "only_inbound_sniff": False,        # default: sniff all ip (safer)
            "send_icmp_time_exceeded": True,    # send ICMP 11/0 on TTL<=1
            "split_horizon": True               # drop if in_if == out_if
        }

        # Sniffer control
        self.sniffers: Dict[str, AsyncSniffer] = {}

    # ---------- Helpers ----------
    def _sort_routes(self):
        # Longest-prefix first, then lower metric
        self.routes.sort(key=lambda r: (r.net().prefixlen, -r.metric), reverse=True)

    def add_route(self, r: RouteEntry) -> bool:
        replaced = False
        for i, cur in enumerate(self.routes):
            if cur.network == r.network and cur.netmask == r.netmask:
                self.routes[i] = r
                replaced = True
                break
        if not replaced:
            self.routes.append(r)
        self._sort_routes()
        log.info(f"添加/更新路由: {r.network}/{r.netmask} via {r.next_hop} dev {r.interface}")
        return True

    def del_route(self, network: str, netmask: str) -> bool:
        before = len(self.routes)
        self.routes = [r for r in self.routes if not (r.network == network and r.netmask == netmask)]
        log.info(f"删除路由: {network}/{netmask}")
        return len(self.routes) != before

    def lookup(self, dst_ip: str) -> Optional[RouteEntry]:
        ipdst = ipaddress.ip_address(dst_ip)
        for r in self.routes:
            if ipdst in r.net():
                return r
        return None

    def arp_resolve(self, iface: IfaceInfo, target_ip: str, timeout=1.0) -> Optional[str]:
        if target_ip in self.arp_cache:
            return self.arp_cache[target_ip]
        self.stats["arp_miss"] += 1
        req = Ether(dst="ff:ff:ff:ff:ff:ff", src=iface.mac) / ARP(op=1, pdst=target_ip, psrc=iface.ip, hwsrc=iface.mac)
        self.stats["arp_sent"] += 1
        ans = srp1(req, iface=iface.name, timeout=timeout, verbose=False)
        if ans and ans.haslayer(ARP):
            mac = ans[ARP].hwsrc
            self.arp_cache[target_ip] = mac
            return mac
        return None

    def _update_flow(self, ip: IP, in_if: str):
        proto = ip.proto
        sport = dport = 0
        if ip.haslayer(TCP):
            sport, dport = ip[TCP].sport, ip[TCP].dport
        elif ip.haslayer(UDP):
            sport, dport = ip[UDP].sport, ip[UDP].dport
        key = (ip.src, ip.dst, proto, sport, dport)
        size = len(bytes(ip))
        now = time.time()
        with self.flows_lock:
            f = self.flows.get(key)
            if not f:
                f = {"pkts": 0, "bytes": 0, "first": now, "last": now, "in_if": in_if}
                self.flows[key] = f
            f["pkts"] += 1
            f["bytes"] += size
            f["last"] = now

    # ---------- Forwarding ----------
    def forward(self, frame: Ether, in_if_name: str):
        if not frame.haslayer(IP):
            return
        self.stats["rx_packets"] += 1
        ip = frame[IP]

        # L4 counters
        if frame.haslayer(ICMP): self.stats["icmp_packets"] += 1
        if frame.haslayer(TCP):  self.stats["tcp_packets"] += 1
        if frame.haslayer(UDP):  self.stats["udp_packets"] += 1

        # TTL
        if ip.ttl <= 1:
            self.stats["ttl_expired"] += 1
            self.stats["dropped_packets"] += 1
            log.info(f"DROP ttl_expired: {ip.src}->{ip.dst}")
            if self.settings["send_icmp_time_exceeded"]:
                self._send_icmp_time_exceeded(ip, in_if_name)
            return

        # Lookup
        rt = self.lookup(ip.dst)
        if not rt:
            self.stats["no_route"] += 1
            self.stats["dropped_packets"] += 1
            log.info(f"DROP no_route: dst={ip.dst}")
            return

        if rt.interface not in self.ifaces:
            self.stats["dropped_packets"] += 1
            log.info(f"DROP iface_missing: out={rt.interface}")
            return

        out_if = self.ifaces[rt.interface]
        if not out_if.enabled:
            self.stats["dropped_packets"] += 1
            log.info(f"DROP iface_disabled: out={rt.interface}")
            return

        # Split horizon
        if self.settings["split_horizon"] and in_if_name == out_if.name:
            self.stats["loop_suppressed"] += 1
            self.stats["dropped_packets"] += 1
            log.info(f"DROP split_horizon: in={in_if_name} out={out_if.name}")
            return

        # Loop guard
        proto = ip.proto
        ip_id = getattr(ip, "id", 0)
        sig = (ip.src, ip.dst, proto, ip_id, in_if_name, out_if.name)
        if sig in self.loop_guard:
            self.stats["loop_suppressed"] += 1
            self.stats["dropped_packets"] += 1
            log.info(f"DROP loop_guard: {ip.src}->{ip.dst} id={ip_id} in={in_if_name} out={out_if.name}")
            return
        self.loop_guard[sig] = time.time()

        # ---- Rebuild L3/L4 safely (force checksum & length recalculation) ----
        new_ip = IP(
            version=ip.version, ihl=ip.ihl, tos=ip.tos,
            id=ip.id, flags=ip.flags, frag=ip.frag,
            ttl=max(1, ip.ttl - 1), proto=ip.proto,
            src=ip.src, dst=ip.dst
        )
        new_ip.len = None
        new_ip.chksum = None

        # Upper layer (rebuild from bytes to avoid shared fields)
        upper = None
        if frame.haslayer(ICMP):
            icmp = ICMP(bytes(frame[ICMP]))
            icmp.chksum = None
            upper = icmp
        elif frame.haslayer(TCP):
            tcp = TCP(bytes(frame[TCP]))
            tcp.chksum = None
            # tcp.len not a field; length covered by IP
            upper = tcp
        elif frame.haslayer(UDP):
            udp = UDP(bytes(frame[UDP]))
            udp.len = None
            udp.chksum = None
            upper = udp
        elif frame.haslayer(Raw):
            upper = Raw(bytes(frame[Raw]))

        # Next-hop and ARP
        nh_ip = rt.next_hop if rt.next_hop != "0.0.0.0" else new_ip.dst
        dst_mac = self.arp_resolve(out_if, nh_ip)
        if not dst_mac:
            self.stats["dropped_packets"] += 1
            log.info(f"DROP arp_unresolved: nh={nh_ip} out={out_if.name}")
            return

        out_frame = Ether(src=out_if.mac, dst=dst_mac) / new_ip
        if upper:
            out_frame = out_frame / upper

        # Send L2 frame
        sendp(out_frame, iface=out_if.name, verbose=False)
        self.stats["tx_packets"] += 1
        self._update_flow(new_ip, in_if_name)
        log.info(f"FORWARD ok: {ip.src} -> {ip.dst} via {out_if.name} (nh={nh_ip},{dst_mac})")

    def _send_icmp_time_exceeded(self, ip: IP, in_if_name: str):
        # Send ICMP 11 to original sender (best-effort)
        rt = self.lookup(ip.src)
        if not rt: return
        if rt.interface not in self.ifaces: return
        out_if = self.ifaces[rt.interface]
        if not out_if.enabled: return

        nh_ip = rt.next_hop if rt.next_hop != "0.0.0.0" else ip.src
        dst_mac = self.arp_resolve(out_if, nh_ip)
        if not dst_mac: return

        payload = bytes(IP(bytes(ip)))[:28]
        icmp = Ether(src=out_if.mac, dst=dst_mac) / \
               IP(src=out_if.ip, dst=ip.src, ttl=64) / \
               ICMP(type=11, code=0) / payload
        sendp(icmp, iface=out_if.name, verbose=False)

    # ---------- Sniffer ----------
    def _build_bpf(self, iface: IfaceInfo) -> str:
        if self.settings["only_inbound_sniff"]:
            # inbound-ish: avoid own-src mac/ip
            bpf = f"ip and not ether src {iface.mac}"
            if iface.ip and iface.ip != "0.0.0.0":
                bpf += f" and not src host {iface.ip}"
            return bpf
        return "ip"

    def _start_sniffer_on(self, iface: IfaceInfo):
        bpf = self._build_bpf(iface)
        log.info(f"🎧 监听接口: {iface.name} (BPF: {bpf})")

        def cb(pkt):
            if not iface.enabled: return
            if not pkt.haslayer(IP): return
            try:
                self.forward(pkt, iface.name)
            except Exception as e:
                log.error(f"转发异常: {e}")

        sn = AsyncSniffer(iface=iface.name, prn=cb, store=False, filter=bpf)
        sn.start()
        self.sniffers[iface.name] = sn

    def start_sniffer(self):
        self.stop_sniffer()
        for ifn, info in self.ifaces.items():
            self._start_sniffer_on(info)
        log.info("Sniffer 已启动（AsyncSniffer）")

    def stop_sniffer(self):
        for ifn, sn in list(self.sniffers.items()):
            try:
                sn.stop()
            except Exception:
                pass
            self.sniffers.pop(ifn, None)
        log.info("Sniffer 已停止")

    # ---------- Iface ops ----------
    def enable_iface(self, ifn: str, enabled: bool) -> bool:
        if ifn in self.ifaces:
            self.ifaces[ifn].enabled = enabled
            log.info(("启用" if enabled else "禁用") + f" 接口: {ifn}")
            return True
        return False

    def add_iface(self, ifn: str) -> bool:
        try:
            ip = get_if_addr(ifn)
            mac = get_if_hwaddr(ifn)
            self.ifaces[ifn] = IfaceInfo(name=ifn, ip=ip, mac=mac, enabled=True)
            log.info(f"新增接口 {ifn}: IP={ip} MAC={mac}")
            # start sniffer immediately if running
            self._start_sniffer_on(self.ifaces[ifn])
            return True
        except Exception as e:
            log.error(f"新增接口失败 {ifn}: {e}")
            return False

    def remove_iface(self, ifn: str) -> bool:
        if ifn in self.ifaces:
            self.ifaces[ifn].enabled = False
            # stop sniffer on it
            sn = self.sniffers.pop(ifn, None)
            if sn:
                try: sn.stop()
                except Exception: pass
            del self.ifaces[ifn]
            # remove routes referencing it
            self.routes = [r for r in self.routes if r.interface != ifn]
            log.info(f"移除接口: {ifn}")
            return True
        return False


# --------------- REST API ----------------
def create_api(router: L3Router) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return {"ok": True, "ifaces": {k: asdict(v) for k, v in router.ifaces.items()}}

    @app.get("/stats")
    def stats():
        return router.stats

    @app.get("/routes")
    def get_routes():
        return [asdict(r) for r in router.routes]

    @app.post("/routes")
    def post_route():
        d = request.get_json(force=True)
        r = RouteEntry(
            network=d["network"],
            netmask=d["netmask"],
            next_hop=d.get("next_hop", "0.0.0.0"),
            interface=d["interface"],
            metric=int(d.get("metric", 1)),
        )
        ok = router.add_route(r)
        return {"success": ok}

    @app.delete("/routes")
    def delete_route():
        d = request.get_json(force=True)
        ok = router.del_route(d["network"], d["netmask"])
        return {"success": ok}

    @app.get("/interfaces")
    def get_ifaces():
        return {k: asdict(v) for k, v in router.ifaces.items()}

    @app.post("/interfaces/<ifn>/enable")
    def if_enable(ifn):
        ok = router.enable_iface(ifn, True)
        return {"success": ok}

    @app.post("/interfaces/<ifn>/disable")
    def if_disable(ifn):
        ok = router.enable_iface(ifn, False)
        return {"success": ok}

    @app.post("/interfaces/add")
    def if_add():
        ifn = request.json["interface"]
        ok = router.add_iface(ifn)
        return {"success": ok}

    @app.post("/interfaces/remove")
    def if_remove():
        ifn = request.json["interface"]
        ok = router.remove_iface(ifn)
        return {"success": ok}

    @app.post("/sniffer/start")
    def snif_start():
        router.start_sniffer()
        return {"success": True}

    @app.post("/sniffer/stop")
    def snif_stop():
        router.stop_sniffer()
        return {"success": True}

    @app.post("/settings")
    def set_settings():
        body = request.get_json(force=True)
        for k, v in body.items():
            if k in router.settings:
                router.settings[k] = v
        # live-update BPF by restart sniffers if BPF-affecting keys changed
        if "only_inbound_sniff" in body:
            router.start_sniffer()
        return {"success": True, "settings": router.settings}

    @app.get("/flows")
    def get_flows():
        top = int(request.args.get("top", 50))
        with router.flows_lock:
            items = []
            for (src, dst, proto, sport, dport), st in router.flows.items():
                items.append({
                    "src": src, "dst": dst, "proto": proto,
                    "sport": sport, "dport": dport, **st
                })
            items.sort(key=lambda x: x["bytes"], reverse=True)
            return items[:top]

    @app.get("/arp")
    def get_arp():
        return dict(router.arp_cache.items())

    @app.get("/debug/route")
    def debug_route():
        dst = request.args.get("dst")
        r = router.lookup(dst) if dst else None
        return {"dst": dst, "route": asdict(r) if r else None}

    return app


# ---------------- Main -------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interfaces", nargs="+", required=True, help="interfaces to listen on")
    p.add_argument("--api-port", type=int, default=8080)
    args = p.parse_args()

    r = L3Router(args.interfaces)
    r.start_sniffer()

    app = create_api(r)
    log.info(f"REST API 启动在 0.0.0.0:{args.api_port}")
    app.run(host="0.0.0.0", port=args.api_port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
