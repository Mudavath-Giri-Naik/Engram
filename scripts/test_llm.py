"""Diagnose the reasoning LLM in isolation. Reads your .env.local config and makes
one real call, printing SUCCESS or the FULL provider error.

    python scripts/test_llm.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engram.config import get_settings  # noqa: E402

_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def main() -> None:
    s = get_settings()
    provider = s.llm_provider.strip().lower()
    model = s.llm_model.strip()
    key = s.llm_api_key.strip()

    print(f"provider = {provider!r}")
    print(f"model    = {model!r}")
    print(f"key set  = {bool(key) and not key.upper().startswith(('REPLACE', 'PASTE')) and 'YOUR_' not in key.upper()}")
    if not s.llm_configured:
        print("\n-> LLM not configured: paste a real key into LLM_API_KEY in .env.local.")
        return

    env_name = _ENV.get(provider)
    if env_name:
        os.environ[env_name] = key

    model_string = model if "/" in model else f"{provider}/{model}"
    print(f"litellm model string = {model_string!r}\n")

    import litellm

    try:
        r = litellm.completion(
            model=model_string,
            messages=[{"role": "user", "content": "Reply with exactly the word: ok"}],
            max_tokens=10,
            temperature=0,
        )
        print("SUCCESS ->", r["choices"][0]["message"]["content"])
    except Exception as e:  # noqa: BLE001
        print("LLM ERROR ->", type(e).__name__)
        print(str(e))
        print(
            "\nCommon fixes:\n"
            "  * 'API key not valid'        -> wrong/expired key; regenerate at "
            "https://aistudio.google.com/apikey\n"
            "  * 'model ... is not found'   -> set LLM_MODEL to a current model, e.g. "
            "gemini-2.5-flash or gemini-2.0-flash\n"
            "  * mentions Vertex/credentials -> restart `serve` so the new code that sets "
            "GEMINI_API_KEY is loaded"
        )


if __name__ == "__main__":
    main()
