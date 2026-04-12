import * as vscode from "vscode";
import { loadProfiles, ModalProfile, fetchAllBilling, BillingInfo } from "./config";

export class AccountTreeProvider
  implements vscode.TreeDataProvider<AccountItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    AccountItem | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private billingCache: Map<string, BillingInfo> = new Map();

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  async refreshWithBilling(): Promise<void> {
    try {
      const billing = await fetchAllBilling();
      this.billingCache.clear();
      for (const b of billing) {
        this.billingCache.set(b.profileName, b);
      }
    } catch {
      // billing fetch failed, show accounts without billing
    }
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: AccountItem): vscode.TreeItem {
    return element;
  }

  getChildren(): AccountItem[] {
    const profiles = loadProfiles();
    if (profiles.length === 0) {
      return [
        new AccountItem(
          "No accounts configured",
          "",
          false,
          true,
          undefined
        ),
      ];
    }
    return profiles.map(
      (p) => new AccountItem(p.name, p.token_id, p.active, false, this.billingCache.get(p.name))
    );
  }
}

export class AccountItem extends vscode.TreeItem {
  constructor(
    public readonly profileName: string,
    public readonly tokenId: string,
    public readonly active: boolean,
    public readonly isPlaceholder: boolean,
    public readonly billing: BillingInfo | undefined
  ) {
    super(profileName, vscode.TreeItemCollapsibleState.None);

    if (isPlaceholder) {
      this.description = "Run 'M-GPUX: Add Account'";
      this.iconPath = new vscode.ThemeIcon("info");
      this.contextValue = "placeholder";
    } else {
      // Build description: active marker + billing
      let desc = active ? "● Active" : "";
      if (billing && billing.used >= 0) {
        const balanceStr = `$${billing.remaining.toFixed(2)} left`;
        desc = desc ? `${desc} · ${balanceStr}` : balanceStr;
      }
      this.description = desc;
      this.iconPath = new vscode.ThemeIcon(
        active ? "account" : "person",
        active
          ? new vscode.ThemeColor("charts.green")
          : undefined
      );
      this.contextValue = "account";

      // Tooltip with detailed billing
      let tip = `Profile: ${profileName}\nToken ID: ${tokenId.substring(0, 8)}...`;
      if (active) { tip += "\n✓ Active"; }
      if (billing && billing.used >= 0) {
        tip += `\n\nBilling this month:`;
        tip += `\n  Used: $${billing.used.toFixed(2)}`;
        tip += `\n  Remaining: $${billing.remaining.toFixed(2)} / $30.00`;
      }
      this.tooltip = tip;

      this.command = {
        command: "mgpux.switchAccount",
        title: "Switch to this account",
        arguments: [this],
      };
    }
  }
}
