# anti-slop

A deterministic content-anti-slop gate for LLM-generated video scripts.

Distilled from an 8-channel AI-content study: the rules below are the
patterns the study found to be the consistent *losers* — off-niche drift,
soft-endorsement filler, multi-topic roundup shape in long-form, over-long
titles, uncited numbers in opinion. The gate never flags the *winners* (bold
claims, numbers, single-topic).

## What it does

Two surfaces, one rule set (the dual-signal pattern):

- **At build time** — `prompt_block()` returns the title/structure/niche
  guidance to append to a script stage's system prompt, so generated titles
  and scripts follow the winning patterns from the first pass.
- **At QA time** — the `check_*` functions re-run the same deterministic
  checks on the finished script and report findings
  (`{severity, title, evidence, remediation}`). Off-niche drift is `high`
  and blocks the gate.

Checks:

| Function | Flags |
|---|---|
| `check_title(title, fmt)` | over-long titles, question titles in the count format, missing 'Told by AI' suffix in the toldby format |
| `check_opinion(script, topic)` | uncited numbers / ungrounded claims in opinion scripts |
| `check_toldby(script, topic)` | told-by-AI format violations (missing suffix, wrong title shape) |
| `check_closing_question(script)` | final scene does not end with a specific, open-ended comment question |
| `check_niche(topic, allowed)` | off-niche drift |
| `check_video_dir(video_dir)` | the whole gate for one video dir (brief + script) |

## Design notes

- **Deterministic, not LLM.** Every check is a regex or a structural test.
  The gate's verdict is reproducible and testable offline — an LLM judge is
  a second signal, never the only one.
- **Conservative on purpose (low false-positive).** A check that cannot run
  is reported as a blind spot, never waved through as clean.
- **Stdlib-only.** It must import cheaply from both the pipeline and the QA
  gate.

## Quickstart

```python
from pathlib import Path
from anti_slop.content_rules import check_title, check_video_dir, prompt_block

check_title("10 AI Tools You Need in 2026 (Roundup!)", "long")
# -> [{severity, title, evidence, remediation}, ...]

check_video_dir(Path("videos/my-video"))   # the full gate for one video

prompt_block(fmt="long")                   # the build-time prompt block
```

## Tests

```sh
python -m pytest tests/ -q
```

## License

MIT — see [LICENSE](LICENSE).

---

Built and maintained by [Thanmai Labs](https://thanmailabs.com) — a local-first AI studio. [Watch how we build](https://www.youtube.com/@thanmailabs).
