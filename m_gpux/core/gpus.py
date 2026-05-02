"""Catalog of available compute SKUs (GPU and CPU)."""

AVAILABLE_GPUS: dict[str, tuple[str, str]] = {
    "1":  ("T4",            "Light inference/exploration (16GB)"),
    "2":  ("L4",            "Balance of cost/performance (24GB)"),
    "3":  ("A10G",          "Good alternative for training/inference (24GB)"),
    "4":  ("L40S",          "Ada Lovelace, great for inference (48GB)"),
    "5":  ("A100",          "High performance (40GB, default SXM)"),
    "6":  ("A100-40GB",     "Ampere 40GB variant"),
    "7":  ("A100-80GB",     "Extreme performance (80GB)"),
    "8":  ("RTX-PRO-6000",  "RTX PRO 6000 — pro workstation GPU (48GB)"),
    "9":  ("H100",          "Hopper architecture (80GB)"),
    "10": ("H100!",         "H100 priority/reserved — guaranteed availability"),
    "11": ("H200",          "Next-gen Hopper with HBM3e (141GB)"),
    "12": ("B200",          "Blackwell architecture — latest gen"),
    "13": ("B200+",         "B200 priority/reserved — guaranteed availability"),
}

AVAILABLE_CPUS: dict[str, tuple[int, int, str]] = {
    "1":  (1,   512,    "1 core, 512 MB — minimal testing"),
    "2":  (2,   1024,   "2 cores, 1 GB — light models"),
    "3":  (4,   2048,   "4 cores, 2 GB — small models"),
    "4":  (8,   4096,   "8 cores, 4 GB — medium models"),
    "5":  (16,  8192,   "16 cores, 8 GB — larger models"),
    "6":  (32,  16384,  "32 cores, 16 GB — large models"),
    "7":  (64,  32768,  "64 cores, 32 GB — max performance"),
}
