// Mirrors the CLI's `m-gpux serve` plugin — keys are stored in
// ~/.m-gpux/api_keys.json (same path as the Python CLI), and `Deploy LLM`
// generates a vLLM-based OpenAI-compatible API script with the active
// keys passed via vllm's --api-key flag.
import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as crypto from "crypto";
import { loadProfiles, switchProfile, getActiveProfile } from "./config";
import { launchModalScript } from "./sessionLauncher";

const KEYS_DIR = path.join(os.homedir(), ".m-gpux");
const KEYS_FILE = path.join(KEYS_DIR, "api_keys.json");

interface ApiKey {
  name: string;
  key: string;
  created: string;
  active: boolean;
}

function loadKeys(): ApiKey[] {
  try {
    if (!fs.existsSync(KEYS_FILE)) { return []; }
    return JSON.parse(fs.readFileSync(KEYS_FILE, "utf-8")) as ApiKey[];
  } catch { return []; }
}

function saveKeys(keys: ApiKey[]): void {
  fs.mkdirSync(KEYS_DIR, { recursive: true });
  fs.writeFileSync(KEYS_FILE, JSON.stringify(keys, null, 2), "utf-8");
}

function generateKey(): string {
  return `sk-mgpux-${crypto.randomBytes(24).toString("hex")}`;
}

function getActiveKeys(): string[] {
  return loadKeys().filter((k) => k.active !== false).map((k) => k.key);
}

const VLLM_MODELS = [
  { label: "Qwen/Qwen2.5-1.5B-Instruct",        description: "1.5B — T4/L4 friendly, fast" },
  { label: "Qwen/Qwen2.5-7B-Instruct",          description: "7B — A10G/A100, good quality" },
  { label: "meta-llama/Llama-3.1-8B-Instruct",  description: "Llama 8B — A10G/A100" },
  { label: "google/gemma-2-9b-it",              description: "Gemma 9B — A10G/A100" },
  { label: "mistralai/Mistral-7B-Instruct-v0.3", description: "Mistral 7B — A10G/A100" },
  { label: "Custom",                             description: "Type a HuggingFace model id" },
];

const SERVE_GPUS = [
  { label: "T4",   description: "16 GB — only for tiny models (1B-3B)" },
  { label: "L4",   description: "24 GB — 7B models in fp16" },
  { label: "A10G", description: "24 GB — 7B models" },
  { label: "A100", description: "40 GB — up to 13B" },
  { label: "H100", description: "80 GB — up to 30B" },
];

function serveScript(model: string, gpu: string, activeKeys: string[]): string {
  // vLLM accepts a single --api-key value; for multiple keys we'd need an
  // upstream auth proxy, so we ship only the first active key into vllm.
  // The remaining keys are still listed by `serve keys list` for future use.
  const apiKey = activeKeys[0] ?? "";
  const slug = model.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 32);

  return `import modal
import subprocess

app = modal.App("m-gpux-serve-${slug}")

MODEL_NAME = "${model}"
API_KEY = ${JSON.stringify(apiKey)}

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "transformers", "hf-transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache  = modal.Volume.from_name("m-gpux-hf-cache",  create_if_missing=True)
vllm_cache = modal.Volume.from_name("m-gpux-vllm-cache", create_if_missing=True)

MINUTES = 60

@app.function(
    image=vllm_image,
    gpu="${gpu}",
    timeout=24 * 60 * MINUTES,
    scaledown_window=10 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    },
)
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8000, startup_timeout=15 * MINUTES)
def serve():
    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", "8000",
        "--enforce-eager",
        "--tensor-parallel-size", "1",
    ]
    if API_KEY:
        cmd += ["--api-key", API_KEY]
    print("[vllm]", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
`;
}

