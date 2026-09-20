import * as vscode from "vscode";
import { ensureMgpuxCli, getCliTerminalEnvironment, getMgpuxTerminalCommand } from "./cliBootstrap";

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

async function runDevCommand(label: string, command: string): Promise<void> {
  if (!(await ensureMgpuxCli(label))) { return; }
  const cwd = workspaceRoot();
  if (!cwd) {
    vscode.window.showWarningMessage("Open a workspace folder before using a dev box.");
    return;
  }
  const terminal = vscode.window.createTerminal({
    name: `M-GPUX: ${label}`,
    cwd,
    env: getCliTerminalEnvironment(),
  });
  terminal.show(true);
  terminal.sendText(`${getMgpuxTerminalCommand()} ${command}`, true);
}

export async function devUp(): Promise<void> {
  await runDevCommand("dev up", "dev up");
}

export async function devManage(): Promise<void> {
  const action = await vscode.window.showQuickPick(
    [
      { label: "$(list-unordered) List boxes", command: "dev list", terminal: "dev list" },
      { label: "$(remote) Open in VS Code", command: "dev code", terminal: "dev code" },
      { label: "$(terminal) SSH", command: "dev ssh", terminal: "dev ssh" },
      { label: "$(debug-pause) Pause", command: "dev pause", terminal: "dev pause" },
      { label: "$(debug-start) Resume", command: "dev resume", terminal: "dev resume" },
      { label: "$(cloud-upload) Push files", command: "dev sync push", terminal: "dev sync push" },
      { label: "$(cloud-download) Pull files", command: "dev sync pull", terminal: "dev sync pull" },
      { label: "$(trash) Delete box", command: "dev down", terminal: "dev down" },
    ],
    {
      title: "M-GPUX Dev Box",
      placeHolder: "Choose an action for this workspace's dev box",
    }
  );
  if (!action) { return; }
  await runDevCommand(action.terminal, action.command);
}
