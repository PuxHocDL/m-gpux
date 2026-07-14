import * as vscode from "vscode";
import { AccountTreeProvider, AccountItem } from "./accountTree";
import { ActionsTreeProvider } from "./actionsTree";
import { SessionsTreeProvider, SessionTreeNode } from "./sessionsTree";
import { PresetsTreeProvider, PresetItem, loadPresets } from "./presetsTree";
import { StatusBarManager } from "./statusBar";
import { runHubWizard } from "./hubWizard";
import { runHostWizard } from "./hostWizard";
import { runServeDeploy, runServeKeyCreate, runServeKeysList, openServeDashboard } from "./serveWizard";
import { createPreset, runPresetByName, deletePresetCommand } from "./presetWizard";
import { composeCheck, composeUp, composeSandbox } from "./composeActions";
import { listApps, activateProfile, runCommand, isAliveAppState } from "./modalCli";
import { refreshFromModal } from "./sessionDiscovery";
import { sessionStore, Session } from "./sessionStore";
import { load as loadPersistedSessions, ensureDirs as ensureSessionDirs } from "./sessionPersistence";
import { resolvePython, clearPythonCache } from "./pythonResolver";
import { pullWorkspace, deriveWorkspaceVolumeName, formatBytes } from "./liveSync";
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
  const presetsTree = new PresetsTreeProvider();

  vscode.window.registerTreeDataProvider("mgpux.accountsView", accountTree);
  vscode.window.registerTreeDataProvider("mgpux.actionsView", actionsTree);
  vscode.window.registerTreeDataProvider("mgpux.sessionsView", sessionsTree);
  vscode.window.registerTreeDataProvider("mgpux.presetsView", presetsTree);

  // Periodically refresh the sessions tree so the "age" / "starting…" descriptions stay live.
  const sessionTicker = setInterval(() => sessionsTree.refresh(), 5000);
  context.subscriptions.push({ dispose: () => clearInterval(sessionTicker) });
  context.subscriptions.push({ dispose: () => sessionStore.dispose() });

  // Restore sessions persisted from a previous VS Code window. The local
  // `modal` process is gone, but if the user launched with --detach the
  // remote Modal app is still running and the access URL is still valid.
  // We first hydrate from local persistence, then ask Modal what's
  // actually running (across all profiles) so sessions launched from the
  // CLI or other VS Code windows also show up.
  (async () => {
    try { await restoreSessions(); } catch { /* best-effort */ }
    try { await refreshFromModal(); } catch { /* best-effort */ }
  })();

  // Re-query Modal every 60s so freshly-stopped apps drop to "stopped" and
  // newly-started ones get adopted without a manual refresh.
  const discoveryTicker = setInterval(() => {
    refreshFromModal().catch(() => { /* ignore */ });
  }, 60_000);
  context.subscriptions.push({ dispose: () => clearInterval(discoveryTicker) });

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
        `M-GPUX Extension v2.7.0 | ${profiles.length} profile(s) configured | Active: ${active?.name ?? "none"}`
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
    vscode.commands.registerCommand("mgpux.refreshSessions", async () => {
      // Re-query Modal so statuses reflect reality (e.g. an app stopped from
      // outside the extension). This does NOT import untracked apps — see
      // mgpux.discoverApps for that.
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "M-GPUX: refreshing sessions from Modal..." },
        async () => {
          try {
            const { refreshed, markedStopped } = await refreshFromModal();
            const parts: string[] = [];
            if (refreshed)     { parts.push(`${refreshed} refreshed`); }
            if (markedStopped) { parts.push(`${markedStopped} marked stopped`); }
            vscode.window.showInformationMessage(
              parts.length ? `M-GPUX: ${parts.join(" • ")}.` : "M-GPUX: no changes."
            );
          } catch (e: any) {
            vscode.window.showWarningMessage(`M-GPUX: refresh failed — ${e?.message ?? e}`);
          }
        }
      );
      sessionsTree.refresh();
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.discoverApps", async () => {
      // Explicit, user-initiated import of m-gpux apps running on Modal that
      // this window isn't tracking. Only this command adopts — the background
      // tick must not, or forgotten apps across every profile keep reappearing
      // in the sidebar on their own.
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "M-GPUX: discovering Modal apps..." },
        async () => {
          try {
            const { refreshed, markedStopped, adopted } = await refreshFromModal({ adopt: true });
            const parts: string[] = [];
            if (adopted)       { parts.push(`${adopted} adopted`); }
            if (refreshed)     { parts.push(`${refreshed} refreshed`); }
            if (markedStopped) { parts.push(`${markedStopped} marked stopped`); }
            vscode.window.showInformationMessage(
              parts.length ? `M-GPUX: ${parts.join(" • ")}.` : "M-GPUX: no m-gpux apps found on Modal."
            );
          } catch (e: any) {
            vscode.window.showWarningMessage(`M-GPUX: discovery failed — ${e?.message ?? e}`);
          }
        }
      );
      sessionsTree.refresh();
    })
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
    vscode.commands.registerCommand("mgpux.syncSession", async (node?: SessionTreeNode) => {
      const id = resolveSessionId(node);
      if (!id) { return; }
      const s = sessionStore.get(id);
      if (!s) { return; }

      // The manual sync is pull-dominant: it brings the whole /workspace volume
      // (notebooks, scripts, generated files — everything the user did in
      // Jupyter/bash) back down to the local folder. We do NOT push local up
      // first; that's what the background live-sync already does continuously
      // for running sessions, and pushing here would risk clobbering fresh
      // remote edits with a stale local copy — the opposite of what the user
      // wants when they click "pull my work back".
      let volume = s.workspaceVolume;
      let target = s.cwd;
      if (!volume) {
        // Adopted/CLI sessions don't carry a volume name. Fall back to the
        // volume derived from the currently open workspace folder — that's the
        // one a Jupyter/bash session launched from this folder would mount.
        const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!folder) {
          vscode.window.showInformationMessage(
            `${s.kind} has no workspace volume and no folder is open — nothing to sync.`
          );
          return;
        }
        volume = deriveWorkspaceVolumeName(folder);
        target = folder;
      }

      const syncProfile = loadProfiles().find((p) => p.name === s.profile);
      if (!syncProfile?.token_id || !syncProfile?.token_secret) {
        vscode.window.showErrorMessage(`M-GPUX: no credentials for profile '${s.profile}'.`);
        return;
      }

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `M-GPUX: pulling ${s.kind} workspace from Modal...` },
        async () => {
          try {
            const res = await pullWorkspace({
              volumeName: volume!,
              workspaceDir: target,
              profile: syncProfile,
              output: s.output,
            });
            if (res.pulled > 0) {
              vscode.window.showInformationMessage(
                `Pulled ${res.pulled} file(s) (${formatBytes(res.bytes)}) into ${target}. ` +
                `${res.skipped} already up to date.`,
                "View Logs"
              ).then((c) => { if (c === "View Logs") { s.output.show(true); } });
            } else {
              vscode.window.showInformationMessage(
                `Already up to date — nothing new on the volume (${res.skipped} file(s) unchanged).`
              );
            }
          } catch (err: any) {
            vscode.window.showErrorMessage(`M-GPUX: sync failed: ${err?.message ?? err}`);
          }
        }
      );
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

      // Tear down live sync first so we don't push to a volume that's about
      // to be detached from a stopped container.
      try { s.liveSync?.dispose(); } catch { /* ignore */ }
      sessionStore.update(id, { liveSync: undefined });

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

  // ─── Stop all apps on a profile ─────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.stopAll", async () => {
      const profiles = loadProfiles();
      if (profiles.length === 0) {
        vscode.window.showWarningMessage("No Modal accounts configured.");
        return;
      }
      let profileName = getActiveProfile()?.name;
      if (profiles.length > 1) {
        const pick = await vscode.window.showQuickPick(
          [
            ...profiles.map((p) => ({
              label: p.active ? `$(check) ${p.name}` : `$(person) ${p.name}`,
              profileName: p.name,
              allProfiles: false,
            })),
            { label: "$(globe) All profiles", profileName: "", allProfiles: true } as any,
          ],
          { title: "Stop apps — select scope" }
        );
        if (!pick) { return; }
        if ((pick as any).allProfiles) {
          await stopAllAppsForProfiles(profiles.map((p) => p.name));
          return;
        }
        profileName = (pick as any).profileName;
      }
      if (!profileName) { return; }
      await stopAllAppsForProfiles([profileName]);
    })
  );

  // ─── Presets ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.refreshPresets", () => presetsTree.refresh())
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.createPreset", async () => {
      await createPreset();
      presetsTree.refresh();
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.runPreset", async (item?: PresetItem) => {
      let name = item?.presetName;
      if (!name) {
        const presets = loadPresets();
        const names = Object.keys(presets).sort();
        if (names.length === 0) {
          const create = await vscode.window.showInformationMessage(
            "No presets saved yet. Create one?", "Create"
          );
          if (create === "Create") { vscode.commands.executeCommand("mgpux.createPreset"); }
          return;
        }
        const pick = await vscode.window.showQuickPick(
          names.map((n) => {
            const p = presets[n];
            return { label: n, description: `${p.action} • ${p.compute_label ?? p.compute_spec ?? "?"}` };
          }),
          { title: "Run preset", placeHolder: "Pick a saved preset" }
        );
        if (!pick) { return; }
        name = pick.label;
      }
      await runPresetByName(name);
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.deletePreset", async (item?: PresetItem) => {
      const name = item?.presetName;
      if (!name) {
        vscode.window.showWarningMessage("Right-click a preset to delete it.");
        return;
      }
      await deletePresetCommand(name);
      presetsTree.refresh();
    })
  );

  // ─── Host wizard ────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.hostApp", () => runHostWizard())
  );

  // ─── Serve LLM ──────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.serveDeploy",         () => runServeDeploy()),
    vscode.commands.registerCommand("mgpux.serveKeysList",       () => runServeKeysList()),
    vscode.commands.registerCommand("mgpux.serveKeysCreate",     () => runServeKeyCreate()),
    vscode.commands.registerCommand("mgpux.openServeDashboard",  () => openServeDashboard())
  );

  // ─── Compose ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("mgpux.composeCheck",   () => composeCheck()),
    vscode.commands.registerCommand("mgpux.composeUp",      () => composeUp()),
    vscode.commands.registerCommand("mgpux.composeSandbox", () => composeSandbox())
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

