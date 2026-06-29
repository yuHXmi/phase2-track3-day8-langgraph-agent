"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from .state import AgentState, ApprovalDecision, Route, make_event


class Classification(BaseModel):
    route: Literal["simple", "tool", "missing_info", "risky", "error"] = Field(
        description="Best route for the support ticket."
    )
    risk_level: Literal["low", "high"] = Field(description="high only for risky side effects")


def _classify_without_llm(query: str) -> Classification:
    """Local fallback for development when no API key is configured."""
    text = query.lower()
    risky_terms = ("refund", "delete", "send", "email", "cancel", "chargeback", "close account")
    tool_terms = ("lookup", "look up", "order", "status", "tracking", "search", "find")
    missing_terms = ("fix it", "help me", "it does not work", "can't do it", "can you fix")
    error_terms = ("timeout", "failure", "crash", "unavailable", "cannot recover", "system error")
    if any(term in text for term in risky_terms):
        return Classification(route="risky", risk_level="high")
    if any(term in text for term in tool_terms):
        return Classification(route="tool", risk_level="low")
    if any(term in text for term in missing_terms) or len(text.split()) <= 4:
        return Classification(route="missing_info", risk_level="low")
    if any(term in text for term in error_terms):
        return Classification(route="error", risk_level="low")
    return Classification(route="simple", risk_level="low")


def _normalize_classification(query: str, result: Classification) -> Classification:
    text = query.lower()
    error_terms = (
        "timeout",
        "failure",
        "crash",
        "unavailable",
        "cannot recover",
        "system error",
    )
    risky_actions = (
        "refund",
        "delete",
        "send",
        "email",
        "cancel",
        "chargeback",
        "close account",
        "remove account",
    )
    asks_for_instructions = (
        text.startswith("how do i")
        or text.startswith("how can i")
        or text.startswith("what is")
        or text.startswith("where can i")
    )
    if result.route == "risky" and asks_for_instructions and not any(
        action in text for action in risky_actions
    ):
        return Classification(route="simple", risk_level="low")
    if result.route in {"missing_info", "simple"} and any(term in text for term in error_terms):
        return Classification(route="error", risk_level="low")
    return result


