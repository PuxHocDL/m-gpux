// Bidirectional file sync between the local workspace and a session's
// Modal Volume.
//
//   - Watch the workspace with a VS Code file watcher. When files change
//     (save/create/delete), queue them; every 5 seconds flush the queue as a
//     single batched upload.
//   - Every 30 seconds pull remote changes back so artifacts the container
//     produced (training outputs, new notebooks) show up locally.
//   - The remote container script (hubWizard / presetWizard) calls
//     volume.commit() + volume.reload() every 5 seconds so its view of
//     /workspace stays in sync with what we push.
//
// All transfers go through volumeSync.ts, which drives the Modal Python SDK in
// a single process. The previous implementation shelled out to `modal volume
// put/get` once per file; that spawned hundreds of processes (slow) and broke
// outright on any workspace path containing a space, because Node's
// `spawn(..., {shell:true})` does not quote arguments.
import * as vscode from "vscode";
import * as path from "path";
import * as crypto from "crypto";
import { ModalProfile } from "./config";
import { runVolumeSync, SYNC_EXCLUDES, formatBytes } from "./volumeSync";

const FLUSH_INTERVAL_MS = 5_000;
const PULL_INTERVAL_MS = 30_000;

export interface LiveSyncOptions {
  volumeName: string;
  workspaceDir: string;         // absolute path to local workspace
  profile: ModalProfile;        // Modal profile (supplies SDK credentials)
  output: vscode.OutputChannel; // shared session output for diagnostics
}

export class LiveSyncDriver implements vscode.Disposable {
  private watcher?: vscode.FileSystemWatcher;
  private flushTimer?: NodeJS.Timeout;
  private pullTimer?: NodeJS.Timeout;
  private pending = new Map<string, "put" | "delete">(); // relative path → action
  private busy = false;
  private status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
  private disposed = false;

  constructor(private readonly opts: LiveSyncOptions) {
    this.status.text = "$(sync~spin) m-gpux sync";
    this.status.tooltip = `Live syncing workspace ↔ ${opts.volumeName}`;
    this.status.show();
  }

  start(): void {
    if (this.disposed) { return; }
    const pattern = new vscode.RelativePattern(this.opts.workspaceDir, "**/*");
    this.watcher = vscode.workspace.createFileSystemWatcher(pattern);
    this.watcher.onDidChange((uri) => this.queue(uri.fsPath, "put"));
    this.watcher.onDidCreate((uri) => this.queue(uri.fsPath, "put"));
    this.watcher.onDidDelete((uri) => this.queue(uri.fsPath, "delete"));

    this.flushTimer = setInterval(() => { void this.flush(); }, FLUSH_INTERVAL_MS);
    this.pullTimer = setInterval(() => { void this.pull(); }, PULL_INTERVAL_MS);

    this.opts.output.appendLine(`[sync] started → volume ${this.opts.volumeName}`);

    // Seed the volume with the current workspace so the container sees the
    // user's latest code. This is a diffing push: files already present on the
    // volume at the same size are not re-uploaded.
    void this.pushAll();
  }

  private queue(absPath: string, action: "put" | "delete"): void {
    const rel = this.relPath(absPath);
    if (!rel || isExcluded(rel)) { return; }
    this.pending.set(rel, action);
  }

  private relPath(absPath: string): string | undefined {
    const root = path.resolve(this.opts.workspaceDir);
    const abs = path.resolve(absPath);
    if (!abs.startsWith(root + path.sep)) { return undefined; }
    return abs.slice(root.length + 1).replace(/\\/g, "/");
  }

  /** Full workspace → volume push (diffed against what the volume already has). */
  private async pushAll(): Promise<void> {
    if (this.disposed || this.busy) { return; }
    this.busy = true;
    this.status.text = "$(sync~spin) m-gpux sync";
    try {
      await runVolumeSync({
        mode: "push",
        volumeName: this.opts.volumeName,
        localDir: this.opts.workspaceDir,
        tokenId: this.opts.profile.token_id,
        tokenSecret: this.opts.profile.token_secret,
        output: this.opts.output,
      });
    } catch (err: any) {
      this.opts.output.appendLine(`[sync] initial push failed: ${err?.message ?? err}`);
    } finally {
      this.status.text = "$(sync) m-gpux sync";
      this.busy = false;
    }
  }

