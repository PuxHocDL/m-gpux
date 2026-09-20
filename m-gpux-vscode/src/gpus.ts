/**
 * GPU catalog shared by every wizard. Mirrors `m_gpux/core/gpus.py`;
 * prices are Modal list prices (USD per GPU-hour) and only used as hints.
 */
export interface GpuInfo {
  /** Modal `gpu=` string. */
  id: string;
  vramGb: number;
  maxCount: number;
  hourly: number;
  note: string;
}

export const GPU_CATALOG: GpuInfo[] = [
  { id: "T4",           vramGb: 16,  maxCount: 8, hourly: 0.59, note: "Turing — light inference / exploration" },
  { id: "L4",           vramGb: 24,  maxCount: 8, hourly: 0.80, note: "Ada — best price/performance for inference" },
  { id: "A10",          vramGb: 24,  maxCount: 4, hourly: 1.10, note: "Ampere — training & inference (formerly A10G)" },
  { id: "L40S",         vramGb: 48,  maxCount: 8, hourly: 1.95, note: "Ada — strong inference, big VRAM per $" },
  { id: "A100",         vramGb: 40,  maxCount: 8, hourly: 2.10, note: "Ampere — may be upgraded to 80GB at no extra cost" },
  { id: "A100-40GB",    vramGb: 40,  maxCount: 8, hourly: 2.10, note: "Ampere 40GB, pinned" },
  { id: "A100-80GB",    vramGb: 80,  maxCount: 8, hourly: 2.50, note: "Ampere 80GB — large training jobs" },
  { id: "RTX-PRO-6000", vramGb: 96,  maxCount: 8, hourly: 3.03, note: "Blackwell workstation GPU" },
  { id: "H100",         vramGb: 80,  maxCount: 8, hourly: 3.95, note: "Hopper — may be upgraded to H200 at no extra cost" },
  { id: "H100!",        vramGb: 80,  maxCount: 8, hourly: 3.95, note: "H100 pinned — never upgraded to H200" },
  { id: "H200",         vramGb: 141, maxCount: 8, hourly: 4.54, note: "Hopper with HBM3e" },
  { id: "B200",         vramGb: 180, maxCount: 8, hourly: 6.25, note: "Blackwell" },
  { id: "B200+",        vramGb: 180, maxCount: 8, hourly: 6.25, note: "B200 or B300, whichever is free first — billed as B200" },
  { id: "B300",         vramGb: 288, maxCount: 8, hourly: 7.10, note: "Blackwell Ultra — newest, most VRAM" },
];

export function gpuDescription(g: GpuInfo): string {
  return `${g.vramGb} GB · ~$${g.hourly.toFixed(2)}/h — ${g.note}`;
}

/** QuickPick items: `{ label, description, spec }` for every GPU. */
export function gpuQuickPickItems(): { label: string; description: string; spec: string }[] {
  return GPU_CATALOG.map((g) => ({ label: g.id, description: gpuDescription(g), spec: `gpu="${g.id}"` }));
}
