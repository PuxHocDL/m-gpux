import * as vscode from "vscode";
import * as cp from "child_process";
import * as fs from "fs";
import { save as persistSessions, logPathFor } from "./sessionPersistence";

export type SessionKind = "jupyter" | "python" | "bash" | "vllm";

export type SessionStatus = "starting" | "ready" | "stopping" | "stopped" | "failed";

export interface Session {
  id: string;
  kind: SessionKind;
  gpu: string;
  profile: string;
  status: SessionStatus;
  startedAt: number;
  appId?: string;
  dashboardUrl?: string;
  accessUrl?: string;
  output: vscode.OutputChannel;
  proc?: cp.ChildProcess;
  cwd: string;
  detached: boolean;
  // Path to the on-disk log file (tailed into the output channel). The file
  // also survives extension restarts so the user can see history after reopen.
  logPath: string;
  // When true, the session was reconstructed from disk after VS Code restart
  // (the spawn handle is therefore unavailable).
  restored?: boolean;
  // Name of the Modal Volume mounted at /workspace inside the container.
  // Present for hub / preset / interactive sessions; the live-sync driver
  // uses it to push local edits into the running session.
  workspaceVolume?: string;
  // Disposable that tears down the live-sync watcher when the session
  // is stopped. Not persisted.
  liveSync?: vscode.Disposable;
}

class SessionStore {
  private sessions = new Map<string, Session>();
  private _onChange = new vscode.EventEmitter<void>();
  readonly onChange = this._onChange.event;

  list(): Session[] {
    return Array.from(this.sessions.values()).sort((a, b) => b.startedAt - a.startedAt);
  }

  get(id: string): Session | undefined {
    return this.sessions.get(id);
  }

  add(s: Session): void {
    this.sessions.set(s.id, s);
    this.persist();
    this._onChange.fire();
  }

  update(id: string, patch: Partial<Session>): void {
    const s = this.sessions.get(id);
    if (!s) { return; }
    Object.assign(s, patch);
    this.persist();
    this._onChange.fire();
  }

  remove(id: string): void {
    const s = this.sessions.get(id);
    if (!s) { return; }
    try { s.liveSync?.dispose(); } catch { /* ignore */ }
    try { s.output.dispose(); } catch { /* ignore */ }
    this.sessions.delete(id);
    this.persist();
    this._onChange.fire();
  }

  private persist(): void {
    persistSessions(this.list());
  }

  dispose(): void {
    for (const s of this.sessions.values()) {
      try { s.liveSync?.dispose(); } catch { /* ignore */ }
      try { s.output.dispose(); } catch { /* ignore */ }
    }
    this.sessions.clear();
    this._onChange.dispose();
  }
}

export const sessionStore = new SessionStore();

export function newSessionId(): string {
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

/** Returns the log path for a session, ensuring the directory exists. */
export function sessionLogPath(id: string): string {
  return logPathFor(id);
}

/** Appends to the on-disk log file (best-effort, sync). */
export function appendSessionLog(session: Session, text: string): void {
  try {
    fs.appendFileSync(session.logPath, text);
  } catch { /* ignore */ }
}
