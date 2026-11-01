"""anti_slop.content_rules — the channel-study learnings, as code.

Single source of truth for the "what works / what doesn't" rules distilled
from an 8-channel AI-content study (the study itself is the provenance; see
the README). Consumed in TWO places (the dual-signal pattern):

  * the BUILD — prompt_block() is appended to the script stage's system
    prompt so every generated title + script follows the winning patterns;
    the deterministic checks run on the generated script and feed the
    corrective pass.
  * the QA GATE — check_video_dir() re-runs the same deterministic checks on
    the finished video's brief + script and reports findings (off-niche =
    high, blocks the gate).

Stdlib-only on purpose: it must import cheaply from both the pipeline package
and the QA gate.

The rules are deliberately conservative (low false-positive): they flag the
patterns the study found to be the consistent *losers* (off-niche, soft-
endorsement filler, multi-topic roundup shape in long-form), and they never
flag the *winners* (bold claims, numbers, FREE, single-topic).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# -- the "what works" guidance (fed to the LLM at build time) ---------------

# The ai-niche title rules (the original wording, kept verbatim so the ai
# prompt is byte-identical to the pre-multi-niche block). Other niches carry
# their own title_rules in config/niches.json.
_DEFAULT_TITLE_RULES = (
    "Prefer the proven shapes, in priority order: (1) a concrete mastery "
    "promise with a time bound ('Learn 80% of X in under N minutes'); (2) a "
    "curation hook with a big effort number and a small result number ('I "
    "tried N+ tools, these K actually work'); (3) the FREE / unlimited / "
    "no-subscription modifier, when it is true; (4) one concrete number or "
    "multiplier that carries the click. A bold, specific claim about a named "
    "model beats neutral coverage. Add a credibility suffix like '(Backed By "
    "Data)' when the video is evidence-based.")


# The count format's title rule (channel-study 2026-10-13): the title is the
# ANSWER itself, not a hook that withholds it. This OVERRIDES the niche's
# generic title_rules for the count format (the exemplar "Why Anthropic Banned
# Being Cruel to Claude" is a declarative 'why' statement, not a mastery
# promise or curation hook).
_COUNT_TITLE_RULES = (
    "The title is the ANSWER itself: a bold, specific, declarative claim "
    "under 60 characters - a 'why' statement or a named current event, NOT a "
    "question and NOT a withheld tease. The viewer should be able to read the "
    "title and know the video's conclusion.")


# The told-by-AI format's title rule (channel-study 2026-10-17, Recursive
# exemplar "#29 How Would AI Actually Kill Us All? Told by AI"). Unlike the
# count format (a declarative answer), the told-by-AI title is an
# existential-stakes QUESTION (the curiosity gap about what is at stake) WITH
# the channel's signature 'Told by AI' suffix. This OVERRIDES the niche's
# generic title_rules for the toldby format.
_TOLDBY_TITLE_RULES = (
    "The title is an existential-stakes question or a bold claim under 60 "
    "characters, WITH the 'Told by AI' suffix (e.g. 'How Would AI Actually "
    "Kill Us All? Told by AI'). The question is the winning pattern for this "
    "format - it opens a curiosity gap about what is at stake. The 'Told by "
    "AI' suffix is the channel's signature device and is always present.")


def prompt_block(profile: dict | None = None, fmt: str = "long") -> str:
    """The title/structure/niche block for a niche profile.

    A missing profile (or the ai profile) reproduces PROMPT_BLOCK exactly;
    other niches swap in their own title_rules from config/niches.json. The
    count format overrides the title rule (the title is the answer, not a
    hook) but keeps the structure + niche guardrails.
    """
    rules = (profile or {}).get("title_rules") or _DEFAULT_TITLE_RULES
    if fmt == "count":
        rules = _COUNT_TITLE_RULES
    elif fmt == "toldby":
        rules = _TOLDBY_TITLE_RULES
    return (
        "TITLE (the single most important field — it decides the click): write "
        "ONE strong, single-topic title, NOT a multi-topic 'A, B, and more' "
        "roundup. "
        + rules
        + " NEVER use soft-endorsement filler ('is incredible', 'you won't "
        "believe', 'game changer', 'mind-blowing') and avoid a question-format "
        "title for an explainer. Keep it under 60 characters. "
        "STRUCTURE: the video is ONE topic. Scene 1 is the hook — the short "
        "answer or the surprising fact, before any background. Do not pad with "
        "repeated claims or a second topic. "
        "NICHE: stay strictly in the topic's niche; do not drift into an "
        "off-niche tangent (off-niche content is the single biggest "
        "view-killer)."
    )


# The ai-niche block (the original constant, kept for the QA gate and any
# direct importers). prompt_block(None) is byte-identical to this.
PROMPT_BLOCK = prompt_block(None)

# -- the "what doesn't work" detectors (deterministic, low false-positive) ---

# Soft-endorsement filler: the consistent bottom pattern across news channels
# ("This X + Y Workflow Is Incredible"). Predicate constructions only — a bold
# claim like "so good even OpenAI are worried" is a WINNER and is not flagged.
SOFT_ENDORSEMENT = (
    "is incredible", "is amazing", "is insane", "is unbelievable",
    "is mind-blowing", "is mind blowing", "you won't believe",
    "you wont believe", "game changer", "game-changer", "mind-blowing",
    "mind blowing", "so good it's", "so good its",
)

# The recurring-series roundup shape ("A, B, and more | <Series>"). Fine for a
# `roundup`-format video; a red flag in a `long`-form title, where the study
# found single-topic deep dives beat multi-topic roundups.
_ROUNDUP_SHAPE = re.compile(r",\s*and more\b|and more\s*\|", re.I)

# A title this long gets truncated in the feed and buries the hook.
TITLE_MAX_CHARS = 60


def _finding(severity: str, title: str, evidence: str,
             remediation: str) -> dict:
    return {"severity": severity, "title": title,
            "evidence": evidence, "remediation": remediation}


def check_title(title: str, fmt: str = "long") -> list[dict]:
    """Deterministic title checks. Returns findings (no id; caller assigns).

    Only flags the study's consistent losers. A clean or winning title returns
    an empty list — these checks must never false-flag a bold, single-topic,
    number-led title.
    """
    findings: list[dict] = []
    t = (title or "").strip()
    if not t:
        return findings
    low = t.lower()

    hit = next((p for p in SOFT_ENDORSEMENT if p in low), None)
    if hit:
        findings.append(_finding(
            "medium", "title uses soft-endorsement filler",
            f"title contains {hit!r}: {t!r}",
            "Replace the filler with a concrete claim, number, or the "
            "FREE/curation hook. Soft-endorsement titles are the consistent "
            "bottom pattern across AI news channels."))

    if fmt == "long" and _ROUNDUP_SHAPE.search(t):
        findings.append(_finding(
            "medium", "long-form title uses a multi-topic roundup shape",
            f"title reads as a roundup: {t!r}",
            "Long-form should be a single-topic deep dive with one strong "
            "hook, not an 'A, B, and more' roundup (the roundup is the floor, "
            "not the ceiling). Pick the single strongest item."))

    # The told-by-AI 'Told by AI' suffix is the channel's signature device and
    # is always present; measure the length without it so the suffix does not
    # push a clean title over the feed limit. For every other format the
    # suffix is absent, so `measure` is identical to `t` (no behavior change).
    measure = re.sub(r"\s*told by ai\s*$", "", t, flags=re.I)
    if len(measure) > TITLE_MAX_CHARS:
        findings.append(_finding(
            "low", "title is too long for the feed",
            f"title is {len(measure)} chars (target <= {TITLE_MAX_CHARS}): "
            f"{t!r}",
            "Tighten to <= 60 chars so the hook is not truncated in the feed."))

    if fmt == "long" and t.endswith("?"):
        findings.append(_finding(
            "info", "explainer title is a question",
            f"long-form explainer title is question-format: {t!r}",
            "Question titles are the weakest pattern for explainers; a "
            "statement or bold claim about a named model outperforms it. "
            "(Advisory — some questions work.)"))
    return findings


def check_opinion(script: dict, topic: dict) -> list[dict]:
    """Opinion-format guardrail: a number is a FACT, not an opinion.

    In an opinion video the take is explicitly framed as the channel's
    opinion, but every factual claim (a name, date, number, quote) must be
    grounded in the brief. The deterministic slice of that rule: a scene
    marked 'opinion' that carries a digit-form number is an uncited factual
    claim — a HIGH finding (it blocks the publish gate). The script stage
    already enforces number traceability for ALL scenes; this catches the
    opinion-labeled scene that smuggles in a number.
    """
    if str((topic or {}).get("format", "long")).lower() != "opinion":
        return []
    findings: list[dict] = []
    for scene in (script or {}).get("scenes", []):
        if scene.get("source") != "opinion":
            continue
        text = f"{scene.get('vo', '')} {scene.get('on_screen', '')}"
        nums = re.findall(r"\$?\d[\d,]*(?:\.\d+)?", text)
        if nums:
            findings.append(_finding(
                "high", "opinion scene carries an uncited number",
                f"scene {scene.get('id')} is marked 'opinion' but contains "
                f"number(s) {sorted(set(nums))}: {text[:80]!r}",
                "A number is a fact, not an opinion. Ground it in the brief "
                "(source 'brief') or drop it from the take."))
    return findings


# The told-by-AI format's 6-beat structure (channel-study 2026-10-17, Recursive
# exemplar). The deterministic slice: the script must carry the three beats
# that are checkable without an LLM - (1) a cold-open authority quote (scene 1
# is a 'text' card with a quoted line), (2) a first-person AI-narrator
# self-intro (scene 2 says 'I'm an AI' / 'as an AI'), and (4) a both-sides
# beat (a named believer + a named skeptic, each with a quote). A missing beat
# is a MEDIUM finding (the corrective loop re-prompts, the QA gate reports).
_TOLDBY_NARRATOR = ("i'm an ai", "im an ai", "as an ai", "i am an ai",
                    "i'm an artificial intelligence", "as an artificial "
                    "intelligence")


def check_toldby(script: dict, topic: dict) -> list[dict]:
    """Told-by-AI format guardrail: the 6-beat structure must be present.

    Applies only to the toldby format. The deterministic slice checks the
    three beats that are verifiable without an LLM: the cold-open authority
    quote (scene 1), the first-person AI-narrator self-intro (scene 2), and
    the both-sides beat (a named believer + a named skeptic). A missing beat
    is a MEDIUM finding. A script with no scenes returns nothing (the script
    stage fails earlier on an empty script).
    """
    if str((topic or {}).get("format", "long")).lower() != "toldby":
        return []
    scenes = (script or {}).get("scenes") or []
    if not scenes:
        return []
    findings: list[dict] = []
    # (1) Cold-open authority quote: scene 1 is a 'text' card with a quoted
    # line (the on-screen line carries the quote).
    s1 = scenes[0]
    s1_text = f"{s1.get('vo', '')} {s1.get('on_screen', '')}".lower()
    if s1.get("visual") != "text" or ("\u201c" not in s1_text
                                      and "\u201d" not in s1_text
                                      and '"' not in s1_text):
        findings.append(_finding(
            "high", "toldby cold-open is not an authority quote",
            f"scene 1 is not a 'text' card with a quoted line: "
            f"{s1_text[:80]!r}",
            "Scene 1 must be a 'text' card carrying a named, dated, quoted "
            "line from the brief (the cold-open authority quote)."))
    # (2) First-person AI-narrator self-intro: scene 2 says 'I'm an AI'.
    if len(scenes) >= 2:
        s2_text = f"{scenes[1].get('vo', '')} " \
                 f"{scenes[1].get('on_screen', '')}".lower()
        if not any(n in s2_text for n in _TOLDBY_NARRATOR):
            findings.append(_finding(
            "high", "toldby self-intro is not first-person AI",
                f"scene 2 does not introduce the AI narrator: "
                f"{s2_text[:80]!r}",
                "Scene 2 must be the first-person AI narrator introducing "
                "itself ('I'm an AI, so this is my story, too')."))
    # (4) Both-sides beat: a named believer + a named skeptic, each with a
    # quote. The deterministic slice: at least two distinct named people with
    # quotes across the beat scenes (the both-sides beat is the middle run).
    all_text = " ".join(
        f"{s.get('vo', '')} {s.get('on_screen', '')}"
        for s in scenes[2:-1] if isinstance(s, dict))
    # Normalize curly quotes to straight so the name+quote pattern matches
    # regardless of which quote style the model used.
    norm = all_text.replace("\u201c", '"').replace("\u201d", '"')
    quoted_names = re.findall(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+\"[^\"]{10,}", norm)
    if len(set(quoted_names)) < 2:
        findings.append(_finding(
            "high", "toldby both-sides beat is missing",
            "fewer than two distinct named people with quotes across the "
            "beat scenes",
            "The both-sides beat needs a named believer and a named skeptic, "
            "each with a direct quote from the brief."))
    return findings


# A must-have for EVERY video (a must-have for every video): the final scene
# ends with a specific, open-ended question that invites the viewer to
# comment. The deterministic slice: the last scene's VO must end with a
# question mark. A generic 'thoughts?'-style closer is flagged as low (it
# invites a comment but is not specific); a missing question is medium (the
# corrective loop re-prompts, the QA gate reports).
_GENERIC_CLOSERS = ("thoughts?", "thoughts on this?", "what do you think?",
                    "any thoughts?", "let me know in the comments",
                    "drop a comment", "comment below")


def check_closing_question(script: dict) -> list[dict]:
    """The final scene must end with a specific, open-ended comment question.

    Applies to every format (a must-have for every video). A
    script with no scenes returns nothing (the script stage fails earlier on
    an empty script). The check is deliberately low false-positive: it only
    looks at the LAST scene's VO and only flags a missing or generic
    question - a specific question (the normal case) returns an empty list.
    """
    scenes = (script or {}).get("scenes") or []
    if not scenes:
        return []
    vo = str(scenes[-1].get("vo", "")).strip()
    if not vo:
        return []
    if vo.endswith("?"):
        low = vo.lower()
        if any(g in low for g in _GENERIC_CLOSERS):
            return [_finding(
                "low", "closing question is generic",
                f"final scene ends with a generic closer: {vo[-80:]!r}",
                "Make the closing question specific to the video's topic - "
                "about the viewer's own experience or choice, not a generic "
                "'thoughts?'.")]
        return []
    return [_finding(
        "medium", "final scene does not end with a comment question",
        f"final scene VO does not end with a question: {vo[-80:]!r}",
        "The final scene MUST end with a specific, open-ended question that "
        "invites the viewer to comment (a must-have for every video).")]


def check_niche(topic: dict, allowed_niches: list[str] | None) -> list[dict]:
    """Off-niche guardrail: the topic's niche must be in the allowed set.

    Off-niche content is the single biggest view-killer found in the study
    (Kevin Stratvert's QuickBooks videos, Jeff Su's career advice). A topic
    whose niche is not in the allowed set is a HIGH finding — it blocks the
    publish gate.
    """
    niche = str((topic or {}).get("niche") or "").strip().lower()
    if not niche or not allowed_niches:
        return []
    if niche not in [n.lower() for n in allowed_niches]:
        return [_finding(
            "high", "off-niche topic",
            f"topic niche {niche!r} is not in the allowed niches "
            f"{allowed_niches}",
            "Stay in-niche. Off-niche content is the biggest view-killer; "
            "re-scope the topic to the channel's niche or drop it.")]
    return []


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def check_video_dir(video_dir: Path,
                    allowed_niches: list[str] | None = None) -> list[dict]:
    """The content gate for one video dir.

    Loads the brief (manifest.json -> topic, the UPLOAD title) and the script
    (script.json, the THUMBNAIL title) and runs the deterministic content
    checks on both. Returns findings (no id; the QA gate assigns ids and folds
    them into the report). A missing brief/script is not an error here — the
    deterministic + vision checks cover the render; the content gate simply
    has nothing to check.
    """
    video_dir = Path(video_dir)
    manifest = _load_json(video_dir / "manifest.json") or {}
    script = _load_json(video_dir / "script.json") or {}
    topic = manifest.get("topic") or {}
    fmt = manifest.get("format") or topic.get("format", "long")

    findings: list[dict] = []
    # The upload title (what viewers see in the feed) is the brief's title.
    brief_title = str(topic.get("title") or "").strip()
    if brief_title:
        for f in check_title(brief_title, fmt):
            f["title"] = f"upload title: {f['title']}"
            findings.append(f)
    # The thumbnail title is the script's title; check it too when it differs.
    script_title = str(script.get("title") or "").strip()
    if script_title and script_title.lower() != brief_title.lower():
        for f in check_title(script_title, fmt):
            f["title"] = f"thumbnail title: {f['title']}"
            findings.append(f)
    findings.extend(check_opinion(script, topic))
    findings.extend(check_toldby(script, topic))
    findings.extend(check_niche(topic, allowed_niches))
    # Closing comment-question (a must-have for every video)
    # 2026-10-13): the final scene must end with a specific, open-ended
    # question that invites the viewer to comment.
    findings.extend(check_closing_question(script))
    return findings
