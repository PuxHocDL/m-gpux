const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const extensionRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(extensionRoot, "..");
const outputDir = path.join(extensionRoot, "resources", "cli");
const extensionVersion = require(path.join(extensionRoot, "package.json")).version;
const expectedPrefix = `m_gpux-${extensionVersion}-`;
fs.mkdirSync(outputDir, { recursive: true });

for (const name of fs.readdirSync(outputDir)) {
  if (/^m_gpux-.*\.whl$/i.test(name)) {
    fs.unlinkSync(path.join(outputDir, name));
  }
}

const configured = process.env.MGPUX_BUILD_PYTHON;
const candidates = [
  ...(configured ? [{ cmd: configured, args: [] }] : []),
  ...(process.platform === "win32"
    ? [
        { cmd: path.join(projectRoot, ".venv", "Scripts", "python.exe"), args: [] },
        { cmd: "py", args: ["-3.13"] },
        { cmd: "py", args: ["-3.12"] },
        { cmd: "py", args: ["-3.11"] },
        { cmd: "py", args: ["-3.10"] },
        { cmd: "python", args: [] },
      ]
    : [
        { cmd: path.join(projectRoot, ".venv", "bin", "python"), args: [] },
        { cmd: "python3", args: [] },
        { cmd: "python", args: [] },
      ]),
];

let lastError = "No Python interpreter was usable.";
for (const candidate of candidates) {
  const version = spawnSync(candidate.cmd, [...candidate.args, "--version"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (version.status !== 0) { continue; }
  process.stdout.write(`Building bundled CLI wheel with ${candidate.cmd} ${candidate.args.join(" ")}\n`);
  const built = spawnSync(
    candidate.cmd,
    [...candidate.args, "-m", "pip", "wheel", "--disable-pip-version-check", "--no-deps", "--wheel-dir", outputDir, projectRoot],
    { cwd: projectRoot, encoding: "utf8", windowsHide: true }
  );
  if (built.stdout) { process.stdout.write(built.stdout); }
  if (built.stderr) { process.stderr.write(built.stderr); }
  if (built.status === 0 && fs.readdirSync(outputDir).some((name) => name.startsWith(expectedPrefix) && name.endsWith(".whl"))) {
    process.stdout.write("Bundled CLI wheel is ready.\n");
    process.exit(0);
  }
  if (built.status === 0) {
    lastError = `CLI and extension versions differ: expected a wheel starting with ${expectedPrefix}`;
    continue;
  }
  lastError = `Wheel build failed with ${candidate.cmd} (exit ${built.status ?? "unknown"}).`;
}

throw new Error(lastError);
