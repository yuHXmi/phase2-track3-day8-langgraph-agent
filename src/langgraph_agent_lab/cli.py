"""CLI for the lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml  # type: ignore[import-untyped]

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import Route, Scenario, initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)
    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        final_state = graph.invoke(state, config=run_config)
        metrics.append(
            metric_from_state(
                final_state,
                scenario.expected_route.value,
                scenario.requires_approval,
            )
        )
    report = summarize_metrics(metrics)
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


@app.command("grade-questions")
def grade_questions(
    questions: Annotated[Path, typer.Option("--questions")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run ad-hoc grading questions and write answer/doc-id checks."""
    payload = json.loads(questions.read_text(encoding="utf-8"))
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    results = []
    for item in payload:
        scenario = Scenario(
            id=item["id"],
            query=item["question"],
            expected_route=Route.TOOL,
        )
        state = initial_state(scenario)
        final_state = graph.invoke(
            state,
            config={"configurable": {"thread_id": state["thread_id"]}},
        )
        answer = str(final_state.get("final_answer") or "")
        must_contain_any = item.get("must_contain_any", [])
        must_not_contain = item.get("must_not_contain", [])
        contains_required = any(token in answer for token in must_contain_any)
        forbidden_hits = [token for token in must_not_contain if token in answer]
        actual_top1_doc_id = final_state.get("top1_doc_id")
        expected_top1_doc_id = item.get("expect_top1_doc_id")
        top1_doc_id_match = actual_top1_doc_id == expected_top1_doc_id
        success = contains_required and not forbidden_hits and top1_doc_id_match
        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "actual_route": final_state.get("route"),
                "answer": answer,
                "must_contain_any": must_contain_any,
                "contains_required_answer": contains_required,
                "must_not_contain": must_not_contain,
                "forbidden_hits": forbidden_hits,
                "expected_top1_doc_id": expected_top1_doc_id,
                "actual_top1_doc_id": actual_top1_doc_id,
                "top1_doc_id_match": top1_doc_id_match,
                "success": success,
                "events": [event.get("node") for event in final_state.get("events", [])],
            }
        )
    report = {
        "total_questions": len(results),
        "answer_contains_pass": sum(1 for item in results if item["contains_required_answer"]),
        "top1_doc_pass": sum(1 for item in results if item["top1_doc_id_match"]),
        "overall_pass": sum(1 for item in results if item["success"]),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Wrote grading question results to {output}")


if __name__ == "__main__":
    app()
