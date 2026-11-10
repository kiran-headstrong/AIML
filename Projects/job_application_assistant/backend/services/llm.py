"""
Shared LLM provider helper.

Constructs a configured LangChain chat model from application settings so that
service-layer components (tech stack extraction, resume parsing, matching,
interview prep, cover letters, ...) share a single, consistent way of talking
to the configured LLM provider.

The concrete provider package (e.g. ``langchain_openai``) is imported *lazily*
inside :func:`get_chat_model` so that importing this module never fails when an
optional provider dependency is not installed. This keeps the rest of the
backend importable in environments where only ``langchain``/``langchain-core``
are present.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

from typing import Any

from config import settings


class LLMConfigurationError(RuntimeError):
    """Raised when a chat model cannot be constructed from the settings.

    This typically means the configured provider is unknown or the provider's
    integration package is not installed in the current environment.
    """


def get_chat_model(**overrides: Any) -> Any:
    """Build a LangChain chat model from application settings.

    The model is configured from :data:`config.settings`
    (``llm_provider``, ``llm_model``, ``llm_api_key``, ``llm_api_base``,
    ``llm_temperature``, ``llm_max_tokens``). Any keyword argument passed in
    ``overrides`` takes precedence over the corresponding setting-derived value
    and is forwarded to the underlying chat-model constructor.

    The provider integration package is imported lazily so that merely
    importing this module does not require the optional dependency to be
    installed.

    Args:
        **overrides: Optional constructor overrides (e.g. ``temperature=0``)
            forwarded to the underlying LangChain chat model.

    Returns:
        A LangChain ``BaseChatModel`` instance (typed as ``Any`` to avoid a
        hard import dependency on a specific provider package).

    Raises:
        LLMConfigurationError: If the configured provider is unsupported or the
            provider's integration package is not installed.
    """
    provider = (settings.llm_provider or "openai").strip().lower()

    if provider == "openai":
        return _build_openai_chat_model(overrides)

    raise LLMConfigurationError(
        f"Unsupported LLM provider '{settings.llm_provider}'. "
        "Supported providers: 'openai'."
    )


def _build_openai_chat_model(overrides: dict[str, Any]) -> Any:
    """Construct a ``langchain_openai.ChatOpenAI`` from settings + overrides.

    Imports ``langchain_openai`` lazily and raises a descriptive
    :class:`LLMConfigurationError` if the package is missing.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise LLMConfigurationError(
            "The 'langchain_openai' package is required to use the 'openai' "
            "LLM provider. Install it with 'pip install langchain-openai'."
        ) from exc

    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    if settings.llm_api_base:
        kwargs["base_url"] = settings.llm_api_base

    # Caller-supplied overrides win over setting-derived defaults.
    kwargs.update(overrides)

    return ChatOpenAI(**kwargs)
