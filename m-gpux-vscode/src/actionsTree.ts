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
        new ActionGroup("Projects", "beaker",   "projects"),
        new ActionGroup("Dev Box",  "remote-explorer", "dev"),
        new ActionGroup("Host",     "globe",    "host"),
        new ActionGroup("Serve LLM", "server",  "serve"),
        new ActionGroup("Compose",  "package",  "compose"),
        new ActionGroup("Manage",   "settings", "manage"),
      ];
    }
    if (element instanceof ActionGroup) {
      switch (element.groupId) {
        case "launch": return [
          new ActionItem("Dashboard",       "Web console: accounts, apps, containers, sandboxes, costs", "dashboard", "mgpux.openDashboard"),
          new ActionItem("GPU Hub",         "Jupyter / script / bash / vLLM wizard", "rocket", "mgpux.openHub"),
          new ActionItem("Run Preset",      "Replay a saved workload",               "play-circle", "mgpux.runPreset"),
          new ActionItem("Probe Hardware",  "Check GPU/CPU/RAM metrics",             "pulse",  "mgpux.loadProbe"),
          new ActionItem("CLI Menu",        "Every m-gpux command in an interactive menu", "terminal", "mgpux.openCliMenu"),
        ];
        case "projects": return [
          new ActionItem("Projects",        "mgpux.toml: run, sweep, history",          "beaker", "mgpux.projects"),
          new ActionItem("Run Anywhere",    "Free Kaggle quota → Colab → Modal credit", "globe", "mgpux.runAnywhere"),
          new ActionItem("Notebook Kernel", "Run a local .ipynb on a Modal GPU",       "notebook", "mgpux.useAsKernel"),
        ];
        case "dev": return [
          new ActionItem("Create / Start", "GPU/CPU Sandbox with SSH and persistent snapshots", "vm-running", "mgpux.devUp"),
          new ActionItem("Manage", "Open, pause, resume, sync, or delete a dev box", "remote-explorer", "mgpux.devManage"),
        ];
        case "host": return [
          new ActionItem("Host Web App",    "Deploy ASGI / WSGI / static site",      "globe",  "mgpux.hostApp"),
        ];
        case "serve": return [
          new ActionItem("Deploy LLM",      "Serve a HuggingFace model as OpenAI API", "rocket",  "mgpux.serveDeploy"),
          new ActionItem("Manage Endpoint", "Warm up, dashboard, logs, restart, stop", "server-process", "mgpux.manageServe"),
          new ActionItem("API Keys",        "Create / revoke API keys",              "key",    "mgpux.serveKeysList"),
          new ActionItem("Compute Gateway", "Async API for predeclared CPU/GPU jobs", "server-environment", "mgpux.manageGateway"),
          new ActionItem("Modal Dashboard", "Open Modal apps page in browser",       "link-external", "mgpux.openServeDashboard"),
        ];
        case "compose": return [
          new ActionItem("Check Compose",   "Validate docker-compose.yml",           "checklist", "mgpux.composeCheck"),
          new ActionItem("Deploy Compose",  "Run docker-compose services on Modal",  "rocket",    "mgpux.composeUp"),
          new ActionItem("Sandbox Mode",    "Isolated Modal Sandboxes per service",  "layers",    "mgpux.composeSandbox"),
          new ActionItem("Sync Changes",    "Watch and sync local edits to the stack", "sync",      "mgpux.composeSync"),
        ];
        case "manage": return [
          new ActionItem("Stop All Apps",   "Stop every running Modal app on the active profile", "debug-stop", "mgpux.stopAll"),
          new ActionItem("Budgets",         "Monthly limits per account, check & enforce", "shield", "mgpux.manageBudgets"),
          new ActionItem("Billing Usage",   "Show cost across all accounts",         "graph",  "mgpux.billingUsage"),
          new ActionItem("Billing Reports", "Usage table, cycle summary, GPU rates", "table",  "mgpux.billingReports"),
          new ActionItem("Images",          "Build, publish and manage prebuilt images", "package", "mgpux.manageImages"),
          new ActionItem("Secrets & Sync",  "Same Secrets and images on every workspace", "key", "mgpux.syncWorkspaces"),
          new ActionItem("Volumes",         "Browse and download Modal Volumes",        "database", "mgpux.browseVolumes"),
          new ActionItem("Notifications",   "Discord / Slack / Telegram / ntfy alerts",  "bell", "mgpux.notifications"),
          new ActionItem("Kaggle & Colab",  "GPU quota, kernels and runtimes on other clouds", "cloud", "mgpux.otherClouds"),
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
