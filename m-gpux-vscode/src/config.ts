import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { parse, stringify } from "smol-toml";
import { resolvePython } from "./pythonResolver";

export interface ModalProfile {
  name: string;
  token_id: string;
  token_secret: string;
  active: boolean;
}

const CONFIG_PATH = path.join(os.homedir(), ".modal.toml");
const BUDGETS_PATH = path.join(os.homedir(), ".m-gpux", "budgets.json");
const MONTHLY_CREDIT = 30.0;

export function getConfigPath(): string {
  return CONFIG_PATH;
}

export function loadProfiles(): ModalProfile[] {
  if (!fs.existsSync(CONFIG_PATH)) {
    return [];
  }
  const content = fs.readFileSync(CONFIG_PATH, "utf-8");
  const doc = parse(content) as Record<string, any>;
  const profiles: ModalProfile[] = [];
  for (const name of Object.keys(doc)) {
    const section = doc[name];
    if (typeof section === "object" && section !== null) {
      profiles.push({
        name,
        token_id: section.token_id ?? "",
        token_secret: section.token_secret ?? "",
        active: section.active === true,
      });
    }
  }
  return profiles;
}

export function getActiveProfile(): ModalProfile | undefined {
  const profiles = loadProfiles();
  return profiles.find((p) => p.active) ?? profiles[0];
}

export function addProfile(
  name: string,
  tokenId: string,
  tokenSecret: string
): void {
  const profiles = loadProfiles();
  const isFirst = profiles.length === 0;

  // Read existing raw content to preserve formatting
  let doc: Record<string, any> = {};
  if (fs.existsSync(CONFIG_PATH)) {
    doc = parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as Record<string, any>;
  }

  doc[name] = {
    token_id: tokenId,
    token_secret: tokenSecret,
    ...(isFirst ? { active: true } : {}),
  };

  fs.writeFileSync(CONFIG_PATH, stringify(doc), "utf-8");
}

export function removeProfile(name: string): boolean {
  if (!fs.existsSync(CONFIG_PATH)) {
    return false;
  }
  const doc = parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as Record<
    string,
    any
  >;
  if (!(name in doc)) {
    return false;
  }

  const wasActive = doc[name]?.active === true;
  delete doc[name];

  // If removed profile was active, promote first remaining
  const remaining = Object.keys(doc);
  if (wasActive && remaining.length > 0) {
    doc[remaining[0]].active = true;
  }

  fs.writeFileSync(CONFIG_PATH, stringify(doc), "utf-8");
  return true;
}

export function switchProfile(name: string): boolean {
  if (!fs.existsSync(CONFIG_PATH)) {
    return false;
  }
  const doc = parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as Record<
    string,
    any
  >;
  if (!(name in doc)) {
    return false;
  }

  for (const key of Object.keys(doc)) {
    if (typeof doc[key] === "object" && doc[key] !== null) {
      delete doc[key].active;
    }
  }
  doc[name].active = true;

  fs.writeFileSync(CONFIG_PATH, stringify(doc), "utf-8");
  return true;
}

export interface BillingInfo {
  profileName: string;
  used: number;     // -1 means error
  remaining: number;
  limit: number;
  hasCustomBudget: boolean;
}

