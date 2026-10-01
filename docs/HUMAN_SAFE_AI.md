# Human-SAFE AI

A design principle used in this project, stated as engineering requirements.
It is a checklist for building systems where AI helps with consequential work.
It makes no claim about AI in general.

| | Requirement | How this repository meets it | Where it is tested |
|---|---|---|---|
| **S**ustainable | AI produces a durable improvement to a human process, not a dependency that needs constant supervision | The agent does the evidence gathering a reviewer would do by hand and hands over a structured recommendation. The process itself is unchanged | `test_recommendation_carries_evidence_and_policy_references` |
| **A**ugmentative | AI increases human capability; it does not silently replace human judgement | Recommendations are advisory. Above the autonomous limit a person decides, with the evidence and the deterministic checks in front of them | `test_overconfident_model_cannot_skip_approval`, `test_model_doubt_adds_review_but_never_decides` |
| **F**ail-safe | Critical workflows stay available when AI is unavailable or disabled | A kill switch refuses the agent. People file the same request through the same governance, approval and execution path. Unusable model output proposes nothing | `test_manual_workflow_runs_under_the_same_controls_with_ai_off`, `test_unusable_model_output_proposes_nothing` |
| **E**mpowering | Humans keep authority over consequential decisions and can see why something happened | Every decision lists its checks and policy references. Every executed action has a receipt naming the agent, model, policy version, evidence and approver | `test_receipt_has_every_field_in_the_specification`, `test_every_step_is_audited_under_one_correlation_id` |

## What "fail-safe" means precisely here

- **AI off**: agent requests are refused, including ones already waiting for
  approval. Manual requests are unaffected.
- **Model broken** (timeout, malformed output): the agent reports
  `MANUAL_REVIEW` and proposes nothing.
- **Ledger unreachable**: agent-originated execution waits, because the on-chain
  registry cannot confirm the agent. The manual path continues and its receipts
  are anchored later.

In each case the AI-dependent path degrades first and the human path keeps working.

## What it does not claim

- That the AI is right. The system assumes it is sometimes wrong.
- That a human approver always catches an error. Approval puts accountability
  in a named person; it does not guarantee attention.
- That switching AI off is free. The investigation goes back to being manual.
