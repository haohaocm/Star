#!/bin/sh
# l3lab_posix.sh - Multi-router lab manager (POSIX /bin/sh) using netns + veth
# KEY FIX: All API calls run inside each router's netns (ip netns exec rX curl ...)
# Requirements: iproute2, curl, python3 (+ scapy flask cachetools netifaces)

ROOT_DIR=`pwd`
: "${ROUTER_PY:=${ROOT_DIR}/router_l3.py}"
: "${STATE_DIR:=/tmp/l3lab}"
LOG_DIR="${STATE_DIR}/logs"
PID_DIR="${STATE_DIR}/pids"
N_FILE="${STATE_DIR}/N"
API_BASE=9000

mkdir -p "${STATE_DIR}" "${LOG_DIR}" "${PID_DIR}" 2>/dev/null

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

need_root() {
  if [ "`id -u`" -ne 0 ]; then red "Please run as root (sudo)."; exit 1; fi
}

check_router_py() {
  if [ ! -f "${ROUTER_PY}" ]; then
    red "router_l3.py not found at ${ROUTER_PY}. Set ROUTER_PY=/abs/path/router_l3.py"
    exit 1
  fi
}

# veth pair between two namespaces with IP config
create_link() {
  if_a="$1"; ns_a="$2"; ip_a="$3"
  if_b="$4"; ns_b="$5"; ip_b="$6"
  ip link add "${if_a}" type veth peer name "${if_b}"
  ip link set "${if_a}" netns "${ns_a}"
  ip link set "${if_b}" netns "${ns_b}"
  ip netns exec "${ns_a}" ip addr add "${ip_a}" dev "${if_a}"
  ip netns exec "${ns_b}" ip addr add "${ip_b}" dev "${if_b}"
  ip netns exec "${ns_a}" ip link set "${if_a}" up
  ip netns exec "${ns_b}" ip link set "${if_b}" up
}

start_router() {
  r="$1"; port="$2"
  if_list=`ip netns exec "${r}" sh -c "ls /sys/class/net | grep -v '^lo$' | tr '\n' ' '"`
  # stop old
  if [ -f "${PID_DIR}/${r}.pid" ]; then
    oldpid=`cat "${PID_DIR}/${r}.pid" 2>/dev/null`
    if [ -n "${oldpid}" ] && kill -0 "${oldpid}" 2>/dev/null; then
      kill "${oldpid}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${PID_DIR}/${r}.pid"
  fi
  green "[${r}] starting router_l3.py on port ${port} (ifaces: ${if_list})"
  ip netns exec "${r}" sh -c "nohup python3 '${ROUTER_PY}' --interfaces ${if_list} --api-port ${port} > '${LOG_DIR}/${r}.log' 2>&1 & echo \$! > '${PID_DIR}/${r}.pid'"
}

# Wait API ready inside ns: try GET /health up to timeout (seconds)
wait_api() {
  r="$1"; port="$2"; timeout="${3:-10}"
  i=0
  while [ "$i" -lt "$timeout" ]; do
    if ip netns exec "${r}" sh -c "curl -s --max-time 1 http://127.0.0.1:${port}/health >/dev/null"; then
      return 0
    fi
    sleep 1
    i=`expr "$i" + 1`
  done
  return 1
}

stop_router() {
  r="$1"
  if [ -f "${PID_DIR}/${r}.pid" ]; then
    pid=`cat "${PID_DIR}/${r}.pid" 2>/dev/null`
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      green "[${r}] stopping pid ${pid}"
      kill "${pid}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${PID_DIR}/${r}.pid"
  fi
}

# POST /routes from inside the target namespace
post_route() {
  r="$1"; port="$2"; net="$3"; mask="$4"; ifname="$5"; nh="${6:-0.0.0.0}"
  ip netns exec "${r}" sh -c "curl -sS -X POST 'http://127.0.0.1:${port}/routes' -H 'Content-Type: application/json' -d '{\"network\":\"${net}\",\"netmask\":\"${mask}\",\"next_hop\":\"${nh}\",\"interface\":\"${ifname}\"}' >/dev/null"
}

