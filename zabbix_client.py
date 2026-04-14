"""
Zabbix API client — token-based authentication (Zabbix 5.4+).

Key operations:
  - is_trigger_active()      : check if trigger is still in PROBLEM state
  - get_top5_current()       : fetch latest Top-5 item value from the host
  - get_process_history_30d(): fetch 30 days of Top-5 item history
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Zabbix history value_type for text items (JSON strings returned by system.run)
HISTORY_TYPE_TEXT = 4


class ZabbixClient:
    def __init__(self):
        self._url   = settings.zabbix_url
        self._token = settings.zabbix_token
        self._req_id = 0

    # ------------------------------------------------------------------
    # Low-level JSON-RPC call
    # ------------------------------------------------------------------
    async def _call(self, method: str, params: dict) -> list | dict:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method":  method,
            "params":  params,
            "id":      self._req_id,
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"Zabbix API error [{method}]: {data['error'].get('data', data['error'])}"
            )
        return data.get("result", [])

    # ------------------------------------------------------------------
    # Host lookup
    # ------------------------------------------------------------------
    async def get_host_id(self, host: str) -> Optional[str]:
        result = await self._call("host.get", {
            "filter": {"host": [host]},
            "output": ["hostid"],
        })
        if not result:
            logger.warning(f"Host '{host}' not found in Zabbix.")
            return None
        return result[0]["hostid"]

    # ------------------------------------------------------------------
    # Trigger / problem status
    # ------------------------------------------------------------------
    async def is_trigger_active(self, host: str, trigger_name: str) -> bool:
        """
        Returns True if the trigger is still in PROBLEM state (value == "1").
        Falls back to True (assume active) if the trigger cannot be found,
        so the alert is not silently dropped.
        """
        result = await self._call("trigger.get", {
            "output":    ["triggerid", "value", "description"],
            "host":      host,
            "search":    {"description": trigger_name},
            "monitored": True,
            "active":    True,
        })
        if not result:
            logger.warning(
                f"Trigger not found for host='{host}', trigger='{trigger_name}'. "
                "Assuming still active (fail-safe)."
            )
            return True  # fail-safe: do not silently skip the alert

        # value "1" = PROBLEM, "0" = OK
        active = any(t.get("value") == "1" for t in result)
        logger.info(f"Trigger '{trigger_name}' on '{host}' active={active}")
        return active

    # ------------------------------------------------------------------
    # Current snapshot
    # ------------------------------------------------------------------
    async def get_top5_current(self, host: str, alert_type: str) -> dict:
        """
        Returns the latest Top-5 dict from Zabbix item lastvalue.
        Example: {"java": 82.0, "python": 41.0, ...}
        """
        host_id = await self.get_host_id(host)
        if not host_id:
            return {}

        item_name = (
            settings.cpu_top_item_name
            if alert_type == "cpu"
            else settings.memory_top_item_name
        )
        result = await self._call("item.get", {
            "hostids": [host_id],
            "search":  {"name": item_name},
            "output":  ["itemid", "name", "lastvalue"],
            "limit":   1,
        })

        if not result:
            logger.error(f"Item '{item_name}' not found on host '{host}'.")
            return {}

        raw = result[0].get("lastvalue", "")
        if not raw:
            logger.error(f"Item '{item_name}' has no lastvalue on host '{host}'.")
            return {}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Cannot parse lastvalue as JSON: {raw[:200]}")
            return {}

    # ------------------------------------------------------------------
    # 30-day history
    # ------------------------------------------------------------------
    async def get_process_history_30d(self, host: str, alert_type: str) -> list[dict]:
        """
        Fetches up to 500 historical snapshots of the Top-5 item over the last 30 days.
        Returns: [{"time": datetime, "processes": {"java": 82.0, ...}}, ...]
        """
        host_id = await self.get_host_id(host)
        if not host_id:
            return []

        item_name = (
            settings.cpu_top_item_name
            if alert_type == "cpu"
            else settings.memory_top_item_name
        )
        items = await self._call("item.get", {
            "hostids": [host_id],
            "search":  {"name": item_name},
            "output":  ["itemid", "value_type"],
            "limit":   1,
        })
        if not items:
            logger.warning(f"Cannot find item '{item_name}' for history lookup.")
            return []

        item_id    = items[0]["itemid"]
        value_type = int(items[0].get("value_type", HISTORY_TYPE_TEXT))

        time_from = int((datetime.utcnow() - timedelta(days=settings.history_days)).timestamp())

        raw_history = await self._call("history.get", {
            "itemids":   [item_id],
            "time_from": time_from,
            "output":    "extend",
            "history":   value_type,
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit":     settings.history_limit,
        })

        snapshots = []
        for entry in raw_history:
            try:
                processes = json.loads(entry["value"])
                snapshots.append({
                    "time":      datetime.utcfromtimestamp(int(entry["clock"])),
                    "processes": processes,
                })
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        logger.info(
            f"Fetched {len(snapshots)} historical snapshots for '{host}' / {alert_type} "
            f"(last {settings.history_days} days)."
        )
        return snapshots
