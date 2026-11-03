import * as vscode from "vscode";
import { BillingInfo, getActiveProfile, loadProfiles } from "./config";

export class StatusBarManager {
  private item: vscode.StatusBarItem;

  constructor(private readonly billingFor: (profile: string) => BillingInfo | undefined = () => undefined) {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      50
    );
    this.item.command = "mgpux.switchAccount";
    this.refresh();
    this.item.show();
  }

  refresh(): void {
    const profile = getActiveProfile();
    if (!profile) {
      this.item.text = "$(cloud) M-GPUX: No Profile";
      this.item.tooltip = "Click to add or switch a Modal profile";
      this.item.backgroundColor = undefined;
      return;
    }

    const billing = this.billingFor(profile.name);
    const known = !!billing && billing.used >= 0;
    this.item.text = known
      ? `$(cloud) ${profile.name} · $${billing!.remaining.toFixed(2)}`
      : `$(cloud) M-GPUX: ${profile.name}`;

    // Nearly out of credit is worth a glance from anywhere in the editor.
    const usedShare = known && billing!.limit > 0 ? billing!.used / billing!.limit : 0;
    this.item.backgroundColor = usedShare >= 0.9
      ? new vscode.ThemeColor("statusBarItem.warningBackground")
      : undefined;

    const tip = new vscode.MarkdownString(undefined, true);
    tip.appendMarkdown(`**M-GPUX** · active account \`${profile.name}\`\n\n`);
    if (known) {
      const kind = billing!.hasCustomBudget ? "budget" : "credit";
      tip.appendMarkdown(
        `$(credit-card) $${billing!.used.toFixed(2)} used · **$${billing!.remaining.toFixed(2)}** ${kind} left ` +
        `of $${billing!.limit.toFixed(2)} this month\n\n`
      );
    }
    tip.appendMarkdown(`${loadProfiles().length} account(s) configured · click to switch`);
    this.item.tooltip = tip;
  }

  dispose(): void {
    this.item.dispose();
  }
}
