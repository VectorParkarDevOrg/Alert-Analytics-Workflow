"""
Zabbix API connectivity and item discovery test.

Usage:
    python test_zabbix.py                  # check API + list first 10 hosts
    python test_zabbix.py <hostname>       # check API + verify items on host
"""
import asyncio
import sys
import json
import httpx
from config import settings

BOLD  = "\033[1m"
GREEN = "\033[32m"
RED   = "\033[31m"
WARN  = "\033[33m"
RESET = "\033[0m"

OK   = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
WARN_SIGN = f"{WARN}!{RESET}"


async def call(method: str, params: dict) -> list | dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {"Authorization": f"Bearer {settings.zabbix_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(settings.zabbix_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("data", data["error"]))
    return data.get("result", [])


async def main():
    hostname = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"\n{BOLD}=== Zabbix Connectivity Test ==={RESET}")
    print(f"  URL   : {settings.zabbix_url}")
    print(f"  Token : {settings.zabbix_token[:8]}{'*' * (len(settings.zabbix_token) - 8)}\n")

    # 1. Reachability
    print(f"{BOLD}1. API Reachability{RESET}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.zabbix_url,
                                     json={"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1})
        resp.raise_for_status()
        print(f"  {OK} HTTP {resp.status_code} — server reachable")
    except Exception as e:
        print(f"  {FAIL} Cannot reach Zabbix: {e}")
        return

    # 2. Token + version
    print(f"\n{BOLD}2. API Version + Token Check{RESET}")
    try:
        version = await call("apiinfo.version", {})
        print(f"  {OK} Zabbix API version: {version}")
        await call("host.get", {"limit": 1, "output": ["hostid"]})
        print(f"  {OK} Token valid — API token accepted")
    except Exception as e:
        print(f"  {FAIL} Token invalid or API error: {e}")
        return

    # 3. Host lookup / item check
    print(f"\n{BOLD}3. Host Lookup{RESET}")
    if not hostname:
        print(f"  {WARN_SIGN} No hostname provided. Run: python test_zabbix.py <your-zabbix-hostname>")
        print(f"  {WARN_SIGN} Listing first 10 hosts instead:")
        hosts = await call("host.get", {"output": ["host", "name"], "limit": 10})
        for h in hosts:
            print(f"     {h['name']}  ({h['host']})")
        return

    hosts = await call("host.get", {"filter": {"host": [hostname]}, "output": ["hostid", "name"]})
    if not hosts:
        print(f"  {FAIL} Host '{hostname}' not found in Zabbix.")
        return

    host_id = hosts[0]["hostid"]
    print(f"  {OK} Host found: {hosts[0]['name']} (ID: {host_id})")

    # 4. Check required items
    print(f"\n{BOLD}4. Required Item Check{RESET}")
    for alert_type, item_name in [
        ("cpu",    settings.cpu_top_item_name),
        ("memory", settings.memory_top_item_name),
    ]:
        items = await call("item.get", {
            "hostids": [host_id],
            "search":  {"name": item_name},
            "output":  ["itemid", "name", "lastvalue"],
            "limit":   1,
        })
        if not items:
            print(f"  {FAIL} [{alert_type.upper()}] Item not found: '{item_name}'")
            continue

        item = items[0]
        raw  = item.get("lastvalue", "")
        if not raw:
            print(f"  {WARN_SIGN} [{alert_type.upper()}] Item found but has no value yet: '{item_name}'")
            continue

        try:
            parsed = json.loads(raw)
            top = sorted(parsed.items(), key=lambda x: -x[1])[:3]
            preview = ", ".join(f"{k}: {v}" for k, v in top)
            print(f"  {OK} [{alert_type.upper()}] '{item_name}'")
            print(f"       Latest value: {{{preview}, ...}}")
        except json.JSONDecodeError:
            print(f"  {WARN_SIGN} [{alert_type.upper()}] Item found but value is not valid JSON: {raw[:80]}")


asyncio.run(main())
