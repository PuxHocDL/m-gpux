import * as vscode from "vscode";
import * as cp from "child_process";

export type SessionKind = "jupyter" | "python" | "bash" | "vllm";

export type SessionStatus = "starting" | "ready" | "stopping" | "stopped" | "failed";

export interface Session {
  id: string;
  kind: SessionKind;
  gpu: string;
  profile: string;
  status: SessionStatus;
  startedAt: number;
  // Modal app id (e.g. "ap-XXXXX") — parsed from CLI output. Required for `modal app stop`.
  appId?: string;
  // Modal dashboard URL — also parsed from CLI output.
  dashboardUrl?: string;
  // Public tunnel URL (Jupyter / ttyd / vLLM) — what the user actually opens.
  accessUrl?: string;
  // OutputChannel for this session's logs. Hidden by default; user can "View Logs" to show.
  output: vscode.OutputChannel;
  // Local `modal run` process. Kept so we can detach the local pipe when the user stops.
  proc?: cp.ChildProcess;
  cwd: string;
  // True when launched with `modal run --detach` — local proc death does not stop the remote app.
  detached: boolean;
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
    this._onChange.fire();
  }

  update(id: string, patch: Partial<Session>): void {
    const s = this.sessions.get(id);
    if (!s) { return; }
    Object.assign(s, patch);
    this._onChange.fire();
  }

  remove(id: string): void {
    const s = this.sessions.get(id);
    if (!s) { return; }
    try { s.output.dispose(); } catch { /* ignore */ }
    this.sessions.delete(id);
    this._onChange.fire();
  }

  dispose(): void {
    for (const s of this.sessions.values()) {
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
