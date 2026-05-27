// Shared launcher that mirrors hubWizard.ts:showAndExecuteScript — write a
// modal_runner.py, optionally preview, then spawn `modal run|deploy` and
// register a Session so the sidebar / status bar reflect it.
//
// hubWizard.ts keeps its own copy for historical reasons; new wizards
// (host, serve, preset) call into this module.
import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import {
  sessionStore,
  newSessionId,
  SessionKind,
  sessionLogPath,
  appendSessionLog,
} from "./sessionStore";
import { activateProfile } from "./modalCli";

const { spawn } = require("child_process");

export interface LaunchOptions {
  scriptContent: string;
  /** Working directory where modal_runner.py is written and `modal` is invoked. */
  cwd: string;
  /** "deploy" leaves a persistent web service running on Modal. "run" is a
   *  foreground one-shot. */
  mode: "deploy" | "run";
  /** Short label for the session, e.g. "asgi", "wsgi", "static", "vllm-serve". */
  kind: SessionKind | string;
  /** Compute label shown in the sidebar — usually "T4", "L4", "CPU", … */
  computeLabel: string;
  /** Modal profile name used to launch this app. */
  profile: string;
  /** When true, opens the generated script in an editor tab for review and
   *  asks the user to confirm before spawning modal. */
  preview?: boolean;
  /** Custom file name for the generated runner (default: "modal_runner.py"). */
  runnerFilename?: string;
}

