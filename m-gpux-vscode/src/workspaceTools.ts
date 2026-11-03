// Editor surfaces for the workspace-level CLI features: mgpux.toml projects
// (up / sweep / run anywhere / runs), Secrets & image sync across accounts,
// notifications, and a Volume browser. Interactive flows (hidden prompts,
// live logs) run in a terminal exactly like the CLI; the Volume browser talks
// to the modal CLI directly so it works without m-gpux installed.
import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { parse } from "smol-toml";
import { runCliInTerminal } from "./cliActions";
import { loadProfiles } from "./config";
import { runModal } from "./modalCli";

const STATE_DIR = path.join(os.homedir(), ".m-gpux");
const RUNS_DIR = path.join(STATE_DIR, "runs");
const SAFE_WORD = /^[A-Za-z0-9_.:/=,@+-]+$/;
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ENV_KEY = /^[A-Za-z_][A-Za-z0-9_]*$/;

interface Choice extends vscode.QuickPickItem { value: string }

async function pick(title: string, items: Choice[], placeHolder?: string): Promise<string | undefined> {
  return (await vscode.window.showQuickPick(items, { title, placeHolder }))?.value;
}

/** Quote one argument for the integrated terminal (bash, zsh, PowerShell and cmd alike). */
export function shellArg(value: string): string {
  if (SAFE_WORD.test(value)) { return value; }
  if (/["`$%!\r\n]/.test(value)) { throw new Error(`Unsupported characters in ${JSON.stringify(value)}`); }
  return `"${value}"`;
}

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

// ─── Projects: mgpux.toml ───────────────────────────────────────

interface ProjectTask { name: string; command: string; gpu: string }

export function readProjectTasks(root: string): { tasks: ProjectTask[]; sweeps: string[] } | undefined {
  const file = path.join(root, "mgpux.toml");
  if (!fs.existsSync(file)) { return undefined; }
  try {
    const doc = parse(fs.readFileSync(file, "utf-8")) as Record<string, any>;
    const defaults = doc.defaults ?? {};
    const tasks = Object.entries<any>(doc.tasks ?? {}).map(([name, t]) => {
      const gpu = t.gpu ?? defaults.gpu ?? "none";
      return { name, command: String(t.command ?? ""), gpu: Array.isArray(gpu) ? gpu.join(" → ") : String(gpu) };
    });
    return { tasks, sweeps: Object.keys(doc.sweeps ?? {}) };
  } catch {
    return { tasks: [], sweeps: [] };
  }
}

async function pickTask(root: string, title: string): Promise<string | undefined> {
  const project = readProjectTasks(root);
  if (!project?.tasks.length) {
    vscode.window.showWarningMessage("mgpux.toml has no [tasks.*] yet.");
    return undefined;
  }
  if (project.tasks.length === 1) { return project.tasks[0].name; }
  return pick(title, project.tasks.map((t) => ({ label: t.name, description: t.gpu, detail: t.command, value: t.name })));
}

export async function manageProject(): Promise<void> {
  const root = workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("Open a folder first: mgpux.toml lives at the root of a project.");
    return;
  }
  const project = readProjectTasks(root);
  const items: Choice[] = project
    ? [
      { label: "$(play) Run a task", description: "m-gpux up — on Modal, results recorded", value: "up" },
      { label: "$(beaker) Sweep a task", description: "Run it over a parameter grid in parallel", value: "sweep" },
      { label: "$(globe) Run a script anywhere", description: "Free Kaggle quota → Colab → Modal credit", value: "run" },
      { label: "$(history) Run history", description: "Exit codes, metrics and cost of past runs", value: "runs" },
      { label: "$(edit) Open mgpux.toml", value: "open" },
    ]
    : [
      { label: "$(new-file) Create mgpux.toml", description: "Declare tasks for this folder", value: "init" },
      { label: "$(new-file) Create mgpux.toml + GitHub Action", description: "Also run tasks from CI", value: "init-ci" },
      { label: "$(globe) Run a script anywhere", description: "Free Kaggle quota → Colab → Modal credit", value: "run" },
      { label: "$(history) Run history", value: "runs" },
    ];
  const action = await pick("M-GPUX Projects", items, project ? `${project.tasks.length} task(s) in mgpux.toml` : "No mgpux.toml in this folder");
  if (!action) { return; }

  if (action === "init" || action === "init-ci") {
    await runCliInTerminal("Init project", action === "init-ci" ? "init --github-action" : "init");
    const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(root, "mgpux.toml"));
    const opened = watcher.onDidCreate(async (uri) => {
      opened.dispose();
      watcher.dispose();
      await vscode.window.showTextDocument(uri);
    });
    setTimeout(() => { opened.dispose(); watcher.dispose(); }, 60_000);
  } else if (action === "open") {
    await vscode.window.showTextDocument(vscode.Uri.file(path.join(root, "mgpux.toml")));
  } else if (action === "up") {
    const task = await pickTask(root, "Run which task?");
    if (!task) { return; }
    const extra = await vscode.window.showInputBox({
      title: `m-gpux up ${task}`,
      prompt: "Extra arguments appended to the task's command (optional)",
      placeHolder: "--epochs 5",
    });
    if (extra === undefined) { return; }
    await runCliInTerminal(`up ${task}`, `up ${shellArg(task)}${extra.trim() ? ` -- ${extra.trim()}` : ""}`);
  } else if (action === "sweep") {
    const names = [...(project?.sweeps ?? []).map((s) => ({ label: `$(beaker) ${s}`, description: "[sweeps] preset", value: s })),
      ...(project?.tasks ?? []).map((t) => ({ label: t.name, description: t.gpu, detail: t.command, value: t.name }))];
    const target = await pick("Sweep which task?", names);
    if (!target) { return; }
    const isPreset = project?.sweeps.includes(target);
    const grid = await vscode.window.showInputBox({
      title: `m-gpux sweep ${target}`,
      prompt: isPreset ? "Extra grid (optional), e.g. seed=1,2,3" : "Grid: name=v1,v2 separated by spaces",
      placeHolder: "lr=1e-4,3e-4 batch=16,32",
      validateInput: (v) => (!isPreset && !v.trim() ? "Give at least one name=v1,v2"
        : v.trim().split(/\s+/).filter(Boolean).every((g) => /^[A-Za-z_]\w*=[^\s"'`$]+$/.test(g)) || !v.trim() ? undefined
          : "Use name=v1,v2 (no quotes or spaces in values)"),
    });
    if (grid === undefined) { return; }
    const flags = grid.trim().split(/\s+/).filter(Boolean).map((g) => `--grid ${g}`).join(" ");
    await runCliInTerminal(`sweep ${target}`, `sweep ${shellArg(target)} ${flags}`.trim());
  } else if (action === "run") {
    await runAnywhere();
  } else {
    await runCliInTerminal("Runs", "runs list");
  }
}

export async function runAnywhere(uri?: vscode.Uri): Promise<void> {
  let script = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
  if (!script || !script.endsWith(".py")) {
    const files = await vscode.workspace.findFiles("**/*.py", "**/{.venv,venv,node_modules,.git}/**", 200);
    const chosen = await vscode.window.showQuickPick(
      files.map((f) => ({ label: vscode.workspace.asRelativePath(f), uri: f })),
      { title: "Run which script anywhere?" }
    );
    if (!chosen) { return; }
    script = chosen.uri.fsPath;
  }
  const gpu = await pick("GPU", [
    { label: "Any / cheapest fit", description: "T4 on Kaggle/Colab, T4 on Modal", value: "" },
    ...["T4", "P100", "L4", "A10", "A100", "A100-80GB", "H100"].map((g) => ({ label: g, value: g })),
  ]);
  if (gpu === undefined) { return; }
  const where = await pick("Where", [
    { label: "$(sparkle) Auto", description: "Free Kaggle quota, then Colab, then Modal credit", value: "auto" },
    { label: "Modal", value: "modal" }, { label: "Kaggle", value: "kaggle" }, { label: "Colab", value: "colab" },
  ]);
  if (!where) { return; }
  const rel = path.relative(workspaceRoot() ?? path.dirname(script), script) || path.basename(script);
  await runCliInTerminal("Run anywhere", `run ${shellArg(rel.split(path.sep).join("/"))}${gpu ? ` --gpu ${gpu}` : ""} --where ${where}`);
}

export interface RunSummary {
  id: string;
  kind: string;
  project: string;
  task: string;
  status: string;
  jobs: number;
  ok: number;
  gpu: string;
  startedAt: string;
  best?: string;
  cost?: number;
}

/** The newest runs recorded by `m-gpux up / sweep / run` (local files only). */
export function recentRuns(limit = 5): RunSummary[] {
  try {
    const files = fs.readdirSync(RUNS_DIR).filter((f) => f.endsWith(".json")).sort().reverse().slice(0, limit);
    return files.flatMap((file) => {
      try {
        const r = JSON.parse(fs.readFileSync(path.join(RUNS_DIR, file), "utf-8"));
        const results: any[] = Array.isArray(r.results) ? r.results : [];
        const best = r.best?.result && typeof r.best.result === "object"
          ? Object.entries(r.best.result).slice(0, 2).map(([k, v]) => `${k}=${typeof v === "number" ? +v.toPrecision(4) : v}`).join(", ")
          : undefined;
        return [{
          id: String(r.id), kind: String(r.kind ?? "up"), project: String(r.project ?? ""), task: String(r.task ?? ""),
          status: String(r.status ?? "?"), jobs: Number(r.jobs ?? results.length), ok: results.filter((x) => x.exit_code === 0).length,
          gpu: String(r.gpu ?? ""), startedAt: String(r.started_at ?? ""), best,
          cost: typeof r.cost_estimate === "number" ? r.cost_estimate : undefined,
        }];
      } catch { return []; }
    });
  } catch {
    return [];
  }
}

// ─── Secrets & images across workspaces ─────────────────────────

function knownImages(): string[] {
  try {
    return Object.keys(JSON.parse(fs.readFileSync(path.join(STATE_DIR, "images.json"), "utf-8"))).sort();
  } catch { return []; }
}

async function pickTargets(title: string): Promise<string | undefined> {
  return pick(title, [
    { label: "$(globe) Every workspace", value: "all" },
    ...loadProfiles().map((p) => ({ label: `$(account) ${p.name}`, description: p.active ? "active" : undefined, value: p.name })),
  ]);
}

export async function manageSync(): Promise<void> {
  const action = await pick("M-GPUX · Secrets & images on every workspace", [
    { label: "$(table) Secret status", description: "Which workspace has which Secret", value: "secrets-status" },
    { label: "$(key) Sync a Secret", description: "Same keys on every workspace (values from env / .env / hidden prompt)", value: "secrets-sync" },
    { label: "$(file) Sync a Secret from a .env file", value: "secrets-dotenv" },
    { label: "$(trash) Delete a Secret", value: "secrets-delete" },
    { label: "$(table) Image status", description: "Which workspace has which published image", value: "image-status" },
    { label: "$(package) Sync an image", description: "Build it where it is missing", value: "image-sync" },
  ]);
  if (!action) { return; }
  if (action === "secrets-status") { return runCliInTerminal("Secrets", "secrets status"); }
  if (action === "image-status") { return runCliInTerminal("Images", "image status"); }
  if (action === "image-sync") {
    const images = knownImages();
    if (!images.length) {
      vscode.window.showInformationMessage("No images built with m-gpux yet. Build one from Quick Actions → Images.");
      return;
    }
    const image = await pick("Sync which image?", images.map((i) => ({ label: i, value: i })));
    if (image) { await runCliInTerminal(`Sync ${image}`, `image sync ${shellArg(image)} --to all`); }
    return;
  }
  const name = await vscode.window.showInputBox({
    title: "Secret name on Modal", placeHolder: "hf", value: action === "secrets-delete" ? "" : "hf",
    validateInput: (v) => (NAME.test(v.trim()) ? undefined : "Letters, digits, '.', '_' or '-'"),
  });
  if (!name) { return; }
  const targets = await pickTargets(action === "secrets-delete" ? `Delete '${name}' from…` : `Write '${name}' to…`);
  if (!targets) { return; }
  const to = `--to ${shellArg(targets)}`;
  if (action === "secrets-delete") {
    await runCliInTerminal(`Delete ${name}`, `secrets delete ${shellArg(name.trim())} ${to}`);
  } else if (action === "secrets-dotenv") {
    const file = await vscode.window.showOpenDialog({ title: "The .env file to read", canSelectMany: false, defaultUri: vscode.Uri.file(workspaceRoot() ?? os.homedir()) });
    if (!file?.[0]) { return; }
    await runCliInTerminal(`Sync ${name}`, `secrets sync ${shellArg(name.trim())} --from-dotenv ${shellArg(file[0].fsPath)} ${to}`);
  } else {
    const keys = await vscode.window.showInputBox({
      title: `Keys for '${name}'`,
      prompt: "Variable NAMES only, space separated. Values come from your environment or a hidden prompt in the terminal.",
      placeHolder: "HF_TOKEN",
      validateInput: (v) => (v.trim() && v.trim().split(/\s+/).every((k) => ENV_KEY.test(k)) ? undefined : "e.g. HF_TOKEN WANDB_API_KEY (no values)"),
    });
    if (!keys) { return; }
    await runCliInTerminal(`Sync ${name}`, `secrets sync ${shellArg(name.trim())} ${keys.trim().split(/\s+/).join(" ")} ${to}`);
  }
}

// ─── Notifications ─────────────────────────────────────────────

function notifyChannels(): string[] {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(STATE_DIR, "notify.json"), "utf-8"));
    return (data.channels ?? []).map((c: any) => String(c.name)).filter(Boolean);
  } catch { return []; }
}

