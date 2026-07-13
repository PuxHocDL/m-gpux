// Discover running Modal apps that the extension can adopt as sessions.
// Used at extension startup (to restore sessions after VS Code restart, even
// for ones the local persistence missed) and on demand via the
// `M-GPUX: Discover Modal Apps` command.
import * as vscode from "vscode";
import { listApps, ModalAppEntry, isAliveAppState } from "./modalCli";
import { loadProfiles } from "./config";
import { sessionStore, Session, SessionKind, sessionLogPath } from "./sessionStore";

export interface DiscoveredApp {
  profile: string;
  appId: string;          // `ap-XXXXX` for run, app NAME for deploy
  name: string;           // human name from `modal app list`
  state: string;          // running / deployed / stopped
  kind: SessionKind;      // inferred from app name prefix
}

/** Map app name → SessionKind. The CLI / extension templates name apps
 *  consistently (`m-gpux-jupyter`, `m-gpux-shell`, `m-gpux-host-asgi`…),
 *  so we can recover the session kind without persisted state. */
function inferKind(name: string): SessionKind {
  if (!name) { return "bash" as SessionKind; }
  if (name.includes("jupyter")) { return "jupyter"; }
  if (name.includes("runner")) { return "python"; }
  if (name.includes("shell") || name.includes("interactive")) { return "bash"; }
  if (name.includes("vllm") || name.includes("serve")) { return "vllm"; }
  // Host wizard uses kinds like "host-asgi" / "host-wsgi" / "host-static"
  // which are not part of the canonical SessionKind union but are still
  // shown correctly by the sessions tree.
  if (name.includes("host-asgi"))   { return "host-asgi" as SessionKind; }
  if (name.includes("host-wsgi"))   { return "host-wsgi" as SessionKind; }
  if (name.includes("host-static")) { return "host-static" as SessionKind; }
  return "bash" as SessionKind;
}

/** Whether the app should be treated as an m-gpux session. We tag every
 *  app the extension/CLI deploys with the `m-gpux-` prefix, so the filter is
 *  prefix-based; anything else is left alone. */
function isMgpuxApp(name: string): boolean {
  return typeof name === "string" && name.startsWith("m-gpux-");
}

/** List running m-gpux apps across the given profiles. */
export async function discoverApps(profiles: string[]): Promise<DiscoveredApp[]> {
  const out: DiscoveredApp[] = [];
  for (const profile of profiles) {
    const apps = await listApps(profile);
    for (const a of apps) {
      if (!isAliveAppState(a.state || "")) { continue; }
      const state = (a.state || "").toLowerCase();
      if (!isMgpuxApp(a.name)) { continue; }
      out.push({
        profile,
        appId: a.appId,
        name: a.name,
        state,
        kind: inferKind(a.name),
      });
    }
  }
  return out;
}

/** Whether a discovered app matches an existing session in the store.
 *  We match on appId OR name to tolerate the run/deploy duality (run apps
 *  store `ap-XXXXX` as appId; deploys store the app name as appId). */
function matchSession(discovered: DiscoveredApp): Session | undefined {
  for (const s of sessionStore.list()) {
    if (!s.appId) { continue; }
    if (s.appId === discovered.appId || s.appId === discovered.name) { return s; }
  }
  return undefined;
}

export interface DiscoveryResult {
  /** Sessions that were already in the store; their status was refreshed. */
  refreshed: number;
  /** Sessions that were in the store but no longer have a matching remote app. */
  markedStopped: number;
  /** New sessions added because a remote app was found that we didn't track. */
  adopted: number;
}

/** Sync the session store with what Modal actually has running.
 *
 *  - Existing sessions with a live remote → status set to "ready"
 *  - Existing sessions whose remote no longer exists → status set to "stopped"
 *  - Remote apps we don't have a session for → adopted as a restored session
 */
export async function refreshFromModal(profiles?: string[]): Promise<DiscoveryResult> {
  const allProfiles = profiles ?? loadProfiles().map((p) => p.name);
  if (allProfiles.length === 0) {
    return { refreshed: 0, markedStopped: 0, adopted: 0 };
  }

  const remote = await discoverApps(allProfiles);
  const remoteByKey = new Map<string, DiscoveredApp>();
  for (const r of remote) {
    remoteByKey.set(r.appId, r);
    if (r.name) { remoteByKey.set(r.name, r); }
  }

  let refreshed = 0;
  let markedStopped = 0;
  let adopted = 0;

  // Pass 1: update existing sessions
  for (const s of sessionStore.list()) {
    if (!s.appId) { continue; }
    const live = remoteByKey.get(s.appId);
    if (live) {
      if (s.status !== "ready" && s.status !== "starting") {
        sessionStore.update(s.id, { status: "ready" });
        refreshed++;
      } else {
        refreshed++;
      }
    } else if (s.status === "ready" || s.status === "starting" || s.status === "stopping") {
      // Was supposed to be alive but Modal disagrees.
      sessionStore.update(s.id, { status: "stopped" });
      markedStopped++;
    }
  }

  // Pass 2: adopt unknown remote apps
  for (const r of remote) {
    if (matchSession(r)) { continue; }
    const id = `discovered-${r.profile}-${r.appId}`;
    if (sessionStore.get(id)) { continue; }
    const output = vscode.window.createOutputChannel(
      `M-GPUX: ${r.kind} (${r.name}) [discovered]`,
      "log"
    );
    output.appendLine(`▸ Discovered from Modal: ${r.name} (${r.profile})`);
    output.appendLine(`  App ID: ${r.appId}`);
    output.appendLine(`  State:  ${r.state}`);
    output.appendLine(`\nThis session was found on Modal but was not launched in this VS Code window.`);
    output.appendLine(`Click Stop to terminate it remotely, or open the dashboard for live logs.`);

    sessionStore.add({
      id,
      kind: r.kind,
      gpu: r.kind === "vllm" ? "GPU" : "remote",
      profile: r.profile,
      status: "ready",
      startedAt: Date.now(),
      appId: r.appId,
      output,
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "",
      detached: true,
      logPath: sessionLogPath(id),
      restored: true,
    });
    adopted++;
  }

  return { refreshed, markedStopped, adopted };
}
