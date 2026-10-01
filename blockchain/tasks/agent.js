/**
 * Admin operations on the registry, run with the admin account.
 *
 *   npx hardhat agent:status     --agent AGENT-TREASURY-001 --network localhost
 *   npx hardhat agent:deactivate --agent AGENT-TREASURY-001 --network localhost
 *   npx hardhat agent:permission --agent AGENT-TREASURY-001 --permission PROPOSE_PAYMENT --allowed false --network localhost
 *
 * These are deliberately not reachable from the application.
 */
const { task } = require("hardhat/config");
const { idHash, loadDeployment } = require("../scripts/lib");

async function registry(hre) {
  const deployment = loadDeployment();
  const [admin] = await hre.ethers.getSigners();
  return hre.ethers.getContractAt("TrustChainRegistry", deployment.address, admin);
}

task("agent:status", "Shows an agent's on-chain registration")
  .addParam("agent", "Agent id, e.g. AGENT-TREASURY-001")
  .setAction(async ({ agent }, hre) => {
    const contract = await registry(hre);
    const record = await contract.getAgent(idHash("agent", agent));
    console.log({ agent, registered: record.registered, active: record.active });
  });

task("agent:deactivate", "Permanently deactivates an agent on-chain")
  .addParam("agent", "Agent id")
  .setAction(async ({ agent }, hre) => {
    const contract = await registry(hre);
    await (await contract.deactivateAgent(idHash("agent", agent))).wait();
    console.log(`${agent} deactivated`);
  });

task("agent:permission", "Grants or revokes an on-chain permission")
  .addParam("agent", "Agent id")
  .addParam("permission", "Permission name, e.g. PROPOSE_PAYMENT")
  .addParam("allowed", "true or false")
  .setAction(async ({ agent, permission, allowed }, hre) => {
    const contract = await registry(hre);
    const grant = allowed === "true";
    await (
      await contract.setAgentPermission(idHash("agent", agent), idHash("permission", permission), grant)
    ).wait();
    console.log(`${agent} ${permission} -> ${grant}`);
  });
