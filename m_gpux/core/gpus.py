"""Catalog of available compute SKUs (GPU and CPU).

Every compute picker reads from here. ``AVAILABLE_GPUS`` values are
``(modal_gpu_string, description)``; the description ends with the estimated
hourly price from :mod:`m_gpux.core.pricing`.
"""

from __future__ import annotations

from m_gpux.core.pricing import cpu_hourly, fmt_hourly, gpu_hourly, load_rates

# (Modal gpu= string, VRAM per GPU in GB, max GPUs per container, description)
GPU_CATALOG: list[tuple[str, int, int, str]] = [
    ("T4", 16, 8, "Turing — light inference / exploration"),
    ("L4", 24, 8, "Ada — best price/performance for inference"),
    ("A10", 24, 4, "Ampere — training & inference (formerly A10G)"),
    ("L40S", 48, 8, "Ada — strong inference, big VRAM per $"),
    ("A100", 40, 8, "Ampere — may be upgraded to 80GB at no extra cost"),
    ("A100-40GB", 40, 8, "Ampere 40GB, pinned"),
    ("A100-80GB", 80, 8, "Ampere 80GB — large training jobs"),
    ("RTX-PRO-6000", 96, 8, "Blackwell workstation GPU"),
    ("H100", 80, 8, "Hopper — may be upgraded to H200 at no extra cost"),
    ("H100!", 80, 8, "H100 pinned — never upgraded to H200"),
    ("H200", 141, 8, "Hopper with HBM3e"),
    ("B200", 180, 8, "Blackwell"),
    ("B200+", 180, 8, "B200 or B300, whichever is free first — billed as B200"),
    ("B300", 288, 8, "Blackwell Ultra — newest, most VRAM"),
]

GPU_MAX_COUNT: dict[str, int] = {name: max_n for name, _, max_n, _ in GPU_CATALOG}
GPU_VRAM_GB: dict[str, int] = {name: vram for name, vram, _, _ in GPU_CATALOG}


def _gpu_entries() -> dict[str, tuple[str, str]]:
    rates = load_rates()
    return {
        str(i): (name, f"{desc} ({vram}GB) · {fmt_hourly(gpu_hourly(name, rates))}")
        for i, (name, vram, _, desc) in enumerate(GPU_CATALOG, start=1)
    }


def _cpu_entries() -> dict[str, tuple[int, int, str]]:
    rates = load_rates()
    base = [
        (1, 512, "minimal testing"),
        (2, 1024, "light models"),
        (4, 2048, "small models"),
        (8, 4096, "medium models"),
        (16, 8192, "larger models"),
        (32, 16384, "large models"),
        (64, 32768, "max performance"),
    ]
    return {
        str(i): (
            cores,
            mem,
            f"{cores} cores, {mem // 1024 or 0.5} GB — {label} · {fmt_hourly(cpu_hourly(cores, mem, rates=rates))}",
        )
        for i, (cores, mem, label) in enumerate(base, start=1)
    }


AVAILABLE_GPUS: dict[str, tuple[str, str]] = _gpu_entries()
AVAILABLE_CPUS: dict[str, tuple[int, int, str]] = _cpu_entries()


def ask_gpu_count(gpu: str, default: int = 1) -> str:
    """Ask how many GPUs to attach; returns a Modal gpu string like ``"H100:2"``."""
    from rich.prompt import IntPrompt

    from m_gpux.core.console import console

    max_n = GPU_MAX_COUNT.get(gpu, 8)
    while True:
        n = IntPrompt.ask(f"How many {gpu} GPUs? (1–{max_n})", default=default)
        if 1 <= n <= max_n:
            break
        console.print(f"[red]{gpu} supports 1–{max_n} GPUs per container.[/red]")
    spec = gpu if n == 1 else f"{gpu}:{n}"
    if n > 1:
        console.print(f"[dim]{spec} → {fmt_hourly(gpu_hourly(spec))} for the GPUs[/dim]")
    return spec
