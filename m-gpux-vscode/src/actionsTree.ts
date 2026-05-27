import * as vscode from "vscode";

export class ActionsTreeProvider implements vscode.TreeDataProvider<ActionItem | ActionGroup> {
  private _onDidChangeTreeData = new vscode.EventEmitter<ActionItem | ActionGroup | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void { this._onDidChangeTreeData.fire(); }

  getTreeItem(element: ActionItem | ActionGroup): vscode.TreeItem { return element; }

  getChildren(element?: ActionItem | ActionGroup): (ActionItem | ActionGroup)[] {
    if (!element) {
      return [
        new ActionGroup("Launch",   "rocket",   "launch"),
        new ActionGroup("Host",     "globe",    "host"),
        new ActionGroup("Serve LLM", "server",  "serve"),
        new ActionGroup("Compose",  "package",  "compose"),
        new ActionGroup("Manage",   "settings", "manage"),
      ];
    }
    if (element instanceof ActionGroup) {
      switch (element.groupId) {
        case "launch": return [
          new ActionItem("GPU Hub",         "Jupyter / script / bash / vLLM wizard", "rocket", "mgpux.openHub"),
          new ActionItem("Run Preset",      "Replay a saved workload",               "play-circle", "mgpux.runPreset"),
          new ActionItem("Probe Hardware",  "Check GPU/CPU/RAM metrics",             "pulse",  "mgpux.loadProbe"),
        ];
        case "host": return [
          new ActionItem("Host Web App",    "Deploy ASGI / WSGI / static site",      "globe",  "mgpux.hostApp"),
        ];
        case "serve": return [
          new ActionItem("Deploy LLM",      "Serve a HuggingFace model as OpenAI API", "rocket",  "mgpux.serveDeploy"),
          new ActionItem("API Keys",        "Create / revoke API keys",              "key",    "mgpux.serveKeysList"),
          new ActionItem("Modal Dashboard", "Open Modal apps page in browser",       "link-external", "mgpux.openServeDashboard"),
        ];
        case "compose": return [
          new ActionItem("Check Compose",   "Validate docker-compose.yml",           "checklist", "mgpux.composeCheck"),
          new ActionItem("Deploy Compose",  "Run docker-compose services on Modal",  "rocket",    "mgpux.composeUp"),
          new ActionItem("Sandbox Mode",    "Isolated Modal Sandboxes per service",  "layers",    "mgpux.composeSandbox"),
        ];
        case "manage": return [
          new ActionItem("Stop All Apps",   "Stop every running Modal app on the active profile", "debug-stop", "mgpux.stopAll"),
          new ActionItem("Billing Usage",   "Show cost across all accounts",         "graph",  "mgpux.billingUsage"),
          new ActionItem("Billing Dashboard", "Open Modal usage page in browser",    "link-external", "mgpux.openBillingDashboard"),
          new ActionItem("Info",            "Show M-GPUX info",                      "info",   "mgpux.showInfo"),
        ];
        default: return [];
      }
    }
    return [];
  }
}

export class ActionGroup extends vscode.TreeItem {
  constructor(label: string, icon: string, public readonly groupId: string) {
    super(label, vscode.TreeItemCollapsibleState.Expanded);
    this.iconPath = new vscode.ThemeIcon(icon);
    this.contextValue = "action-group";
  }
}

export class ActionItem extends vscode.TreeItem {
  constructor(label: string, desc: string, icon: string, commandId: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = desc;
    this.iconPath = new vscode.ThemeIcon(icon);
    this.command = { command: commandId, title: label };
  }
}
