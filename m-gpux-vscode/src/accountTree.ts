import * as vscode from "vscode";
import { loadProfiles, ModalProfile } from "./config";

export class AccountTreeProvider
  implements vscode.TreeDataProvider<AccountItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    AccountItem | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
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
          true
        ),
      ];
    }
    return profiles.map(
      (p) => new AccountItem(p.name, p.token_id, p.active, false)
    );
  }
}

export class AccountItem extends vscode.TreeItem {
  constructor(
    public readonly profileName: string,
    public readonly tokenId: string,
    public readonly active: boolean,
    public readonly isPlaceholder: boolean
  ) {
    super(profileName, vscode.TreeItemCollapsibleState.None);

    if (isPlaceholder) {
      this.description = "Run 'M-GPUX: Add Account'";
      this.iconPath = new vscode.ThemeIcon("info");
      this.contextValue = "placeholder";
    } else {
      this.description = active ? "● Active" : "";
      this.iconPath = new vscode.ThemeIcon(
        active ? "account" : "person",
        active
          ? new vscode.ThemeColor("charts.green")
          : undefined
      );
      this.contextValue = "account";
      this.tooltip = `Profile: ${profileName}\nToken ID: ${tokenId.substring(0, 8)}...${active ? "\n✓ Active" : ""}`;
      this.command = {
        command: "mgpux.switchAccount",
        title: "Switch to this account",
        arguments: [this],
      };
    }
  }
}
