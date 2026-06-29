"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    Memory is the default checkpointer. SQLite is implemented as an extension path.
    For SQLite, install `langgraph-checkpoint-sqlite` or the project `sqlite` extra.
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError("Install SQLite support with: pip install -e '.[sqlite]'") from exc
        db_path = database_url or "outputs/checkpoints.sqlite"
        if db_path.startswith("sqlite:///"):
            db_path = db_path.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn=conn)
    if kind == "postgres":
        raise RuntimeError(
            "Postgres checkpointer is an optional extension and is not implemented."
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
