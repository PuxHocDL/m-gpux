// Thin shell-outs to the `m-gpux compose` CLI. Re-implementing the
// docker-compose analyzer + sandbox driver in TypeScript would mean
// duplicating ~1k lines of plugin code, so we run the Python CLI in a
// VS Code terminal where the user can read live output (and answer any
// interactive prompts compose may emit). The extension also surfaces the
// detected compose file so the user knows which workspace is being acted on.
import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { ensureMgpuxCli } from "./modalCli";

const COMPOSE_FILENAMES = ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"];

function findComposeFile(): { dir: string; file: string } | undefined {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) { return undefined; }
  for (const name of COMPOSE_FILENAMES) {
    const candidate = path.join(root, name);
    if (fs.existsSync(candidate)) {
      return { dir: root, file: candidate };
    }
  }
  return undefined;
}

async function runInTerminal(label: string, cmd: string, cwd: string): Promise<void> {
  const term = vscode.window.createTerminal({ name: `M-GPUX: ${label}`, cwd });
  term.show(true);
  term.sendText(cmd, true);
}

export async function composeCheck(): Promise<void> {
  if (!(await ensureMgpuxCli("Compose check"))) { return; }
  const found = findComposeFile();
  if (!found) {
    vscode.window.showWarningMessage(
      "No docker-compose.yml in the workspace root."
    );
    return;
  }
  await runInTerminal("compose check", "m-gpux compose check", found.dir);
}

export async function composeUp(): Promise<void> {
  if (!(await ensureMgpuxCli("Compose up"))) { return; }
  const found = findComposeFile();
  if (!found) {
    vscode.window.showWarningMessage("No docker-compose.yml in the workspace root.");
    return;
  }
  const mode = await vscode.window.showQuickPick(
    [
      { label: "$(rocket) Subprocess",  description: "Default — services run in one Modal app via subprocess", value: "up" },
      { label: "$(server) VM mode",     description: "Provision a Modal GPU container (Triton-style)",         value: "vm up" },
      { label: "$(layers) Sandbox mode", description: "Isolated Modal Sandboxes per service",                  value: "sandbox up" },
    ],
    { title: "M-GPUX Compose — Deployment mode" }
  );
  if (!mode) { return; }
  await runInTerminal(`compose ${(mode as any).value}`, `m-gpux compose ${(mode as any).value}`, found.dir);
}

export async function composeSandbox(): Promise<void> {
  if (!(await ensureMgpuxCli("Compose sandbox"))) { return; }
  const found = findComposeFile();
  if (!found) {
    vscode.window.showWarningMessage("No docker-compose.yml in the workspace root.");
    return;
  }
  const sub = await vscode.window.showQuickPick(
    [
      { label: "check", description: "Validate compose for sandbox mode" },
      { label: "up",    description: "Start sandboxes for all services" },
      { label: "ps",    description: "List sandbox status" },
      { label: "logs",  description: "Stream logs from a sandbox" },
      { label: "exec",  description: "Run a one-off command in a sandbox" },
      { label: "down",  description: "Stop all sandboxes" },
    ],
    { title: "M-GPUX Compose Sandbox" }
  );
  if (!sub) { return; }
  let cmd = `m-gpux compose sandbox ${sub.label}`;
  if (sub.label === "exec") {
    const svc = await vscode.window.showInputBox({ title: "Service name", placeHolder: "web" });
    if (!svc) { return; }
    cmd += ` ${svc}`;
  }
  await runInTerminal(`compose sandbox ${sub.label}`, cmd, found.dir);
}