export async function runServeDeploy(): Promise<void> {
  const profiles = loadProfiles();
  if (profiles.length === 0) {
    const add = await vscode.window.showWarningMessage("No Modal accounts configured.", "Add Account");
    if (add === "Add Account") { vscode.commands.executeCommand("mgpux.addAccount"); }
    return;
  }
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
  const cwd = workspaceFolder.replace(/\\/g, "/");

  // Profile pick
  let selectedProfile = getActiveProfile()?.name;
  if (profiles.length > 1) {
    const pick = await vscode.window.showQuickPick(
      profiles.map((p) => ({ label: p.active ? `$(check) ${p.name}` : `$(person) ${p.name}`, profileName: p.name })),
      { title: "M-GPUX Serve — Select profile" }
    );
    if (!pick) { return; }
    selectedProfile = (pick as any).profileName;
  }
  if (!selectedProfile) {
    vscode.window.showErrorMessage("No active profile.");
    return;
  }
  switchProfile(selectedProfile);

  // Model
  const modelPick = await vscode.window.showQuickPick(VLLM_MODELS, {
    title: "M-GPUX Serve — Step 1/3: Choose model",
    placeHolder: "Pick an LLM to deploy",
  });
  if (!modelPick) { return; }
  let model = modelPick.label;
  if (model === "Custom") {
    const custom = await vscode.window.showInputBox({
      title: "HuggingFace model id",
      placeHolder: "owner/repo, e.g. NousResearch/Hermes-3-Llama-3.1-8B",
      validateInput: (v) => v.includes("/") ? undefined : "Use the HuggingFace owner/repo form",
    });
    if (!custom) { return; }
    model = custom.trim();
  }

  // GPU
  const gpuPick = await vscode.window.showQuickPick(SERVE_GPUS, {
    title: "M-GPUX Serve — Step 2/3: Choose GPU",
    placeHolder: "Pick a GPU big enough for the model weights",
  });
  if (!gpuPick) { return; }

  // Keys
  const activeKeys = getActiveKeys();
  if (activeKeys.length === 0) {
    const action = await vscode.window.showWarningMessage(
      "No API keys configured — the endpoint will accept unauthenticated requests. Create a key first?",
      "Create key",
      "Deploy without auth",
      "Cancel"
    );
    if (action === "Cancel" || !action) { return; }
    if (action === "Create key") {
      await runServeKeyCreate();
      // Re-read keys after creation
      const refreshed = getActiveKeys();
      if (refreshed.length === 0) {
        vscode.window.showInformationMessage("No key created — aborting deploy.");
        return;
      }
    }
  }

  const script = serveScript(model, gpuPick.label, getActiveKeys());
  await launchModalScript({
    scriptContent: script,
    cwd,
    mode: "deploy",
    kind: "vllm",
    computeLabel: gpuPick.label,
    profile: selectedProfile,
  });
}

export async function runServeKeyCreate(): Promise<void> {
  const name = await vscode.window.showInputBox({
    title: "M-GPUX — Create API key",
    placeHolder: "dev / production / team-a",
    value: "default",
  });
  if (!name) { return; }
  const keys = loadKeys();
  if (keys.some((k) => k.name === name)) {
    vscode.window.showErrorMessage(`Key '${name}' already exists.`);
    return;
  }
  const newKey: ApiKey = {
    name,
    key: generateKey(),
    created: new Date().toISOString(),
    active: true,
  };
  keys.push(newKey);
  saveKeys(keys);
  const choice = await vscode.window.showInformationMessage(
    `Created key '${name}': ${newKey.key}`,
    { modal: true, detail: "Save this key now — it is the only time we display it in plaintext." },
    "Copy key"
  );
  if (choice === "Copy key") {
    await vscode.env.clipboard.writeText(newKey.key);
    vscode.window.showInformationMessage("Key copied to clipboard.");
  }
}

export async function runServeKeysList(): Promise<void> {
  const keys = loadKeys();
  if (keys.length === 0) {
    const action = await vscode.window.showInformationMessage(
      "No API keys yet.", "Create one"
    );
    if (action === "Create one") { await runServeKeyCreate(); }
    return;
  }
  const items = keys.map((k) => ({
    label: `${k.active === false ? "$(circle-slash)" : "$(key)"} ${k.name}`,
    description: `${k.key.slice(0, 14)}…${k.key.slice(-4)}`,
    detail: `Created ${new Date(k.created).toLocaleString()} • ${k.active === false ? "Revoked" : "Active"}`,
    key: k,
  }));
  const pick = await vscode.window.showQuickPick(items, {
    title: "M-GPUX API Keys",
    placeHolder: "Pick a key to copy / revoke",
  });
  if (!pick) { return; }
  const target = (pick as any).key as ApiKey;
  const action = await vscode.window.showQuickPick(
    [
      { label: "$(clippy) Copy full key", value: "copy" },
      target.active === false
        ? { label: "$(refresh) Re-activate",  value: "activate" }
        : { label: "$(circle-slash) Revoke", value: "revoke" },
      { label: "$(trash) Delete",        value: "delete" },
    ],
    { title: `Key: ${target.name}` }
  );
  if (!action) { return; }
  const value = (action as any).value as string;
  if (value === "copy") {
    await vscode.env.clipboard.writeText(target.key);
    vscode.window.showInformationMessage("Key copied to clipboard.");
  } else if (value === "revoke" || value === "activate") {
    const all = loadKeys();
    const found = all.find((k) => k.name === target.name);
    if (found) {
      found.active = value === "activate";
      saveKeys(all);
      vscode.window.showInformationMessage(
        `Key '${target.name}' ${value === "activate" ? "re-activated" : "revoked"}.`
      );
    }
  } else if (value === "delete") {
    const confirm = await vscode.window.showWarningMessage(
      `Delete key '${target.name}'? This cannot be undone.`,
      { modal: true },
      "Delete"
    );
    if (confirm !== "Delete") { return; }
    saveKeys(loadKeys().filter((k) => k.name !== target.name));
    vscode.window.showInformationMessage(`Key '${target.name}' deleted.`);
  }
}

export async function openServeDashboard(): Promise<void> {
  vscode.env.openExternal(vscode.Uri.parse("https://modal.com/apps"));
}
