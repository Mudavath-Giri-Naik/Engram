"""LLM reasoning via litellm — provider-swappable, strict-JSON output.

The reasoning LLM is the ONLY paid external dependency. We use litellm so the
provider (anthropic | openai | gemini) is chosen entirely via env. We parse the
response robustly (strip code fences; retry once on parse failure) and NEVER
fabricate a ReasoningResult — if parsing fails after a retry, we raise.
"""

from __future__ import annotations

import json
import re

from engram.config import get_settings
from engram.domain.models import FaultQuery, ReasoningResult, RetrievedIncident
from engram.reasoning.prompts import SYSTEM_PROMPT, build_user_prompt

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ReasoningError(RuntimeError):
    pass


def _model_string() -> str:
    """litellm model string, e.g. 'anthropic/claude-3-5-sonnet-latest'."""
    s = get_settings()
    provider = s.llm_provider.strip().lower()
    model = s.llm_model.strip()
    if not provider or not model:
        raise ReasoningError(
            "LLM not configured. Set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in .env.local."
        )
    # litellm accepts 'provider/model'; if model already namespaced, pass through.
    return model if "/" in model else f"{provider}/{model}"


def _extract_json(text: str) -> dict:
    cleaned = _FENCE_RE.sub("", text).strip()
    # Be tolerant of leading prose: grab the outermost {...} block.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _call_llm(system: str, user: str) -> str:
    import litellm

    s = get_settings()
    resp = litellm.completion(
        model=_model_string(),
        api_key=s.llm_api_key or None,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=1500,
    )
    return resp["choices"][0]["message"]["content"] or ""


def reason(query: FaultQuery, retrieved: list[RetrievedIncident]) -> ReasoningResult:
    """Run comparative reasoning. Raises ReasoningError on misconfig/parse failure."""
    s = get_settings()
    if not s.llm_configured:
        raise ReasoningError(
            "LLM not configured. Set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in "
            ".env.local before calling /v1/query reasoning."
        )

    user_prompt = build_user_prompt(query, retrieved)

    last_err: Exception | None = None
    for _attempt in range(2):  # one retry
        raw = _call_llm(SYSTEM_PROMPT, user_prompt)
        try:
            data = _extract_json(raw)
            data["requires_human_approval"] = True  # enforce invariant
            return ReasoningResult.model_validate(data)
        except Exception as e:  # noqa: BLE001
            last_err = e
            user_prompt += (
                "\n\nYour previous reply could not be parsed as the required strict "
                "JSON object. Reply with ONLY the JSON object, no prose, no fences."
            )
    raise ReasoningError(f"LLM did not return valid ReasoningResult JSON after retry: {last_err}")
# End of reasoner — reasoning is the only paid dependency; everything else is local.