cmd_chain() {
  need_root; check_router_py
  N="$1"
  case "$N" in '' ) red "Usage: $0 chain <N> (N>=2)"; exit 1;; esac
  case "$N" in *[!0-9]* ) red "N must be integer"; exit 1;; esac
  if [ "$N" -lt 2 ]; then red "N must be >= 2"; exit 1; fi
  echo "${N}" > "${N_FILE}"

  i=1
  while [ "$i" -le "$N" ]; do
    ip netns add "r${i}" 2>/dev/null || true
    ip netns exec "r${i}" ip link set lo up
    i=`expr "$i" + 1`
  done
  ip netns add hL 2>/dev/null || true
  ip netns add hR 2>/dev/null || true
  ip netns exec hL ip link set lo up
  ip netns exec hR ip link set lo up

  # hL <-> r1
  ip link add r1hL type veth peer name hLr1
  ip link set r1hL netns r1
  ip link set hLr1 netns hL
  ip netns exec r1 ip addr add 10.0.1.1/24 dev r1hL
  ip netns exec hL ip addr add 10.0.1.10/24 dev hLr1
  ip netns exec r1 ip link set r1hL up
  ip netns exec hL ip link set hLr1 up
  ip netns exec hL ip route add default via 10.0.1.1

  # hR <-> rN
  ip link add r${N}hR type veth peer name hRr${N}
  ip link set r${N}hR netns r${N}
  ip link set hRr${N} netns hR
  ip netns exec r${N} ip addr add 10.0.2.1/24 dev r${N}hR
  ip netns exec hR ip addr add 10.0.2.10/24 dev hRr${N}
  ip netns exec r${N} ip link set r${N}hR up
  ip netns exec hR ip link set hRr${N} up
  ip netns exec hR ip route add default via 10.0.2.1

  # r1..rN chain, /30 links
  i=1
  while [ "$i" -le `expr "$N" - 1` ]; do
    j=`expr "$i" + 1`
    create_link "r${i}r${j}" "r${i}" "10.200.${i}.1/30" "r${j}r${i}" "r${j}" "10.200.${i}.2/30"
    i=`expr "$i" + 1`
  done

  green "Chain created: routers r1..r${N}, hosts hL(10.0.1.10) <-> hR(10.0.2.10)"
  printf "Run: %s start  # start router processes\n" "$0"
}

cmd_start() {
  need_root; check_router_py
  if [ ! -f "${N_FILE}" ]; then red "No lab found. Run: $0 chain <N>"; exit 1; fi
  N=`cat "${N_FILE}"`

  i=1
  while [ "$i" -le "$N" ]; do
    port=`expr ${API_BASE} + ${i}`
    start_router "r${i}" "${port}"
    i=`expr "$i" + 1`
  done

  # wait APIs
  i=1
  while [ "$i" -le "$N" ]; do
    port=`expr ${API_BASE} + ${i}`
    if ! wait_api "r${i}" "${port}" 15; then
      yellow "[r${i}] API not ready on 127.0.0.1:${port}. Check ${LOG_DIR}/r${i}.log"
    fi
    i=`expr "$i" + 1`
  done

  # on-link routes (inside each ns)
  post_route "r1"  `expr ${API_BASE} + 1`     "10.0.1.0" "255.255.255.0" "r1hL"   "0.0.0.0"
  post_route "r${N}" `expr ${API_BASE} + ${N}` "10.0.2.0" "255.255.255.0" "r${N}hR" "0.0.0.0"

  i=1
  while [ "$i" -le `expr "$N" - 1` ]; do
    j=`expr "$i" + 1`
    post_route "r${i}" `expr ${API_BASE} + ${i}` "10.200.${i}.0" "255.255.255.252" "r${i}r${j}" "0.0.0.0"
    post_route "r${j}" `expr ${API_BASE} + ${j}` "10.200.${i}.0" "255.255.255.252" "r${j}r${i}" "0.0.0.0"
    i=`expr "$i" + 1`
  done

  # end-to-end static routes
  i=2
  while [ "$i" -le "$N" ]; do
    nh="10.200.`expr ${i} - 1`.1"
    post_route "r${i}" `expr ${API_BASE} + ${i}` "10.0.1.0" "255.255.255.0" "r${i}r`expr ${i} - 1`" "${nh}"
    i=`expr "$i" - 0 + 1`
  done
  i=1
  while [ "$i" -le `expr "$N" - 1` ]; do
    nh="10.200.${i}.2"
    post_route "r${i}" `expr ${API_BASE} + ${i}` "10.0.2.0" "255.255.255.0" "r${i}r`expr ${i} + 1`" "${nh}"
    i=`expr "$i" - 0 + 1`
  done

  green "Routers started. APIs are inside namespaces: r1..r${N} on 127.0.0.1:9001..`expr 9000 + ${N}`"
  printf "Tip: check logs: %s/rX.log\n" "${LOG_DIR}"
}

