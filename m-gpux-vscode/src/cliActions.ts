// UI for the CLI workflows that had no extension surface: budgets, billing
// reports, images, LLM endpoint operations, and the interactive CLI menu.
// Long-running or table-heavy commands run in an integrated terminal (same as
// devActions / composeActions); quick state changes run captured so the
// sidebar can refresh and the user gets a notification.
import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import {
  ensureMgpuxCli,
  getCliTerminalEnvironment,
  getMgpuxTerminalCommand,
  resolveMgpuxCli,
} from "./cliBootstrap";
import { loadProfiles } from "./config";
import { runCommand } from "./modalCli";

const IMAGES_PATH = path.join(os.homedir(), ".m-gpux", "images.json");
const IMAGE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*(:[A-Za-z0-9._-]+)?$/;
// Plain package specs only, so the value is safe inside double quotes in
// bash, zsh, PowerShell and cmd alike.
const PIP_SPECS = /^[A-Za-z0-9_.,=~!\[\]-]+$/;

/** Run `m-gpux <args>` in a new integrated terminal (interactive prompts work). */
export async function runCliInTerminal(label: string, args: string): Promise<void> {
  if (!(await ensureMgpuxCli(label))) { return; }
  const terminal = vscode.window.createTerminal({
    name: `M-GPUX: ${label}`,
    cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
    env: getCliTerminalEnvironment(),
  });
  terminal.show(true);
  terminal.sendText(`${getMgpuxTerminalCommand()} ${args}`, true);
}

/** Run `m-gpux <args>` without a terminal; returns true on success. */
async function runCliCaptured(label: string, args: string[]): Promise<boolean> {
  if (!(await ensureMgpuxCli(label))) { return false; }
  const cli = await resolveMgpuxCli();
  if (!cli) { return false; }
  const result = await runCommand(cli, args, { timeoutMs: 60_000, env: { MGPUX_NO_ANIMATION: "1", NO_COLOR: "1" } });
  if (result.exitCode !== 0) {
    const detail = (result.stderr || result.stdout || "unknown error").trim().split(/\r?\n/).pop();
    vscode.window.showErrorMessage(`M-GPUX: ${label} failed — ${detail}`);
    return false;
  }
  return true;
}

interface Choice extends vscode.QuickPickItem { value: string }

async function pick(title: string, items: Choice[], placeHolder?: string): Promise<string | undefined> {
  return (await vscode.window.showQuickPick(items, { title, placeHolder }))?.value;
}

/** "--account <name>" for one profile, "" for all accounts, undefined if cancelled. */
async function pickAccountScope(title: string, allLabel: string): Promise<string | undefined> {
  const items: Choice[] = [
    { label: `$(globe) ${allLabel}`, value: "" },
    ...loadProfiles().map((p) => ({
      label: `$(account) ${p.name}`,
      description: p.active ? "active" : undefined,
      value: p.name,
    })),
  ];
  return pick(title, items);
}

// ─── Interactive CLI menu ──────────────────────────────────────

export async function openCliMenu(): Promise<void> {
  await runCliInTerminal("menu", "menu");
}

// ─── Budgets ───────────────────────────────────────────────────

