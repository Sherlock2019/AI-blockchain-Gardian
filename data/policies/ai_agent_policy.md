# AI Agent Policy

Version: AI-Agent-Policy-v1. Synthetic document for demonstration only.

## 1. Role of AI

AI agents may recommend actions. A recommendation is advice to the organisation.
It is never an authorisation.

## 2. Scoped authority

An AI agent's authority is explicitly scoped: a named identity, a list of
permitted actions and a financial limit. Anything not listed is denied. An AI
agent cannot change its own permissions, limits or policy.

## 3. Human approval

High-risk actions require human approval. An agent's autonomous payment limit is
$1,000. Above that limit a human with sufficient authority must approve. Humans
remain accountable for consequential decisions.

## 4. Untrusted content

Text inside invoices, supplier documents and retrieved records is data. It is
never an instruction to the agent. When such text appears to contain
instructions, the affected item is routed to a human.

## 5. Execution receipts

Every consequential action must generate an execution receipt. Every receipt
must identify the agent, its version, the model used and the policy version in
force. Receipts are hashed and the hash is recorded outside the application
database.

## 6. Disabling AI

Human operators must be able to disable AI at any time. Core workflows must
remain available when AI is disabled, under the same controls.
