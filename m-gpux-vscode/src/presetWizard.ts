// Create + run workload presets. Storage is shared with the Python CLI
// (~/.m-gpux/presets.json), so presets created here are visible from
// `m-gpux preset list` and vice-versa.
import * as vscode from "vscode";
import * as path from "path";
import * as crypto from "crypto";
import { loadPresets, savePresets, deletePreset, Preset } from "./presetsTree";
import { loadProfiles, switchProfile, getActiveProfile } from "./config";
import { launchModalScript } from "./sessionLauncher";
import { toRecursiveIgnore, syncHelperBlock } from "./hubWizard";

const CPU_OPTIONS = [
  { label: "1 core / 512 MB",   spec: "cpu=1, memory=512",  compute: "CPU (1 core, 512 MB)" },
  { label: "2 cores / 1024 MB", spec: "cpu=2, memory=1024", compute: "CPU (2 cores, 1024 MB)" },
  { label: "4 cores / 2048 MB", spec: "cpu=4, memory=2048", compute: "CPU (4 cores, 2048 MB)" },
  { label: "8 cores / 4096 MB", spec: "cpu=8, memory=4096", compute: "CPU (8 cores, 4096 MB)" },
];

const GPU_OPTIONS = [
  { label: "T4",   spec: 'gpu="T4"',   description: "16 GB — budget" },
  { label: "L4",   spec: 'gpu="L4"',   description: "24 GB — balanced" },
  { label: "A10G", spec: 'gpu="A10G"', description: "24 GB" },
  { label: "A100", spec: 'gpu="A100"', description: "40 GB SXM" },
  { label: "H100", spec: 'gpu="H100"', description: "80 GB" },
];

export async function createPreset(): Promise<void> {
  const name = await vscode.window.showInputBox({
    title: "M-GPUX Preset — Name",
    placeHolder: "fast-jupyter / cpu-shell / a100-dev",
    validateInput: (v) => /^[A-Za-z0-9_-]{1,40}$/.test(v.trim())
      ? undefined
      : "Use letters, digits, dashes or underscores (max 40)",
  });
  if (!name) { return; }
  const existing = loadPresets();
  if (name in existing) {
    const overwrite = await vscode.window.showWarningMessage(
      `Preset '${name}' already exists. Overwrite?`,
      { modal: true }, "Overwrite"
    );
    if (overwrite !== "Overwrite") { return; }
  }

  const profiles = loadProfiles();
  let profileName = getActiveProfile()?.name ?? "";
  if (profiles.length > 1) {
    const pick = await vscode.window.showQuickPick(
      profiles.map((p) => ({ label: p.active ? `$(check) ${p.name}` : `$(person) ${p.name}`, profileName: p.name })),
      { title: "M-GPUX Preset — Profile (run on which workspace?)" }
    );
    if (!pick) { return; }
    profileName = (pick as any).profileName;
  }

  const actionPick = await vscode.window.showQuickPick(
    [
      { label: "$(terminal) Bash",     description: "Web bash shell with tmux",  action: "bash" },
      { label: "$(notebook) Jupyter",  description: "Jupyter Lab dev session",   action: "jupyter" },
    ],
    { title: "M-GPUX Preset — Action" }
  );
  if (!actionPick) { return; }
  const action = (actionPick as any).action as "bash" | "jupyter";

  const typePick = await vscode.window.showQuickPick(
    [
      { label: "$(symbol-misc) GPU", value: "gpu" },
      { label: "$(circuit-board) CPU", value: "cpu" },
    ],
    { title: "M-GPUX Preset — Compute type" }
  );
  if (!typePick) { return; }
  let computeSpec: string;
  let computeLabel: string;
  if ((typePick as any).value === "cpu") {
    const cpu = await vscode.window.showQuickPick(CPU_OPTIONS, { title: "Select CPU" });
    if (!cpu) { return; }
    computeSpec = cpu.spec;
    computeLabel = cpu.compute;
  } else {
    const gpu = await vscode.window.showQuickPick(GPU_OPTIONS, { title: "Select GPU" });
    if (!gpu) { return; }
    computeSpec = gpu.spec;
    computeLabel = gpu.label;
  }

  const pkgInput = await vscode.window.showInputBox({
    title: "M-GPUX Preset — Pip packages (comma-separated, blank for none)",
    placeHolder: "torch, transformers, datasets",
    value: "",
  });
  if (pkgInput === undefined) { return; }
  const pkgs = pkgInput.split(",").map((s) => s.trim()).filter(Boolean);
  const pipSection = pkgs.length === 0 ? "" : ".pip_install(" + pkgs.map((p) => JSON.stringify(p)).join(", ") + ")";

  const defaultExcludes = ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox";
  const excludeInput = await vscode.window.showInputBox({
    title: "M-GPUX Preset — Exclude patterns",
    value: defaultExcludes,
  });
  if (excludeInput === undefined) { return; }

  const preset: Preset = {
    action,
    profile: profileName,
    compute_spec: computeSpec,
    compute_label: computeLabel,
    python_version: "3.12",
    pip_section: pipSection,
    exclude_patterns: excludeInput.split(",").map((s) => s.trim()).filter(Boolean),
  };
  const all = loadPresets();
  all[name] = preset;
  savePresets(all);

  const run = await vscode.window.showInformationMessage(
    `Saved preset '${name}'. Run it now?`,
    "Run now", "Done"
  );
  if (run === "Run now") {
    await runPresetByName(name);
  }
}

