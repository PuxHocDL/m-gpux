import * as vscode from "vscode";
import { getActiveProfile } from "./config";

export class StatusBarManager {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      50
    );
    this.item.command = "mgpux.switchAccount";
    this.item.tooltip = "Click to switch Modal profile";
    this.refresh();
    this.item.show();
  }

  refresh(): void {
    const profile = getActiveProfile();
    if (profile) {
      this.item.text = `$(cloud) M-GPUX: ${profile.name}`;
    } else {
      this.item.text = "$(cloud) M-GPUX: No Profile";
    }
  }

  dispose(): void {
    this.item.dispose();
  }
}
