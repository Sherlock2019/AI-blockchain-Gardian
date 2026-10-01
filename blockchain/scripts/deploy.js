/**
 * Deploys TrustChainRegistry to the local Hardhat node and registers the agents
 * from data/agents.json.
 *
 * Account 0 is the admin: it deploys, registers agents and grants permissions.
 * Account 1 is the recorder: the only account the backend uses. The backend
 * never holds the admin account, so it cannot change what its agent may do.
 */
const fs = require("fs");
const path = require("path");
const hre = require("hardhat");
const { DEPLOYMENT_FILE, idHash, loadAgents } = require("./lib");

async function main() {
  const [admin, recorder] = await hre.ethers.getSigners();
  const registry = await hre.ethers.deployContract("TrustChainRegistry", admin);
  await registry.waitForDeployment();
  const address = await registry.getAddress();

  await (await registry.setRecorder(recorder.address, true)).wait();

  for (const agent of loadAgents()) {
    const agentId = idHash("agent", agent.id);
    await (await registry.registerAgent(agentId, idHash("policy", agent.policy))).wait();
    for (const permission of agent.allowed_actions) {
      await (await registry.setAgentPermission(agentId, idHash("permission", permission), true)).wait();
    }
    console.log(`registered ${agent.id} with ${agent.allowed_actions.length} permissions`);
  }

  const artifact = await hre.artifacts.readArtifact("TrustChainRegistry");
  const network = await hre.ethers.provider.getNetwork();
  const deployment = {
    contract: "TrustChainRegistry",
    address,
    chainId: Number(network.chainId),
    admin: admin.address,
    recorder: recorder.address,
    deployedAt: new Date().toISOString(),
    abi: artifact.abi,
  };
  fs.mkdirSync(path.dirname(DEPLOYMENT_FILE), { recursive: true });
  fs.writeFileSync(DEPLOYMENT_FILE, JSON.stringify(deployment, null, 2));
  console.log(`TrustChainRegistry deployed at ${address}`);
  console.log(`deployment written to ${DEPLOYMENT_FILE}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
