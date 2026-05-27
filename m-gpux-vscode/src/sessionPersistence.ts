import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import type { Session, SessionKind, SessionStatus } from "./sessionStore";

const STATE_DIR = path.join(os.homedir(), ".m-gpux", "vscode");
const STATE_FILE = path.join(STATE_DIR, "sessions.json");
const LOG_DIR = path.join(STATE_DIR, "logs");

export interface PersistedSession {
  id: string;
  kind: SessionKind;
  gpu: string;
  profile: string;
  status: SessionStatus;
  startedAt: number;
  appId?: string;
  dashboardUrl?: string;
  accessUrl?: string;
  cwd: string;
  detached: boolean;
  logPath: string;
  workspaceVolume?: string;
}

export function ensureDirs(): void {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

export function logPathFor(sessionId: string): string {
  ensureDirs();
  return path.join(LOG_DIR, `${sessionId}.log`);
}

export function load(): PersistedSession[] {
  try {
    if (!fs.existsSync(STATE_FILE)) { return []; }
    const raw = fs.readFileSync(STATE_FILE, "utf-8");
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) { return []; }
    return data;
  } catch {
    return [];
  }
}

export function save(sessions: Session[]): void {
  try {
    ensureDirs();
    const persisted: PersistedSession[] = sessions.map((s) => ({
      id: s.id,
      kind: s.kind,
      gpu: s.gpu,
      profile: s.profile,
      status: s.status,
      startedAt: s.startedAt,
      appId: s.appId,
      dashboardUrl: s.dashboardUrl,
      accessUrl: s.accessUrl,
      cwd: s.cwd,
      detached: s.detached,
      logPath: logPathFor(s.id),
      workspaceVolume: s.workspaceVolume,
    }));
    fs.writeFileSync(STATE_FILE, JSON.stringify(persisted, null, 2), "utf-8");
  } catch {
    // best-effort; persistence failure is non-fatal
  }
}

export function deleteLog(sessionId: string): void {
  try {
    const p = logPathFor(sessionId);
    if (fs.existsSync(p)) { fs.unlinkSync(p); }
  } catch { /* ignore */ }
}