  /** Push whatever the watcher queued since the last flush. */
  private async flush(): Promise<void> {
    if (this.disposed || this.busy || this.pending.size === 0) { return; }
    this.busy = true;
    const batch = Array.from(this.pending.entries());
    this.pending.clear();
    const paths = batch.filter(([, a]) => a === "put").map(([p]) => p);
    const deletes = batch.filter(([, a]) => a === "delete").map(([p]) => p);
    this.status.text = `$(sync~spin) m-gpux sync (${batch.length})`;
    try {
      await runVolumeSync({
        mode: "push",
        volumeName: this.opts.volumeName,
        localDir: this.opts.workspaceDir,
        tokenId: this.opts.profile.token_id,
        tokenSecret: this.opts.profile.token_secret,
        output: this.opts.output,
        paths,
        deletes,
      });
    } catch (err: any) {
      this.opts.output.appendLine(`[sync] push failed: ${err?.message ?? err}`);
    } finally {
      this.status.text = "$(sync) m-gpux sync";
      this.busy = false;
    }
  }

  /** Pull remote-side changes back into the workspace. */
  private async pull(): Promise<void> {
    if (this.disposed || this.busy) { return; }
    this.busy = true;
    try {
      await pullWorkspace({
        volumeName: this.opts.volumeName,
        workspaceDir: this.opts.workspaceDir,
        profile: this.opts.profile,
        output: this.opts.output,
      });
    } catch (err: any) {
      this.opts.output.appendLine(`[sync] pull failed: ${err?.message ?? err}`);
    } finally {
      this.busy = false;
    }
  }

  dispose(): void {
    if (this.disposed) { return; }
    this.disposed = true;
    if (this.flushTimer) { clearInterval(this.flushTimer); }
    if (this.pullTimer) { clearInterval(this.pullTimer); }
    this.watcher?.dispose();
    this.status.dispose();
    this.opts.output.appendLine(`[sync] stopped`);
  }
}

function isExcluded(rel: string): boolean {
  return rel.split("/").some((part) => part && SYNC_EXCLUDES.includes(part));
}

/** Whether background auto-sync is enabled. Off by default: a loop that pushes
 *  the workspace every few seconds is intrusive and surprising, so syncing is
 *  something the user triggers (the Push / Pull buttons on a session) unless
 *  they explicitly opt into the live loop. */
export function isAutoSyncEnabled(): boolean {
  return vscode.workspace.getConfiguration("mgpux").get<boolean>("autoSync", false);
}

/** Start the live-sync loop for a session, if auto-sync is on and the profile
 *  has usable credentials. Returns the driver so the caller can store it on the
 *  session (and dispose it later); undefined when sync isn't applicable. */
export function startLiveSync(opts: {
  volumeName?: string;
  workspaceDir: string;
  profile: ModalProfile | undefined;
  output: vscode.OutputChannel;
  /** Bypass the setting — used by the "turn auto-sync on" command. */
  force?: boolean;
}): LiveSyncDriver | undefined {
  if (!opts.volumeName) { return undefined; }
  if (!opts.force && !isAutoSyncEnabled()) {
    opts.output.appendLine(
      `[sync] auto-sync is off — use the session's Push/Pull buttons, ` +
      `or enable "mgpux.autoSync" to sync continuously.`
    );
    return undefined;
  }
  if (!opts.profile?.token_id || !opts.profile?.token_secret) {
    opts.output.appendLine(`[sync] disabled: no credentials for this profile`);
    return undefined;
  }
  try {
    const driver = new LiveSyncDriver({
      volumeName: opts.volumeName,
      workspaceDir: opts.workspaceDir,
      profile: opts.profile,
      output: opts.output,
    });
    driver.start();
    return driver;
  } catch (err: any) {
    opts.output.appendLine(`[sync] failed to start: ${err?.message ?? err}`);
    return undefined;
  }
}

export interface PullOptions {
  volumeName: string;
  workspaceDir: string;
  profile: ModalProfile;
  output: vscode.OutputChannel;
}

/** Push the local workspace up to the session's Volume, on demand. */
export async function pushWorkspace(opts: PullOptions): Promise<{ pushed: number; skipped: number; bytes: number }> {
  const res = await runVolumeSync({
    mode: "push",
    volumeName: opts.volumeName,
    localDir: opts.workspaceDir,
    tokenId: opts.profile.token_id,
    tokenSecret: opts.profile.token_secret,
    output: opts.output,
  });
  return { pushed: res.pushed, skipped: res.skipped, bytes: res.bytes };
}

/** Pull the workspace Volume down into the local folder. Only files that are
 *  missing locally or differ in size are transferred, so a repeat pull after
 *  the first one is cheap — the user's new notebook comes back without
 *  re-downloading the whole seeded workspace. Returns files written + bytes. */
export async function pullWorkspace(opts: PullOptions): Promise<{ pulled: number; skipped: number; bytes: number }> {
  const res = await runVolumeSync({
    mode: "pull",
    volumeName: opts.volumeName,
    localDir: opts.workspaceDir,
    tokenId: opts.profile.token_id,
    tokenSecret: opts.profile.token_secret,
    output: opts.output,
  });
  return { pulled: res.pulled, skipped: res.skipped, bytes: res.bytes };
}

export { formatBytes };

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
