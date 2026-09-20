// Thin wrappers around the `modal` and `m-gpux` CLIs. The extension
// shells out for ground-truth state (app list, profile activate) and to
// reuse CLI features that would be costly to re-implement in TypeScript
// (compose, preset).
export { hasMgpuxCli, ensureMgpuxCli } from "./cliBootstrap";

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
      shell: false,
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
  const result = await runCommand("modal", ["profile", "activate", profile], { cwd });
  if (result.exitCode !== 0) {
    const detail = (result.stderr || result.stdout || "unknown error").trim();
    throw new Error(`Could not activate Modal profile '${profile}': ${detail}`);
  }
}

export interface ModalAppEntry {
  appId: string;
  name: string;
  state: string;
  /** Running container count. A "deployed" app persists in Modal forever, so
   *  state alone says nothing about whether anything is actually running —
   *  a Jupyter that scaled to zero is still "deployed" with tasks=0. */
  tasks: number;
}

/** States `modal app list --json` can report (see `APP_STATE_TO_MESSAGE` in the
 *  modal client's `cli/app.py`). Notably there is no "running" state — apps
 *  launched via `modal run` show up as "ephemeral" (foreground) or
 *  "ephemeral (detached)" (backgrounded with `--detach`), and `modal deploy`
 *  apps show up as "deployed". Code that used to match only "running" /
 *  "deployed" silently treated every ephemeral/detached/initializing app as
 *  dead, which is why sessions that were still alive on Modal showed up as
 *  "stopped" in the sidebar. */
const ALIVE_APP_STATES = new Set([
  "deployed",
  "ephemeral",
  "ephemeral (detached)",
  "initializing...",
]);

export function isAliveAppState(state: string): boolean {
  return ALIVE_APP_STATES.has(state.trim().toLowerCase());
}

/** Pull the App name and the web-endpoint function name out of a generated
 *  `modal_runner.py` (all m-gpux templates follow `modal.App("name")` plus a
 *  `@modal.web_server` / `@modal.asgi_app` / `@modal.wsgi_app` decorated
 *  `def fn():`). Used to look up the deployed URL via the SDK when the
 *  `modal deploy` CLI output doesn't contain it (see fetchFunctionWebUrl). */
export function extractWebEndpoint(scriptContent: string): { appName: string; functionName: string } | undefined {
  const appMatch = scriptContent.match(/modal\.App\(\s*"([^"]+)"/);
  if (!appMatch) { return undefined; }
  const fnMatch = scriptContent.match(/@modal\.(?:web_server|asgi_app|wsgi_app)\([^)]*\)\s*\r?\n(?:@[^\r\n]+\r?\n)*def\s+(\w+)\s*\(/);
  if (!fnMatch) { return undefined; }
  return { appName: appMatch[1], functionName: fnMatch[1] };
}

/** List Modal apps for a profile. Query/JSON failures throw by default so a
 *  transient outage cannot be mistaken for an empty account. Pass
 *  `strict=false` only for explicitly best-effort callers. */
export async function listApps(profile: string, env = "main", strict = true): Promise<ModalAppEntry[]> {
  const res = await runCommand(
    "modal",
    ["app", "list", "--env", env, "--json"],
    { env: { MODAL_PROFILE: profile } }
  );
  if (res.exitCode !== 0) {
    if (strict) {
      throw new Error((res.stderr || res.stdout || `Could not list apps for '${profile}'`).trim());
    }
    return [];
  }
  try {
    const apps = JSON.parse(res.stdout || "[]");
    return apps.map((a: any) => ({
      appId: a["App ID"] ?? a.app_id ?? a.id ?? "",
      // `modal app list --json` labels this column "Description" (capital D) —
      // there is NO "Name" field. Reading only a["Name"]/a.name/a.description
      // yielded "" for every app, so isMgpuxApp("") was always false and
      // discovery found zero apps → live sessions all got marked "stopped".
      name: a["Name"] ?? a.name ?? a["Description"] ?? a.description ?? "",
      state: (a["State"] ?? a.state ?? "").toString().toLowerCase(),
      tasks: Number(a["Tasks"] ?? a.tasks ?? a.n_running_tasks ?? 0) || 0,
    })).filter((a: ModalAppEntry) => a.appId);
  } catch (err) {
    if (strict) {
      throw new Error(`Invalid response from modal app list for '${profile}': ${String(err)}`);
    }
    return [];
  }
}
