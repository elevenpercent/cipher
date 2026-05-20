const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const PYPI_URL = "git+https://github.com/elevenpercent/cipher.git@master";
const HOME = process.env.USERPROFILE || process.env.HOME || require("os").homedir();
const CIPHER_DIR = path.join(HOME, ".cipher");
const MARKER = path.join(CIPHER_DIR, ".npm-installed");

if (!fs.existsSync(MARKER)) {
  console.log("Installing cipher-agent (Python package)...");
  try {
    execSync(`pip install "${PYPI_URL}"`, { stdio: "inherit", shell: true });
    fs.mkdirSync(CIPHER_DIR, { recursive: true });
    fs.writeFileSync(MARKER, "");
    console.log("cipher-agent installed successfully.");
  } catch (e) {
    console.error("Failed to install cipher-agent via pip.");
    console.error("Make sure Python 3.10+ and pip are installed and in PATH.");
    process.exit(1);
  }
}
