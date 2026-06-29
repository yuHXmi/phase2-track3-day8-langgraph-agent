# Day 08 Lab Report

## 1. Team / student

- Name: Ha Xuan Huy
- Repo/commit: [yuHXmi/phase2-track3-day8-langgraph-agent](https://github.com/yuHXmi/phase2-track3-day8-langgraph-agent) @ cfa19385a7715d2bf9dd35c6b2e7360d31a4bfbc
- Date: 29/06/2026

## 2. Architecture

The workflow is a LangGraph `StateGraph` for support-ticket orchestration. It normalizes intake,
classifies the ticket, routes to direct answering, tool lookup, clarification, risky-action
approval, or retry handling, and forces every terminal path through `finalize` for auditability.

Primary path:

`START -> intake -> classify -> route-specific nodes -> finalize -> END`

Conditional gates:

- `route_after_classify`: selects `answer`, `tool`, `clarify`, `risky_action`, or `retry`.
- `route_after_evaluate`: sends good tool results to `answer` and bad results to `retry`.
- `route_after_retry`: bounds retries with `attempt < max_attempts`.
- `route_after_approval`: proceeds only after approval, otherwise asks for clarification.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| `query` | overwrite | normalized user request |
| `route` | overwrite | current classification result |
| `risk_level` | overwrite | quick risk marker for risky flows |
| `attempt` | overwrite | retry counter |
| `max_attempts` | overwrite | scenario or config retry bound |
| `evaluation_result` | overwrite | retry-loop gate |
| `final_answer` | overwrite | final user-facing response |
| `pending_question` | overwrite | clarification flow output |
| `proposed_action` | overwrite | risky action submitted for approval |
| `approval` | overwrite | HITL or mock approval decision |
| `messages` | append | lightweight audit trace |
| `tool_results` | append | tool history across retries |
| `errors` | append | retry/dead-letter diagnostics |
| `events` | append | node-level audit events for metrics |

## 4. Scenario results

Summary:

| Metric | Value |
|---|---:|
| Total scenarios | 7 |
| Success rate | 100.00% |
| Average nodes visited | 6.43 |
| Total retries | 3 |
| Total interrupts/approvals | 2 |
| Resume success | no |

Per scenario:

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | yes | 0 | 0 |
| S02_tool | tool | tool | yes | 0 | 0 |
| S03_missing | missing_info | missing_info | yes | 0 | 0 |
| S04_risky | risky | risky | yes | 0 | 1 |
| S05_error | error | error | yes | 2 | 0 |
| S06_delete | risky | risky | yes | 0 | 1 |
| S07_dead_letter | error | error | yes | 1 | 0 |

## 5. Failure analysis

1. Retry or tool failure: tool outputs containing `ERROR` are evaluated as `needs_retry`.
The retry node increments `attempt`, appends an error, and `route_after_retry` prevents
unbounded loops by dead-lettering once `attempt >= max_attempts`.

2. Risky action without approval: refund, delete, email, cancellation, and similar side-effect
requests route through `risky_action -> approval` before any tool/action path. If approval is
rejected, the graph asks for clarification instead of executing the action.

Observed retry diagnostics:

- S05_error: Retry attempt 1 after transient failure; Retry attempt 2 after transient failure
- S07_dead_letter: Retry attempt 1 after transient failure

## 6. Persistence / recovery evidence

The graph accepts a checkpointer from `build_checkpointer()`. Memory checkpointing is used by
default for tests and scenario runs with a per-scenario `thread_id`. SQLite support is implemented
as an extension path via `build_checkpointer("sqlite", database_url)`.

## 7. Extension work

- SQLite checkpointer support for durable runs.
- Mock HITL approval path with optional `LANGGRAPH_INTERRUPT=true` interrupt integration.
- Metrics-backed report generation from `outputs/metrics.json`.

## 8. Improvement plan

With one more day, the first production hardening step would be replacing the mock tool with
typed tool adapters and making `evaluate_node` an LLM-as-judge with explicit evidence scoring.
