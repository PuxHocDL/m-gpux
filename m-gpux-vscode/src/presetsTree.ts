// Presets are stored in ~/.m-gpux/presets.json — same path the Python CLI
// uses, so a preset created here is visible from `m-gpux preset list` and
// vice-versa.
import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const PRESETS_DIR = path.join(os.homedir(), ".m-gpux");
const PRESETS_PATH = path.join(PRESETS_DIR, "presets.json");

export interface Preset {
  action: string;           // "bash" | "jupyter"
  profile?: string;
  compute_spec?: string;    // e.g. 'gpu="L4"' or 'cpu=4, memory=2048'
  compute_label?: string;
  python_version?: string;
  pip_section?: string;
  exclude_patterns?: string[];
}

export type PresetMap = Record<string, Preset>;

export function loadPresets(): PresetMap {
  try {
    if (!fs.existsSync(PRESETS_PATH)) { return {}; }
    return JSON.parse(fs.readFileSync(PRESETS_PATH, "utf-8")) as PresetMap;
  } catch { return {}; }
}

export function savePresets(presets: PresetMap): void {
  fs.mkdirSync(PRESETS_DIR, { recursive: true });
  fs.writeFileSync(PRESETS_PATH, JSON.stringify(presets, null, 2) + "\n", "utf-8");
}

export function deletePreset(name: string): boolean {
  const all = loadPresets();
  if (!(name in all)) { return false; }
  delete all[name];
  savePresets(all);
  return true;
}

export class PresetsTreeProvider implements vscode.TreeDataProvider<PresetItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<PresetItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void { this._onDidChangeTreeData.fire(); }

  getTreeItem(element: PresetItem): vscode.TreeItem { return element; }

  getChildren(): PresetItem[] {
    const all = loadPresets();
    const names = Object.keys(all).sort();
    if (names.length === 0) {
      return [new PresetItem(
        "No presets yet",
        "Click + to create one",
        "info",
        undefined,
        "mgpux.createPreset",
        true
      )];
    }
    return names.map((name) => {
      const p = all[name];
      const compute = p.compute_label ?? p.compute_spec ?? "?";
      const desc = `${p.action ?? "?"} • ${compute}${p.profile ? ` • ${p.profile}` : ""}`;
      return new PresetItem(name, desc, p.action === "jupyter" ? "notebook" : "terminal", name, "mgpux.runPreset", false);
    });
  }
}

export class PresetItem extends vscode.TreeItem {
  public readonly presetName?: string;
  public readonly isPlaceholder: boolean;

  constructor(
    label: string,
    description: string,
    icon: string,
    presetName: string | undefined,
    commandId: string,
    isPlaceholder: boolean
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = description;
    this.iconPath = new vscode.ThemeIcon(icon);
    this.presetName = presetName;
    this.isPlaceholder = isPlaceholder;
    this.contextValue = isPlaceholder ? "preset-empty" : "preset";
    this.command = {
      command: commandId,
      title: label,
      arguments: presetName ? [this] : [],
    };
  }
}
