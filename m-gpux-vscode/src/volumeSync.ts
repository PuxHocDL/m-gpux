// Workspace <-> Modal Volume transfer, driven through the Modal Python SDK.
//
// This replaces the old approach of shelling out to `modal volume put/get`
// once per file, which had two fatal problems:
//
//   1. `runCommand` spawns with `shell: true`, and Node does NOT quote
//      arguments in shell mode. Any local path containing a space (e.g.
//      "C:\Users\Phuc Nguyen\...") was split into two argv entries, so every
//      single `modal volume put` failed. (`modal volume get` happened to
//      survive because os.tmpdir() returns the 8.3 short name with no space.)
//   2. One subprocess per file — a 200-file workspace meant 200 `modal`
//      start-ups, which is why a push/pull took minutes.
//
// Instead we run ONE Python process that uses the SDK directly:
//   - push: `Volume.batch_upload()` uploads every changed file over a single
//     connection.
//   - pull: `Volume.listdir(recursive=True)` gives every remote file with its
//     size + mtime, so we download ONLY files that are missing locally or
//     differ — the user's new notebook comes back without re-downloading the
//     entire seeded workspace.
import * as vscode from "vscode";
import { resolvePython } from "./pythonResolver";

const { execFile } = require("child_process");

/** Files/dirs never transferred in either direction. Matched against each
 *  path segment, so "a/__pycache__/b.pyc" is excluded too. */
export const SYNC_EXCLUDES = [
  ".git",
  ".venv",
  "venv",
  "env",
  "__pycache__",
  "node_modules",
  ".mypy_cache",
  ".pytest_cache",
  ".tox",
  "dist",
  "build",
  ".idea",
  ".vscode",
  ".DS_Store",
  ".ipynb_checkpoints",
  "modal_runner.py",
  ".mgpux-probe.py",
];

export interface VolumeSyncResult {
  pushed: number;
  pulled: number;
  skipped: number;
  removed: number;
  bytes: number;
  errors: string[];
}

// Python driver. Reads a JSON request on argv and prints a JSON result.
// Kept dependency-free beyond the modal SDK itself.
//
// Note on change detection: Modal reports mtime == 0 for volume entries (the
// server does not track it), so timestamps are useless here — we compare file
// SIZE instead, in both directions. Anything missing or size-mismatched moves;
// same-size files are treated as unchanged. That's what makes a repeat sync
// cheap: the user's new notebook transfers, the 200 seeded repo files don't.
const SYNC_SCRIPT = String.raw`
import json, os, sys, io

MAX_FILE_BYTES = 100 * 1024 * 1024

def main():
    req = json.loads(sys.argv[1])
    mode = req["mode"]
    local_dir = req["localDir"]
    excludes = set(req["excludes"])
    only = req.get("paths")        # push: restrict to these relative paths
    deletes = req.get("deletes") or []

    from modal.client import Client
    from modal.volume import Volume, FileEntryType

    client = Client.from_credentials(req["tokenId"], req["tokenSecret"])
    vol = Volume.from_name(
        req["volume"],
        environment_name=req.get("environment") or "main",
        create_if_missing=True,
        client=client,
    )

    def excluded(rel):
        return any(part in excludes for part in rel.replace("\\", "/").split("/") if part)

    def remote_sizes():
        sizes = {}
        for e in vol.listdir("/", recursive=True):
            if e.type == FileEntryType.FILE:
                sizes[e.path.replace("\\", "/").lstrip("/")] = e.size
        return sizes

    pushed = pulled = skipped = removed = total_bytes = 0
    errors = []

    if mode == "push":
        candidates = []
        if only is not None:
            for rel in only:
                rel = rel.replace("\\", "/").lstrip("/")
                if not rel or excluded(rel):
                    continue
                candidates.append((os.path.join(local_dir, *rel.split("/")), rel))
        else:
            for root, dirnames, filenames in os.walk(local_dir):
                dirnames[:] = [d for d in dirnames if d not in excludes]
                for fn in filenames:
                    abs_path = os.path.join(root, fn)
                    rel = os.path.relpath(abs_path, local_dir).replace("\\", "/")
                    if not excluded(rel):
                        candidates.append((abs_path, rel))

        # Only diff against the remote for a full push; an explicit path list
        # comes from the file watcher and is known-dirty already.
        known = remote_sizes() if only is None else {}

        files = []
        for abs_path, rel in candidates:
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                skipped += 1
                continue
            if only is None and known.get(rel) == size:
                skipped += 1
                continue
            files.append((abs_path, rel, size))

        if files:
            # One connection for the whole batch, instead of one modal CLI
            # process per file (what made a 200-file push take minutes).
            with vol.batch_upload(force=True) as batch:
                for abs_path, rel, _ in files:
                    batch.put_file(abs_path, "/" + rel)
            pushed = len(files)
            total_bytes = sum(s for _, _, s in files)

        for rel in deletes:
            rel = rel.replace("\\", "/").lstrip("/")
            if not rel or excluded(rel):
                continue
            try:
                vol.remove_file(rel, recursive=True)
                removed += 1
            except Exception:
                pass  # already gone remotely

    elif mode == "pull":
        try:
            entries = vol.listdir("/", recursive=True)
        except Exception as exc:
            print(json.dumps({"error": "listdir failed: %s" % exc}))
            return

        wanted = []
        for entry in entries:
            if entry.type != FileEntryType.FILE:
                continue
            rel = entry.path.replace("\\", "/").lstrip("/")
            if not rel or excluded(rel):
                continue
            dest = os.path.join(local_dir, *rel.split("/"))
            try:
                if os.path.getsize(dest) == entry.size:
                    skipped += 1
                    continue
            except OSError:
                pass  # missing locally -> download
            wanted.append((rel, dest))

        def fetch(item):
            rel, dest = item
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            buf = io.BytesIO()
            vol.read_file_into_fileobj(rel, buf)
            data = buf.getvalue()
            with open(dest, "wb") as fh:
                fh.write(data)
            return len(data)

        # Each file is a separate round trip, so downloading them one at a time
        # is latency-bound (~1.5s/file => 5 min for a couple of MB). Fan out.
        if wanted:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            workers = min(16, max(4, len(wanted)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fetch, it): it for it in wanted}
                for fut in as_completed(futures):
                    rel = futures[fut][0]
                    try:
                        total_bytes += fut.result()
                        pulled += 1
                    except Exception as exc:
                        errors.append("%s: %s" % (rel, exc))
    else:
        print(json.dumps({"error": "unknown mode %s" % mode}))
        return

    print(json.dumps({
        "pushed": pushed,
        "pulled": pulled,
        "skipped": skipped,
        "removed": removed,
        "bytes": total_bytes,
        "errors": errors[:20],
    }))

try:
    main()
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
`;

