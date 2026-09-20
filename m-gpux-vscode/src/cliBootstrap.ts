import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawn } from "child_process";
import * as vscode from "vscode";
import { resolveBootstrapPython, setManagedPythonPath } from "./pythonResolver";

interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

let extensionContext: vscode.ExtensionContext | undefined;
let extensionVersion = "3.0.0";
let managedRoot = "";
let managedBin = "";
let managedPython = "";
let managedMgpux = "";
let bundledWheel: string | undefined;
let cachedMgpux: string | undefined;
let installPromise: Promise<boolean> | undefined;
let output: vscode.OutputChannel | undefined;

function executableNames(root: string): { bin: string; python: string; mgpux: string } {
  if (os.platform() === "win32") {
    const bin = path.join(root, "Scripts");
    return {
      bin,
      python: path.join(bin, "python.exe"),
      mgpux: path.join(bin, "m-gpux.exe"),
    };
  }
  const bin = path.join(root, "bin");
  return {
    bin,
    python: path.join(bin, "python"),
    mgpux: path.join(bin, "m-gpux"),
  };
}

function pathKey(): string {
  return Object.keys(process.env).find((key) => key.toLowerCase() === "path")
    ?? (os.platform() === "win32" ? "Path" : "PATH");
}

function prependToProcessPath(directory: string): void {
  if (!directory) { return; }
  const key = pathKey();
  const current = process.env[key] ?? "";
  const entries = current.split(path.delimiter).filter(Boolean);
  const normalized = os.platform() === "win32" ? directory.toLowerCase() : directory;
  if (!entries.some((entry) => (os.platform() === "win32" ? entry.toLowerCase() : entry) === normalized)) {
    process.env[key] = [directory, ...entries].join(path.delimiter);
  }
}

function configureResolvedCommand(command: string): void {
  cachedMgpux = command;
  if (path.isAbsolute(command)) {
    prependToProcessPath(path.dirname(command));
  }
  if (managedPython && fs.existsSync(managedPython)) {
    setManagedPythonPath(managedPython);
  }
}

function execCommand(
  command: string,
  args: string[],
  timeoutMs: number,
  onData?: (text: string) => void,
  cwd?: string
): Promise<CommandResult> {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    let timedOut = false;
    const finish = (exitCode: number) => {
      if (settled) { return; }
      settled = true;
      clearTimeout(timer);
      resolve({ stdout, stderr: timedOut ? `${stderr}\nCommand timed out.`.trim() : stderr, exitCode });
    };
    const child = spawn(command, args, {
      shell: false,
      windowsHide: true,
      cwd,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
    });
    const timer = setTimeout(() => {
      timedOut = true;
      try { child.kill(); } catch { /* process already exited */ }
    }, timeoutMs);
    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      onData?.(text);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      onData?.(text);
    });
    child.on("error", (error: Error) => {
      stderr += error.message;
      finish(1);
    });
    child.on("close", (code: number | null) => finish(timedOut ? 1 : (code ?? 1)));
  });
}

function parseVersion(text: string): number[] | undefined {
  const match = text.match(/(?:^|\s)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?(?:\s|$)/);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : undefined;
}

function isCompatibleVersion(text: string): boolean {
  const actual = parseVersion(text);
  const required = parseVersion(extensionVersion);
  if (!actual || !required || actual[0] !== required[0]) { return false; }
  for (let i = 0; i < 3; i++) {
    if (actual[i] > required[i]) { return true; }
    if (actual[i] < required[i]) { return false; }
  }
  return true;
}

async function probeMgpux(command: string): Promise<boolean> {
  if (path.isAbsolute(command) && !fs.existsSync(command)) { return false; }
  const result = await execCommand(command, ["--version"], 5000);
  return result.exitCode === 0 && isCompatibleVersion(`${result.stdout}\n${result.stderr}`);
}