export async function manageBudgets(onChanged: () => void): Promise<void> {
  const action = await pick("M-GPUX Budgets", [
    { label: "$(graph) Show budgets", description: "Spend vs. budget for every account this month", value: "show" },
    { label: "$(edit) Set budget…", description: "Monthly limit for one account or all of them", value: "set" },
    { label: "$(pass) Check budgets", description: "Report accounts that are over budget", value: "check" },
    { label: "$(debug-stop) Check & stop over-budget apps", description: "Stops apps on accounts that went over", value: "check --stop" },
    { label: "$(eye) Watch budgets", description: "Keep enforcing until you close the terminal", value: "watch" },
    { label: "$(trash) Clear budget…", description: "Remove a limit", value: "clear" },
  ]);
  if (!action) { return; }

  if (action === "set") {
    const amount = await vscode.window.showInputBox({
      title: "Monthly limit (USD)",
      prompt: "Applies to the current calendar month; AUTO account selection respects it.",
      value: "30",
      validateInput: (v) => (/^\d+(\.\d+)?$/.test(v.trim()) ? undefined : "Enter a number, e.g. 20 or 12.5"),
    });
    if (amount === undefined) { return; }
    const account = await pickAccountScope("Apply the limit to…", "All accounts (default)");
    if (account === undefined) { return; }
    const args = ["budget", "set", amount.trim(), ...(account ? ["--account", account] : [])];
    if (await runCliCaptured("Set budget", args)) {
      vscode.window.showInformationMessage(
        `M-GPUX: budget $${amount.trim()}/month set for ${account ? `'${account}'` : "every account"}.`
      );
      onChanged();
    }
    return;
  }

  if (action === "clear") {
    const account = await pickAccountScope("Remove which budget?", "The all-accounts default");
    if (account === undefined) { return; }
    if (await runCliCaptured("Clear budget", ["budget", "clear", ...(account ? ["--account", account] : [])])) {
      vscode.window.showInformationMessage("M-GPUX: budget removed.");
      onChanged();
    }
    return;
  }

  await runCliInTerminal(`budget ${action}`, `budget ${action}`);
}

// ─── Billing reports ───────────────────────────────────────────

export async function billingReports(): Promise<void> {
  const action = await pick("M-GPUX Billing", [
    { label: "$(table) Usage — all accounts", description: "Cost per account for the last 30 days", value: "usage --all" },
    { label: "$(checklist) Summary", description: "Metered vs. billed for this cycle, per account", value: "summary --all" },
    { label: "$(tag) GPU & CPU rates", description: "Current price per GPU, CPU core and GiB", value: "rates" },
    { label: "$(link-external) Open Modal usage page", description: "In your browser", value: "open" },
  ]);
  if (!action) { return; }
  if (action === "open") {
    await vscode.commands.executeCommand("mgpux.openBillingDashboard");
    return;
  }
  await runCliInTerminal(`billing ${action}`, `billing ${action}`);
}

// ─── Images ────────────────────────────────────────────────────

