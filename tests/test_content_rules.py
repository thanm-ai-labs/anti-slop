"""Tests for anti_slop.content_rules — the deterministic content-anti-slop gate.

The rules are deliberately conservative (low false-positive): they flag the
patterns the channel study found to be the consistent *losers* (off-niche,
soft-endorsement filler, multi-topic roundup shape in long-form, uncited
numbers in opinion), and they never flag the *winners* (bold claims, numbers,
single-topic). These tests pin both sides: the losers must be flagged, the
winners must pass clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anti_slop import content_rules as cr  # noqa: E402


# ---------------------------------------------------------------------------
# check_title — losers flagged, winners clean
# ---------------------------------------------------------------------------

def test_flags_soft_endorsement_filler():
    for t in ("This Model Is Incredible", "A Game Changer for Local AI",
              "You Won't Believe This AI Trick"):
        findings = cr.check_title(t, "long")
        assert any(f["title"] == "title uses soft-endorsement filler"
                   for f in findings), t


def test_flags_roundup_shape_in_long_form():
    t = "Local LLMs, RAG, and More | AI Weekly"
    findings = cr.check_title(t, "long")
    assert any("roundup" in f["title"] for f in findings), t


def test_roundup_shape_ok_in_roundup_format():
    t = "Local LLMs, RAG, and More | AI Weekly"
    assert cr.check_title(t, "roundup") == []


def test_flags_over_long_title():
    t = "A" * 70
    findings = cr.check_title(t, "long")
    assert any(f["title"] == "title is too long for the feed"
               for f in findings), t


def test_toldby_suffix_not_counted_toward_length():
    # 55 chars + the suffix: clean without the suffix, would be over with it.
    t = "How Would AI Actually Kill Us All? Told by AI"
    assert cr.check_title(t, "toldby") == []


def test_question_title_advisory_in_long_form():
    findings = cr.check_title("Why Do Local Models Win?", "long")
    assert any(f["severity"] == "info" for f in findings)


def test_bold_specific_title_is_clean():
    # The winners: bold, specific, number-led, single-topic.
    for t in ("Qwen3 Beats the Cloud on My M5",
              "I Tried 12 Local LLMs, These 3 Actually Work",
              "FREE: Run a 70B Model on One Machine"):
        assert cr.check_title(t, "long") == [], t


# ---------------------------------------------------------------------------
# check_opinion — a number is a fact, not an opinion
# ---------------------------------------------------------------------------

def test_opinion_scene_with_number_is_high():
    script = {"scenes": [
        {"id": 1, "source": "opinion", "vo": "This is a 10x improvement.",
         "on_screen": ""},
    ]}
    topic = {"format": "opinion"}
    findings = cr.check_opinion(script, topic)
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


def test_opinion_scene_without_number_is_clean():
    script = {"scenes": [
        {"id": 1, "source": "opinion", "vo": "This is the right direction.",
         "on_screen": ""},
    ]}
    assert cr.check_opinion(script, {"format": "opinion"}) == []


def test_opinion_check_only_applies_to_opinion_format():
    script = {"scenes": [
        {"id": 1, "source": "opinion", "vo": "A 10x improvement.",
         "on_screen": ""},
    ]}
    assert cr.check_opinion(script, {"format": "long"}) == []


# ---------------------------------------------------------------------------
# check_niche — off-niche is high (blocks the gate)
# ---------------------------------------------------------------------------

def test_off_niche_is_high():
    findings = cr.check_niche({"niche": "cooking"}, ["ai"])
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


def test_in_niche_is_clean():
    assert cr.check_niche({"niche": "ai"}, ["ai"]) == []


def test_no_allowed_set_is_clean():
    assert cr.check_niche({"niche": "anything"}, None) == []


# ---------------------------------------------------------------------------
# check_closing_question — the final scene must ask a specific question
# ---------------------------------------------------------------------------

def test_specific_closing_question_is_clean():
    script = {"scenes": [{"vo": "Which model would you run first?"}]}
    assert cr.check_closing_question(script) == []


def test_generic_closing_question_is_flagged():
    script = {"scenes": [{"vo": "What are your thoughts?"}]}
    findings = cr.check_closing_question(script)
    assert any(f["title"] == "closing question is generic"
               for f in findings)


def test_missing_closing_question_is_flagged():
    script = {"scenes": [{"vo": "That is the whole story."}]}
    findings = cr.check_closing_question(script)
    assert any(f["title"] == "final scene does not end with a comment question"
               for f in findings)


# ---------------------------------------------------------------------------
# prompt_block — the build-time guidance
# ---------------------------------------------------------------------------

def test_prompt_block_is_nonempty_and_format_sensitive():
    long_block = cr.prompt_block(fmt="long")
    count_block = cr.prompt_block(fmt="count")
    assert isinstance(long_block, str) and len(long_block) > 100
    assert isinstance(count_block, str) and len(count_block) > 100
    assert long_block != count_block
