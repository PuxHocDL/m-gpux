import * as vscode from "vscode";

type ActionId =
  | "hub"
  | "loadProbe"
  | "billingDashboard"
  | "info";

export class ActionsTreeProvider
  implements vscode.TreeDataProvider<ActionItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    ActionItem | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: ActionItem): vscode.TreeItem {
    return element;
  }

  getChildren(): ActionItem[] {
    return [
      new ActionItem("GPU Hub", "Launch GPU provisioning wizard", "rocket", "mgpux.openHub"),
      new ActionItem("Probe Hardware", "Check GPU/CPU/Memory metrics", "pulse", "mgpux.loadProbe"),
      new ActionItem("Billing Usage", "Show cost across all accounts", "graph", "mgpux.billingUsage"),
      new ActionItem("Billing Dashboard", "Open Modal usage page in browser", "globe", "mgpux.openBillingDashboard"),
      new ActionItem("Info", "Show M-GPUX info", "info", "mgpux.showInfo"),
    ];
  }
}

export class ActionItem extends vscode.TreeItem {
  constructor(
    label: string,
    desc: string,
    icon: string,
    commandId: string
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = desc;
    this.iconPath = new vscode.ThemeIcon(icon);
    this.command = {
      command: commandId,
      title: label,
    };
  }
}
