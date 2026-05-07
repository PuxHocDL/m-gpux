import * as vscode from "vscode";
import { AccountTreeProvider, AccountItem } from "./accountTree";
import { ActionsTreeProvider } from "./actionsTree";
import { StatusBarManager } from "./statusBar";
import { runHubWizard } from "./hubWizard";
import {
  loadProfiles,
  addProfile,
  removeProfile,
  switchProfile,
  getActiveProfile,
} from "./config";

let statusBar: StatusBarManager;

export function activate(context: vscode.ExtensionContext) {
  // --- Tree Views ---
  const accountTree = new AccountTreeProvider();
  const actionsTree = new ActionsTreeProvider();

  vscode.window.registerTreeDataProvider("mgpux.accountsView", accountTree);
  vscode.window.registerTreeDataProvider("mgpux.actionsView", actionsTree);

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
        `M-GPUX Extension v2.4.0 | ${profiles.length} profile(s) configured | Active: ${active?.name ?? "none"}`
      );
    })
  );
}

export function deactivate() {
  statusBar?.dispose();
}
