import * as vscode from "vscode";
import { AccountTreeProvider, AccountItem } from "./accountTree";
import { ActionsTreeProvider } from "./actionsTree";
import { SessionsTreeProvider, SessionTreeNode } from "./sessionsTree";
import { StatusBarManager } from "./statusBar";
import { runHubWizard } from "./hubWizard";
import { sessionStore, Session } from "./sessionStore";
import { load as loadPersistedSessions, ensureDirs as ensureSessionDirs } from "./sessionPersistence";
import { resolvePython, clearPythonCache } from "./pythonResolver";
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

  // Restore sessions persisted from a previous VS Code window. The local
  // `modal` process is gone, but if the user launched with --detach the
  // remote Modal app is still running and the access URL is still valid.
  restoreSessions().catch(() => { /* best-effort */ });

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

  // Billing Usage — show inline summary built from the cached billing in the
  // account tree. Avoids depending on the `m-gpux` Python CLI being installed
  // (which breaks on Python 3.14 setups).
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.billingUsage", async () => {
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "M-GPUX: Fetching billing data..." },
        async () => { await accountTree.refreshWithBilling(); }
      );
      statusBar.refresh();

      const profiles = loadProfiles();
      const lines: string[] = [];
      let totalUsed = 0;
      let countWithData = 0;
      for (const p of profiles) {
        const b = accountTree.billingCache.get(p.name);
        if (b && b.used >= 0) {
          lines.push(`${p.active ? "● " : "  "}${p.name}: $${b.used.toFixed(2)} used · $${b.remaining.toFixed(2)} left`);
          totalUsed += b.used;
          countWithData++;
        } else {
          lines.push(`  ${p.name}: (no data)`);
        }
      }
      if (countWithData > 0) {
        lines.push("");
        lines.push(`Total used (this month): $${totalUsed.toFixed(2)}`);
      }

      const summary = lines.join("\n") || "No accounts configured.";
      await vscode.window.showInformationMessage(
        summary,
        { modal: true, detail: "Open Modal Dashboard for the authoritative usage breakdown." },
        "Open Dashboard"
      ).then((choice) => {
        if (choice === "Open Dashboard") {
          vscode.env.openExternal(vscode.Uri.parse("https://modal.com/settings/usage"));
        }
      });
    })
  );

  // Load Probe — self-contained Modal script (no m-gpux CLI dependency).
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
        { title: "Probe Hardware — Select GPU", placeHolder: "Which GPU to probe?" }
      );
      if (!gpuPick) { return; }

      const probeScript = buildProbeScript(gpuPick.label);
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
      const probePath = require("path").join(workspaceFolder, ".mgpux-probe.py");
      require("fs").writeFileSync(probePath, probeScript, "utf-8");

      const out = vscode.window.createOutputChannel(`M-GPUX: Probe ${gpuPick.label}`, "log");
      out.show(true);
      out.appendLine(`▸ Running: modal run .mgpux-probe.py`);
      out.appendLine(`  GPU: ${gpuPick.label}`);
      out.appendLine(`  CWD: ${workspaceFolder}\n`);

      const proc = spawn("modal", ["run", ".mgpux-probe.py"], {
        cwd: workspaceFolder,
        shell: true,
        env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
      });
      proc.stdout.on("data", (d: Buffer) => out.append(d.toString()));
      proc.stderr.on("data", (d: Buffer) => out.append(d.toString()));
      proc.on("close", (code: number | null) => {
        out.appendLine(`\nExit ${code}`);
        try { require("fs").unlinkSync(probePath); } catch { /* ignore */ }
      });
    })
  );

  // Show Info
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.showInfo", () => {
      const active = getActiveProfile();
      const profiles = loadProfiles();
      vscode.window.showInformationMessage(
        `M-GPUX Extension v2.5.2 | ${profiles.length} profile(s) configured | Active: ${active?.name ?? "none"}`
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

  // Python diagnostics — helpful when modal SDK is missing on the local
  // interpreter (the most common cause of "billing unavailable" on fresh
  // Python 3.14 installs).
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.checkPython", async () => {
      clearPythonCache();
      const py = await resolvePython(true);
      if (!py) {
        const choice = await vscode.window.showErrorMessage(
          "No Python interpreter found. Install Python 3.10–3.13 and re-run.",
          "Open Python downloads"
        );
        if (choice === "Open Python downloads") {
          vscode.env.openExternal(vscode.Uri.parse("https://www.python.org/downloads/"));
        }
        return;
      }
      const cmdline = [py.cmd, ...py.args].join(" ");
      if (py.hasModal) {
        vscode.window.showInformationMessage(
          `M-GPUX uses: ${cmdline}  (Python ${py.version}, modal ✓)`
        );
      } else {
        const choice = await vscode.window.showWarningMessage(
          `Found Python ${py.version} (${cmdline}) but \`modal\` is not installed there. ` +
          `Billing widgets will show no data. Install with: ${cmdline} -m pip install modal`,
          "Open Modal docs"
        );
        if (choice === "Open Modal docs") {
          vscode.env.openExternal(vscode.Uri.parse("https://modal.com/docs/guide"));
        }
      }
    })
  );

  // Re-resolve python whenever the user changes the override setting.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("mgpux.pythonPath")) {
        clearPythonCache();
        accountTree.refreshWithBilling();
      }
    })
  );
}

