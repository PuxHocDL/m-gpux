// Bidirectional file sync between the local workspace and a session's
// Modal Volume. Strategy:
//
//   - Watch the workspace with a VS Code file watcher. When a file
//     changes (save/create/delete), queue it; every 5 seconds flush the
//     queue with `modal volume put` (or `modal volume rm` for deletes).
//   - In parallel, every 5 seconds run a `modal volume get` for an
//     output-folder allowlist (configurable; default `outputs/` and
//     `runs/`) so artifacts the remote produces show up locally.
//   - The remote container script (hubWizard / presetWizard) calls
//     `volume.commit()` + `volume.reload()` every 5 seconds so its view
//     of `/workspace` stays in sync with what we put.
//
// We invoke `modal volume put/get` as one-shot CLI commands rather than
// trying to keep an in-process Python SDK alive — that keeps the
// extension TS-only and avoids a hot connection.
import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as crypto from "crypto";
import { runCommand } from "./modalCli";

const FLUSH_INTERVAL_MS = 5_000;

const DEFAULT_EXCLUDES = [
  ".git",
  ".venv",
  "venv",
  "env",
  "__pycache__",
  "node_modules",
  ".mypy_cache",
  ".pytest_cache",
  ".tox",
  "*.egg-info",
  "dist",
  "build",
  ".idea",
  ".vscode",
  ".DS_Store",
  // Files written by the extension itself
  "modal_runner.py",
  ".mgpux-probe.py",
];

const DEFAULT_OUTPUT_DIRS = ["outputs", "runs", "checkpoints", "logs"];

const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB — skip anything bigger to keep pushes fast

export interface LiveSyncOptions {
  volumeName: string;
  workspaceDir: string;     // absolute path to local workspace
  profile: string;          // Modal profile name (selects credentials)
  output: vscode.OutputChannel; // shared session output for diagnostics
  outputDirs?: string[];    // remote dirs to pull back (defaults to DEFAULT_OUTPUT_DIRS)
}

export class LiveSyncDriver implements vscode.Disposable {
  private watcher?: vscode.FileSystemWatcher;
  private flushTimer?: NodeJS.Timeout;
  private pullTimer?: NodeJS.Timeout;
  private pendingPuts = new Map<string, "put" | "delete">(); // relative path → action
  private flushing = false;
  private pulling = false;
  private status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
  private disposed = false;

  constructor(private readonly opts: LiveSyncOptions) {
    this.status.text = "$(sync~spin) m-gpux sync";
    this.status.tooltip = `Live syncing workspace → ${opts.volumeName}`;
    this.status.show();
  }

  start(): void {
    if (this.disposed) { return; }
    const pattern = new vscode.RelativePattern(this.opts.workspaceDir, "**/*");
    this.watcher = vscode.workspace.createFileSystemWatcher(pattern);
    this.watcher.onDidChange((uri) => this.queue(uri.fsPath, "put"));
    this.watcher.onDidCreate((uri) => this.queue(uri.fsPath, "put"));
    this.watcher.onDidDelete((uri) => this.queue(uri.fsPath, "delete"));

    this.flushTimer = setInterval(() => { this.flush().catch(() => { /* logged inside */ }); }, FLUSH_INTERVAL_MS);
    this.pullTimer  = setInterval(() => { this.pull().catch(() => { /* logged inside */ }); }, FLUSH_INTERVAL_MS);

    this.opts.output.appendLine(`[sync] started → volume ${this.opts.volumeName} (interval ${FLUSH_INTERVAL_MS / 1000}s)`);

    // Initial push of the whole workspace so the volume matches local state
    // before the user starts editing.
    this.flushFull().catch((err) => {
      this.opts.output.appendLine(`[sync] initial push failed: ${err?.message ?? err}`);
    });
  }

  private queue(absPath: string, action: "put" | "delete"): void {
    const rel = this.relPath(absPath);
    if (!rel) { return; }
    if (this.isExcluded(rel)) { return; }
    this.pendingPuts.set(rel, action);
  }

  private relPath(absPath: string): string | undefined {
    const root = path.resolve(this.opts.workspaceDir);
    const abs = path.resolve(absPath);
    if (!abs.startsWith(root + path.sep) && abs !== root) { return undefined; }
    return abs.slice(root.length + 1).replace(/\\/g, "/");
  }

  private isExcluded(rel: string): boolean {
    if (!rel) { return true; }
    for (const pat of DEFAULT_EXCLUDES) {
      if (rel === pat || rel.startsWith(pat + "/")) { return true; }
      if (pat.startsWith("*.") && rel.endsWith(pat.slice(1))) { return true; }
      // Match the pattern anywhere in the path (e.g. "foo/__pycache__/bar.pyc")
      if (rel.includes("/" + pat + "/") || rel.includes("/" + pat)) { return true; }
    }
    return false;
  }