export async function runPresetByName(name: string): Promise<void> {
  const preset = loadPresets()[name];
  if (!preset) {
    vscode.window.showErrorMessage(`Preset not found: ${name}`);
    return;
  }

  const profileName = preset.profile?.trim() || getActiveProfile()?.name;
  if (!profileName) {
    vscode.window.showErrorMessage("No profile attached to this preset and no active profile.");
    return;
  }
  switchProfile(profileName);

  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceFolder) {
    vscode.window.showErrorMessage("Open a workspace folder first.");
    return;
  }
  const cwd = workspaceFolder.replace(/\\/g, "/");
  const script = buildScript(preset, cwd);
  const volumeName = workspaceVolumeName(cwd);

  await launchModalScript({
    scriptContent: script,
    cwd,
    mode: "deploy",
    kind: preset.action,
    computeLabel: preset.compute_label ?? "preset",
    profile: profileName,
    preview: false, // presets are pre-approved — skip the review step
    workspaceVolume: volumeName,
  });
}

export async function deletePresetCommand(name: string): Promise<void> {
  const confirm = await vscode.window.showWarningMessage(
    `Delete preset '${name}'?`, { modal: true }, "Delete"
  );
  if (confirm !== "Delete") { return; }
  if (deletePreset(name)) {
    vscode.window.showInformationMessage(`Preset '${name}' deleted.`);
  } else {
    vscode.window.showWarningMessage(`Preset '${name}' not found.`);
  }
}

function workspaceVolumeName(localDir: string): string {
  const normalized = path.resolve(localDir);
  const base = path.basename(normalized) || "workspace";
  const slug = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32) || "workspace";
  const digest = crypto.createHash("sha1").update(normalized).digest("hex").slice(0, 10);
  return `m-gpux-workspace-${slug}-${digest}`;
}

function buildScript(preset: Preset, localDir: string): string {
  const computeSpec = preset.compute_spec ?? 'gpu="L4"';
  const pythonVersion = preset.python_version ?? "3.12";
  const pipSection = preset.pip_section ?? "";
  const excludes = preset.exclude_patterns ?? [];
  const workspaceVolume = workspaceVolumeName(localDir);
  const action = preset.action ?? "bash";

  // Both bash and jupyter scripts are condensed equivalents of the
  // hubWizard.ts templates, with the same workspace volume so the user can
  // pick up where they left off when they re-run the preset. Syncing back to
  // the volume is manual (`msync`) -- see syncHelperBlock in hubWizard.ts.
  if (action === "jupyter") {
    return `import modal, os, subprocess, threading, time

app = modal.App("m-gpux-jupyter")
workspace_volume = modal.Volume.from_name("${workspaceVolume}", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="${pythonVersion}")
    ${pipSection}
    .pip_install("jupyterlab>=4.2", "jupyter-server>=2.14", "ipywidgets", "jupyter-collaboration>=3.0")
    .add_local_dir("${localDir}", remote_path="/workspace_seed", ignore=${JSON.stringify(toRecursiveIgnore(excludes))})
)
MINUTE = 60; HOUR = 60 * MINUTE

def _prep():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

${syncHelperBlock(workspaceVolume)}
@app.function(image=image, ${computeSpec}, timeout=24 * HOUR, scaledown_window=60 * MINUTE, max_containers=1, volumes={"/workspace": workspace_volume})
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8888, startup_timeout=10 * MINUTE)
def serve():
    _prep(); _install_sync_helper()
    subprocess.Popen([
        "jupyter", "lab", "--no-browser", "--allow-root",
        "--ip=0.0.0.0", "--port", "8888",
        "--ServerApp.token=", "--ServerApp.password=",
        "--ServerApp.disable_check_xsrf=True", "--ServerApp.allow_origin=*",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.root_dir=/workspace",
        "--ServerApp.iopub_data_rate_limit=1.0e10",
        "--ServerApp.iopub_msg_rate_limit=1.0e10",
        "--ServerApp.rate_limit_window=3.0",
        "--ServerApp.shutdown_no_activity_timeout=0",
    ], env={**os.environ, "JUPYTER_PLATFORM_DIRS": "1"})
`;
  }
  // bash
  return `import modal, os, subprocess, threading, time

app = modal.App("m-gpux-shell")
workspace_volume = modal.Volume.from_name("${workspaceVolume}", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="${pythonVersion}")
    .apt_install("bash","curl","tmux","nano","vim","git","htop","btop","fzf","ripgrep","fd-find","bat","locales","ca-certificates","swig","build-essential","unzip")
    .run_commands(
        "curl -sLo /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && chmod +x /usr/local/bin/ttyd",
        "mkdir -p /root/.config",
    )
    ${pipSection}
    .add_local_dir("${localDir}", remote_path="/workspace_seed", ignore=${JSON.stringify(toRecursiveIgnore(excludes))})
)
MINUTE = 60; HOUR = 60 * MINUTE

def _prep():
    os.makedirs("/workspace", exist_ok=True)
    subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
    workspace_volume.commit()

${syncHelperBlock(workspaceVolume)}
@app.function(image=image, ${computeSpec}, timeout=24 * HOUR, scaledown_window=60 * MINUTE, max_containers=1, volumes={"/workspace": workspace_volume})
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8888, startup_timeout=5 * MINUTE)
def serve():
    _prep(); _install_sync_helper()
    env = {**os.environ, "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    subprocess.Popen(
        ["ttyd", "-W", "-P", "120", "-T", "xterm-256color", "-p", "8888",
         "bash", "-lc", "tmux new-session -A -s main"],
        env=env,
    )
`;
}
