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
