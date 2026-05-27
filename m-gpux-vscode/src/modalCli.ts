// Thin wrappers around the `modal` and `m-gpux` CLIs. The extension
// shells out for ground-truth state (app list, profile activate) and to
// reuse CLI features that would be costly to re-implement in TypeScript
// (compose, preset).
import * as vscode from "vscode";

const { spawn } = require("child_process");

export interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export function runCommand(
  cmd: string,
  args: string[],
  opts: { cwd?: string; env?: Record<string, string>; timeoutMs?: number } = {}
): Promise<SpawnResult> {
  return new Promise((resolve) => {
    const proc = spawn(cmd, args, {
      cwd: opts.cwd,
      shell: true,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", ...(opts.env ?? {}) },
    });
    let stdout = "";
    let stderr = "";
    const timer = opts.timeoutMs
      ? setTimeout(() => { try { proc.kill(); } catch { /* ignore */ } }, opts.timeoutMs)
      : null;
    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    proc.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    proc.on("close", (code: number | null) => {
      if (timer) { clearTimeout(timer); }
      resolve({ stdout, stderr, exitCode: code ?? 1 });
    });
    proc.on("error", (err: Error) => {
      if (timer) { clearTimeout(timer); }
      resolve({ stdout, stderr: err.message, exitCode: 1 });
    });
  });
}

export async function activateProfile(profile: string, cwd?: string): Promise<void> {
  await runCommand("modal", ["profile", "activate", profile], { cwd });
}

export interface ModalAppEntry {
  appId: string;
  name: string;
  state: string;
}

/** List Modal apps for a profile. Returns empty array if `modal` is not installed
 *  or the command fails. */
export async function listApps(profile: string, env = "main"): Promise<ModalAppEntry[]> {
  const res = await runCommand(
    "modal",
    ["app", "list", "--env", env, "--json"],
    { env: { MODAL_PROFILE: profile } }
  );
  if (res.exitCode !== 0) { return []; }
  try {
    const apps = JSON.parse(res.stdout || "[]");
    return apps.map((a: any) => ({
      appId: a["App ID"] ?? a.app_id ?? a.id ?? "",
      name: a["Name"] ?? a.name ?? a.description ?? "",
      state: (a["State"] ?? a.state ?? "").toString().toLowerCase(),
    })).filter((a: ModalAppEntry) => a.appId);
  } catch {
    return [];
  }
}

/** Whether the `m-gpux` Python CLI is reachable on PATH. */
export async function hasMgpuxCli(): Promise<boolean> {
  const res = await runCommand("m-gpux", ["--version"], { timeoutMs: 4000 });
  return res.exitCode === 0;
}

/** Show a guided modal asking the user to install m-gpux if it's missing. */
export async function ensureMgpuxCli(featureName: string): Promise<boolean> {
  if (await hasMgpuxCli()) { return true; }
  const choice = await vscode.window.showWarningMessage(
    `'${featureName}' requires the m-gpux Python CLI. Install with: pip install m-gpux`,
    "Copy install command",
    "Open docs"
  );
  if (choice === "Copy install command") {
    await vscode.env.clipboard.writeText("pip install m-gpux");
    vscode.window.showInformationMessage("Copied: pip install m-gpux");
  } else if (choice === "Open docs") {
    vscode.env.openExternal(vscode.Uri.parse("https://puxhocdl.github.io/m-gpux/"));
  }
  return false;
}