function loadBudgets(): Record<string, number> {
  try {
    const raw = JSON.parse(fs.readFileSync(BUDGETS_PATH, "utf-8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) { return {}; }
    const out: Record<string, number> = {};
    for (const [key, value] of Object.entries(raw)) {
      const amount = Number(value);
      if (Number.isFinite(amount) && amount >= 0) { out[key] = amount; }
    }
    return out;
  } catch {
    return {};
  }
}

/**
 * Fetch billing for a single profile using the Modal SDK via Python subprocess.
 * Picks a Python interpreter that actually has `modal` importable — needed
 * because the user's default `python` may be 3.14 (or any version) without
 * the modal SDK installed.
 */
async function fetchUsageForProfile(tokenId: string, tokenSecret: string): Promise<number> {
  const py = await resolvePython();
  if (!py || !py.hasModal) { return -1; }

  return new Promise((resolve) => {
    const { execFile } = require("child_process");
    const script = [
      "import json,sys",
      "from datetime import datetime,timezone",
      "try:",
      "  creds=json.load(sys.stdin)",
      "  from modal.client import Client",
      "  client=Client.from_credentials(creds['tokenId'],creds['tokenSecret'])",
      "  total=None",
      "  try:",
      "    import modal",
      "    ws=getattr(modal,'Workspace',None)",
      "    if ws is not None and hasattr(ws,'from_context'):",
      "      billing=ws.from_context(client=client).billing",
      "      if hasattr(billing,'summary'):",
      "        total=float(billing.summary().metered_cost)",
      "  except Exception:",
      "    total=None",
      "  if total is None:",
      "    from modal.billing import workspace_billing_report",
      "    now=datetime.now(timezone.utc)",
      "    start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)",
      "    reports=workspace_billing_report(start=start,resolution='d',client=client)",
      "    total=sum(float(r.get('cost',0) if isinstance(r,dict) else getattr(r,'cost',0)) for r in reports)",
      "  print(json.dumps({'cost':total}))",
      "except Exception as e:",
      "  print(json.dumps({'error':str(e)}))",
    ].join("\n");
    const child = execFile(py.cmd, [...py.args, "-c", script], {
      timeout: 15000,
    }, (err: any, stdout: string) => {
      if (err) { resolve(-1); return; }
      try {
        const lastLine = stdout.trim().split(/\r?\n/).pop() ?? "";
        const data = JSON.parse(lastLine);
        resolve(data.error ? -1 : (data.cost ?? -1));
      } catch { resolve(-1); }
    });
    child.stdin.on("error", () => { /* process may exit before reading */ });
    child.stdin.end(JSON.stringify({ tokenId, tokenSecret }));
  });
}

/**
 * Look up the public web URL of a deployed function via the Modal SDK.
 *
 * Recent `modal` CLI versions (1.4.x) stopped printing "Created web function
 * ... => https://...modal.run" during `modal deploy` — the deploy output
 * only shows the dashboard "View Deployment" link now, not the tunnel URL.
 * Scraping stdout for it (the old approach) silently never matches, so this
 * falls back to asking the server directly via `modal.Function.from_name(...)
 * .get_web_url()`, the same way `fetchUsageForProfile` above asks for billing.
 * Best-effort: returns undefined on any failure (missing SDK, function not a
 * web endpoint yet, network hiccup, etc.) — callers should treat this as
 * optional and not gate session "ready" status on it.
 */
export async function fetchFunctionWebUrl(
  tokenId: string,
  tokenSecret: string,
  appName: string,
  functionName: string,
  environmentName = "main"
): Promise<string | undefined> {
  const py = await resolvePython();
  if (!py || !py.hasModal) { return undefined; }

  return new Promise((resolve) => {
    const { execFile } = require("child_process");
    const script = [
      "import json,sys",
      "try:",
      "  req=json.load(sys.stdin)",
      "  from modal import Function",
      "  from modal.client import Client",
      "  client = Client.from_credentials(req['tokenId'], req['tokenSecret'])",
      "  fn = Function.from_name(req['appName'], req['functionName'], environment_name=req['environmentName'], client=client)",
      "  print(json.dumps({'url': fn.get_web_url() or ''}))",
      "except Exception as e:",
      "  print(json.dumps({'error': str(e)}))",
    ].join("\n");
    const child = execFile(py.cmd, [...py.args, "-c", script], { timeout: 20000 }, (err: any, stdout: string) => {
      if (err) { resolve(undefined); return; }
      try {
        const lastLine = stdout.trim().split(/\r?\n/).pop() ?? "";
        const data = JSON.parse(lastLine);
        resolve(data.url ? data.url : undefined);
      } catch { resolve(undefined); }
    });
    child.stdin.on("error", () => { /* process may exit before reading */ });
    child.stdin.end(JSON.stringify({ tokenId, tokenSecret, appName, functionName, environmentName }));
  });
}

export async function fetchAllBilling(): Promise<BillingInfo[]> {
  const profiles = loadProfiles();
  const budgets = loadBudgets();
  const results = new Array<BillingInfo>(profiles.length);
  let next = 0;

  // A few profiles in parallel keeps a large multi-account setup responsive
  // without opening one Python/Modal connection for every account at once.
  async function worker(): Promise<void> {
    while (true) {
      const index = next++;
      if (index >= profiles.length) { return; }
      const p = profiles[index];
      const hasCustomBudget = budgets[p.name] !== undefined || budgets["*"] !== undefined;
      const limit = budgets[p.name] ?? budgets["*"] ?? MONTHLY_CREDIT;
      if (!p.token_id || !p.token_secret) {
        results[index] = { profileName: p.name, used: -1, remaining: -1, limit, hasCustomBudget };
        continue;
      }
      const used = await fetchUsageForProfile(p.token_id, p.token_secret);
      results[index] = {
        profileName: p.name,
        used,
        remaining: used < 0 ? -1 : Math.max(limit - used, 0),
        limit,
        hasCustomBudget,
      };
    }
  }
  const concurrency = Math.min(6, profiles.length);
  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  return results;
}