  /** One-shot full push, used on start. Walks the workspace and queues
   *  every non-excluded file. The flush loop then batches them. */
  private async flushFull(): Promise<void> {
    const seedRoot = path.resolve(this.opts.workspaceDir);
    const walk = (dir: string) => {
      let entries: fs.Dirent[];
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        const full = path.join(dir, e.name);
        const rel = this.relPath(full);
        if (!rel || this.isExcluded(rel)) { continue; }
        if (e.isDirectory()) {
          walk(full);
        } else if (e.isFile()) {
          this.pendingPuts.set(rel, "put");
        }
      }
    };
    walk(seedRoot);
    await this.flush();
  }

  private async flush(): Promise<void> {
    if (this.disposed || this.flushing || this.pendingPuts.size === 0) { return; }
    this.flushing = true;
    const batch = Array.from(this.pendingPuts.entries());
    this.pendingPuts.clear();
    this.status.text = `$(sync~spin) m-gpux sync (${batch.length})`;

    let ok = 0;
    let failed = 0;
    for (const [rel, action] of batch) {
      const remoteSlash = "/" + rel;
      if (action === "delete") {
        const res = await runCommand(
          "modal",
          ["volume", "rm", "--recursive", this.opts.volumeName, remoteSlash],
          { env: { MODAL_PROFILE: this.opts.profile }, timeoutMs: 30_000 }
        );
        if (res.exitCode === 0) { ok++; } else { failed++; }
      } else {
        const localAbs = path.join(this.opts.workspaceDir, rel);
        try {
          const stat = fs.statSync(localAbs);
          if (!stat.isFile()) { continue; }
          if (stat.size > MAX_FILE_SIZE_BYTES) {
            this.opts.output.appendLine(`[sync] skipping ${rel} (${(stat.size / 1048576).toFixed(1)} MB > 100 MB cap)`);
            continue;
          }
        } catch { continue; }
        const res = await runCommand(
          "modal",
          ["volume", "put", "--force", this.opts.volumeName, localAbs, remoteSlash],
          { env: { MODAL_PROFILE: this.opts.profile }, timeoutMs: 60_000 }
        );
        if (res.exitCode === 0) { ok++; } else {
          failed++;
          this.opts.output.appendLine(`[sync] put ${rel} failed: ${res.stderr.trim().split("\n").pop()}`);
        }
      }
    }

    this.opts.output.appendLine(`[sync] ▲ pushed ${ok}/${batch.length} file(s)${failed ? `, ${failed} failed` : ""}`);
    this.status.text = "$(sync) m-gpux sync";
    this.flushing = false;
  }

  private async pull(): Promise<void> {
    if (this.disposed || this.pulling) { return; }
    this.pulling = true;
    const dirs = this.opts.outputDirs ?? DEFAULT_OUTPUT_DIRS;
    let pulled = 0;
    for (const dir of dirs) {
      const localTarget = path.join(this.opts.workspaceDir, dir);
      const tmpDir = path.join(os.tmpdir(), `mgpux-pull-${crypto.randomBytes(6).toString("hex")}`);
      const res = await runCommand(
        "modal",
        ["volume", "get", "--force", this.opts.volumeName, "/" + dir, tmpDir],
        { env: { MODAL_PROFILE: this.opts.profile }, timeoutMs: 60_000 }
      );
      if (res.exitCode !== 0) {
        // Most likely the dir doesn't exist on the remote yet — that's fine.
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
        continue;
      }
      // Merge tmpDir → localTarget (overwrite). We don't delete files that
      // the remote removed; the user can clean up manually if needed —
      // safer than wiping local results on a transient remote rename.
      try {
        const tmpInner = path.join(tmpDir, dir);
        const src = fs.existsSync(tmpInner) ? tmpInner : tmpDir;
        copyTree(src, localTarget);
        pulled++;
      } catch (err: any) {
        this.opts.output.appendLine(`[sync] pull ${dir} merge failed: ${err?.message ?? err}`);
      } finally {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
      }
    }
    if (pulled > 0) {
      this.opts.output.appendLine(`[sync] ▼ pulled ${pulled} output dir(s) from volume`);
    }
    this.pulling = false;
  }

  dispose(): void {
    if (this.disposed) { return; }
    this.disposed = true;
    if (this.flushTimer) { clearInterval(this.flushTimer); }
    if (this.pullTimer)  { clearInterval(this.pullTimer); }
    this.watcher?.dispose();
    this.status.dispose();
    this.opts.output.appendLine(`[sync] stopped`);
  }
}

function copyTree(src: string, dst: string): void {
  if (!fs.existsSync(src)) { return; }
  const stat = fs.statSync(src);
  if (stat.isFile()) {
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    return;
  }
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const a = path.join(src, entry.name);
    const b = path.join(dst, entry.name);
    if (entry.isDirectory()) { copyTree(a, b); }
    else if (entry.isFile()) { fs.copyFileSync(a, b); }
  }
}

export function deriveWorkspaceVolumeName(localDir: string): string {
  // Must match hubWizard.workspaceVolumeName so the volume the script
  // mounts is the same one we're pushing to.
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
