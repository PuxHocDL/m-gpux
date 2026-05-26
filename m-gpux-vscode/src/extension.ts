import * as vscode from "vscode";
import { AccountTreeProvider, AccountItem } from "./accountTree";
import { ActionsTreeProvider } from "./actionsTree";
import { SessionsTreeProvider, SessionTreeNode } from "./sessionsTree";
import { StatusBarManager } from "./statusBar";
import { runHubWizard } from "./hubWizard";
import { sessionStore } from "./sessionStore";
import {
  loadProfiles,
  addProfile,
  removeProfile,
  switchProfile,
  getActiveProfile,
} from "./config";

const { spawn } = require("child_process");

let statusBar: StatusBarManager;

export function activate(context: vscode.ExtensionContext) {
  // --- Tree Views ---
  const accountTree = new AccountTreeProvider();
  const actionsTree = new ActionsTreeProvider();
  const sessionsTree = new SessionsTreeProvider();

  vscode.window.registerTreeDataProvider("mgpux.accountsView", accountTree);
  vscode.window.registerTreeDataProvider("mgpux.actionsView", actionsTree);
  vscode.window.registerTreeDataProvider("mgpux.sessionsView", sessionsTree);

  // Periodically refresh the sessions tree so the "age" / "starting…" descriptions stay live.
  const sessionTicker = setInterval(() => sessionsTree.refresh(), 5000);
  context.subscriptions.push({ dispose: () => clearInterval(sessionTicker) });
  context.subscriptions.push({ dispose: () => sessionStore.dispose() });

  // --- Status Bar ---
  statusBar = new StatusBarManager();
  context.subscriptions.push({ dispose: () => statusBar.dispose() });

  // Helper to refresh all UI
  function refreshAll() {
    accountTree.refresh();
    statusBar.refresh();
  }

  // Fetch billing on activation (async, non-blocking)
  accountTree.refreshWithBilling();

  // --- Commands ---

  // GPU Hub
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.openHub", async () => {
      await runHubWizard();
      refreshAll();
    })
  );

  // Add Account
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.addAccount", async () => {
      // Try paste shortcut first
      const raw = await vscode.window.showInputBox({
        title: "Add Modal Account",
        prompt:
          'Paste a `modal token set --token-id ... --token-secret ...` command, or leave empty to enter manually',
        placeHolder:
          "modal token set --token-id ak-... --token-secret as-... --profile=myprofile",
      });

      let tokenId: string | undefined;
      let tokenSecret: string | undefined;
      let name: string | undefined;

      if (raw && raw.trim()) {
        // Parse the command
        const idMatch = raw.match(/--token-id\s+(\S+)/);
        const secretMatch = raw.match(/--token-secret\s+(\S+)/);
        const profileMatch = raw.match(/--profile[=\s]+(\S+)/);
        if (idMatch && secretMatch) {
          tokenId = idMatch[1];
          tokenSecret = secretMatch[1];
          name = profileMatch?.[1];
          vscode.window.showInformationMessage(
            "Parsed token from command successfully!"
          );
        } else {
          vscode.window.showWarningMessage(
            "Could not parse command. Please enter manually."
          );
        }
      }

      if (!tokenId) {
        tokenId = await vscode.window.showInputBox({
          title: "Modal Token ID",
          prompt: "Enter your Modal Token ID",
          placeHolder: "ak-...",
        });
        if (!tokenId) { return; }
      }

      if (!tokenSecret) {
        tokenSecret = await vscode.window.showInputBox({
          title: "Modal Token Secret",
          prompt: "Enter your Modal Token Secret",
          placeHolder: "as-...",
          password: true,
        });
        if (!tokenSecret) { return; }
      }

      if (!name) {
        name = await vscode.window.showInputBox({
          title: "Profile Name",
          prompt: "A friendly name for this profile (e.g. personal, work)",
          placeHolder: "my-profile",
        });
        if (!name) { return; }
      }

      addProfile(name, tokenId, tokenSecret);
      vscode.window.showInformationMessage(
        `Profile '${name}' added successfully!`
      );
      refreshAll();
    })
  );

  // Switch Account
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "mgpux.switchAccount",
      async (item?: AccountItem) => {
        let targetName: string;

        if (item && !item.isPlaceholder) {
          targetName = item.profileName;
        } else {
          const profiles = loadProfiles();
          if (profiles.length === 0) {
            vscode.window.showWarningMessage("No accounts configured.");
            return;
          }
          const pick = await vscode.window.showQuickPick(
            profiles.map((p) => ({
              label: p.active ? `$(check) ${p.name}` : p.name,
              description: p.active ? "Active" : "",
              profileName: p.name,
            })),
            { title: "Switch Modal Profile" }
          );
          if (!pick) { return; }
          targetName = (pick as any).profileName;
        }

        switchProfile(targetName);

        // Also activate via Modal CLI
        const terminal = vscode.window.activeTerminal;
        if (terminal) {
          terminal.sendText(`modal profile activate ${targetName}`);
        }

        vscode.window.showInformationMessage(
          `Switched to profile '${targetName}'`
        );
        refreshAll();
      }
    )
  );

  // Remove Account
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "mgpux.removeAccount",
      async (item?: AccountItem) => {
        let targetName: string;

        if (item && !item.isPlaceholder) {
          targetName = item.profileName;
        } else {
          const profiles = loadProfiles();
          const pick = await vscode.window.showQuickPick(
            profiles.map((p) => ({ label: p.name })),
            { title: "Remove Modal Profile" }
          );
          if (!pick) { return; }
          targetName = pick.label;
        }

        const confirm = await vscode.window.showWarningMessage(
          `Remove profile '${targetName}'? This cannot be undone.`,
          { modal: true },
          "Remove"
        );
        if (confirm !== "Remove") { return; }

        removeProfile(targetName);
        vscode.window.showInformationMessage(
          `Profile '${targetName}' removed.`
        );
        refreshAll();
      }
    )
  );

  // Refresh Accounts
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.refreshAccounts", async () => {
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "M-GPUX: Fetching billing data..." },
        async () => { await accountTree.refreshWithBilling(); }
      );
      statusBar.refresh();
    })
  );

  // Open Billing Dashboard
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.openBillingDashboard", () => {
      vscode.env.openExternal(
        vscode.Uri.parse("https://modal.com/settings/usage")
      );
    })
  );

  // Billing Usage (show cost in terminal)
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.billingUsage", async () => {
      const pick = await vscode.window.showQuickPick(
        [
          { label: "All Accounts", description: "Aggregate across all profiles", flag: "--all" },
          { label: "Active Account", description: "Current active profile only", flag: "" },
        ],
        { title: "Billing Usage — Scope" }
      );
      if (!pick) { return; }
      const terminal = vscode.window.createTerminal({ name: "M-GPUX: Billing" });
      terminal.show();
      const flag = (pick as any).flag;
      terminal.sendText(`m-gpux billing usage ${flag}`.trim());
    })
  );

  // Load Probe
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.loadProbe", async () => {
      const gpuPick = await vscode.window.showQuickPick(
        [
          { label: "T4", description: "16 GB — budget" },
          { label: "L4", description: "24 GB — balanced" },
          { label: "A10G", description: "24 GB" },
          { label: "A100", description: "40 GB SXM" },
          { label: "H100", description: "80 GB" },
        ],
        {
          title: "Probe Hardware — Select GPU",
          placeHolder: "Which GPU to probe?",
        }
      );
      if (!gpuPick) { return; }

      const terminal = vscode.window.createTerminal({
        name: `M-GPUX: Probe ${gpuPick.label}`,
      });
      terminal.show();
      terminal.sendText(`m-gpux load probe --gpu ${gpuPick.label}`);
    })
  );

  // Show Info
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.showInfo", () => {
      const active = getActiveProfile();
      const profiles = loadProfiles();
      vscode.window.showInformationMessage(
        `M-GPUX Extension v2.5.0 | ${profiles.length} profile(s) configured | Active: ${active?.name ?? "none"}`
      );
    })
  );

  // --- Session commands ---

  function resolveSessionId(node?: SessionTreeNode): string | undefined {
    if (node?.sessionId) { return node.sessionId; }
    const sessions = sessionStore.list();
    if (sessions.length === 0) {
      vscode.window.showInformationMessage("No active sessions.");
      return undefined;
    }
    return sessions[0].id;
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.refreshSessions", () => sessionsTree.refresh())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.openSession", async (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      const s = sessionStore.get(id);
      if (!s?.accessUrl) {
        vscode.window.showInformationMessage("Session has no access URL yet — still starting.");
        return;
      }
      vscode.env.openExternal(vscode.Uri.parse(s.accessUrl));
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.copySessionUrl", async (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      const s = sessionStore.get(id);
      if (!s?.accessUrl) {
        vscode.window.showInformationMessage("Session has no access URL yet.");
        return;
      }
      await vscode.env.clipboard.writeText(s.accessUrl);
      vscode.window.showInformationMessage("URL copied to clipboard.");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.viewSessionLogs", (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      const s = sessionStore.get(id);
      s?.output.show(true);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.stopSession", async (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      const s = sessionStore.get(id);
      if (!s) { return; }
      if (s.status === "stopped" || s.status === "failed") {
        const remove = await vscode.window.showQuickPick(
          [
            { label: "Remove from list", action: "remove" as const },
            { label: "Keep", action: "keep" as const },
          ],
          { title: `Session ${s.kind}/${s.gpu} already ${s.status}` }
        );
        if (remove?.action === "remove") {
          sessionStore.remove(id);
        }
        return;
      }

      const confirm = await vscode.window.showWarningMessage(
        s.appId
          ? `Stop ${s.kind} on ${s.gpu}?\nThis will run \`modal app stop ${s.appId}\` on profile '${s.profile}'.`
          : `Stop ${s.kind} on ${s.gpu}?\nApp ID not detected yet — only the local process will be killed.`,
        { modal: true },
        "Stop"
      );
      if (confirm !== "Stop") { return; }

      sessionStore.update(id, { status: "stopping" });
      s.output.appendLine("\n▸ Stop requested by user.");

      // Kill local proc (best-effort — for detached runs this only closes the pipe)
      try { s.proc?.kill(); } catch { /* ignore */ }

      if (!s.appId) {
        sessionStore.update(id, { status: "stopped", proc: undefined });
        vscode.window.showInformationMessage(`Stopped ${s.kind} (local only — no app ID).`);
        return;
      }

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `M-GPUX: stopping ${s.appId}...`,
        },
        async () => {
          // Ensure right profile is active before issuing app stop
          await new Promise<void>((resolve) => {
            const p = spawn("modal", ["profile", "activate", s.profile], { cwd: s.cwd, shell: true });
            p.on("close", () => resolve());
            p.on("error", () => resolve());
          });

          const result = await new Promise<{ code: number; out: string }>((resolve) => {
            const p = spawn("modal", ["app", "stop", s.appId!], {
              cwd: s.cwd,
              shell: true,
              env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
            });
            let out = "";
            p.stdout.on("data", (d: Buffer) => { out += d.toString(); s.output.append(d.toString()); });
            p.stderr.on("data", (d: Buffer) => { out += d.toString(); s.output.append(d.toString()); });
            p.on("close", (code: number | null) => resolve({ code: code ?? 1, out }));
            p.on("error", (err: Error) => resolve({ code: 1, out: err.message }));
          });

          if (result.code === 0) {
            sessionStore.update(id, { status: "stopped", proc: undefined });
            vscode.window.showInformationMessage(`Stopped ${s.kind} on ${s.gpu} (${s.appId}).`);
          } else {
            sessionStore.update(id, { status: "failed", proc: undefined });
            vscode.window.showErrorMessage(
              `Failed to stop ${s.appId} — see logs.`
            );
          }
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.removeSession", (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      sessionStore.remove(id);
    })
  );
}

export function deactivate() {
  statusBar?.dispose();
}