export async function manageNotifications(): Promise<void> {
  const channels = notifyChannels();
  const action = await pick("M-GPUX Notifications", [
    { label: "$(add) Add a channel", description: "Discord, Slack, Telegram, ntfy or webhook", value: "add" },
    ...(channels.length ? [
      { label: "$(bell) Send a test", description: channels.join(", "), value: "test" },
      { label: "$(eye) Watch apps, credit and jobs", description: "Notify until you close the terminal", value: "watch" },
      { label: "$(list-unordered) Channels", value: "list" },
      { label: "$(trash) Remove a channel", value: "remove" },
    ] : []),
    { label: "$(info) Events", description: "What a channel can subscribe to", value: "events" },
  ], channels.length ? `${channels.length} channel(s)` : "No channels yet");
  if (!action) { return; }
  if (action === "add") {
    const kind = await pick("Channel type", [
      { label: "Discord", description: "Channel → Integrations → Webhooks", value: "discord" },
      { label: "Slack", description: "Incoming webhook", value: "slack" },
      { label: "Telegram", description: "Bot token from @BotFather + chat id", value: "telegram" },
      { label: "ntfy", description: "Phone push via ntfy.sh topic", value: "ntfy" },
      { label: "Webhook", description: "Any HTTPS endpoint (JSON body)", value: "webhook" },
    ]);
    // The URL / token is a credential: the CLI asks for it with a hidden prompt.
    if (kind) { await runCliInTerminal("Notifications", `notify add ${kind}`); }
  } else if (action === "remove") {
    const name = await pick("Remove which channel?", channels.map((c) => ({ label: c, value: c })));
    if (name) { await runCliInTerminal("Notifications", `notify remove ${shellArg(name)}`); }
  } else if (action === "watch") {
    await runCliInTerminal("Notify watch", "notify watch");
  } else {
    await runCliInTerminal("Notifications", `notify ${action}`);
  }
}

