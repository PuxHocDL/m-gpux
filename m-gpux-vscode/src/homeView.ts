// The "Overview" webview at the top of the M-GPUX sidebar. It only renders a
// snapshot and forwards clicks to the existing mgpux.* commands, so every
// action behaves exactly as it does from the trees and the command palette.
import * as vscode from "vscode";
import { loadProfiles } from "./config";
import { AccountTreeProvider } from "./accountTree";
import { PresetsTreeProvider, loadPresets } from "./presetsTree";
import { sessionStore } from "./sessionStore";
import { isAutoSyncEnabled } from "./liveSync";

const ALLOWED_COMMANDS = new Set([
  "mgpux.openHub", "mgpux.devUp", "mgpux.devManage", "mgpux.serveDeploy", "mgpux.manageServe",
  "mgpux.serveKeysList", "mgpux.manageGateway", "mgpux.hostApp", "mgpux.composeUp",
  "mgpux.composeSandbox", "mgpux.openDashboard", "mgpux.addAccount", "mgpux.switchAccount",
  "mgpux.manageBudgets", "mgpux.billingReports", "mgpux.manageImages", "mgpux.otherClouds",
  "mgpux.loadProbe", "mgpux.openCliMenu", "mgpux.stopAll", "mgpux.openBillingDashboard",
  "mgpux.createPreset", "mgpux.runPreset", "mgpux.discoverApps", "mgpux.openSession",
  "mgpux.viewSessionLogs", "mgpux.stopSession", "mgpux.removeSession", "mgpux.syncSession",
  "mgpux.pushSession", "mgpux.toggleAutoSync", "mgpux.setupCli", "mgpux.checkPython",
]);

const SESSION_COMMANDS = new Set([
  "mgpux.openSession", "mgpux.viewSessionLogs", "mgpux.stopSession",
  "mgpux.removeSession", "mgpux.syncSession", "mgpux.pushSession",
]);

/** Commands that take a tree item get the same shape the tree would pass. */
function commandArgs(command: string, arg: unknown): unknown[] {
  if (typeof arg !== "string" || !arg) { return []; }
  if (command === "mgpux.switchAccount") { return [{ profileName: arg, isPlaceholder: false }]; }
  if (command === "mgpux.runPreset") { return [{ presetName: arg }]; }
  if (SESSION_COMMANDS.has(command)) { return [{ sessionId: arg }]; }
  return [];
}

export class HomeViewProvider implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewId = "mgpux.homeView";

  private view?: vscode.WebviewView;
  private pending?: NodeJS.Timeout;
  private busy = false;
  private readonly disposables: vscode.Disposable[] = [];

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly accountTree: AccountTreeProvider,
    presetsTree: PresetsTreeProvider,
    private readonly version: string,
    private readonly refreshAll: () => Promise<void>,
  ) {
    this.disposables.push(
      accountTree.onDidChangeTreeData(() => this.post()),
      presetsTree.onDidChangeTreeData(() => this.post()),
      sessionStore.onChange(() => this.post()),
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration("mgpux.autoSync")) { this.post(); }
      }),
    );
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    const media = vscode.Uri.joinPath(this.extensionUri, "media");
    view.webview.options = { enableScripts: true, localResourceRoots: [media] };
    view.webview.html = this.html(view.webview, media);
    view.webview.onDidReceiveMessage((msg) => this.onMessage(msg), undefined, this.disposables);
    view.onDidChangeVisibility(() => { if (view.visible) { this.post(); } }, undefined, this.disposables);
    view.onDidDispose(() => { this.view = undefined; }, undefined, this.disposables);
  }

  /** Coalesce bursts of store/tree events into one render. */
  post(): void {
    if (!this.view || this.pending) { return; }
    this.pending = setTimeout(() => {
      this.pending = undefined;
      this.view?.webview.postMessage({ type: "state", state: this.snapshot() });
    }, 60);
  }

  private async onMessage(msg: any): Promise<void> {
    if (msg?.type === "ready") {
      this.post();
    } else if (msg?.type === "refresh") {
      if (this.busy) { return; }
      this.busy = true;
      this.post();
      try { await this.refreshAll(); } finally { this.busy = false; this.post(); }
    } else if (msg?.type === "run" && ALLOWED_COMMANDS.has(msg.command)) {
      await vscode.commands.executeCommand(msg.command, ...commandArgs(msg.command, msg.arg));
    }
  }

  /** Everything the page shows. Tokens never leave the extension host. */
  private snapshot() {
    const accounts = loadProfiles().map((p) => {
      const b = this.accountTree.billingCache.get(p.name);
      const known = !!b && b.used >= 0;
      return {
        name: p.name,
        active: p.active,
        used: known ? b!.used : null,
        remaining: known ? b!.remaining : null,
        limit: b?.limit ?? null,
        budget: b?.hasCustomBudget ?? false,
      };
    });
    if (accounts.length && !accounts.some((a) => a.active)) { accounts[0].active = true; }
    const presets = Object.entries(loadPresets())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, p]) => ({ name, action: p.action ?? "?", compute: p.compute_label ?? p.compute_spec ?? "" }));
    const sessions = sessionStore.list().map((s) => ({
      id: s.id,
      kind: s.kind as string,
      gpu: s.gpu,
      profile: s.profile,
      status: s.status,
      startedAt: s.startedAt,
      appId: s.appId ?? null,
      hasUrl: !!s.accessUrl,
      hasVolume: !!s.workspaceVolume,
      restored: !!s.restored,
    }));
    return {
      version: this.version,
      loading: this.accountTree.loading,
      busy: this.busy,
      autoSync: isAutoSyncEnabled(),
      accounts,
      sessions,
      presets,
    };
  }

  private html(webview: vscode.Webview, media: vscode.Uri): string {
    const nonce = Array.from({ length: 32 }, () => Math.floor(Math.random() * 36).toString(36)).join("");
    const css = webview.asWebviewUri(vscode.Uri.joinPath(media, "home.css"));
    const js = webview.asWebviewUri(vscode.Uri.joinPath(media, "home.js"));
    const csp = [
      "default-src 'none'",
      `style-src ${webview.cspSource}`,
      `img-src ${webview.cspSource} data:`,
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="${css}">
</head>
<body>
  <main id="root" class="root" aria-busy="true"></main>
  <script nonce="${nonce}" src="${js}"></script>
</body>
</html>`;
  }

  dispose(): void {
    if (this.pending) { clearTimeout(this.pending); }
    for (const d of this.disposables) { d.dispose(); }
  }
}
