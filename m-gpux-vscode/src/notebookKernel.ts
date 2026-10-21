// Notebook kernels on Modal GPUs, straight from VS Code's kernel picker.
//
// We register a Jupyter Server Collection with the Jupyter extension
// (ms-toolsai.jupyter). In any .ipynb: Select Kernel → "M-GPUX — Modal GPU" →
// "New Modal GPU server…" asks for an account, a GPU, packages and an idle
// timeout, then starts `jupyter server` inside a Modal container (behind a
// modal.forward tunnel, protected by a random token) and hands the URL + token
// to the Jupyter extension. Cells then run on the GPU.
//
// Cost control: kernels idle for the chosen time are culled, the server then
// shuts itself down, the Modal function returns and the container stops. The
// server also shows up in Active Sessions, where Stop / Pull work as usual.
import * as vscode from "vscode";
import * as crypto from "crypto";
import * as fs from "fs";
import * as http from "http";
import * as https from "https";
import * as path from "path";
import type {
  Jupyter,
  JupyterServer,
  JupyterServerCollection,
  JupyterServerCommand,
  JupyterServerCommandProvider,
  JupyterServerProvider,
} from "@vscode/jupyter-extension";
import { getActiveProfile, loadProfiles } from "./config";
import { GPU_CATALOG, gpuDescription } from "./gpus";
import { syncHelperBlock, toRecursiveIgnore, workspaceVolumeName } from "./hubWizard";
import { modalCommand } from "./modalCli";
import { appendSessionLog, newSessionId, sessionLogPath, sessionStore } from "./sessionStore";

const { spawn } = require("child_process");

const JUPYTER_EXTENSION_ID = "ms-toolsai.jupyter";
const COLLECTION_ID = "mgpux-modal";
const STATE_KEY = "mgpux.notebookServers";
const SECRET_PREFIX = "mgpux.notebookToken.";
const PYTHON_VERSION = "3.12";
const MAX_HOURS = 24;
const STARTUP_TIMEOUT_MS = 20 * 60_000; // first image build can be slow
const DEFAULT_EXCLUDES = [
  ".venv", "venv", "__pycache__", ".git", "node_modules",
  ".mypy_cache", ".pytest_cache", "*.egg-info", ".tox", ".ipynb_checkpoints",
];
const URL_MARKER = "MGPUX_JUPYTER_URL=";
const PIP_SPEC = /^[A-Za-z0-9_.\[\]=<>!~,-]+$/;
// tensorrt-* and many nvidia-* packages on PyPI are placeholders that fetch
// the real wheel from NVIDIA at install time, which fails inside image builds;
// pointing pip at NVIDIA's index installs the real wheel directly.
const NVIDIA_INDEX = "https://pypi.nvidia.com";
const NVIDIA_PACKAGE = /^(tensorrt|nvidia-|polygraphy|onnx-graphsurgeon|cuda-python)/i;

function needsNvidiaIndex(specs: string[]): boolean {
  return specs.some((spec) => NVIDIA_PACKAGE.test(spec.trim()));
}