async function restoreSessions(): Promise<void> {
  ensureSessionDirs();
  const persisted = loadPersistedSessions();
  if (persisted.length === 0) { return; }

  // Bucket by profile so we issue one `modal app list` per profile.
  const byProfile = new Map<string, typeof persisted>();
  for (const p of persisted) {
    if (!byProfile.has(p.profile)) { byProfile.set(p.profile, []); }
    byProfile.get(p.profile)!.push(p);
  }

  const liveAppIds = new Set<string>();
  for (const [profile, _entries] of byProfile) {
    const ids = await fetchLiveAppIds(profile);
    for (const id of ids) { liveAppIds.add(id); }
  }

  for (const p of persisted) {
    // Determine fresh status from Modal app list (only if we have an app id).
    let status: Session["status"] = p.status;
    if (p.appId) {
      status = liveAppIds.has(p.appId) ? "ready" : "stopped";
    } else if (status === "starting") {
      // No app id was ever captured and the previous host died — call it failed.
      status = "failed";
    }

    const outputChannel = vscode.window.createOutputChannel(
      `M-GPUX: ${p.kind} (${p.gpu}) [restored]`,
      "log"
    );
    // Replay the on-disk log so the user can view it.
    try {
      const logged = require("fs").readFileSync(p.logPath, "utf-8");
      outputChannel.append(logged);
    } catch { /* file may not exist */ }
    outputChannel.appendLine("\n[restored from previous VS Code session]");

    sessionStore.add({
      id: p.id,
      kind: p.kind,
      gpu: p.gpu,
      profile: p.profile,
      status,
      startedAt: p.startedAt,
      appId: p.appId,
      dashboardUrl: p.dashboardUrl,
      accessUrl: p.accessUrl,
      output: outputChannel,
      cwd: p.cwd,
      detached: p.detached,
      logPath: p.logPath,
      restored: true,
    });
  }
}

function fetchLiveAppIds(profile: string): Promise<string[]> {
  return new Promise((resolve) => {
    const proc = spawn(
      "modal",
      ["app", "list", "--env", "main", "--json"],
      {
        shell: true,
        env: { ...process.env, MODAL_PROFILE: profile, PYTHONIOENCODING: "utf-8" },
      }
    );
    let stdout = "";
    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    proc.on("error", () => resolve([]));
    proc.on("close", () => {
      try {
        const apps = JSON.parse(stdout || "[]");
        const ids: string[] = [];
        for (const a of apps) {
          const id = a["App ID"] ?? a.app_id ?? a.id;
          const state = (a["State"] ?? a.state ?? "").toString().toLowerCase();
          if (id && (state === "running" || state === "deployed")) {
            ids.push(id);
          }
        }
        resolve(ids);
      } catch {
        resolve([]);
      }
    });
  });
}

function buildProbeScript(gpu: string): string {
  return `import modal

app = modal.App("m-gpux-probe")
image = modal.Image.debian_slim(python_version="3.12")

@app.function(image=image, gpu="${gpu}", timeout=300)
def probe():
    import subprocess, json
    info = {}
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.free,utilization.gpu,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ], text=True)
        for line in out.strip().split("\\n"):
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 7:
                info = {
                    "name": p[0], "driver": p[1],
                    "vram_total_mb": int(p[2]), "vram_free_mb": int(p[3]),
                    "util_pct": int(p[4]), "temp_c": int(p[5]),
                    "power_w": float(p[6]),
                }
                break
    except Exception as exc:
        info["nvidia_smi_error"] = str(exc)
    try:
        with open("/proc/meminfo") as f:
            mi = {k.strip(): v.strip() for line in f for k, v in [line.split(":")]}
        info["ram_total_gib"] = round(int(mi["MemTotal"].split()[0]) / 1048576, 1)
        info["ram_free_gib"] = round(int(mi["MemAvailable"].split()[0]) / 1048576, 1)
    except Exception:
        pass
    try:
        info["cpu_count"] = int(subprocess.check_output(["nproc"], text=True).strip())
    except Exception:
        pass
    print("\\n=== Probe ${gpu} ===")
    print(json.dumps(info, indent=2))

@app.local_entrypoint()
def main():
    probe.remote()
`;
}

export function deactivate() {
  statusBar?.dispose();
}
