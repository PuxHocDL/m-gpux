import * as vscode from "vscode";
import { sessionStore, Session, SessionStatus } from "./sessionStore";

const KIND_ICON: Record<string, string> = {
  jupyter: "notebook",
  python: "play",
  bash: "terminal",
  vllm: "server",
  "host-asgi":   "server-environment",
  "host-wsgi":   "server",
  "host-static": "file-directory",
};

const STATUS_ICON: Record<SessionStatus, string> = {
  starting: "loading~spin",
  ready: "pass-filled",
  stopping: "loading~spin",
  stopped: "circle-slash",
  failed: "error",
};

export class SessionsTreeProvider implements vscode.TreeDataProvider<SessionTreeNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<SessionTreeNode | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor() {
    sessionStore.onChange(() => this._onDidChangeTreeData.fire());
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: SessionTreeNode): vscode.TreeItem {
    return element;
  }

  getChildren(element?: SessionTreeNode): SessionTreeNode[] {
    if (element) {
      return element.children ?? [];
    }
    const sessions = sessionStore.list();
    if (sessions.length === 0) {
      const empty = new SessionTreeNode(
        "No active sessions",
        "Launch via GPU Hub",
        new vscode.ThemeIcon("dash"),
        vscode.TreeItemCollapsibleState.None
      );
      empty.contextValue = "empty";
      return [empty];
    }
    return sessions.map((s) => buildSessionNode(s));
  }
}

function buildSessionNode(s: Session): SessionTreeNode {
  const icon = new vscode.ThemeIcon(KIND_ICON[s.kind] ?? "circle-large-outline");
  const statusIcon = new vscode.ThemeIcon(STATUS_ICON[s.status] ?? "circle-outline");
  const age = formatAge(Date.now() - s.startedAt);
  const label = `${s.kind} • ${s.gpu}`;
  const description = describeStatus(s, age);

  const node = new SessionTreeNode(label, description, icon, vscode.TreeItemCollapsibleState.Collapsed);
  node.tooltip = buildTooltip(s);
  node.contextValue = `session.${s.status}${s.accessUrl ? ".hasUrl" : ""}${s.appId ? ".hasApp" : ""}`;
  node.sessionId = s.id;

  const children: SessionTreeNode[] = [];

  children.push(makeChild(
    "Status",
    s.status,
    statusIcon
  ));

  if (s.accessUrl) {
    const urlNode = makeChild("Access URL", s.accessUrl, new vscode.ThemeIcon("link-external"));
    urlNode.command = {
      command: "mgpux.openSession",
      title: "Open",
      arguments: [node],
    };
    children.push(urlNode);
  } else if (s.status === "starting") {
    children.push(makeChild("Access URL", "waiting…", new vscode.ThemeIcon("watch")));
  }

  if (s.dashboardUrl) {
    const dash = makeChild("Modal Dashboard", s.dashboardUrl, new vscode.ThemeIcon("dashboard"));
    dash.command = {
      command: "vscode.open",
      title: "Open",
      arguments: [vscode.Uri.parse(s.dashboardUrl)],
    };
    children.push(dash);
  }

  if (s.appId) {
    children.push(makeChild("App ID", s.appId, new vscode.ThemeIcon("tag")));
  }

  children.push(makeChild("Profile", s.profile, new vscode.ThemeIcon("person")));
  children.push(makeChild("Started", new Date(s.startedAt).toLocaleString(), new vscode.ThemeIcon("clock")));

  node.children = children;
  return node;
}

function makeChild(label: string, description: string, icon: vscode.ThemeIcon): SessionTreeNode {
  const n = new SessionTreeNode(label, description, icon, vscode.TreeItemCollapsibleState.None);
  n.contextValue = "session.field";
  return n;
}

function describeStatus(s: Session, age: string): string {
  const tag = s.restored ? " • restored" : "";
  switch (s.status) {
    case "starting": return `starting • ${age}${tag}`;
    case "ready": return `ready • ${age}${tag}`;
    case "stopping": return `stopping…`;
    case "stopped": return `stopped${tag}`;
    case "failed": return `failed${tag}`;
  }
}

function buildTooltip(s: Session): vscode.MarkdownString {
  const md = new vscode.MarkdownString(undefined, true);
  md.appendMarkdown(`**${s.kind}** on \`${s.gpu}\`\n\n`);
  md.appendMarkdown(`- Status: \`${s.status}\`\n`);
  md.appendMarkdown(`- Profile: \`${s.profile}\`\n`);
  if (s.appId) { md.appendMarkdown(`- App ID: \`${s.appId}\`\n`); }
  if (s.accessUrl) { md.appendMarkdown(`- URL: ${s.accessUrl}\n`); }
  if (s.detached) { md.appendMarkdown(`- Detached: remote keeps running after VS Code closes\n`); }
  return md;
}

function formatAge(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) { return `${s}s`; }
  const m = Math.floor(s / 60);
  if (m < 60) { return `${m}m`; }
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}

export class SessionTreeNode extends vscode.TreeItem {
  sessionId?: string;
  children?: SessionTreeNode[];

  constructor(
    label: string,
    description: string,
    icon: vscode.ThemeIcon,
    collapsibleState: vscode.TreeItemCollapsibleState
  ) {
    super(label, collapsibleState);
    this.description = description;
    this.iconPath = icon;
  }
}
