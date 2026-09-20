"""Modal compute prices, for cost estimates in pickers and budgets.

Live prices come from ``modal.Workspace.billing.rates()`` (modal>=1.5.4) and are
cached in ``~/.m-gpux/rates.json`` so pickers never block on the network. When
nothing is cached we fall back to ``STATIC_RATES`` (snapshot of Modal's list
prices, USD).
"""

from __future__ import annotations

import time
from typing import Optional

from m_gpux.core.state import STATE_DIR, _read_json, _write_json

RATES_PATH = STATE_DIR / "rates.json"
RATES_MAX_AGE = 7 * 24 * 3600

# Snapshot of `modal billing rates` (2026-09). Keys match Modal's rate names.
STATIC_RATES: dict[str, float] = {
    "gpu_hour_cost_t4": 0.59,
    "gpu_hour_cost_l4": 0.80,
    "gpu_hour_cost_a10g": 1.10,
    "gpu_hour_cost_l40s": 1.95,
    "gpu_hour_cost_a100_40gb": 2.10,
    "gpu_hour_cost_a100_80gb": 2.50,
    "gpu_hour_cost_rtx6000": 3.03,
    "gpu_hour_cost_h100": 3.95,
    "gpu_hour_cost_h200": 4.54,
    "gpu_hour_cost_b200": 6.25,
    "gpu_hour_cost_b300": 7.10,
    "cpu_hour_cost": 0.0473,
    "mem_gib_hour_cost": 0.008,
    "cpu_hour_cost_sandbox": 0.1419,
    "mem_gib_hour_cost_sandbox": 0.024,
    "volume_storage_gib_month_cost": 0.09,
}

# Modal gpu= string (without ":count") → rate key.
GPU_RATE_KEYS: dict[str, str] = {
    "T4": "gpu_hour_cost_t4",
    "L4": "gpu_hour_cost_l4",
    "A10": "gpu_hour_cost_a10g",
    "A10G": "gpu_hour_cost_a10g",
    "L40S": "gpu_hour_cost_l40s",
    "A100": "gpu_hour_cost_a100_40gb",
    "A100-40GB": "gpu_hour_cost_a100_40gb",
    "A100-80GB": "gpu_hour_cost_a100_80gb",
    "RTX-PRO-6000": "gpu_hour_cost_rtx6000",
    "H100": "gpu_hour_cost_h100",
    "H100!": "gpu_hour_cost_h100",
    "H200": "gpu_hour_cost_h200",
    "B200": "gpu_hour_cost_b200",
    "B200+": "gpu_hour_cost_b200",
    "B300": "gpu_hour_cost_b300",
}


def load_rates() -> dict[str, float]:
    """Cached live rates merged over the static snapshot (never hits the network)."""
    rates = dict(STATIC_RATES)
    cached = _read_json(RATES_PATH, {})
    if isinstance(cached, dict) and isinstance(cached.get("rates"), dict):
        for k, v in cached["rates"].items():
            try:
                rates[k] = float(v)
            except (TypeError, ValueError):
                pass
    return rates


def rates_age_seconds() -> Optional[float]:
    cached = _read_json(RATES_PATH, {})
    fetched = cached.get("fetched_at") if isinstance(cached, dict) else None
    return time.time() - fetched if isinstance(fetched, (int, float)) else None


def refresh_rates(token_id: str, token_secret: str) -> dict[str, float]:
    """Fetch live rates from Modal (modal>=1.5.4) and update the cache."""
    import modal
    from modal.client import Client

    client = Client.from_credentials(str(token_id), str(token_secret))
    live = modal.Workspace.from_context(client=client).billing.rates()
    data = {k: float(v) for k, v in live.items() if k in STATIC_RATES or k.startswith(("gpu_", "cpu_", "mem_"))}
    _write_json(RATES_PATH, {"fetched_at": time.time(), "rates": data})
    return load_rates()


def split_gpu_spec(spec: str) -> tuple[str, int]:
    """``"H100:4"`` → ``("H100", 4)``."""
    name, _, count = spec.partition(":")
    try:
        return name, max(int(count), 1) if count else 1
    except ValueError:
        return name, 1


def gpu_hourly(spec: str, rates: Optional[dict[str, float]] = None) -> Optional[float]:
    """GPU-only $/hour for a Modal gpu string such as ``"A100-80GB:2"``."""
    rates = rates or load_rates()
    name, count = split_gpu_spec(spec)
    key = GPU_RATE_KEYS.get(name)
    return rates[key] * count if key and key in rates else None


def cpu_hourly(cores: float, memory_mb: int, sandbox: bool = False, rates: Optional[dict[str, float]] = None) -> float:
    """$/hour for CPU cores + memory. Sandboxes are billed at the higher sandbox rates."""
    rates = rates or load_rates()
    suffix = "_sandbox" if sandbox else ""
    return cores * rates["cpu_hour_cost" + suffix] + (memory_mb / 1024) * rates["mem_gib_hour_cost" + suffix]


def fmt_hourly(value: Optional[float]) -> str:
    if value is None:
        return "price n/a"
    return f"~${value:.2f}/h" if value >= 0.1 else f"~${value:.3f}/h"
