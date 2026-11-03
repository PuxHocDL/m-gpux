// Modal Jupyter sessions as VS Code notebook kernels.
//
// The Jupyter extension (ms-toolsai.jupyter) lets other extensions contribute
// "Jupyter Server Collections" to the notebook kernel picker. Every running
// M-GPUX Jupyter session becomes a server there, so a local .ipynb can run its
// cells on a Modal GPU without leaving the editor. The collection also offers
// "Launch a GPU Jupyter server…", which runs the Hub wizard and returns the
// new server once its URL is up.
//
// Only the structural types of the public API are declared here (see
// @vscode/jupyter-extension api.d.ts) so the extension does not depend on it.
import * as vscode from "vscode";
import { runHubWizard } from "./hubWizard";
import { refreshFromModal } from "./sessionDiscovery";
import { Session, sessionStore } from "./sessionStore";

const JUPYTER_EXTENSION = "ms-toolsai.jupyter";
const COLLECTION_ID = "mgpux-modal";
const LAUNCH_TIMEOUT_MS = 20 * 60 * 1000;

interface JupyterServer {
  readonly id: string;
  readonly label: string;
  readonly connectionInformation?: { readonly baseUrl: vscode.Uri; readonly token?: string; readonly headers?: Record<string, string> };
}
interface JupyterServerCommand { label: string; description?: string; canBeAutoSelected?: boolean }
interface JupyterServerCollection {
  label: string;
  documentation?: vscode.Uri;
  commandProvider?: {
    provideCommands(value: string | undefined, token: vscode.CancellationToken): vscode.ProviderResult<JupyterServerCommand[]>;
    handleCommand(command: JupyterServerCommand, token: vscode.CancellationToken): vscode.ProviderResult<JupyterServer>;
  };
  dispose(): void;
}
interface JupyterApi {
  createJupyterServerCollection(
    id: string,
    label: string,
    provider: {
      onDidChangeServers?: vscode.Event<void>;
      provideJupyterServers(token: vscode.CancellationToken): vscode.ProviderResult<JupyterServer[]>;
      resolveJupyterServer(server: JupyterServer, token: vscode.CancellationToken): vscode.ProviderResult<JupyterServer>;
    }
  ): JupyterServerCollection;
}

/** A session can serve kernels when it is a Jupyter app with a URL (idle ones cold-start on connect). */
export function isKernelSession(s: Session): boolean {
  return s.kind === "jupyter" && !!s.accessUrl && (s.status === "ready" || s.status === "idle");
}

/** Base URL and token from a session's access URL (`https://…modal.run/lab?token=…`). */
export function connectionFor(accessUrl: string): { baseUrl: string; token: string } | undefined {
  try {
    const url = new URL(accessUrl);
    if (url.protocol !== "https:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") { return undefined; }
    const token = url.searchParams.get("token") ?? "";
    // Jupyter serves from the root of the tunnel; strip UI paths like /lab or /tree.
    const path = url.pathname.replace(/\/(lab|tree|notebooks)(\/.*)?$/, "").replace(/\/+$/, "");
    return { baseUrl: `${url.origin}${path}/`, token };
  } catch {
    return undefined;
  }
}

function serverFor(s: Session): JupyterServer | undefined {
  const conn = s.accessUrl ? connectionFor(s.accessUrl) : undefined;
  if (!conn) { return undefined; }
  const state = s.status === "idle" ? " · scaled to zero (first cell cold-starts)" : "";
  return {
    id: s.id,
    label: `${s.gpu} · ${s.profile}${state}`,
    connectionInformation: { baseUrl: vscode.Uri.parse(conn.baseUrl), token: conn.token },
  };
}

export class ModalKernelProvider implements vscode.Disposable {
  private collection?: JupyterServerCollection;
  private registering?: Promise<boolean>;
  private readonly changed = new vscode.EventEmitter<void>();
  private readonly disposables: vscode.Disposable[] = [this.changed];
  private lastIds = "";

  constructor() {
    this.disposables.push(
      sessionStore.onChange(() => {
        const ids = sessionStore.list().filter(isKernelSession).map((s) => `${s.id}:${s.accessUrl}`).join("|");
        if (ids !== this.lastIds) {
          this.lastIds = ids;
          this.changed.fire();
        }
      }),
      // Registering early would activate the Jupyter extension for nothing;
      // wait until a notebook is actually open.
      vscode.workspace.onDidOpenNotebookDocument(() => { void this.ensureRegistered(false); }),
    );
    if (vscode.workspace.notebookDocuments.length) { void this.ensureRegistered(false); }
  }

  static jupyterInstalled(): boolean {
    return !!vscode.extensions.getExtension(JUPYTER_EXTENSION);
  }