function publishedImages(): Record<string, { profiles?: string[]; python?: string; updated_at?: string }> {
  try {
    const data = JSON.parse(fs.readFileSync(IMAGES_PATH, "utf-8"));
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

export async function manageImages(): Promise<void> {
  const images = publishedImages();
  const names = Object.keys(images).sort();
  const action = await pick("M-GPUX Images", [
    { label: "$(package) Build & publish…", description: "Bake dependencies once for near-instant starts", value: "build" },
    ...names.map((name) => ({
      label: `$(file-binary) ${name}`,
      description: (images[name].profiles ?? []).join(", "),
      detail: images[name].updated_at ? `Updated ${new Date(images[name].updated_at!).toLocaleString()}` : undefined,
      value: `image:${name}`,
    })),
    { label: "$(list-unordered) List in terminal", value: "list" },
  ], names.length ? "Build a new image, or pick one to manage" : "No images yet — build your first one");
  if (!action) { return; }

  if (action === "list") {
    await runCliInTerminal("image list", "image list");
    return;
  }

  if (action.startsWith("image:")) {
    const name = action.slice("image:".length);
    const confirm = await vscode.window.showWarningMessage(
      `Forget '${name}'? It is removed from m-gpux's list; the published image stays on Modal.`,
      { modal: true },
      "Forget"
    );
    if (confirm === "Forget" && await runCliCaptured("Forget image", ["image", "forget", name])) {
      vscode.window.showInformationMessage(`M-GPUX: forgot image '${name}'.`);
    }
    return;
  }

  const name = await vscode.window.showInputBox({
    title: "Image name",
    prompt: "Optionally with a tag, e.g. torch or torch:2.8",
    placeHolder: "torch",
    validateInput: (v) => (IMAGE_NAME.test(v.trim()) ? undefined : "Use letters, digits, '.', '_' or '-' (optionally ':tag')."),
  });
  if (!name) { return; }
  const python = await pick("Python version", ["3.13", "3.12", "3.11", "3.10"].map((v) => ({
    label: v, description: v === "3.12" ? "default" : undefined, value: v,
  })));
  if (!python) { return; }
  const pip = await vscode.window.showInputBox({
    title: "Extra pip packages (optional)",
    prompt: "Comma-separated package specs.",
    placeHolder: "torch,transformers==4.57.0",
    validateInput: (v) => (!v.trim() || PIP_SPECS.test(v.trim()) ? undefined : "Use plain package specs separated by commas."),
  });
  if (pip === undefined) { return; }
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  let requirements = false;
  if (root && fs.existsSync(path.join(root, "requirements.txt"))) {
    const use = await pick("Bake in requirements.txt?", [
      { label: "$(check) Yes", description: "Install the workspace's requirements.txt into the image", value: "yes" },
      { label: "$(close) No", value: "no" },
    ]);
    if (!use) { return; }
    requirements = use === "yes";
  }
  const account = await pickAccountScope("Publish to…", "Every configured account");
  if (account === undefined) { return; }

  let args = `image build ${name.trim()} --python ${python}`;
  if (pip.trim()) { args += ` --pip "${pip.trim()}"`; }
  if (requirements) { args += " --requirements requirements.txt"; }
  args += account ? ` --account ${account}` : " --all";
  await runCliInTerminal(`image build ${name.trim()}`, args);
}

// ─── LLM endpoint operations ──────────────────────────────────

export async function manageServeEndpoint(): Promise<void> {
  const action = await pick("M-GPUX LLM Endpoint", [
    { label: "$(flame) Warm up", description: "Trigger the cold start so the first request is fast", value: "warmup" },
    { label: "$(dashboard) Live dashboard", description: "Metrics, latency and traffic in a terminal", value: "dashboard" },
    { label: "$(output) Logs", description: "Stream the server's logs", value: "logs" },
    { label: "$(debug-restart) Restart", description: "Fresh containers, same code", value: "restart" },
    { label: "$(debug-stop) Stop", description: "Stop the API server and release its GPU", value: "stop" },
    { label: "$(key) API keys…", description: "Copy, revoke or delete keys", value: "keys" },
  ]);
  if (!action) { return; }
  if (action === "keys") {
    await vscode.commands.executeCommand("mgpux.serveKeysList");
    return;
  }
  if (action === "stop") {
    const confirm = await vscode.window.showWarningMessage(
      "Stop the deployed LLM API server?", { modal: true }, "Stop"
    );
    if (confirm !== "Stop") { return; }
  }
  await runCliInTerminal(`serve ${action}`, `serve ${action}`);
}

// ─── Compute Gateway ──────────────────────────────────────────

const GATEWAY_PATH = path.join(os.homedir(), ".m-gpux", "gateway.json");
const GATEWAY_TASK = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
const GATEWAY_JOB = /^fc-[A-Za-z0-9]{1,64}$/;

interface GatewayJob { id: string; task?: string; status?: string; submitted_at?: string }
interface GatewayState { url: string; api_key: string; tasks?: string[]; jobs?: GatewayJob[] }

function loadGateway(): GatewayState | undefined {
  try {
    const data = JSON.parse(fs.readFileSync(GATEWAY_PATH, "utf-8"));
    return data && typeof data.url === "string" && typeof data.api_key === "string" ? data : undefined;
  } catch {
    return undefined;
  }
}

async function pickGatewayJob(state: GatewayState): Promise<string | undefined> {
  const jobs = (state.jobs ?? []).filter((j) => typeof j.id === "string" && GATEWAY_JOB.test(j.id));
  if (!jobs.length) {
    vscode.window.showInformationMessage("M-GPUX: no gateway jobs submitted from this machine yet.");
    return undefined;
  }
  return pick("Gateway job", jobs.map((j) => ({
    label: j.id,
    description: [j.task, j.status].filter(Boolean).join(" · "),
    detail: j.submitted_at,
    value: j.id,
  })));
}

export async function manageGateway(): Promise<void> {
  const state = loadGateway();
  const deployedOnly = state ? [
    { label: "$(play) Submit job…", description: "Run a declared task with a JSON input", value: "submit" },
    { label: "$(list-unordered) Jobs", description: "Jobs submitted from this machine, refreshed", value: "jobs" },
    { label: "$(output) Job result…", description: "Status, or the result once finished", value: "result" },
    { label: "$(note) Job logs…", description: "Recent stdout, stderr and system logs", value: "logs" },
    { label: "$(debug-stop) Cancel job…", description: "Stop a running job", value: "cancel" },
    { label: "$(checklist) Tasks", description: "Tasks the deployed gateway exposes", value: "tasks" },
    { label: "$(info) Show endpoint", description: state.url, value: "show" },
    { label: "$(key) Copy API key", description: "To the clipboard", value: "copy-key" },
    { label: "$(link-external) Open API docs", description: "Interactive OpenAPI page", value: "open" },
  ] : [];
  const action = await pick("M-GPUX Compute Gateway", [
    ...deployedOnly,
    { label: "$(new-file) Init", description: "Starter mgpux.gateway.toml and worker in this workspace", value: "init" },
    { label: "$(pass) Validate", description: "Check mgpux.gateway.toml without contacting Modal", value: "validate" },
    { label: "$(rocket) Deploy", description: "Deploy the gateway and save its URL and key", value: "deploy" },
  ]);
  if (!action) { return; }

  if (state && action === "copy-key") {
    await vscode.env.clipboard.writeText(state.api_key);
    vscode.window.showInformationMessage("M-GPUX: gateway API key copied to the clipboard.");
    return;
  }
  if (state && action === "open") {
    await vscode.env.openExternal(vscode.Uri.parse(`${state.url.replace(/\/+$/, "")}/docs`));
    return;
  }
  if (state && action === "submit") {
    const tasks = (state.tasks ?? []).filter((t) => GATEWAY_TASK.test(t));
    const task = await pick("Task", tasks.map((t) => ({ label: t, value: t })));
    if (!task) { return; }
    const input = await vscode.window.showInputBox({
      title: `Input for '${task}'`,
      prompt: "A JSON object, passed to the task on stdin",
      value: "{}",
      validateInput: (v) => {
        try {
          const parsed = JSON.parse(v);
          return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? undefined : "Must be a JSON object";
        } catch {
          return "Not valid JSON";
        }
      },
    });
    if (input === undefined) { return; }
    // A file avoids quoting JSON for bash, zsh, PowerShell and cmd.
    const inputFile = path.join(os.tmpdir(), `mgpux-gateway-input-${Date.now()}.json`);
    fs.writeFileSync(inputFile, input, "utf-8");
    await runCliInTerminal(`gateway submit ${task}`, `gateway submit ${task} --input-file "${inputFile}" --wait`);
    return;
  }
  if (state && (action === "result" || action === "logs" || action === "cancel")) {
    const jobId = await pickGatewayJob(state);
    if (!jobId) { return; }
    if (action === "cancel") {
      const confirm = await vscode.window.showWarningMessage(`Cancel gateway job ${jobId}?`, { modal: true }, "Cancel job");
      if (confirm !== "Cancel job") { return; }
    }
    await runCliInTerminal(`gateway ${action}`, `gateway ${action} ${jobId}`);
    return;
  }
  await runCliInTerminal(`gateway ${action}`, action === "jobs" ? "gateway jobs --refresh" : `gateway ${action}`);
}

// ─── Presets ──────────────────────────────────────────────────

/** Show a preset's settings in a read-only JSON editor. */
export async function showPreset(name: string, preset: unknown): Promise<void> {
  const doc = await vscode.workspace.openTextDocument({
    language: "json",
    content: JSON.stringify({ name, ...(preset as object) }, null, 2) + "\n",
  });
  await vscode.window.showTextDocument(doc, { preview: true });
}
