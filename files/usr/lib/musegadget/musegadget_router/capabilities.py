"""Router capabilities that can be advertised to Muse as named commands.

Each capability is one command in the Muse command list. Handlers run in the
service process (root) with fixed argument lists, never through a shell, and
validate every parameter they take. Nothing is advertised unless the
administrator enabled it in /etc/config/musegadget.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import time

from musegadget.executor import error, ok

PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
HOST_RE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|[0-9A-Fa-f:]{2,45})$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SERVICE_ACTIONS = ("start", "stop", "restart", "reload")
NEVER_CONTROL = ("musegadget",)  # restarting it would kill the command that asked
MAX_LOG_LINES = 200
MAX_TEXT = 48 * 1024

GENERIC_COMMANDS = ("system.run", "file.read", "file.write", "device.health")


def _run(argv, timeout=10):
    proc = subprocess.run(
        argv, capture_output=True, text=True, errors="replace",
        timeout=timeout, env={"PATH": PATH, "LANG": "C"},
    )
    return proc.returncode, proc.stdout, proc.stderr


def _ubus(obj, method):
    code, out, err = _run(["ubus", "call", obj, method])
    if code != 0:
        raise RuntimeError(f"ubus {obj} {method}: {err.strip() or code}")
    return json.loads(out)


def _clip(text):
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n...[truncated]"


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _int_param(params, name, default, low, high):
    value = params.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return max(low, min(high, value))


# -- Read-only ----------------------------------------------------------------

def router_status(params):
    out = {}
    board = _ubus("system", "board")
    out["model"] = board.get("model")
    out["hostname"] = board.get("hostname")
    release = board.get("release") or {}
    out["firmware"] = release.get("description")
    info = _ubus("system", "info")
    out["uptime_s"] = info.get("uptime")
    out["load"] = [round(x / 65536, 2) for x in info.get("load", [])]
    mem = info.get("memory") or {}
    if mem:
        out["memory_mb"] = {"total": mem["total"] // 2**20, "free": mem["free"] // 2**20}
    try:
        out["connections"] = {
            "current": int(_read("/proc/sys/net/netfilter/nf_conntrack_count")),
            "max": int(_read("/proc/sys/net/netfilter/nf_conntrack_max")),
        }
    except (OSError, ValueError):
        pass
    interfaces = []
    for item in _ubus("network.interface", "dump").get("interface", []):
        if item.get("interface") == "loopback":
            continue
        interfaces.append({
            "name": item.get("interface"),
            "up": item.get("up"),
            "proto": item.get("proto"),
            "device": item.get("l3_device") or item.get("device"),
            "uptime_s": item.get("uptime"),
            "ipv4": [a["address"] for a in item.get("ipv4-address", [])],
            "ipv6": [a["address"] for a in item.get("ipv6-address", [])],
        })
    out["interfaces"] = interfaces
    return ok(out)


def router_clients(params):
    clients = {}
    try:
        for line in _read("/tmp/dhcp.leases").splitlines():
            parts = line.split()
            if len(parts) >= 4:
                expiry, mac, ip, host = parts[:4]
                clients[ip] = {
                    "ip": ip, "mac": mac, "hostname": None if host == "*" else host,
                    "lease_expires": int(expiry),
                }
    except OSError:
        pass
    _, neigh, _ = _run(["ip", "neigh", "show"])
    for line in neigh.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[1] != "dev":
            continue
        ip, dev = parts[0], parts[2]
        if ":" in ip:  # IPv6 neighbours repeat the IPv4 entry of the same device
            continue
        entry = clients.setdefault(ip, {"ip": ip, "mac": None, "hostname": None})
        entry["interface"] = dev
        entry["state"] = parts[-1]
        if "lladdr" in parts:
            entry["mac"] = parts[parts.index("lladdr") + 1]
    listed = [c for c in clients.values() if c.get("state") != "FAILED"]
    listed.sort(key=lambda c: tuple(int(p) if p.isdigit() else 0 for p in c["ip"].split(".")))
    return ok({"count": len(listed), "clients": listed[:200]})


def _net_dev():
    counters = {}
    for line in _read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        name = name.strip()
        if name != "lo" and len(fields) >= 10:
            counters[name] = (int(fields[0]), int(fields[8]))
    return counters


def router_traffic(params):
    seconds = _int_param(params, "sample_seconds", 0, 0, 10)
    first = _net_dev()
    if seconds:
        time.sleep(seconds)
    second = _net_dev() if seconds else first
    result = []
    for name, (rx, tx) in sorted(second.items()):
        entry = {"interface": name, "rx_bytes": rx, "tx_bytes": tx}
        if seconds and name in first:
            entry["rx_bps"] = (rx - first[name][0]) * 8 // seconds
            entry["tx_bps"] = (tx - first[name][1]) * 8 // seconds
        result.append(entry)
    return ok({"sample_seconds": seconds, "interfaces": result})


def router_services(params):
    try:
        running = set(_ubus("service", "list"))
    except (RuntimeError, ValueError):
        running = set()
    services = []
    for path in sorted(glob.glob("/etc/init.d/*")):
        name = os.path.basename(path)
        services.append({
            "name": name,
            "enabled": bool(glob.glob(f"/etc/rc.d/S??{name}")),
            "running": name in running,
        })
    return ok({"count": len(services), "services": services})


def router_log(params):
    lines = _int_param(params, "lines", 50, 1, MAX_LOG_LINES)
    needle = params.get("filter")
    if needle is not None and not isinstance(needle, str):
        return error("filter must be a string")
    _, out, _ = _run(["logread", "-l", str(MAX_LOG_LINES * 5 if needle else lines)])
    rows = out.splitlines()
    if needle:
        rows = [r for r in rows if needle.lower() in r.lower()]
    return ok({"log": _clip("\n".join(rows[-lines:]))})


def _host_param(params, name="host"):
    host = params.get(name)
    if not isinstance(host, str) or not HOST_RE.match(host):
        raise ValueError(f"{name} must be a hostname or IP address")
    return host


def router_ping(params):
    host = _host_param(params)
    count = _int_param(params, "count", 3, 1, 5)
    code, out, err = _run(["ping", "-c", str(count), "-W", "2", host], timeout=count * 3 + 5)
    return ok({"host": host, "reachable": code == 0, "output": _clip(out or err)})


def router_dns_lookup(params):
    name = _host_param(params, "name")
    argv = ["nslookup", name]
    if params.get("server") is not None:
        argv.append(_host_param(params, "server"))
    code, out, err = _run(argv, timeout=15)
    return ok({"name": name, "ok": code == 0, "output": _clip(out or err)})


# -- Actions (change the router) ------------------------------------------------

def router_service_control(params):
    name = params.get("service")
    action = params.get("action")
    allowed = os.environ.get("MUSEGADGET_CONTROL_SERVICES", "").split()
    if not isinstance(name, str) or not SERVICE_RE.match(name):
        return error("service must be a service name")
    if name in NEVER_CONTROL or name not in allowed:
        return error(f"service {name!r} is not in the list the administrator allowed")
    if action not in SERVICE_ACTIONS:
        return error("action must be one of: " + ", ".join(SERVICE_ACTIONS))
    script = f"/etc/init.d/{name}"
    if not os.access(script, os.X_OK):
        return error(f"no such service: {name}")
    code, out, err = _run([script, action], timeout=60)
    return ok({"service": name, "action": action, "exit_code": code, "output": _clip(out or err)})


def router_reboot(params):
    if params.get("confirm") is not True:
        return error("pass confirm=true to reboot the router")
    subprocess.Popen(
        ["sh", "-c", "sleep 5; reboot"], start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": PATH},
    )
    return ok({"message": "Rebooting in 5 seconds. The router will be offline for a minute or two."})


def _spec(description, required=None, optional=None, timeout_ms=None):
    spec = {"description": description, "required": required or {}, "optional": optional or {}}
    if timeout_ms:
        spec["timeout_ms"] = timeout_ms
    return spec


CAPABILITIES = [
    {
        "id": "router.status", "risk": "read", "handler": router_status,
        "title": "Router status",
        "summary": "Model, firmware, uptime, load, memory, connection count and every network interface with its addresses.",
        "spec": _spec("Router overview: model, firmware, uptime, load, memory, connection count, and each network interface (WAN/LAN) with state and IP addresses."),
    },
    {
        "id": "router.clients", "risk": "read", "handler": router_clients,
        "title": "Connected devices",
        "summary": "Hostnames, IPs and MAC addresses of devices on the LAN (DHCP leases and ARP table).",
        "spec": _spec("List devices on the router's network with IP, MAC address, hostname and reachability."),
    },
    {
        "id": "router.traffic", "risk": "read", "handler": router_traffic,
        "title": "Traffic counters",
        "summary": "Bytes sent and received per interface, with live rates if you ask for a sample.",
        "spec": _spec(
            "Network traffic per interface: total bytes received and sent since boot, and bits per second over a short sample.",
            optional={"sample_seconds": {"type": "integer", "description": "Measure live rates over this many seconds (0-10). Default 0 returns totals only."}},
            timeout_ms=20000,
        ),
    },
    {
        "id": "router.services", "risk": "read", "handler": router_services,
        "title": "Service list",
        "summary": "Which init services exist, which start at boot and which are running.",
        "spec": _spec("List the router's services with whether each starts at boot and is running."),
    },
    {
        "id": "router.log", "risk": "read", "handler": router_log,
        "title": "System log",
        "summary": "Recent lines of the router's system log, optionally filtered by a word.",
        "spec": _spec(
            "Read recent lines from the router's system log.",
            optional={
                "lines": {"type": "integer", "description": "How many recent lines to return (1-200). Default 50."},
                "filter": {"type": "string", "description": "Only return lines containing this text, case-insensitive."},
            },
        ),
    },
    {
        "id": "router.ping", "risk": "read", "handler": router_ping,
        "title": "Ping",
        "summary": "Ping a host from the router to test connectivity.",
        "spec": _spec(
            "Ping a hostname or IP address from the router and report whether it is reachable.",
            required={"host": {"type": "string", "description": "Hostname or IP address."}},
            optional={"count": {"type": "integer", "description": "Number of pings (1-5). Default 3."}},
            timeout_ms=25000,
        ),
    },
    {
        "id": "router.dns_lookup", "risk": "read", "handler": router_dns_lookup,
        "title": "DNS lookup",
        "summary": "Resolve a name using the router's DNS or a server you name.",
        "spec": _spec(
            "Resolve a hostname with the router's resolver, or with a specific DNS server.",
            required={"name": {"type": "string", "description": "Hostname to resolve."}},
            optional={"server": {"type": "string", "description": "DNS server to ask instead of the default."}},
            timeout_ms=20000,
        ),
    },
    {
        "id": "router.service_control", "risk": "action", "handler": router_service_control,
        "title": "Control services",
        "summary": "Start, stop or restart the services you list below. Muse can only touch services on that list.",
        "spec": _spec(
            "Start, stop, restart or reload one of the router's services. Only services the administrator allowed can be controlled.",
            required={
                "service": {"type": "string", "description": "Service name, as listed by router.services."},
                "action": {"type": "string", "description": "start, stop, restart or reload."},
            },
            timeout_ms=70000,
        ),
    },
    {
        "id": "router.reboot", "risk": "action", "handler": router_reboot,
        "title": "Reboot router",
        "summary": "Reboot the router. The network goes down for a minute or two.",
        "spec": _spec(
            "Reboot the router after a 5 second delay. The router, and so this connection, will be offline for a minute or two.",
            required={"confirm": {"type": "boolean", "description": "Must be true."}},
        ),
    },
]

BY_ID = {c["id"]: c for c in CAPABILITIES}
HANDLERS = {c["id"]: c["handler"] for c in CAPABILITIES}


def enabled_ids():
    wanted = os.environ.get("MUSEGADGET_CAPS", "").split()
    return [c["id"] for c in CAPABILITIES if c["id"] in wanted]


def disabled_generic():
    wanted = os.environ.get("MUSEGADGET_DISABLE", "").split()
    return [name for name in GENERIC_COMMANDS if name in wanted]


def catalog():
    """The capability list for the LuCI page."""
    return [{k: c[k] for k in ("id", "title", "summary", "risk")} for c in CAPABILITIES]