// ─── Helpers ─────────────────────────────────────────────────────
async function stopAllAppsForProfiles(profiles: string[]): Promise<void> {
  // Collect running apps per profile first so the confirmation modal can
  // show a clear summary before we begin issuing destructive commands.
  const plan: { profile: string; appId: string; name: string }[] = [];
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "M-GPUX: scanning running apps..." },
    async () => {
      for (const profile of profiles) {
        const apps = await listApps(profile);
        for (const a of apps) {
          if (isAliveAppState(a.state)) {
            plan.push({ profile, appId: a.appId, name: a.name || a.appId });
          }
        }
      }
    }
  );

  if (plan.length === 0) {
    vscode.window.showInformationMessage(
      profiles.length === 1
        ? `No running apps on profile '${profiles[0]}'.`
        : `No running apps across ${profiles.length} profiles.`
    );
    return;
  }

  const preview = plan.slice(0, 6).map((p) => `• ${p.name} (${p.profile})`).join("\n");
  const more = plan.length > 6 ? `\n…and ${plan.length - 6} more` : "";
  const confirm = await vscode.window.showWarningMessage(
    `Stop ${plan.length} Modal app(s)?`,
    { modal: true, detail: preview + more },
    "Stop all"
  );
  if (confirm !== "Stop all") { return; }

  let ok = 0;
  let failed = 0;
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `M-GPUX: stopping ${plan.length} app(s)...`, cancellable: false },
    async (progress) => {
      let done = 0;
      for (const entry of plan) {
        progress.report({
          message: `${entry.name} (${entry.profile})`,
          increment: 100 / plan.length,
        });
        await activateProfile(entry.profile);
        const res = await runCommand("modal", ["app", "stop", entry.appId], {});
        if (res.exitCode === 0) { ok++; } else { failed++; }
        done++;
      }
    }
  );
  vscode.window.showInformationMessage(
    `M-GPUX: stopped ${ok} app(s)${failed ? `, ${failed} failed — check logs` : ""}.`
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

  // Live app ids/names, scoped per profile — the same app name ("m-gpux-jupyter")
  // exists on many accounts, so a global set would let a session on one profile
  // look alive because a different profile has that app.
  const liveByProfile = new Map<string, Map<string, number>>();
  for (const [profile] of byProfile) {
    liveByProfile.set(profile, await fetchLiveApps(profile));
  }

  // Deploys reuse one App name per kind and `modal deploy` replaces the app of
  // that name, so several persisted sessions can share an appId. Only the most
  // recent one in each (profile, appId) group can be the live app; the rest were
  // superseded. Without this, every past Jupyter session restores as "ready".
  const newestByKey = new Map<string, number>();
  for (const p of persisted) {
    if (!p.appId) { continue; }
    const key = `${p.profile} ${p.appId}`;
    const best = newestByKey.get(key);
    if (best === undefined || p.startedAt > best) { newestByKey.set(key, p.startedAt); }
  }

  for (const p of persisted) {
    // Determine fresh status from Modal app list (we match by ID OR name —
    // `modal run` sessions key on ap-XXXXX, `modal deploy` sessions key on the
    // app's declared name).
    let status: Session["status"] = p.status;
    if (p.appId) {
      const tasks = liveByProfile.get(p.profile)?.get(p.appId);
      const isNewest = newestByKey.get(`${p.profile} ${p.appId}`) === p.startedAt;
      // Alive on Modal AND not superseded by a newer deploy of the same app.
      // Even then it's only "ready" if a container is actually up — a deployed
      // app that scaled to zero is "idle", not running your kernel.
      status = tasks !== undefined && isNewest ? (tasks > 0 ? "ready" : "idle") : "stopped";
    } else if (status === "starting") {
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
      workspaceVolume: p.workspaceVolume,
      restored: true,
    });
  }
}

/** Live m-gpux-or-not apps on a profile, mapped from App ID *and* app name to
 *  the number of containers actually running. Deploy sessions key on the name,
 *  run sessions on the `ap-XXXXX` id, so both are indexed. */
async function fetchLiveApps(profile: string): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  for (const a of await listApps(profile)) {
    if (!isAliveAppState(a.state)) { continue; }
    if (a.appId) { out.set(a.appId, a.tasks); }
    if (a.name) { out.set(a.name, a.tasks); }
  }
  return out;
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