  /** Register the collection once; `interactive` offers to install the Jupyter extension. */
  async ensureRegistered(interactive: boolean): Promise<boolean> {
    if (this.collection) { return true; }
    const ext = vscode.extensions.getExtension<JupyterApi>(JUPYTER_EXTENSION);
    if (!ext) {
      if (interactive) {
        const choice = await vscode.window.showInformationMessage(
          "Running notebooks on Modal kernels needs the Jupyter extension.", "Install Jupyter"
        );
        if (choice === "Install Jupyter") {
          await vscode.commands.executeCommand("workbench.extensions.installExtension", JUPYTER_EXTENSION);
        }
      }
      return false;
    }
    this.registering ??= (async () => {
      try {
        const api = ext.isActive ? ext.exports : await ext.activate();
        if (!api?.createJupyterServerCollection) { return false; }
        this.collection = api.createJupyterServerCollection(COLLECTION_ID, "M-GPUX · Modal GPUs", {
          onDidChangeServers: this.changed.event,
          provideJupyterServers: () => sessionStore.list().filter(isKernelSession).map(serverFor).filter((s): s is JupyterServer => !!s),
          resolveJupyterServer: (server) => server,
        });
        this.collection.documentation = vscode.Uri.parse("https://puxhocdl.github.io/m-gpux/vscode/#notebook-kernels");
        this.collection.commandProvider = {
          provideCommands: () => [
            { label: "$(rocket) Launch a GPU Jupyter server on Modal…", description: "Hub wizard, then connect", canBeAutoSelected: true },
            { label: "$(cloud-download) Find running M-GPUX Jupyter apps", description: "Adopt sessions started elsewhere" },
          ],
          handleCommand: (command, token) =>
            command.label.includes("Launch") ? this.launch(token) : this.discover(),
        };
        this.disposables.push({ dispose: () => this.collection?.dispose() });
        return true;
      } catch (err: any) {
        if (interactive) { vscode.window.showErrorMessage(`M-GPUX: could not register Modal kernels — ${err?.message ?? err}`); }
        return false;
      } finally {
        this.registering = undefined;
      }
    })();
    return this.registering;
  }

  /** Run the Hub wizard for Jupyter and resolve with the new server once its URL is known. */
  private async launch(token: vscode.CancellationToken): Promise<JupyterServer | undefined> {
    const before = new Set(sessionStore.list().map((s) => s.id));
    await runHubWizard("jupyter");
    const started = sessionStore.list().find((s) => !before.has(s.id) && s.kind === "jupyter");
    if (!started) { throw new vscode.CancellationError(); }
    return vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "M-GPUX: waiting for the Jupyter server on Modal…", cancellable: true },
      (_progress, cancel) => new Promise<JupyterServer | undefined>((resolve, reject) => {
        const finish = (server?: JupyterServer, error?: Error) => {
          sub.dispose();
          clearTimeout(timer);
          if (error) { reject(error); } else { resolve(server); }
        };
        const check = () => {
          const s = sessionStore.get(started.id);
          if (!s || s.status === "failed" || s.status === "stopped") {
            finish(undefined, new Error("The Jupyter session did not start; see its logs in the Sessions view."));
          } else if (isKernelSession(s)) {
            finish(serverFor(s));
          }
        };
        const sub = sessionStore.onChange(check);
        const timer = setTimeout(() => finish(undefined, new Error("Timed out waiting for the Jupyter URL.")), LAUNCH_TIMEOUT_MS);
        cancel.onCancellationRequested(() => finish(undefined, new vscode.CancellationError()));
        token.onCancellationRequested(() => finish(undefined, new vscode.CancellationError()));
        check();
      })
    );
  }

  private async discover(): Promise<JupyterServer | undefined> {
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "M-GPUX: looking for Jupyter apps on Modal…" },
      () => refreshFromModal({ adopt: true }).catch(() => undefined)
    );
    const servers = sessionStore.list().filter(isKernelSession).map(serverFor).filter((s): s is JupyterServer => !!s);
    if (servers.length === 0) {
      vscode.window.showInformationMessage("No running M-GPUX Jupyter apps found. Launch one from the same menu.");
      return undefined; // back to the kernel picker
    }
    if (servers.length === 1) { return servers[0]; }
    const pick = await vscode.window.showQuickPick(servers.map((s) => ({ label: s.label, server: s })), { title: "Modal Jupyter server" });
    if (!pick) { throw new vscode.CancellationError(); }
    return pick.server;
  }

  /** "Use as notebook kernel": make sure a notebook is open, then open the kernel picker. */
  async useForNotebook(): Promise<void> {
    if (!(await this.ensureRegistered(true))) { return; }
    if (!vscode.window.activeNotebookEditor) {
      const choice = await vscode.window.showInformationMessage(
        "Open the notebook you want to run on Modal, or start a new one.", "New notebook", "Cancel"
      );
      if (choice !== "New notebook") { return; }
      await vscode.commands.executeCommand("ipynb.newUntitledIpynb");
    }
    vscode.window.showInformationMessage(
      "In the kernel picker choose “Select Another Kernel… → M-GPUX · Modal GPUs”, then the session."
    );
    await vscode.commands.executeCommand("notebook.selectKernel");
  }

  dispose(): void {
    for (const d of this.disposables) { try { d.dispose(); } catch { /* ignore */ } }
  }
}
