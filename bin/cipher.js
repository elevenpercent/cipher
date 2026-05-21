const { execSync, spawn } = require("child_process");
const path = require("path");

const PYPI_URL = "git+https://github.com/elevenpercent/cipher.git@master";

try {
  execSync("pip show cipher-agent", { stdio: "ignore", shell: true });
} catch {
  console.log("Installing cipher-agent (Python package)...");
  try {
    execSync(`pip install "${PYPI_URL}"`, { stdio: "inherit", shell: true });
  } catch (e) {
    console.error("Failed to install cipher-agent. Make sure Python 3.10+ and pip are installed.");
    process.exit(1);
  }
}

const cp = spawn("cip", process.argv.slice(2), { stdio: "inherit", shell: true });
cp.on("exit", (code) => process.exit(code));
