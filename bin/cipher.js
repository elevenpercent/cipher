#!/usr/bin/env node
"use strict";
const { execFileSync, spawnSync } = require("child_process");
const path = require("path");

// Find a working Python 3.10+ executable
function findPython() {
  const candidates = process.platform === "win32"
    ? ["py", "python", "python3"]
    : ["python3", "python"];
  for (const cmd of candidates) {
    try {
      const r = spawnSync(cmd, ["-c", "import sys;print(sys.version_info>=(3,10))"],
                          { encoding: "utf8", timeout: 5000 });
      if (r.stdout && r.stdout.trim() === "True") return cmd;
    } catch {}
  }
  return null;
}

const PYTHON = findPython();

if (!PYTHON) {
  console.error("ERROR: Python 3.10+ not found.");
  console.error("Install it from: https://python.org/downloads");
  process.exit(1);
}

// Install cipher-agent if not already present
try {
  spawnSync(PYTHON, ["-m", "pip", "show", "cipher-agent"],
            { stdio: "ignore", timeout: 10000 });
} catch {}

// Check import actually works (detects corrupt installs)
const check = spawnSync(PYTHON, ["-c", "import cipher"],
                        { encoding: "utf8", timeout: 5000 });
if (check.status !== 0) {
  console.log("Installing cipher-agent...");
  const install = spawnSync(
    PYTHON,
    ["-m", "pip", "install", "--upgrade", "--no-cache-dir",
     "https://github.com/elevenpercent/cipher/archive/refs/heads/master.zip"],
    { stdio: "inherit", timeout: 120000 }
  );
  if (install.status !== 0) {
    console.error("Install failed. Try: pip install --upgrade git+https://github.com/elevenpercent/cipher.git@master");
    process.exit(1);
  }
}

// On Windows, find the cip.exe directly and exec it — avoids terminal inheritance issues
// that break Textual's full-screen TUI when spawned from Node.js
if (process.platform === "win32") {
  const getSripts = spawnSync(PYTHON,
    ["-c", "import sysconfig; print(sysconfig.get_path('scripts'))"],
    { encoding: "utf8", timeout: 5000 });
  const scriptsDir = getSripts.stdout && getSripts.stdout.trim();
  const cipExe = scriptsDir ? path.join(scriptsDir, "cip.exe") : null;

  try {
    if (cipExe) {
      require("fs").accessSync(cipExe);
      // exec the cip.exe directly — this replaces the Node process entirely on Windows
      const result = spawnSync(cipExe, process.argv.slice(2),
                               { stdio: "inherit", windowsHide: false });
      process.exit(result.status || 0);
    }
  } catch {}

  // Fallback: run via python -m cipher without shell:true
  const result = spawnSync(PYTHON, ["-m", "cipher", ...process.argv.slice(2)],
                           { stdio: "inherit", windowsHide: false });
  process.exit(result.status || 0);
} else {
  // On Unix just exec directly — spawnSync blocks and preserves the TTY
  const result = spawnSync(PYTHON, ["-m", "cipher", ...process.argv.slice(2)],
                           { stdio: "inherit" });
  process.exit(result.status || 0);
}
