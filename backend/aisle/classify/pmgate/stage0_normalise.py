"""Stage 0 — Normalise (no LLM). Unicode NFKC, strip markup/emoji-runs
(keeping one emoji as a sentiment feature), collapse repeated characters,
detect language. Romanised Hindi/Hinglish is first-class: it is never
dropped, only translated for the embedding step while the original is
always preserved (`raw_text` in `documents` is never touched by this
stage — only the derived working copy is).
"""
from __future__ import annotations

import re
import unicodedata

from langdetect import LangDetectException, detect

EMOJI_RUN_RE = re.compile(
    "([\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]{2,})"
)
REPEATED_CHAR_RE = re.compile(r"(.)\1{2,}")  # 3+ repeats of the same char, e.g. "sooooo"
MARKUP_RE = re.compile(r"<[^>]+>")


class NormalisedDoc:
    __slots__ = ("clean_text", "lang", "had_emoji_run", "kept_emoji")

    def __init__(self, clean_text: str, lang: str | None, had_emoji_run: bool, kept_emoji: str | None):
        self.clean_text = clean_text
        self.lang = lang
        self.had_emoji_run = had_emoji_run
        self.kept_emoji = kept_emoji


def detect_lang(text: str) -> str | None:
    try:
        return detect(text)
    except LangDetectException:
        return None


def normalise(raw_text: str) -> NormalisedDoc:
    text = unicodedata.normalize("NFKC", raw_text)
    text = MARKUP_RE.sub(" ", text)

    kept_emoji = None
    had_emoji_run = False

    def _collapse_emoji_run(match: re.Match) -> str:
        nonlocal kept_emoji, had_emoji_run
        had_emoji_run = True
        run = match.group(1)
        if kept_emoji is None:
            kept_emoji = run[0]
        return run[0]  # keep exactly one emoji as a sentiment feature

    text = EMOJI_RUN_RE.sub(_collapse_emoji_run, text)
    text = REPEATED_CHAR_RE.sub(lambda m: m.group(1) * 2, text)  # "sooooo" -> "soo"
    text = re.sub(r"\s+", " ", text).strip()

    return NormalisedDoc(clean_text=text, lang=detect_lang(text) if text else None, had_emoji_run=had_emoji_run, kept_emoji=kept_emoji)