// ─── Volume browser ─────────────────────────────────────────────

interface VolumeEntry { name: string; dir: boolean; size: string; modified: string }

async function modalJson(profile: string, args: string[]): Promise<any[]> {
  const res = await runModal([...args, "--json"], { env: { MODAL_PROFILE: profile }, timeoutMs: 60_000 });
  if (res.exitCode !== 0) { throw new Error((res.stderr || res.stdout || "modal failed").trim().split(/\r?\n/).pop()); }
  return JSON.parse(res.stdout || "[]");
}

async function listVolumes(profile: string): Promise<string[]> {
  const rows = await modalJson(profile, ["volume", "list"]);
  return rows.map((r) => String(r.Name ?? r.name ?? r.Label ?? "")).filter(Boolean).sort();
}

async function listDir(profile: string, volume: string, dir: string): Promise<VolumeEntry[]> {
  const rows = await modalJson(profile, ["volume", "ls", volume, dir]);
  return rows.map((r) => ({
    name: String(r.filename ?? r.Filename ?? "").replace(/\/$/, ""),
    dir: String(r.type ?? r.Type ?? "").toLowerCase().startsWith("dir"),
    size: String(r.size ?? r.Size ?? ""),
    modified: String(r.created_modified ?? r["Created/Modified"] ?? ""),
  })).sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name));
}

