const { expect } = require("chai");
const { ethers } = require("hardhat");
const { idHash } = require("../scripts/lib");

const ZERO = ethers.ZeroHash;
const AGENT = idHash("agent", "AGENT-TREASURY-001");
const POLICY = idHash("policy", "AI-Agent-Policy-v1");
const PROPOSE = idHash("permission", "PROPOSE_PAYMENT");
const CHANGE_BANK = idHash("permission", "CHANGE_SUPPLIER_BANK_ACCOUNT");
const ROLE = idHash("role", "FINANCE_MANAGER");
const hash = (label) => ethers.sha256(ethers.toUtf8Bytes(label));

describe("TrustChainRegistry", function () {
  let registry, admin, recorder, outsider;

  beforeEach(async function () {
    [admin, recorder, outsider] = await ethers.getSigners();
    registry = await ethers.deployContract("TrustChainRegistry", admin);
    await registry.setRecorder(recorder.address, true);
  });

  async function registerWithPermission() {
    await registry.registerAgent(AGENT, POLICY);
    await registry.setAgentPermission(AGENT, PROPOSE, true);
  }

  const record = (signer, actionId, overrides = {}) => {
    const args = {
      agentId: AGENT,
      permission: PROPOSE,
      policyHash: POLICY,
      approvalHash: ZERO,
      receiptHash: hash("receipt"),
      success: true,
      ...overrides,
    };
    return registry
      .connect(signer)
      .recordExecution(
        actionId,
        args.agentId,
        args.permission,
        args.policyHash,
        args.approvalHash,
        args.receiptHash,
        args.success
      );
  };

  describe("agent registration", function () {
    it("registers an agent as active and emits AgentRegistered", async function () {
      await expect(registry.registerAgent(AGENT, POLICY))
        .to.emit(registry, "AgentRegistered")
        .withArgs(AGENT, POLICY);
      const agent = await registry.getAgent(AGENT);
      expect(agent.registered).to.equal(true);
      expect(agent.active).to.equal(true);
      expect(agent.policyHash).to.equal(POLICY);
    });

    it("rejects a second registration of the same agent", async function () {
      await registry.registerAgent(AGENT, POLICY);
      await expect(registry.registerAgent(AGENT, POLICY))
        .to.be.revertedWithCustomError(registry, "AgentAlreadyRegistered")
        .withArgs(AGENT);
    });

    it("rejects the zero id", async function () {
      await expect(registry.registerAgent(ZERO, POLICY)).to.be.revertedWithCustomError(
        registry,
        "ZeroValue"
      );
    });

    it("only the admin may register", async function () {
      await expect(
        registry.connect(recorder).registerAgent(AGENT, POLICY)
      ).to.be.revertedWithCustomError(registry, "NotAdmin");
    });
  });

  describe("permissions", function () {
    it("an agent has no permission until one is granted", async function () {
      await registry.registerAgent(AGENT, POLICY);
      expect(await registry.isAuthorized(AGENT, PROPOSE)).to.equal(false);
      await expect(registry.setAgentPermission(AGENT, PROPOSE, true))
        .to.emit(registry, "AgentPermissionSet")
        .withArgs(AGENT, PROPOSE, true);
      expect(await registry.isAuthorized(AGENT, PROPOSE)).to.equal(true);
      expect(await registry.isAuthorized(AGENT, CHANGE_BANK)).to.equal(false);
    });

    it("a permission can be revoked", async function () {
      await registerWithPermission();
      await registry.setAgentPermission(AGENT, PROPOSE, false);
      expect(await registry.isAuthorized(AGENT, PROPOSE)).to.equal(false);
    });

    it("the recorder cannot grant its agent a permission", async function () {
      await registry.registerAgent(AGENT, POLICY);
      await expect(
        registry.connect(recorder).setAgentPermission(AGENT, CHANGE_BANK, true)
      ).to.be.revertedWithCustomError(registry, "NotAdmin");
    });

    it("cannot set a permission for an unregistered agent", async function () {
      await expect(
        registry.setAgentPermission(AGENT, PROPOSE, true)
      ).to.be.revertedWithCustomError(registry, "AgentNotRegistered");
    });
  });

  describe("deactivation", function () {
    it("deactivates an agent and emits AgentDeactivated", async function () {
      await registerWithPermission();
      await expect(registry.deactivateAgent(AGENT))
        .to.emit(registry, "AgentDeactivated")
        .withArgs(AGENT);
      expect(await registry.isAuthorized(AGENT, PROPOSE)).to.equal(false);
      expect((await registry.getAgent(AGENT)).active).to.equal(false);
    });

    it("refuses executions from a deactivated agent", async function () {
      await registerWithPermission();
      await registry.deactivateAgent(AGENT);
      await expect(record(recorder, hash("action")))
        .to.be.revertedWithCustomError(registry, "AgentNotActive")
        .withArgs(AGENT);
    });

    it("only the admin may deactivate", async function () {
      await registry.registerAgent(AGENT, POLICY);
      await expect(
        registry.connect(outsider).deactivateAgent(AGENT)
      ).to.be.revertedWithCustomError(registry, "NotAdmin");
    });
  });

  describe("approval recording", function () {
    it("records an approval hash once", async function () {
      const action = hash("action");
      await expect(registry.connect(recorder).recordApproval(action, hash("approval"), ROLE))
        .to.emit(registry, "ApprovalRecorded")
        .withArgs(action, hash("approval"), ROLE);
      expect((await registry.getApproval(action)).approvalHash).to.equal(hash("approval"));
      await expect(
        registry.connect(recorder).recordApproval(action, hash("other"), ROLE)
      ).to.be.revertedWithCustomError(registry, "ApprovalAlreadyRecorded");
    });

    it("only a recorder may record approvals", async function () {
      await expect(
        registry.connect(outsider).recordApproval(hash("action"), hash("approval"), ROLE)
      ).to.be.revertedWithCustomError(registry, "NotRecorder");
    });
  });

  describe("execution recording", function () {
    beforeEach(registerWithPermission);

    it("records an execution and emits ExecutionRecorded", async function () {
      const action = hash("action");
      await expect(record(recorder, action))
        .to.emit(registry, "ExecutionRecorded")
        .withArgs(action, AGENT, hash("receipt"), ZERO, true);
      const execution = await registry.getExecution(action);
      expect(execution.receiptHash).to.equal(hash("receipt"));
      expect(execution.agentId).to.equal(AGENT);
      expect(execution.blockNumber).to.be.greaterThan(0n);
    });

    it("is write-once per action", async function () {
      const action = hash("action");
      await record(recorder, action);
      await expect(record(recorder, action, { receiptHash: hash("rewritten") }))
        .to.be.revertedWithCustomError(registry, "ExecutionAlreadyRecorded")
        .withArgs(action);
      expect((await registry.getExecution(action)).receiptHash).to.equal(hash("receipt"));
    });

    it("refuses an unregistered agent", async function () {
      const stranger = idHash("agent", "AGENT-UNKNOWN");
      await expect(record(recorder, hash("action"), { agentId: stranger }))
        .to.be.revertedWithCustomError(registry, "AgentNotRegistered")
        .withArgs(stranger);
    });

    it("refuses a permission the agent was never granted", async function () {
      await expect(record(recorder, hash("action"), { permission: CHANGE_BANK }))
        .to.be.revertedWithCustomError(registry, "PermissionNotGranted")
        .withArgs(AGENT, CHANGE_BANK);
    });

    it("requires the approval hash to match the recorded approval", async function () {
      const action = hash("action");
      await expect(
        record(recorder, action, { approvalHash: hash("approval") })
      ).to.be.revertedWithCustomError(registry, "ApprovalMismatch");

      await registry.connect(recorder).recordApproval(action, hash("approval"), ROLE);
      await expect(
        record(recorder, action, { approvalHash: hash("forged") })
      ).to.be.revertedWithCustomError(registry, "ApprovalMismatch");
      await expect(record(recorder, action, { approvalHash: hash("approval") })).to.emit(
        registry,
        "ExecutionRecorded"
      );
    });

    it("accepts a human-initiated action with a zero agent id", async function () {
      await expect(record(recorder, hash("manual"), { agentId: ZERO })).to.emit(
        registry,
        "ExecutionRecorded"
      );
    });

    it("only a recorder may record executions", async function () {
      await expect(record(outsider, hash("action"))).to.be.revertedWithCustomError(
        registry,
        "NotRecorder"
      );
      await expect(record(admin, hash("action"))).to.be.revertedWithCustomError(
        registry,
        "NotRecorder"
      );
    });

    it("a removed recorder can no longer write", async function () {
      await registry.setRecorder(recorder.address, false);
      await expect(record(recorder, hash("action"))).to.be.revertedWithCustomError(
        registry,
        "NotRecorder"
      );
    });
  });

  describe("verification", function () {
    beforeEach(registerWithPermission);

    it("verifies a matching receipt hash and rejects a different one", async function () {
      const action = hash("action");
      await record(recorder, action);
      expect(await registry.verifyExecution(action, hash("receipt"))).to.equal(true);
      expect(await registry.verifyExecution(action, hash("tampered"))).to.equal(false);
    });

    it("returns false for an action that was never recorded", async function () {
      expect(await registry.verifyExecution(hash("missing"), hash("receipt"))).to.equal(false);
      expect(await registry.verifyExecution(hash("missing"), ZERO)).to.equal(false);
    });
  });

  describe("admin transfer", function () {
    it("hands control to the new admin only", async function () {
      await registry.transferAdmin(outsider.address);
      await expect(registry.registerAgent(AGENT, POLICY)).to.be.revertedWithCustomError(
        registry,
        "NotAdmin"
      );
      await expect(registry.connect(outsider).registerAgent(AGENT, POLICY)).to.emit(
        registry,
        "AgentRegistered"
      );
    });
  });
});