/** Configure the per-extension managed environment. Must run during activate(). */
export function initializeCliBootstrap(context: vscode.ExtensionContext): void {
  extensionContext = context;
  extensionVersion = String(context.extension.packageJSON.version ?? extensionVersion);
  managedRoot = path.join(context.globalStorageUri.fsPath, "cli");
  const names = executableNames(managedRoot);
  managedBin = names.bin;
  managedPython = names.python;
  managedMgpux = names.mgpux;
  const wheelDir = context.asAbsolutePath(path.join("resources", "cli"));
  try {
    const prefix = `m_gpux-${extensionVersion}-`;
    const wheelName = fs.readdirSync(wheelDir).find((name) => name.startsWith(prefix) && name.endsWith(".whl"));
    bundledWheel = wheelName ? path.join(wheelDir, wheelName) : undefined;
  } catch {
    bundledWheel = undefined;
  }
  output = vscode.window.createOutputChannel("M-GPUX: CLI setup", "log");
  context.subscriptions.push(output);

  if (fs.existsSync(managedMgpux)) {
    prependToProcessPath(managedBin);
    setManagedPythonPath(fs.existsSync(managedPython) ? managedPython : undefined);
  }
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
    if (event.affectsConfiguration("mgpux.cliPath")) { cachedMgpux = undefined; }
  }));
}

/** Resolve a compatible CLI from user config, PATH, or extension storage. */
export async function resolveMgpuxCli(forceRefresh = false): Promise<string | undefined> {
  if (!forceRefresh && cachedMgpux && await probeMgpux(cachedMgpux)) { return cachedMgpux; }
  cachedMgpux = undefined;
  const configured = (vscode.workspace.getConfiguration("mgpux").get<string>("cliPath") ?? "").trim();
  const candidates = [configured, "m-gpux", managedMgpux].filter(Boolean);
  const seen = new Set<string>();
  for (const command of candidates) {
    const key = os.platform() === "win32" ? command.toLowerCase() : command;
    if (seen.has(key)) { continue; }
    seen.add(key);
    if (await probeMgpux(command)) {
      configureResolvedCommand(command);
      return command;
    }
  }
  return undefined;
}

export async function hasMgpuxCli(): Promise<boolean> {
  return Boolean(await resolveMgpuxCli());
}

/**
 * Environment for integrated terminals. A managed CLI's bin directory is
 * prepended so both `m-gpux` and its sibling `modal` executable are available.
 */
export function getCliTerminalEnvironment(): Record<string, string> {
  const key = pathKey();
  return { [key]: process.env[key] ?? "" };
}

/** The basename is safe in PowerShell/cmd/bash because its directory is on PATH. */
export function getMgpuxTerminalCommand(): string {
  return cachedMgpux && path.isAbsolute(cachedMgpux) ? path.basename(cachedMgpux) : (cachedMgpux ?? "m-gpux");
}

async function installManagedCli(): Promise<boolean> {
  if (!extensionContext) {
    vscode.window.showErrorMessage("M-GPUX CLI setup is unavailable before the extension finishes activating.");
    return false;
  }
  if (installPromise) { return installPromise; }

  const currentInstall = Promise.resolve(vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "M-GPUX: setting up private CLI...", cancellable: false },
    async (progress) => {
      output?.clear();
      output?.appendLine(`Installing a private m-gpux CLI for extension ${extensionVersion}`);
      const python = await resolveBootstrapPython();
      if (!python) {
        const choice = await vscode.window.showErrorMessage(
          "M-GPUX needs Python 3.10 or newer to create its private CLI environment.",
          "Download Python",
          "Open setup log"
        );
        if (choice === "Download Python") {
          await vscode.env.openExternal(vscode.Uri.parse("https://www.python.org/downloads/"));
        } else if (choice === "Open setup log") {
          output?.show(true);
        }
        return false;
      }

      fs.mkdirSync(path.dirname(managedRoot), { recursive: true });
      progress.report({ message: `Creating Python ${python.version} environment` });
      output?.appendLine(`Python: ${python.cmd} ${python.args.join(" ")} (${python.version})`);
      const stream = (text: string) => output?.append(text);
      if (!fs.existsSync(managedPython)) {
        const created = await execCommand(python.cmd, [...python.args, "-m", "venv", managedRoot], 120_000, stream);
        if (created.exitCode !== 0 || !fs.existsSync(managedPython)) {
          output?.appendLine("\nFailed to create the private virtual environment.");
          output?.show(true);
          vscode.window.showErrorMessage("Could not create the M-GPUX private CLI environment. See 'M-GPUX: CLI setup' output.");
          return false;
        }
      }

      const required = parseVersion(extensionVersion) ?? [3, 0, 0];
      const packageSpec = `m-gpux>=${required.join(".")},<${required[0] + 1}`;
      const installTarget = bundledWheel ?? packageSpec;
      progress.report({ message: bundledWheel ? "Installing bundled CLI" : `Installing ${packageSpec}` });
      output?.appendLine(`\nInstalling ${bundledWheel ? `bundled wheel ${path.basename(bundledWheel)}` : packageSpec}...`);
      let installed = await execCommand(
        managedPython,
        [
          "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade",
          installTarget,
        ],
        600_000,
        stream,
        path.dirname(managedRoot)
      );
      // Reinstall only the bundled project wheel so a repaired/dev VSIX with
      // the same semantic version refreshes its code without redownloading
      // every dependency. The first pass above guarantees dependencies exist.
      if (installed.exitCode === 0 && bundledWheel) {
        installed = await execCommand(
          managedPython,
          [
            "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
            "--force-reinstall", "--no-deps", bundledWheel,
          ],
          120_000,
          stream,
          path.dirname(managedRoot)
        );
      }
      if (installed.exitCode !== 0 || !(await probeMgpux(managedMgpux))) {
        output?.appendLine("\nInstallation did not produce a compatible m-gpux executable.");
        output?.show(true);
        vscode.window.showErrorMessage("M-GPUX CLI installation failed. See 'M-GPUX: CLI setup' output.");
        return false;
      }

      configureResolvedCommand(managedMgpux);
      prependToProcessPath(managedBin);
      output?.appendLine("\nCLI setup complete.");
      vscode.window.showInformationMessage("M-GPUX CLI is ready. The extension will manage it automatically.");
      return true;
    }
  ));
  installPromise = currentInstall;

  try {
    return await currentInstall;
  } finally {
    installPromise = undefined;
  }
}