async function download(profile: string, volume: string, remote: string): Promise<void> {
  const root = workspaceRoot() ?? os.homedir();
  const dest = await vscode.window.showOpenDialog({
    title: `Download ${volume}:${remote} into…`, canSelectFiles: false, canSelectFolders: true,
    defaultUri: vscode.Uri.file(root), openLabel: "Download here",
  });
  if (!dest?.[0]) { return; }
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `M-GPUX: downloading ${volume}:${remote}…` },
    async () => {
      const res = await runModal(["volume", "get", volume, remote, dest[0].fsPath], { env: { MODAL_PROFILE: profile }, timeoutMs: 60 * 60_000 });
      if (res.exitCode !== 0) {
        vscode.window.showErrorMessage(`Download failed: ${(res.stderr || res.stdout).trim().split(/\r?\n/).pop()}`);
      } else {
        vscode.window.showInformationMessage(`Downloaded ${remote} to ${dest[0].fsPath}`, "Reveal")
          .then((c) => { if (c) { vscode.commands.executeCommand("revealFileInOS", dest[0]); } });
      }
    }
  );
}

export async function browseVolumes(): Promise<void> {
  const profiles = loadProfiles();
  if (!profiles.length) {
    vscode.window.showWarningMessage("No Modal accounts configured.");
    return;
  }
  const profile = profiles.length === 1 ? profiles[0].name : await pick("Volumes on which account?",
    profiles.map((p) => ({ label: `$(account) ${p.name}`, description: p.active ? "active" : undefined, value: p.name })));
  if (!profile) { return; }

  let volumes: string[];
  try {
    volumes = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `M-GPUX: listing volumes on ${profile}…` },
      () => listVolumes(profile)
    );
  } catch (err: any) {
    vscode.window.showErrorMessage(`M-GPUX: ${err?.message ?? err}`);
    return;
  }
  const volume = await pick(`Volumes · ${profile}`, volumes.map((v) => ({
    label: `$(database) ${v}`,
    description: v === "m-gpux-hf-cache" ? "shared Hugging Face cache" : v.endsWith("-outputs") ? "run outputs" : undefined,
    value: v,
  })), volumes.length ? undefined : "No volumes on this account");
  if (!volume) { return; }

  let dir = "/";
  for (;;) {
    const qp = vscode.window.createQuickPick<Choice>();
    qp.title = `${volume}:${dir}  ·  ${profile}`;
    qp.busy = true;
    qp.placeholder = "Loading…";
    qp.show();
    let entries: VolumeEntry[] = [];
    try {
      entries = await listDir(profile, volume, dir);
    } catch (err: any) {
      qp.hide();
      vscode.window.showErrorMessage(`M-GPUX: ${err?.message ?? err}`);
      return;
    }
    qp.busy = false;
    qp.placeholder = "Open a folder, or pick a file to download";
    qp.items = [
      ...(dir !== "/" ? [{ label: "$(arrow-up) ..", value: ".." }] : []),
      { label: "$(cloud-download) Download this folder", value: ":download" },
      { label: "$(copy) Copy the CLI command", value: ":copy" },
      ...entries.map((e) => ({
        label: `${e.dir ? "$(folder)" : "$(file)"} ${e.name.split("/").pop()}`,
        description: e.dir ? "" : e.size,
        detail: e.modified || undefined,
        value: (e.dir ? "d:" : "f:") + e.name,
      })),
    ];
    const chosen = await new Promise<string | undefined>((resolve) => {
      qp.onDidAccept(() => { resolve(qp.selectedItems[0]?.value); qp.hide(); });
      qp.onDidHide(() => resolve(undefined));
    });
    qp.dispose();
    if (!chosen) { return; }
    if (chosen === "..") {
      dir = "/" + dir.split("/").filter(Boolean).slice(0, -1).join("/");
    } else if (chosen === ":download") {
      return download(profile, volume, dir);
    } else if (chosen === ":copy") {
      const account = /\s/.test(profile) ? `"${profile}"` : profile;
      await vscode.env.clipboard.writeText(`m-gpux volume get ${volume} ${dir} ./${volume} --account ${account}`);
      vscode.window.showInformationMessage("Command copied.");
      return;
    } else if (chosen.startsWith("d:")) {
      const name = chosen.slice(2);
      dir = name.startsWith("/") ? name : `/${name}`;
    } else {
      const name = chosen.slice(2);
      return download(profile, volume, name.startsWith("/") ? name : `/${name}`);
    }
  }
}
