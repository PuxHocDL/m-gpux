import * as vscode from "vscode";
import { execFile } from "child_process";
import * as os from "os";

const TEST_CANDIDATES_WIN: { cmd: string; args: string[] }[] = [
  // Windows py launcher with explicit versions, newest-stable first
  { cmd: "py", args: ["-3.13"] },
  { cmd: "py", args: ["-3.12"] },
  { cmd: "py", args: ["-3.11"] },
  { cmd: "py", args: ["-3.10"] },
  { cmd: "py", args: [] },
  { cmd: "python3.13", args: [] },
  { cmd: "python3.12", args: [] },
  { cmd: "python3.11", args: [] },
  { cmd: "python3.10", args: [] },
  { cmd: "python3", args: [] },
  { cmd: "python", args: [] },
];

const TEST_CANDIDATES_UNIX: { cmd: string; args: string[] }[] = [
  { cmd: "python3.13", args: [] },
  { cmd: "python3.12", args: [] },
  { cmd: "python3.11", args: [] },
  { cmd: "python3.10", args: [] },
  { cmd: "python3", args: [] },
  { cmd: "python", args: [] },
];

export interface PythonInterpreter {
  cmd: string;
  args: string[];
  version: string;
  hasModal: boolean;
}

let cachedInterpreter: PythonInterpreter | undefined;
let cachePromise: Promise<PythonInterpreter | undefined> | undefined;

function probeInterpreter(cmd: string, args: string[]): Promise<PythonInterpreter | undefined> {
  return new Promise((resolve) => {
    const probe = "import sys,json\ntry:\n import modal\n m=getattr(modal,'__version__','?')\nexcept Exception:\n m=None\nprint(json.dumps({'v':'%d.%d.%d'%sys.version_info[:3],'modal':m}))";
    execFile(cmd, [...args, "-c", probe], { timeout: 5000, shell: false } as any, (err: any, stdout: string) => {
      if (err) { resolve(undefined); return; }
      try {
        const data = JSON.parse(stdout.trim());
        resolve({
          cmd,
          args,
          version: data.v,
          hasModal: Boolean(data.modal),
        });
      } catch {
        resolve(undefined);
      }
    });
  });
}

/**
 * Resolve a Python interpreter that can `import modal`. Prefers user setting,
 * then falls back through known candidates. Returns the first interpreter with
 * modal installed. If none have modal, returns the first usable Python (so the
 * caller can surface a meaningful error).
 */
export async function resolvePython(forceRefresh = false): Promise<PythonInterpreter | undefined> {
  if (!forceRefresh && cachedInterpreter) { return cachedInterpreter; }
  if (!forceRefresh && cachePromise) { return cachePromise; }

  cachePromise = (async () => {
    // 1. Honour user setting first
    const cfg = vscode.workspace.getConfiguration("mgpux");
    const userPath = (cfg.get<string>("pythonPath") ?? "").trim();
    if (userPath) {
      const probed = await probeInterpreter(userPath, []);
      if (probed) {
        cachedInterpreter = probed;
        return probed;
      }
    }

    // 2. Walk candidates
    const candidates = os.platform() === "win32" ? TEST_CANDIDATES_WIN : TEST_CANDIDATES_UNIX;
    let firstUsable: PythonInterpreter | undefined;
    for (const c of candidates) {
      const probed = await probeInterpreter(c.cmd, c.args);
      if (!probed) { continue; }
      if (probed.hasModal) {
        cachedInterpreter = probed;
        return probed;
      }
      if (!firstUsable) { firstUsable = probed; }
    }
    cachedInterpreter = firstUsable;
    return firstUsable;
  })();

  try {
    return await cachePromise;
  } finally {
    cachePromise = undefined;
  }
}

export function clearPythonCache(): void {
  cachedInterpreter = undefined;
  cachePromise = undefined;
}
