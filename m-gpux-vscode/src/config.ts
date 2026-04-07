import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { parse, stringify } from "smol-toml";

export interface ModalProfile {
  name: string;
  token_id: string;
  token_secret: string;
  active: boolean;
}

const CONFIG_PATH = path.join(os.homedir(), ".modal.toml");

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
}

const MONTHLY_CREDIT = 30.0;

/**
 * Fetch billing for a single profile using the Modal SDK via Python subprocess.
 */
function fetchUsageForProfile(tokenId: string, tokenSecret: string): Promise<number> {
  return new Promise((resolve) => {
    const { execFile } = require("child_process");
    const script = [
      "import json,sys",
      "from datetime import datetime,timezone",
      "try:",
      "  from modal.billing import workspace_billing_report",
      "  from modal.client import Client",
      "  now=datetime.now(timezone.utc)",
      "  start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)",
      "  client=Client.from_credentials(sys.argv[1],sys.argv[2])",
      "  reports=workspace_billing_report(start=start,resolution='d',client=client)",
      "  total=sum(float(r.get('cost',0)) for r in reports)",
      "  print(json.dumps({'cost':total}))",
      "except Exception as e:",
      "  print(json.dumps({'error':str(e)}))",
    ].join("\n");
    execFile("python", ["-c", script, tokenId, tokenSecret], {
      timeout: 15000,
    }, (err: any, stdout: string) => {
      if (err) { resolve(-1); return; }
      try {
        const data = JSON.parse(stdout.trim());
        resolve(data.error ? -1 : (data.cost ?? -1));
      } catch { resolve(-1); }
    });
  });
}

export async function fetchAllBilling(): Promise<BillingInfo[]> {
  const profiles = loadProfiles();
  const results: BillingInfo[] = [];
  for (const p of profiles) {
    if (!p.token_id || !p.token_secret) {
      results.push({ profileName: p.name, used: -1, remaining: -1 });
      continue;
    }
    const used = await fetchUsageForProfile(p.token_id, p.token_secret);
    if (used < 0) {
      results.push({ profileName: p.name, used: -1, remaining: -1 });
    } else {
      results.push({
        profileName: p.name,
        used,
        remaining: Math.max(MONTHLY_CREDIT - used, 0),
      });
    }
  }
  return results;
}
