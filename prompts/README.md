# Prompts

The top-level README's repo-layout diagram describes this directory as
holding versioned prompt files (`<name>/v1.md`, `v2.md`, ...). That
structure was never actually built — **every prompt in this codebase is an
inline Python string constant**, versioned with a `PROMPT_VERSION` tag, in
the module that uses it. Nothing reads from this directory at runtime
(`aisle.settings.PROMPTS_DIR` is defined but never opened/read anywhere in
`backend/aisle/`).

This file exists so the directory itself is trackable in git — an empty
directory can't be committed, which is exactly why `prompts/` silently
never made it into any commit and broke the Docker build's
`COPY prompts/ prompts/` step on a fresh checkout (nothing to do with
`.gitignore`; git simply doesn't track empty directories).

## Where the real prompts actually live today

| Prompt | Version tag | Module |
|---|---|---|
| Junk gate | `junk_gate.v1` | `backend/aisle/classify/pmgate/stage1_junk.py` |
| PM utility scoring | `pm_utility.v1` | `backend/aisle/classify/pmgate/stage2_utility.py` |
| Discovery relevance | `discovery_relevance.v1` | `backend/aisle/classify/pmgate/stage3_relevance.py` |
| Structured extraction | `extraction.v1` | `backend/aisle/classify/pmgate/stage4_extraction.py` |
| Theme naming | `theme_naming.v1` | `backend/aisle/cluster/themes.py` |
| Theme merge adjudication | `theme_merge.v1` | `backend/aisle/cluster/themes.py` |
| Insight draft | `insight_draft.v1` | `backend/aisle/insights/generate.py` |
| Insight adversarial pass | `insight_adversarial.v1` | `backend/aisle/insights/generate.py` |
| Insight verification | `insight_verify.v1` | `backend/aisle/insights/generate.py` |
| QnA agent synthesis | `qa_agent.v1` | `backend/aisle/qa/agent.py` |

## If you want to actually externalize these

Migrating a prompt out of its module and into `prompts/<name>/v1.md` is a
real (if mechanical) change per prompt: load the file's contents at import
time, keep the same `PROMPT_VERSION` string (the LLM cache key is derived
from `model + prompt_version + rendered prompt text`, so bumping the
version when a prompt file's *content* changes is what forces
reclassification — see `aisle/llm/cache.py`), and keep the `.format()`/
f-string interpolation points the module currently fills in inline. Not
done here since it's a larger, separate change from "the directory is
empty and breaks the Docker build."