cmd_status() {
  need_root
  echo "=== Namespaces ==="; ip netns list 2>/dev/null
  if [ -f "${N_FILE}" ]; then
    N=`cat "${N_FILE}"`; echo "=== Router APIs (inside ns) ==="
    i=1
    while [ "$i" -le "$N" ]; do
      port=`expr ${API_BASE} + ${i}`
      echo "r${i}: http://127.0.0.1:${port}  (use: ip netns exec r${i} curl ...)"
      i=`expr "$i" + 1`
    done
  fi
  echo "=== PIDs ==="; ls -1 "${PID_DIR}" 2>/dev/null || true
  echo "=== Logs ==="; ls -1 "${LOG_DIR}" 2>/dev/null || true
}

cmd_ping() {
  need_root
  echo "Ping hL(10.0.1.10) -> hR(10.0.2.10)"
  ip netns exec hL ping -c 3 -W 1 10.0.2.10 || true
}

cmd_stats() {
  if [ ! -f "${N_FILE}" ]; then red "No lab found."; exit 1; fi
  N=`cat "${N_FILE}"`
  i=1
  while [ "$i" -le "$N" ]; do
    echo "---- r${i} /stats ----"
    port=`expr ${API_BASE} + ${i}`
    ip netns exec "r${i}" sh -c "curl -s http://127.0.0.1:${port}/stats" | python3 -m json.tool 2>/dev/null || true
    i=`expr "$i" + 1`
  done
}

cmd_stop() {
  need_root
  if [ ! -f "${N_FILE}" ]; then red "No lab found."; exit 1; fi
  N=`cat "${N_FILE}"`
  i=1
  while [ "$i" -le "$N" ]; do stop_router "r${i}"; i=`expr "$i" + 1`; done
  green "Routers stopped (namespaces kept)."
}

cmd_destroy() {
  need_root
  if [ -f "${N_FILE}" ]; then
    N=`cat "${N_FILE}"`; i=1
    while [ "$i" -le "$N" ]; do stop_router "r${i}"; i=`expr "$i" + 1`; done
  fi
  for ns in `ip netns list 2>/dev/null | awk '{print $1}'`; do
    case "$ns" in r[0-9]*|hL|hR) ip netns del "$ns" 2>/dev/null || true ;; esac
  done
  rm -rf "${STATE_DIR}" 2>/dev/null || true
  green "Destroyed lab (namespaces and state cleaned)."
}

usage() {
  cat <<USAGE
Usage:
  $0 chain <N>     Build a chain of N routers with two hosts
  $0 start         Start router processes (APIs are inside each netns)
  $0 status        Show namespaces, API hints, logs
  $0 ping          Ping from hL(10.0.1.10) to hR(10.0.2.10)
  $0 stats         Show /stats for all routers (netns-aware)
  $0 stop          Stop router processes (keep namespaces)
  $0 destroy       Remove namespaces and cleanup
Env:
  ROUTER_PY=/abs/path/router_l3.py
  STATE_DIR=/tmp/l3lab
USAGE
}

main() {
  cmd="$1"; [ -z "$cmd" ] && usage && exit 0
  shift 1
  case "$cmd" in
    chain)   cmd_chain "$@";;
    start)   cmd_start "$@";;
    status)  cmd_status "$@";;
    ping)    cmd_ping "$@";;
    stats)   cmd_stats "$@";;
    stop)    cmd_stop "$@";;
    destroy) cmd_destroy "$@";;
    *) usage;;
  esac
}
main "$@"