export interface VolumeSyncOptions {
  mode: "push" | "pull";
  volumeName: string;
  localDir: string;
  tokenId: string;
  tokenSecret: string;
  output: vscode.OutputChannel;
  /** push only: restrict the upload to these workspace-relative paths (used by
   *  the file watcher). Omit to walk the whole workspace and upload the diff. */
  paths?: string[];
  /** push only: remove these workspace-relative paths from the volume. */
  deletes?: string[];
  /** Abort the transfer after this long. Pulls of a large workspace can be
   *  slow on first run; subsequent runs only move deltas. */
  timeoutMs?: number;
}

/** Run one push or pull against a Modal Volume. Throws on setup failure
 *  (no Python with modal installed) and on a hard error from the driver. */
export async function runVolumeSync(opts: VolumeSyncOptions): Promise<VolumeSyncResult> {
  const py = await resolvePython();
  if (!py || !py.hasModal) {
    throw new Error(
      "No Python interpreter with the `modal` package was found. " +
      "Install it with `pip install modal`, or set `mgpux.pythonPath`."
    );
  }

  const request = JSON.stringify({
    mode: opts.mode,
    volume: opts.volumeName,
    localDir: opts.localDir,
    tokenId: opts.tokenId,
    tokenSecret: opts.tokenSecret,
    environment: "main",
    excludes: SYNC_EXCLUDES,
    ...(opts.paths ? { paths: opts.paths } : {}),
    ...(opts.deletes && opts.deletes.length ? { deletes: opts.deletes } : {}),
  });

  opts.output.appendLine(`[sync] ${opts.mode} → volume ${opts.volumeName} (via Modal SDK)`);

  return new Promise((resolve, reject) => {
    execFile(
      py.cmd,
      [...py.args, "-c", SYNC_SCRIPT, request],
      {
        timeout: opts.timeoutMs ?? 15 * 60_000,
        maxBuffer: 16 * 1024 * 1024,
        env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
      },
      (err: any, stdout: string, stderr: string) => {
        const raw = (stdout || "").trim().split("\n").pop() ?? "";
        let parsed: any;
        try {
          parsed = JSON.parse(raw);
        } catch {
          const detail = (stderr || err?.message || "no output").toString().trim().split("\n").slice(-3).join(" ");
          opts.output.appendLine(`[sync] ${opts.mode} failed: ${detail}`);
          reject(new Error(detail || `sync ${opts.mode} failed`));
          return;
        }
        if (parsed.error) {
          opts.output.appendLine(`[sync] ${opts.mode} failed: ${parsed.error}`);
          reject(new Error(parsed.error));
          return;
        }
        const result: VolumeSyncResult = {
          pushed: parsed.pushed ?? 0,
          pulled: parsed.pulled ?? 0,
          skipped: parsed.skipped ?? 0,
          removed: parsed.removed ?? 0,
          bytes: parsed.bytes ?? 0,
          errors: parsed.errors ?? [],
        };
        const moved = opts.mode === "push" ? result.pushed : result.pulled;
        const arrow = opts.mode === "push" ? "▲" : "▼";
        opts.output.appendLine(
          `[sync] ${arrow} ${opts.mode === "push" ? "pushed" : "pulled"} ${moved} file(s), ` +
          `${result.skipped} unchanged` +
          (result.removed ? `, ${result.removed} removed` : "") +
          `, ${formatBytes(result.bytes)}`
        );
        for (const e of result.errors) {
          opts.output.appendLine(`[sync]   ! ${e}`);
        }
        resolve(result);
      }
    );
  });
}

export function formatBytes(n: number): string {
  if (n < 1024) { return `${n} B`; }
  if (n < 1024 * 1024) { return `${(n / 1024).toFixed(1)} KB`; }
  if (n < 1024 * 1024 * 1024) { return `${(n / 1048576).toFixed(1)} MB`; }
  return `${(n / 1073741824).toFixed(2)} GB`;
}