async function chooseExistingCli(): Promise<boolean> {
  const selected = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
    openLabel: "Use this m-gpux executable",
    title: "Select m-gpux executable",
  });
  const command = selected?.[0]?.fsPath;
  if (!command) { return false; }
  if (!(await probeMgpux(command))) {
    vscode.window.showErrorMessage(`'${command}' is not a compatible m-gpux ${extensionVersion} CLI.`);
    return false;
  }
  await vscode.workspace.getConfiguration("mgpux").update("cliPath", command, vscode.ConfigurationTarget.Global);
  configureResolvedCommand(command);
  return true;
}

/** Explicit command used from the Command Palette. */
export async function setupMgpuxCli(): Promise<boolean> {
  const existing = await resolveMgpuxCli(true);
  if (existing) {
    const choice = await vscode.window.showInformationMessage(
      `M-GPUX CLI is ready: ${existing}`,
      "Update managed CLI",
      "Choose another executable"
    );
    if (choice === "Choose another executable") { return chooseExistingCli(); }
    if (choice !== "Update managed CLI") { return true; }
  }
  return installManagedCli();
}

/** Ensure CLI-only features can continue, with a one-click local bootstrap. */
export async function ensureMgpuxCli(featureName: string): Promise<boolean> {
  if (await resolveMgpuxCli()) { return true; }
  const choice = await vscode.window.showWarningMessage(
    `'${featureName}' needs a compatible m-gpux CLI. The extension can install an isolated copy without changing your system Python.`,
    "Install automatically",
    "Choose existing CLI",
    "Open docs"
  );
  if (choice === "Install automatically") { return installManagedCli(); }
  if (choice === "Choose existing CLI") { return chooseExistingCli(); }
  if (choice === "Open docs") {
    await vscode.env.openExternal(vscode.Uri.parse("https://puxhocdl.github.io/m-gpux/"));
  }
  return false;
}

/** Offer setup once per extension version without blocking activation. */
export async function offerCliSetupIfMissing(): Promise<void> {
  if (!extensionContext || await resolveMgpuxCli()) { return; }
  const key = `mgpux.cliSetupOffered.${extensionVersion}`;
  if (extensionContext.globalState.get<boolean>(key)) { return; }
  await extensionContext.globalState.update(key, true);
  const choice = await vscode.window.showInformationMessage(
    "M-GPUX CLI was not found. Install a private copy to enable Dev Box and Compose commands?",
    "Set up CLI",
    "Later"
  );
  if (choice === "Set up CLI") { await installManagedCli(); }
}
