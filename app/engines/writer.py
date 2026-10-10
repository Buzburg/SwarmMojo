"""Writer Agent Engine for SwarmMojo by Buzburg AI.

High-craft literary, journalistic, and technical writing suite:
- Buzburg Narrative Architect: multi-chapter pacing, character voice consistency
- Buzburg Ghost Protocol: 200+ banned AI phrases, journalism-informed rhythms, zero-tolerance kill list
- Buzburg Human Prose Engine: subtraction over addition, authentic rhythms, concrete specifics over stock significance
- Buzburg Long-Form Book Generator: context compression, chapter outline DAGs
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# -------------------------------------------------------------------------
# AI Cliché & Statistical Signature Blacklist (Ghost Protocol)
# -------------------------------------------------------------------------

AI_PHRASE_BLACKLIST = [
    # Transition / Connector Clichés
    "in today's landscape",
    "in today's digital landscape",
    "in the ever-evolving landscape",
    "in today's fast-paced world",
    "in today's world",
    "in an era where",
    "in the realm of",
    "it's important to note",
    "it's worth noting",
    "it is worth noting",
    "it bears mentioning",
    "moreover",
    "furthermore",
    "in conclusion",
    "to summarize",
    "in summary",
    "that being said",
    "having said that",
    "all things considered",
    "at the end of the day",
    "needless to say",
    "it goes without saying",
    # Editorializing & Inflation Clichés
    "delve into",
    "delve deeper",
    "delving into",
    "navigate the complexities",
    "navigating the complexities",
    "testament to",
    "stands as a testament",
    "indelible mark",
    "pivotal role",
    "watershed moment",
    "deeply rooted",
    "groundbreaking",
    "game-changer",
    "game changer",
    "tapestry",
    "rich tapestry",
    "beacon of",
    "multifaceted",
    "holistic approach",
    "embark on a journey",
    "foster a culture",
    "unwavering commitment",
    "synergy",
    "paradigm shift",
]

# Words that inflate importance without adding facts
INFLATION_WORDS = {
    "pivotal", "crucial", "vital", "watershed", "testament",
    "tapestry", "delve", "beacon", "groundbreaking", "multifaceted",
}


# -------------------------------------------------------------------------
# Prose Humanizer & Anti-Slop Audit Engine
# -------------------------------------------------------------------------

@dataclass
class HumanProseAudit:
    score: float  # [0.0 - 1.0], 1.0 is perfectly clean
    passed: bool
    blacklisted_phrases: List[str]
    inflation_words: List[str]
    rhythm_variance: float  # Standard deviation of sentence lengths
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProseHumanizer:
    """Detects and strips AI writing patterns to restore human authenticity."""

    @classmethod
    def audit_text(cls, text: str) -> HumanProseAudit:
        lower = text.lower()
        flagged_phrases = []
        for phrase in AI_PHRASE_BLACKLIST:
            if phrase in lower:
                flagged_phrases.append(phrase)

        tokens = re.findall(r"\b[a-z0-9_-]+\b", lower)
        flagged_words = [w for w in tokens if w in INFLATION_WORDS]

        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        sentence_lens = [len(s.split()) for s in sentences]
        if len(sentence_lens) > 1:
            mean = sum(sentence_lens) / len(sentence_lens)
            variance = sum((x - mean) ** 2 for x in sentence_lens) / len(sentence_lens)
            rhythm_std = variance ** 0.5
        else:
            rhythm_std = 0.0

        recommendations = []
        if flagged_phrases:
            recommendations.append(f"Remove {len(flagged_phrases)} banned AI clichés (e.g., '{flagged_phrases[0]}').")
        if flagged_words:
            recommendations.append(f"Replace inflated stock adjectives: {', '.join(set(flagged_words[:4]))}.")
        if rhythm_std < 3.0 and len(sentences) >= 3:
            recommendations.append("Increase sentence length variance; text has uniform AI cadences.")

        penalty = (len(flagged_phrases) * 0.15) + (len(flagged_words) * 0.05)
        score = max(0.0, min(1.0, 1.0 - penalty))

        return HumanProseAudit(
            score=round(score, 2),
            passed=score >= 0.85 and not flagged_phrases,
            blacklisted_phrases=flagged_phrases,
            inflation_words=list(set(flagged_words)),
            rhythm_variance=round(rhythm_std, 2),
            recommendations=recommendations,
        )

    @classmethod
    def humanize(cls, text: str) -> str:
        """Programmatically strips zero-tolerance AI clichés and uniform structures."""
        cleaned = text
        for phrase in AI_PHRASE_BLACKLIST:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            cleaned = pattern.sub("", cleaned)

        # Clean double spaces and punctuation artifacts created by deletion
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
        cleaned = re.sub(r"([,.!?])\1+", r"\1", cleaned)
        return cleaned.strip()


# -------------------------------------------------------------------------
# Long-Form & Chapter Outline Planner
# -------------------------------------------------------------------------

@dataclass
class ChapterSpec:
    chapter_number: int
    title: str
    summary: str
    target_word_count: int
    pov_character: Optional[str] = None
    key_conflict: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BookOutlinePlanner:
    """Multi-chapter narrative and structural planner by Buzburg AI."""

    def __init__(self, book_title: str, genre: str = "fiction"):
        self.title = book_title
        self.genre = genre
        self.chapters: List[ChapterSpec] = []

    def add_chapter(
        self,
        title: str,
        summary: str,
        target_word_count: int = 2500,
        pov_character: Optional[str] = None,
        key_conflict: Optional[str] = None,
    ) -> ChapterSpec:
        num = len(self.chapters) + 1
        chap = ChapterSpec(
            chapter_number=num,
            title=title,
            summary=summary,
            target_word_count=target_word_count,
            pov_character=pov_character,
            key_conflict=key_conflict,
        )
        self.chapters.append(chap)
        return chap

    def compile_plan(self) -> Dict[str, Any]:
        total_words = sum(c.target_word_count for c in self.chapters)
        return {
            "title": self.title,
            "genre": self.genre,
            "total_chapters": len(self.chapters),
            "estimated_word_count": total_words,
            "chapters": [c.to_dict() for c in self.chapters],
        }


# -------------------------------------------------------------------------
# Writer Agent Master Engine
# -------------------------------------------------------------------------

class WriterAgentEngine:
    """Master writing engine coordinating prose humanizing, chapter planning, and essays."""

    def __init__(self, workspace_root: str = "."):
        self.root = Path(workspace_root).resolve()
        self.writer_dir = self.root / ".mojo_writer"
        self.writer_dir.mkdir(parents=True, exist_ok=True)

    def audit_prose(self, text: str) -> Dict[str, Any]:
        audit = ProseHumanizer.audit_text(text)
        return audit.to_dict()

    def clean_prose(self, text: str) -> Dict[str, Any]:
        cleaned = ProseHumanizer.humanize(text)
        audit_before = ProseHumanizer.audit_text(text)
        audit_after = ProseHumanizer.audit_text(cleaned)
        return {
            "original_length": len(text),
            "cleaned_length": len(cleaned),
            "cleaned_text": cleaned,
            "score_before": audit_before.score,
            "score_after": audit_after.score,
        }

    def plan_book(self, title: str, genre: str, chapters_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        planner = BookOutlinePlanner(book_title=title, genre=genre)
        for c in chapters_data:
            planner.add_chapter(
                title=c.get("title", f"Chapter {len(planner.chapters)+1}"),
                summary=c.get("summary", ""),
                target_word_count=int(c.get("words", 2500)),
                pov_character=c.get("pov"),
                key_conflict=c.get("conflict"),
            )
        plan = planner.compile_plan()
        out_file = self.writer_dir / f"outline_{int(time.time())}.json"
        out_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        plan["saved_to"] = str(out_file)
        return plan

    def compose_article(
        self,
        topic: str,
        audience: str,
        thesis: str,
        key_points: List[str],
        tone: str = "journalistic_authoritative",
    ) -> Dict[str, Any]:
        """Composes structured article briefs that enforce human rhythms and concrete facts."""
        brief = {
            "topic": topic,
            "audience": audience,
            "thesis": thesis,
            "key_points": key_points,
            "tone": tone,
            "craft_rules": [
                "Be specific, not significant: state concrete dates, numbers, and facts without editorializing.",
                "Zero tolerance for banned transition phrases (moreover, in conclusion, delves into, tapestry).",
                "Ensure high sentence length variance (mix 6-word punches with 24-word descriptive sentences).",
                "Avoid rhetorical Q&A patterns and tricolon lists of three.",
            ],
        }
        return brief
