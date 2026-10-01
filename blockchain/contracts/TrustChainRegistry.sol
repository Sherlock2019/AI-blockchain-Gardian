// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title TrustChainRegistry
/// @notice Registry of AI agent identities and permissions, plus a write-once
///         log of approval and execution-receipt hashes.
/// @dev Holds only hashes and opaque identifiers. No business data, prompts or
///      personal information is ever written here.
///
///      Two roles, held by different keys:
///        admin    - registers agents and grants permissions.
///        recorder - the application backend; may only append records.
///      The recorder cannot register an agent or grant a permission, so a
///      compromised backend cannot widen its own agent's authority on-chain.
contract TrustChainRegistry {
    struct Agent {
        bool registered;
        bool active;
        bytes32 policyHash;
        uint64 registeredAt;
    }

    struct Approval {
        bytes32 approvalHash;
        bytes32 approverRole;
        uint64 timestamp;
    }

    struct Execution {
        bytes32 agentId;
        bytes32 permission;
        bytes32 policyHash;
        bytes32 approvalHash;
        bytes32 receiptHash;
        uint64 timestamp;
        uint64 blockNumber;
        bool success;
    }

    address public admin;
    mapping(address => bool) public recorders;

    mapping(bytes32 => Agent) private agents;
    mapping(bytes32 => mapping(bytes32 => bool)) private permissions;
    mapping(bytes32 => Approval) private approvals;
    mapping(bytes32 => Execution) private executions;

    event AdminTransferred(address indexed previousAdmin, address indexed newAdmin);
    event RecorderSet(address indexed recorder, bool allowed);
    event AgentRegistered(bytes32 indexed agentId, bytes32 policyHash);
    event AgentDeactivated(bytes32 indexed agentId);
    event AgentPermissionSet(bytes32 indexed agentId, bytes32 indexed permission, bool allowed);
    event ApprovalRecorded(bytes32 indexed actionId, bytes32 approvalHash, bytes32 approverRole);
    event ExecutionRecorded(
        bytes32 indexed actionId,
        bytes32 indexed agentId,
        bytes32 receiptHash,
        bytes32 approvalHash,
        bool success
    );

    error NotAdmin();
    error NotRecorder();
    error ZeroValue();
    error AgentAlreadyRegistered(bytes32 agentId);
    error AgentNotRegistered(bytes32 agentId);
    error AgentNotActive(bytes32 agentId);
    error PermissionNotGranted(bytes32 agentId, bytes32 permission);
    error ApprovalAlreadyRecorded(bytes32 actionId);
    error ApprovalMismatch(bytes32 actionId);
    error ExecutionAlreadyRecorded(bytes32 actionId);

    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin();
        _;
    }

    modifier onlyRecorder() {
        if (!recorders[msg.sender]) revert NotRecorder();
        _;
    }

    constructor() {
        admin = msg.sender;
        emit AdminTransferred(address(0), msg.sender);
    }

    // ------------------------------------------------------------------ admin

    function transferAdmin(address newAdmin) external onlyAdmin {
        if (newAdmin == address(0)) revert ZeroValue();
        emit AdminTransferred(admin, newAdmin);
        admin = newAdmin;
    }

    function setRecorder(address recorder, bool allowed) external onlyAdmin {
        if (recorder == address(0)) revert ZeroValue();
        recorders[recorder] = allowed;
        emit RecorderSet(recorder, allowed);
    }

    function registerAgent(bytes32 agentId, bytes32 policyHash) external onlyAdmin {
        if (agentId == bytes32(0)) revert ZeroValue();
        if (agents[agentId].registered) revert AgentAlreadyRegistered(agentId);
        agents[agentId] = Agent({
            registered: true,
            active: true,
            policyHash: policyHash,
            registeredAt: uint64(block.timestamp)
        });
        emit AgentRegistered(agentId, policyHash);
    }

    /// @notice Permanently deactivates an agent. A replacement gets a new id,
    ///         so the history of the old one stays unambiguous.
    function deactivateAgent(bytes32 agentId) external onlyAdmin {
        if (!agents[agentId].registered) revert AgentNotRegistered(agentId);
        agents[agentId].active = false;
        emit AgentDeactivated(agentId);
    }

    function setAgentPermission(bytes32 agentId, bytes32 permission, bool allowed)
        external
        onlyAdmin
    {
        if (!agents[agentId].registered) revert AgentNotRegistered(agentId);
        permissions[agentId][permission] = allowed;
        emit AgentPermissionSet(agentId, permission, allowed);
    }

    // --------------------------------------------------------------- recorder

    /// @notice Records the hash of a human approval for an action. Write-once.
    function recordApproval(bytes32 actionId, bytes32 approvalHash, bytes32 approverRole)
        external
        onlyRecorder
    {
        if (actionId == bytes32(0) || approvalHash == bytes32(0)) revert ZeroValue();
        if (approvals[actionId].approvalHash != bytes32(0)) revert ApprovalAlreadyRecorded(actionId);
        approvals[actionId] = Approval({
            approvalHash: approvalHash,
            approverRole: approverRole,
            timestamp: uint64(block.timestamp)
        });
        emit ApprovalRecorded(actionId, approvalHash, approverRole);
    }

    /// @notice Records the receipt hash of an executed action. Write-once.
    /// @param agentId   Hash of the acting agent, or zero for a human-initiated action.
    /// @param approvalHash Zero when no human approval was required. When non-zero
    ///        it must equal the approval already recorded for this action.
    function recordExecution(
        bytes32 actionId,
        bytes32 agentId,
        bytes32 permission,
        bytes32 policyHash,
        bytes32 approvalHash,
        bytes32 receiptHash,
        bool success
    ) external onlyRecorder {
        if (actionId == bytes32(0) || receiptHash == bytes32(0)) revert ZeroValue();
        if (executions[actionId].receiptHash != bytes32(0)) {
            revert ExecutionAlreadyRecorded(actionId);
        }
        if (agentId != bytes32(0)) {
            Agent storage agent = agents[agentId];
            if (!agent.registered) revert AgentNotRegistered(agentId);
            if (!agent.active) revert AgentNotActive(agentId);
            if (!permissions[agentId][permission]) revert PermissionNotGranted(agentId, permission);
        }
        if (approvalHash != bytes32(0) && approvals[actionId].approvalHash != approvalHash) {
            revert ApprovalMismatch(actionId);
        }
        executions[actionId] = Execution({
            agentId: agentId,
            permission: permission,
            policyHash: policyHash,
            approvalHash: approvalHash,
            receiptHash: receiptHash,
            timestamp: uint64(block.timestamp),
            blockNumber: uint64(block.number),
            success: success
        });
        emit ExecutionRecorded(actionId, agentId, receiptHash, approvalHash, success);
    }

    // ------------------------------------------------------------------ views

    function getAgent(bytes32 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }

    function isAuthorized(bytes32 agentId, bytes32 permission) external view returns (bool) {
        Agent storage agent = agents[agentId];
        return agent.registered && agent.active && permissions[agentId][permission];
    }

    function getApproval(bytes32 actionId) external view returns (Approval memory) {
        return approvals[actionId];
    }

    function getExecution(bytes32 actionId) external view returns (Execution memory) {
        return executions[actionId];
    }

    /// @notice True when a receipt hash was recorded for the action and equals the one given.
    function verifyExecution(bytes32 actionId, bytes32 receiptHash) external view returns (bool) {
        bytes32 recorded = executions[actionId].receiptHash;
        return recorded != bytes32(0) && recorded == receiptHash;
    }
}
