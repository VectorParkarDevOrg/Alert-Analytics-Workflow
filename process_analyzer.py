"""
Analyzes current top-5 processes against 30-day Zabbix history.
Pure logic — no I/O, fully testable in isolation.
"""
from datetime import datetime
from typing import Optional

from config import settings


def analyze_processes(
    top5: dict,
    history: list[dict],
    alert_type: str,
) -> dict:
    """
    Parameters
    ----------
    top5       : {process_name: value} from Zabbix current snapshot
    history    : [{"time": datetime, "processes": {...}}, ...] — 30-day snapshots
    alert_type : "cpu" or "memory"

    Returns
    -------
    {
        "top5_sorted"        : [(name, value), ...],
        "process_stats"      : {name: {value, unit, historical_count, last_seen, seen_before}},
        "summary"            : str,
        "recurring_processes": [name, ...],
        "new_processes"      : [name, ...],
    }
    """
    unit = "CPU%" if alert_type == "cpu" else "MEM%"

    # Sort and cap at configured top-N count
    top5_sorted: list[tuple[str, float]] = sorted(
        top5.items(), key=lambda x: -x[1]
    )[:settings.top_process_count]

    # --- per-process historical stats ---
    process_stats: dict[str, dict] = {}
    for proc_name, proc_val in top5_sorted:
        count = 0
        last_seen: Optional[datetime] = None

        for snapshot in history:
            if proc_name in snapshot["processes"]:
                count += 1
                t = snapshot["time"]
                if last_seen is None or t > last_seen:
                    last_seen = t

        process_stats[proc_name] = {
            "value":             proc_val,
            "unit":              unit,
            "historical_count":  count,
            "last_seen":         last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else None,
            "seen_before":       count > 0,
        }

    # --- classify ---
    recurring = [n for n, s in process_stats.items() if s["seen_before"]]
    new_procs  = [n for n, s in process_stats.items() if not s["seen_before"]]

    # --- build human-readable summary ---
    names = [p[0] for p in top5_sorted]
    lines = [
        f"Top {settings.top_process_count} {alert_type.upper()}-consuming processes on this host: "
        + ", ".join(names) + ".",
        "",
        f"Historical analysis (last {settings.history_days} days):",
    ]

    for name, stats in process_stats.items():
        if stats["seen_before"]:
            lines.append(
                f"  • {name}: seen {stats['historical_count']} time(s), "
                f"last on {stats['last_seen']}"
            )
        else:
            lines.append(f"  • {name}: not seen before in previous alerts")

    lines.append("")
    if recurring:
        primary = max(recurring, key=lambda n: process_stats[n]["historical_count"])
        cnt     = process_stats[primary]["historical_count"]
        lines.append(
            f"This appears to be a recurring issue. "
            f"'{primary}' is the primary contributor "
            f"(appeared {cnt} time(s) in the last 30 days)."
        )
    else:
        lines.append(
            "None of the current top processes were seen in similar alerts "
            "during the last 30 days. This appears to be a new issue."
        )

    return {
        "top5_sorted":         top5_sorted,
        "process_stats":       process_stats,
        "summary":             "\n".join(lines),
        "recurring_processes": recurring,
        "new_processes":       new_procs,
    }