/** Package names listed in a requirements file (options, comments and blanks skipped). */
function requirementNames(file: string): string[] {
  try {
    return fs.readFileSync(file, "utf-8").split(/\r?\n/)
      .map((line) => line.replace(/#.*/, "").trim())
      .filter((line) => line && !line.startsWith("-"));
  } catch {
    return [];
  }
}

interface NotebookServer {
  id: string;
  label: string;
  baseUrl: string;
  sessionId: string;
  profile: string;
  compute: string;
  startedAt: number;
}

export interface LaunchOptions {
  profile: string;
  compute: { label: string; spec: string };
  requirements?: string;
  packages: string[];
  idleSeconds: number;
  localDir?: string;
}

// ─── Remote script ─────────────────────────────────────────────

export function serverScript(opts: LaunchOptions): string {
  const volume = opts.localDir ? workspaceVolumeName(opts.localDir) : "m-gpux-notebook-scratch";
  const steps = [`modal.Image.debian_slim(python_version=${JSON.stringify(PYTHON_VERSION)})`];
  steps.push(`.pip_install("jupyter-server>=2.14", "ipykernel>=6.29", "ipywidgets>=8")`);
  const nvidiaIndex = (specs: string[]) => (needsNvidiaIndex(specs) ? `, extra_index_url=${JSON.stringify(NVIDIA_INDEX)}` : "");
  if (opts.requirements) {
    steps.push(`.pip_install_from_requirements(${JSON.stringify(opts.requirements)}${nvidiaIndex(requirementNames(opts.requirements))})`);
  }
  if (opts.packages.length) {
    steps.push(`.pip_install(${opts.packages.map((p) => JSON.stringify(p)).join(", ")}${nvidiaIndex(opts.packages)})`);
  }
  if (opts.localDir) {
    steps.push(
      `.add_local_dir(${JSON.stringify(opts.localDir)}, remote_path="/workspace_seed", ` +
      `ignore=${JSON.stringify(toRecursiveIgnore(DEFAULT_EXCLUDES))})`
    );
  }
  return `import os
import socket
import subprocess
import time

import modal

app = modal.App("m-gpux-notebook")
workspace_volume = modal.Volume.from_name(${JSON.stringify(volume)}, create_if_missing=True)
image = (
    ${steps.join("\n    ")}
)


${syncHelperBlock(volume)}

def _wait_for_port(port, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


@app.function(
    image=image,
    ${opts.compute.spec},
    timeout=${MAX_HOURS} * 60 * 60,
    volumes={"/workspace": workspace_volume},
)
def notebook_server(token: str, idle_seconds: int):
    os.makedirs("/workspace", exist_ok=True)
    if os.path.isdir("/workspace_seed"):
        # Local files win on every launch; remote-only outputs stay.
        subprocess.run(["cp", "-a", "/workspace_seed/.", "/workspace/"], check=False)
        workspace_volume.commit()
    _install_sync_helper()

    cmd = [
        "jupyter", "server",
        "--no-browser", "--allow-root",
        "--ip=0.0.0.0", "--port=8888",
        f"--IdentityProvider.token={token}",
        "--ServerApp.root_dir=/workspace",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.iopub_data_rate_limit=1.0e10",
        "--ServerApp.iopub_msg_rate_limit=1.0e10",
    ]
    if idle_seconds > 0:
        # Idle kernels are culled even while VS Code stays connected (a busy
        # kernel never is); with no kernels left the server exits, this
        # function returns and Modal stops the container.
        cmd += [
            f"--MappingKernelManager.cull_idle_timeout={idle_seconds}",
            "--MappingKernelManager.cull_interval=60",
            "--MappingKernelManager.cull_connected=True",
            f"--ServerApp.shutdown_no_activity_timeout={idle_seconds}",
        ]

    with modal.forward(8888) as tunnel:
        proc = subprocess.Popen(cmd, cwd="/workspace", env={**os.environ, "JUPYTER_PLATFORM_DIRS": "1"})
        if _wait_for_port(8888):
            print("${URL_MARKER}" + tunnel.url, flush=True)
        else:
            print("[m-gpux] Jupyter server did not start listening on :8888", flush=True)
            proc.terminate()
        proc.wait()
    workspace_volume.commit()
    print("[m-gpux] Jupyter server stopped.", flush=True)


@app.local_entrypoint()
def main():
    notebook_server.remote(os.environ["MGPUX_JUPYTER_TOKEN"], int(os.environ.get("MGPUX_IDLE_SECONDS", "0")))
`;
}

// ─── Helpers ───────────────────────────────────────────────────

/** GET <baseUrl>/api/status with the token; resolves true on HTTP 200. */
function isServerAlive(baseUrl: string, token: string, timeoutMs = 5000): Promise<boolean> {
  return new Promise((resolve) => {
    let url: URL;
    try { url = new URL("api/status", baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`); } catch { resolve(false); return; }
    const req = (url.protocol === "http:" ? http : https).get(url, { headers: { Authorization: `token ${token}` }, timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.on("error", () => resolve(false));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function cancelled(): never {
  throw new vscode.CancellationError();
}

function workspaceDirFor(): string | undefined {
  const nb = vscode.window.activeNotebookEditor?.notebook.uri;
  if (nb?.scheme === "file") {
    const folder = vscode.workspace.getWorkspaceFolder(nb);
    return (folder?.uri.fsPath ?? path.dirname(nb.fsPath)).replace(/\\/g, "/");
  }
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath.replace(/\\/g, "/");
}

// ─── Wizard ────────────────────────────────────────────────────

async function askLaunchOptions(): Promise<LaunchOptions> {
  const profiles = loadProfiles();
  if (profiles.length === 0) {
    const choice = await vscode.window.showErrorMessage("M-GPUX: add a Modal account first.", "Add Account");
    if (choice === "Add Account") { await vscode.commands.executeCommand("mgpux.addAccount"); }
    cancelled();
  }
  const active = getActiveProfile()?.name ?? profiles[0].name;
  let profile = active;
  if (profiles.length > 1) {
    const pick = await vscode.window.showQuickPick(
      [...profiles].sort((a, b) => Number(b.name === active) - Number(a.name === active)).map((p) => ({
        label: p.name, description: p.name === active ? "active" : undefined,
      })),
      { title: "GPU notebook — Modal account", ignoreFocusOut: true }
    );
    if (!pick) { cancelled(); }
    profile = pick.label;
  }

  const compute = await vscode.window.showQuickPick(
    [
      ...GPU_CATALOG.map((g) => ({ label: `$(chip) ${g.id}`, description: gpuDescription(g), value: { label: g.id, spec: `gpu=${JSON.stringify(g.id)}` } })),
      { label: "$(server) CPU only", description: "4 cores · 16 GB — no GPU charges", value: { label: "CPU 4c/16GB", spec: "cpu=4.0, memory=16384" } },
    ],
    { title: "GPU notebook — Compute", placeHolder: "Prices are Modal list prices per hour", ignoreFocusOut: true }
  );
  if (!compute) { cancelled(); }

  const localDir = workspaceDirFor();
  const reqPath = localDir ? path.join(localDir, "requirements.txt") : undefined;
  const hasRequirements = Boolean(reqPath && fs.existsSync(reqPath));
  const stacks = await vscode.window.showQuickPick(
    [
      ...(hasRequirements ? [{ label: "requirements.txt", description: "From your workspace", picked: true, pkgs: [] as string[] }] : []),
      { label: "Data science", description: "numpy, pandas, matplotlib, scikit-learn", picked: !hasRequirements, pkgs: ["numpy", "pandas", "matplotlib", "scikit-learn"] },
      { label: "PyTorch", description: "torch, torchvision", picked: false, pkgs: ["torch", "torchvision"] },
      { label: "Hugging Face", description: "transformers, accelerate, datasets", picked: false, pkgs: ["transformers", "accelerate", "datasets"] },
    ],
    { title: "GPU notebook — Packages (ipykernel is always included)", canPickMany: true, ignoreFocusOut: true }
  );
  if (!stacks) { cancelled(); }
  const extra = await vscode.window.showInputBox({
    title: "GPU notebook — Extra pip packages (optional)",
    prompt: "Space or comma separated, e.g. vllm einops==0.8.1",
    ignoreFocusOut: true,
    validateInput: (v) => v.split(/[\s,]+/).filter(Boolean).every((p) => PIP_SPEC.test(p)) ? undefined : "Use plain pip specs like torch or einops==0.8.1",
  });
  if (extra === undefined) { cancelled(); }

  const idle = await vscode.window.showQuickPick(
    [
      { label: "15 minutes", seconds: 15 * 60 },
      { label: "30 minutes", description: "recommended", seconds: 30 * 60 },
      { label: "1 hour", seconds: 60 * 60 },
      { label: "2 hours", seconds: 2 * 60 * 60 },
      { label: `Never`, description: `runs until you stop it (max ${MAX_HOURS} h)`, seconds: 0 },
    ],
    { title: "GPU notebook — Shut down when kernels are idle for", ignoreFocusOut: true }
  );
  if (!idle) { cancelled(); }

  return {
    profile,
    compute: compute.value,
    requirements: stacks.some((s) => s.label === "requirements.txt") ? reqPath!.replace(/\\/g, "/") : undefined,
    packages: [...new Set([...stacks.flatMap((s) => s.pkgs), ...extra.split(/[\s,]+/).filter(Boolean)])],
    idleSeconds: idle.seconds,
    localDir,
  };
}

// ─── Provider ──────────────────────────────────────────────────

class ModalNotebookServers implements JupyterServerProvider, JupyterServerCommandProvider {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeServers = this.changed.event;

  constructor(private readonly context: vscode.ExtensionContext) {
    // A server stopped from Active Sessions (or that shut itself down)
    // disappears from the kernel picker.
    context.subscriptions.push(sessionStore.onChange(() => {
      const ended = this.servers().filter((s) => {
        const status = sessionStore.get(s.sessionId)?.status;
        return status === undefined || status === "stopped" || status === "failed";
      });
      if (ended.length) { void this.forget(ended.map((s) => s.id)); }
    }));
  }

  private servers(): NotebookServer[] {
    return this.context.globalState.get<NotebookServer[]>(STATE_KEY, []);
  }

  private async forget(ids: string[]): Promise<void> {
    await this.context.globalState.update(STATE_KEY, this.servers().filter((s) => !ids.includes(s.id)));
    await Promise.all(ids.map((id) => this.context.secrets.delete(SECRET_PREFIX + id)));
    this.changed.fire();
  }

  private toJupyterServer(s: NotebookServer, token?: string): JupyterServer {
    return {
      id: s.id,
      label: s.label,
      connectionInformation: token ? { baseUrl: vscode.Uri.parse(s.baseUrl), token } : undefined,
    };
  }

  async provideJupyterServers(): Promise<JupyterServer[]> {
    const checks = await Promise.all(this.servers().map(async (s) => {
      const token = await this.context.secrets.get(SECRET_PREFIX + s.id);
      return { s, alive: Boolean(token) && await isServerAlive(s.baseUrl, token!) };
    }));
    const dead = checks.filter((c) => !c.alive).map((c) => c.s.id);
    if (dead.length) { void this.forget(dead); }
    return checks.filter((c) => c.alive).map((c) => this.toJupyterServer(c.s));
  }

  async resolveJupyterServer(server: JupyterServer): Promise<JupyterServer> {
    const stored = this.servers().find((s) => s.id === server.id);
    const token = await this.context.secrets.get(SECRET_PREFIX + server.id);
    if (!stored || !token) { throw new Error("This M-GPUX notebook server is no longer running."); }
    return this.toJupyterServer(stored, token);
  }

  provideCommands(): JupyterServerCommand[] {
    return [{ label: "$(add) New Modal GPU server…", description: "Starts Jupyter on a Modal GPU", canBeAutoSelected: true }];
  }

  async handleCommand(_command: JupyterServerCommand, token: vscode.CancellationToken): Promise<JupyterServer> {
    const opts = await askLaunchOptions();
    if (token.isCancellationRequested) { cancelled(); }
    const server = await this.launch(opts);
    return this.toJupyterServer(server, await this.context.secrets.get(SECRET_PREFIX + server.id));
  }

  private launch(opts: LaunchOptions): Promise<NotebookServer> {
    return Promise.resolve(vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `M-GPUX: starting a notebook server on ${opts.compute.label}`, cancellable: true },
      (progress, cancel) => this.start(opts, progress, cancel)
    ));
  }

  private async start(
    opts: LaunchOptions,
    progress: vscode.Progress<{ message?: string }>,
    cancel: vscode.CancellationToken
  ): Promise<NotebookServer> {
    const id = crypto.randomUUID();
    const jupyterToken = crypto.randomBytes(32).toString("hex");
    const sessionId = newSessionId();
    const dir = path.join(this.context.globalStorageUri.fsPath, "notebook");
    fs.mkdirSync(dir, { recursive: true });
    const scriptPath = path.join(dir, `m-gpux-notebook-${id.slice(0, 8)}.py`);
    fs.writeFileSync(scriptPath, serverScript(opts), "utf-8");

    const output = vscode.window.createOutputChannel(`M-GPUX: Notebook ${opts.compute.label}`, "log");
    const logPath = sessionLogPath(sessionId);
    sessionStore.add({
      id: sessionId,
      kind: "jupyter",
      gpu: `${opts.compute.label} · notebook`,
      profile: opts.profile,
      status: "starting",
      startedAt: Date.now(),
      output,
      cwd: opts.localDir ?? dir,
      detached: true,
      logPath,
      workspaceVolume: opts.localDir ? workspaceVolumeName(opts.localDir) : undefined,
    });
    const log = (text: string) => {
      output.append(text);
      const s = sessionStore.get(sessionId);
      if (s) { appendSessionLog(s, text); }
    };
    log(`▸ Notebook server on ${opts.compute.label} (profile ${opts.profile})\n`);
    log(`  Packages: ${[opts.requirements ? "requirements.txt" : "", ...opts.packages].filter(Boolean).join(", ") || "ipykernel only"}\n`);
    log(`  Idle shutdown: ${opts.idleSeconds ? `${opts.idleSeconds / 60} min` : "off"}\n\n`);

    progress.report({ message: "building the image and starting the container…" });
    const modal = await modalCommand(["run", "--detach", scriptPath]);
    const proc = spawn(modal.cmd, modal.args, {
      cwd: opts.localDir ?? dir,
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        MODAL_PROFILE: opts.profile,
        MGPUX_JUPYTER_TOKEN: jupyterToken,
        MGPUX_IDLE_SECONDS: String(opts.idleSeconds),
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
    });
    sessionStore.update(sessionId, { proc });

    let baseUrl: string | undefined;
    let exitCode: number | null | undefined;
    let buffer = "";
    const onData = (chunk: Buffer) => {
      const text = chunk.toString();
      // Never echo the marker line verbatim — keep the log readable.
      log(text.split(URL_MARKER).join("Jupyter server URL: "));
      buffer = (buffer + text).slice(-16000);
      const app = buffer.match(/https?:\/\/modal\.com\/apps\/[^\s"']*\/(ap-[A-Za-z0-9]+)/);
      if (app && !sessionStore.get(sessionId)?.appId) {
        sessionStore.update(sessionId, { appId: app[1], dashboardUrl: app[0] });
      }
      const url = buffer.match(new RegExp(`${URL_MARKER}(https?://\\S+)`));
      if (url && !baseUrl) { baseUrl = url[1]; }
    };
    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", (err: Error) => { log(`\n✗ Could not start modal: ${err.message}\n`); exitCode = -1; });
    proc.on("close", (code: number | null) => {
      exitCode = code;
      try { fs.unlinkSync(scriptPath); } catch { /* already gone */ }
      const s = sessionStore.get(sessionId);
      if (!s || s.status === "stopped") { return; }
      log(code === 0 ? "\n• Notebook server shut down.\n" : `\n✗ modal exited with code ${code}.\n`);
      sessionStore.update(sessionId, { status: code === 0 || s.status === "stopping" ? "stopped" : "failed", proc: undefined });
    });

    const fail = async (message: string): Promise<never> => {
      try { proc.kill(); } catch { /* already exited */ }
      const appId = sessionStore.get(sessionId)?.appId;
      if (appId) {
        const stop = await modalCommand(["app", "stop", "--yes", appId]);
        spawn(stop.cmd, stop.args, { shell: false, windowsHide: true, stdio: "ignore", env: { ...process.env, MODAL_PROFILE: opts.profile } });
      }
      sessionStore.update(sessionId, { status: message === "cancelled" ? "stopped" : "failed", proc: undefined });
      if (message === "cancelled") { cancelled(); }
      output.show(true);
      throw new Error(`M-GPUX: ${message} See the "M-GPUX: Notebook ${opts.compute.label}" output for details.`);
    };

    const deadline = Date.now() + STARTUP_TIMEOUT_MS;
    let urlAnnounced = false;
    while (true) {
      if (cancel.isCancellationRequested) { return fail("cancelled"); }
      if (exitCode !== undefined) {
        return fail(/Image build for \S+ failed/.test(buffer)
          ? "a package failed to install while building the image. Fix it in requirements.txt (or leave requirements.txt unticked) and start again."
          : "the notebook server exited before it was ready.");
      }
      if (Date.now() > deadline) { return fail("the notebook server did not become ready in time."); }
      if (baseUrl) {
        if (!urlAnnounced) { progress.report({ message: "waiting for Jupyter to answer…" }); urlAnnounced = true; }
        if (await isServerAlive(baseUrl, jupyterToken)) { break; }
      }
      await sleep(1500);
    }

    const server: NotebookServer = {
      id,
      label: `${opts.compute.label} · ${opts.profile}`,
      baseUrl: baseUrl!,
      sessionId,
      profile: opts.profile,
      compute: opts.compute.label,
      startedAt: Date.now(),
    };
    await this.context.secrets.store(SECRET_PREFIX + id, jupyterToken);
    await this.context.globalState.update(STATE_KEY, [...this.servers(), server]);
    sessionStore.update(sessionId, { status: "ready" });
    log(`\n✓ Ready. Cells now run on ${opts.compute.label}. Stop it from Active Sessions when you are done.\n`);
    this.changed.fire();
    return server;
  }
}

// ─── Registration ──────────────────────────────────────────────

let collection: JupyterServerCollection | undefined;

async function ensureCollection(context: vscode.ExtensionContext, interactive: boolean): Promise<boolean> {
  if (collection) { return true; }
  const ext = vscode.extensions.getExtension<Jupyter>(JUPYTER_EXTENSION_ID);
  if (!ext) {
    if (interactive) {
      const choice = await vscode.window.showWarningMessage(
        "GPU notebooks need Microsoft's Jupyter extension.", "Install Jupyter"
      );
      if (choice === "Install Jupyter") {
        await vscode.commands.executeCommand("workbench.extensions.installExtension", JUPYTER_EXTENSION_ID);
      }
    }
    return false;
  }
  const api = ext.isActive ? ext.exports : await ext.activate();
  if (typeof api?.createJupyterServerCollection !== "function") {
    if (interactive) { vscode.window.showErrorMessage("M-GPUX: please update the Jupyter extension to use GPU notebooks."); }
    return false;
  }
  const provider = new ModalNotebookServers(context);
  collection = api.createJupyterServerCollection(COLLECTION_ID, "M-GPUX — Modal GPU", provider);
  collection.commandProvider = provider;
  collection.documentation = vscode.Uri.parse("https://puxhocdl.github.io/m-gpux/");
  context.subscriptions.push({ dispose: () => { collection?.dispose(); collection = undefined; } });
  return true;
}

/** Register the kernel source once a notebook is open (avoids activating Jupyter early). */
export function registerNotebookKernels(context: vscode.ExtensionContext): void {
  const isJupyter = (doc: vscode.NotebookDocument) => doc.notebookType === "jupyter-notebook" || doc.notebookType === "interactive";
  if (vscode.workspace.notebookDocuments.some(isJupyter)) {
    void ensureCollection(context, false);
  }
  context.subscriptions.push(vscode.workspace.onDidOpenNotebookDocument((doc) => {
    if (isJupyter(doc)) { void ensureCollection(context, false); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand("mgpux.notebookKernel", async () => {
    if (!(await ensureCollection(context, true))) { return; }
    if (!vscode.window.activeNotebookEditor) {
      const choice = await vscode.window.showInformationMessage(
        "Open a notebook, then Select Kernel → M-GPUX — Modal GPU → New Modal GPU server.",
        "New Notebook"
      );
      if (choice !== "New Notebook") { return; }
      await vscode.commands.executeCommand("ipynb.newUntitledIpynb");
    }
    await vscode.commands.executeCommand("notebook.selectKernel");
  }));
}