export async function launchModalScript(opts: LaunchOptions): Promise<void> {
  const runnerFilename = opts.runnerFilename ?? "modal_runner.py";
  const runnerPath = path.join(opts.cwd, runnerFilename);
  fs.writeFileSync(runnerPath, opts.scriptContent, "utf-8");

  if (opts.preview !== false) {
    const doc = await vscode.workspace.openTextDocument(runnerPath);
    await vscode.window.showTextDocument(doc, { preview: true });
    const choice = await vscode.window.showInformationMessage(
      `Ready to launch ${opts.kind} on ${opts.computeLabel}. Review the script, then choose an action.`,
      { modal: true },
      "Launch",
      "Cancel"
    );
    if (choice === "Cancel" || !choice) {
      vscode.window.showInformationMessage(
        `Execution cancelled. ${runnerFilename} kept for manual use.`
      );
      return;
    }
  }

  const output = vscode.window.createOutputChannel(
    `M-GPUX: ${opts.kind} (${opts.computeLabel})`,
    "log"
  );
  output.appendLine(`═══════════════════════════════════════════════`);
  output.appendLine(`  M-GPUX: Launching ${opts.kind} on ${opts.computeLabel}`);
  output.appendLine(`  Profile: ${opts.profile}`);
  output.appendLine(`  Mode: ${opts.mode === "deploy" ? "Persistent web service" : "One-shot run"}`);
  output.appendLine(`  CWD: ${opts.cwd}`);
  output.appendLine(`  Time: ${new Date().toLocaleString()}`);
  output.appendLine(`═══════════════════════════════════════════════\n`);

  output.appendLine(`▸ Activating profile: ${opts.profile}`);
  await activateProfile(opts.profile, opts.cwd);
  output.appendLine(`✓ Profile activated\n`);

  const args = opts.mode === "deploy" ? ["deploy", runnerFilename] : ["run", runnerFilename];
  output.appendLine(`▸ Running: modal ${args.join(" ")}\n`);

  const sessionId = newSessionId();
  const logPath = sessionLogPath(sessionId);
  try { fs.writeFileSync(logPath, ""); } catch { /* ignore */ }

  // SessionKind is a small union ("jupyter"|"python"|"bash"|"vllm"); when the
  // caller passes a non-canonical label we still register the session so the
  // sidebar shows it — TypeScript is satisfied by the cast and the union is
  // only used cosmetically for icons.
  const kind = opts.kind as SessionKind;

  sessionStore.add({
    id: sessionId,
    kind,
    gpu: opts.computeLabel,
    profile: opts.profile,
    status: "starting",
    startedAt: Date.now(),
    output,
    cwd: opts.cwd,
    detached: opts.mode === "deploy",
    logPath,
  });

  vscode.commands.executeCommand("mgpux.sessionsView.focus").then(undefined, () => { /* ignore */ });

  const isWin = process.platform === "win32";
  const proc = spawn("modal", args, {
    cwd: opts.cwd,
    shell: isWin,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  });
  sessionStore.update(sessionId, { proc });

  let buffer = "";
  let gotAccessUrl = false;
  let gotAppMeta = false;

  const handleChunk = (text: string) => {
    output.append(text);
    const s = sessionStore.get(sessionId);
    if (s) { appendSessionLog(s, text); }
    buffer += text;
    if (buffer.length > 16000) { buffer = buffer.slice(-8000); }

    if (!gotAppMeta) {
      const runMatch = buffer.match(/https?:\/\/modal\.com\/apps\/[^\s"']*\/(ap-[A-Za-z0-9]+)/);
      if (runMatch) {
        gotAppMeta = true;
        sessionStore.update(sessionId, { appId: runMatch[1], dashboardUrl: runMatch[0] });
      } else {
        const deployMatch = buffer.match(/https?:\/\/modal\.com\/apps\/[^\s"']*\/deployed\/([A-Za-z0-9_-]+)/);
        if (deployMatch) {
          gotAppMeta = true;
          sessionStore.update(sessionId, { appId: deployMatch[1], dashboardUrl: deployMatch[0] });
        }
      }
    }

    if (!gotAccessUrl) {
      const m = buffer.match(/https?:\/\/[^\s"']*modal\.(?:host|run)[^\s"']*/);
      if (m) {
        gotAccessUrl = true;
        const url = m[0];
        sessionStore.update(sessionId, { status: "ready", accessUrl: url });
        vscode.window.showInformationMessage(
          `${opts.kind} ready on ${opts.computeLabel}: ${url}`,
          "Open in Browser",
          "Copy URL"
        ).then((choice) => {
          if (choice === "Open in Browser") {
            vscode.env.openExternal(vscode.Uri.parse(url));
          } else if (choice === "Copy URL") {
            vscode.env.clipboard.writeText(url);
            vscode.window.showInformationMessage("URL copied.");
          }
        });
      }
    }
  };

  proc.stdout.on("data", (d: Buffer) => handleChunk(d.toString()));
  proc.stderr.on("data", (d: Buffer) => handleChunk(d.toString()));

  proc.on("close", (code: number | null) => {
    const s = sessionStore.get(sessionId);
    if (!s) { return; }
    if (code === 0) {
      output.appendLine(`\n✓ Local process completed (code 0).`);
      const stillUp = opts.mode === "deploy" && gotAccessUrl;
      sessionStore.update(sessionId, { status: stillUp ? "ready" : "stopped", proc: undefined });
    } else if (s.status === "stopping") {
      output.appendLine(`\n• Local process exited after stop (code ${code}).`);
      sessionStore.update(sessionId, { status: "stopped", proc: undefined });
    } else {
      output.appendLine(`\n✗ Process exited with code ${code}.`);
      sessionStore.update(sessionId, { status: "failed", proc: undefined });
      vscode.window.showWarningMessage(
        `M-GPUX: ${opts.kind} on ${opts.computeLabel} exited with code ${code}. Right-click the session → View Logs.`
      );
    }
    try { if (fs.existsSync(runnerPath)) { fs.unlinkSync(runnerPath); } } catch { /* ignore */ }
  });

  proc.on("error", (err: Error) => {
    output.appendLine(`\n✗ Failed to start: ${err.message}`);
    sessionStore.update(sessionId, { status: "failed", proc: undefined });
    vscode.window.showErrorMessage(`M-GPUX: failed to run modal: ${err.message}`);
  });
}
