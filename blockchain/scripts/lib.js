const fs = require("fs");
const path = require("path");
const { ethers } = require("ethers");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DEPLOYMENT_FILE =
  process.env.LEDGER_DEPLOYMENT_FILE ||
  path.join(REPO_ROOT, "blockchain", "deployments", "localhost.json");

/** Same derivation as backend/app/security/hashing.py:id_hash. */
function idHash(kind, identifier) {
  return ethers.sha256(ethers.toUtf8Bytes(`${kind}:${identifier}`));
}

function loadAgents() {
  const dataDir = process.env.DATA_DIR || path.join(REPO_ROOT, "data");
  return JSON.parse(fs.readFileSync(path.join(dataDir, "agents.json"), "utf8"));
}

function loadDeployment() {
  return JSON.parse(fs.readFileSync(DEPLOYMENT_FILE, "utf8"));
}

module.exports = { DEPLOYMENT_FILE, idHash, loadAgents, loadDeployment };
