"""LLM factory helper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DOTENV_LOADED = False


def _load_env_file() -> None:
    """Load simple KEY=VALUE pairs from `.env` without overwriting existing env vars."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    env_path = Path(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def get_llm(model: str | None = None, temperature: float = 0.0) -> Any:
    """Create an LLM client from environment configuration.

    Provider priority:
    1. GEMINI_API_KEY -> ChatGoogleGenerativeAI
    2. OPENAI_API_KEY -> ChatOpenAI
    3. ANTHROPIC_API_KEY -> ChatAnthropic
    """
    _load_env_file()

    if os.getenv("GEMINI_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install -e '.[google]'") from exc
        selected_model = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        return ChatGoogleGenerativeAI(
            model=selected_model,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature,
            timeout=30,
            max_retries=1,
        )

    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install -e '.[openai]'") from exc
        selected_model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        return ChatOpenAI(
            model_name=selected_model,
            temperature=temperature,
            timeout=30,
            max_retries=1,
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install: pip install -e '.[anthropic]'") from exc
        selected_model = model or os.getenv("LLM_MODEL") or "claude-sonnet-4-20250514"
        return ChatAnthropic(
            model=selected_model,
            temperature=temperature,
            timeout=30,
            max_retries=1,
        )

    raise RuntimeError(
        "No LLM API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY "
        "in .env or your shell environment."
    )