def _content_text(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return " ".join(str(item) for item in content)
    return str(content)


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── Workflow nodes ─────────────────────────────────────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM.

    *** MUST use a real LLM call — keyword-only heuristics will lose points. ***

    Use .with_structured_output() or equivalent to get reliable enum classification.
    The LLM should classify into one of: simple, tool, missing_info, risky, error.

    Hints:
    - See llm.py for the get_llm() helper
    - Use Pydantic model or TypedDict with .with_structured_output()
    - Set risk_level to "high" for risky routes, "low" otherwise
    - Priority guide: risky > tool > missing_info > error > simple

    Return: {"route": str, "risk_level": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    prompt = (
        "Classify this support ticket into exactly one route.\n"
        "Routes:\n"
        "- risky: side-effect actions such as refunds, deletions, emails, cancellations.\n"
        "  Only use risky when the agent is being asked to perform the action.\n"
        "  How-to questions about user self-service are simple, even for password resets.\n"
        "- tool: information lookup such as order status, tracking, or account search.\n"
        "- missing_info: vague or incomplete request lacking actionable details.\n"
        "- error: system failures such as timeout, crash, service unavailable.\n"
        "- simple: general support question answerable without tools.\n"
        "Priority: risky > tool > missing_info > error > simple.\n"
        f"Ticket: {query}"
    )
    used_llm = True
    try:
        from .llm import get_llm

        result = get_llm(temperature=0.0).with_structured_output(Classification).invoke(prompt)
    except Exception as exc:
        used_llm = False
        result = _classify_without_llm(query)
        fallback_reason = exc.__class__.__name__
    else:
        fallback_reason = ""

    result = _normalize_classification(query, result)
    route = result.route
    risk_level = "high" if route == Route.RISKY.value else result.risk_level
    return {
        "route": route,
        "risk_level": risk_level,
        "events": [
            make_event(
                "classify",
                "completed",
                f"classified as {route}",
                used_llm=used_llm,
                fallback_reason=fallback_reason,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.

    Requirements:
    - Read current attempt count from state
    - If route is "error" and attempt < 2: return error result (string containing "ERROR")
    - Otherwise: return a mock success result string
    - Append result to tool_results list

    Return: {"tool_results": [result_string], "events": [make_event(...)]}
    """
    attempt = int(state.get("attempt", 0) or 0)
    route = state.get("route", "")
    query = state.get("query", "")
    if route == Route.ERROR.value and attempt < 2:
        result = f"ERROR transient failure on attempt {attempt + 1}: backend timeout"
        event_type = "failed"
    else:
        result = f"SUCCESS mock tool result for query '{query}'"
        if state.get("proposed_action"):
            result = f"{result}; approved action: {state['proposed_action']}"
        event_type = "completed"
    return {
        "tool_results": [result],
        "events": [make_event("tool", event_type, result, attempt=attempt)],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Check whether the latest tool result is satisfactory or needs retry.

    SHOULD use LLM-as-judge for bonus points. Heuristic (e.g., check for "ERROR" substring)
    is acceptable for base score.

    Requirements:
    - Read the latest entry from tool_results
    - Set evaluation_result to "needs_retry" or "success"
    - This field drives route_after_evaluate conditional edge

    Note: You may need to add 'evaluation_result' to AgentState if not present.

    Return: {"evaluation_result": str, "events": [make_event(...)]}
    """
    latest = (state.get("tool_results") or [""])[-1]
    evaluation_result = "needs_retry" if "ERROR" in latest.upper() else "success"
    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", evaluation_result, latest_result=latest)],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***

    The LLM should generate a helpful response grounded in available context:
    - tool_results (if any)
    - approval decision (if risky route)
    - original query

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    context = "\n".join(state.get("tool_results") or []) or "No tool results were needed."
    approval = state.get("approval")
    prompt = (
        "You are a concise support agent. Answer the user using only the provided context.\n"
        f"User query: {query}\n"
        f"Route: {state.get('route', '')}\n"
        f"Tool/context results:\n{context}\n"
        f"Approval decision: {approval}\n"
        "Give a helpful final response. Do not invent unavailable facts."
    )
    used_llm = True
    try:
        from .llm import get_llm

        answer = _content_text(get_llm(temperature=0.2).invoke(prompt)).strip()
    except Exception as exc:
        used_llm = False
        answer = (
            f"I handled your request: {query}. "
            f"Available context: {context}. "
            "Please follow up if you need a specific account detail."
        )
        fallback_reason = exc.__class__.__name__
    else:
        fallback_reason = ""
    return {
        "final_answer": answer,
        "events": [
            make_event(
                "answer",
                "completed",
                "final answer generated",
                used_llm=used_llm,
                fallback_reason=fallback_reason,
            )
        ],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generate a specific clarification question based on the vague/incomplete query.

    Note: You may need to add 'pending_question' to AgentState if not present.

    Return: {"pending_question": str, "final_answer": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    question = (
        "Could you share the specific account, order, error message, or action you want help with?"
    )
    if query:
        question = f"I need one more detail to help with '{query}': {question}"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Describe the proposed action and why it requires approval.

    Note: You may need to add 'proposed_action' to AgentState if not present.

    Return: {"proposed_action": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    proposed_action = f"Review and approve requested side-effect action: {query}"
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.

    Return approval decision and an audit event.
    """
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        payload = interrupt(
            {
                "proposed_action": state.get("proposed_action"),
                "query": state.get("query"),
            }
        )
        approved = bool(payload.get("approved", False)) if isinstance(payload, dict) else False
        comment = str(payload.get("comment", "")) if isinstance(payload, dict) else ""
        reviewer = (
            str(payload.get("reviewer", "human-reviewer"))
            if isinstance(payload, dict)
            else "human-reviewer"
        )
    else:
        approved = True
        comment = "Mock approval for lab automation."
        reviewer = "mock-reviewer"
    approval = ApprovalDecision(approved=approved, reviewer=reviewer, comment=comment).model_dump()
    return {
        "approval": approval,
        "events": [make_event("approval", "completed", "approval recorded", approved=approved)],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.

    Requirements:
    - Read current attempt from state, increment by 1
    - Add an error message to errors list
    - Return updated attempt count

    Return: {"attempt": int, "errors": [str], "events": [make_event(...)]}
    """
    attempt = int(state.get("attempt", 0) or 0) + 1
    message = f"Retry attempt {attempt} after transient failure"
    return {
        "attempt": attempt,
        "errors": [message],
        "events": [make_event("retry", "completed", message, attempt=attempt)],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded.

    This is the third layer: retry → fallback → dead letter.
    Log the failure and set a final_answer explaining that the request could not be completed.

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    answer = (
        "The request could not be completed after the allowed retry attempts. "
        "It has been moved to the dead-letter path for manual investigation."
    )
    return {
        "route": Route.ERROR.value,
        "final_answer": answer,
        "events": [make_event("dead_letter", "completed", "max retries exhausted")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END.

    Return: {"events": [make_event("finalize", "completed", "workflow finished")]}
    """
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
