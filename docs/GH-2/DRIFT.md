# GH-2 Drift Review

**Date:** 2026-04-29
**Branch:** main
**Commit:** ec08587 (base) + GH-2 uncommitted changes

---

### Spec ↔ Code Alignment

| Spec Criterion | Evidence | Status |
|---|---|---|
| `app/config.py`: add `anthropic_api_key`, `anthropic_model`; remove `openai_model` | `config.py:33-34` — both fields present; `openai_model` absent | IMPLEMENTED |
| `app/agents/base.py`: swap client + API call shape | `base.py:8,32-33,78-86` — `import anthropic`, `AsyncAnthropic`, `messages.create(system=..., max_tokens=1024)`, `response.content[0].text` | IMPLEMENTED |
| `app/agents/arbiter.py`: swap client + 2 call sites | `arbiter.py:7,46-47,111-116,119,170-175,178` — both `chat.completions.create()` → `messages.create()`, both response parsings updated | IMPLEMENTED |
| `app/services/questions.py`: swap client + remove `response_format` | `questions.py:7,25-26,68-77,80` — `import anthropic`, `AsyncAnthropic`, `system=` extracted, `response_format` removed, `response.content[0].text` | IMPLEMENTED |
| `app/services/clerk.py`: swap client + 2 call sites + extract system prompt | `clerk.py:7,47-48,85,121-126,128,171-175,178` — system removed from messages list, `system=CLERK_SYSTEM_PROMPT` at call site, both responses updated | IMPLEMENTED |
| `pyproject.toml`: add `anthropic>=0.40.0` | `pyproject.toml:19` — added above `openai` line | IMPLEMENTED |
| `requirements.txt`: add `anthropic>=0.40.0` | `requirements.txt:13` — added above `openai` line | IMPLEMENTED |
| `.env.example`: add `ANTHROPIC_API_KEY` | `.env.example:4-5` — added with comment clarifying embeddings-only OpenAI key | IMPLEMENTED |
| No `AsyncOpenAI` in agents/ or services/ LLM files | `grep` returns empty | IMPLEMENTED |
| `OpenAIEmbedding` in `ingestion.py` and `retrieval.py` untouched | Both files not modified | IMPLEMENTED |

---

### Summary

- SPEC_GAP: 0
- SCOPE_DRIFT: 0
- IMPL_GAP: 0
- ALIGNED: 10/10

### Verdict

ALIGNED
