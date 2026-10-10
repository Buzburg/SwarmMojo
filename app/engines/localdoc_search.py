# Copyright 2026 Buzburg LLC
# SPDX-License-Identifier: Apache-2.0
"""Bounded local document ingestion and cached semantic/keyword retrieval."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol, cast, Any

try:
    import numpy as np
    from numpy.typing import NDArray
except ImportError:
    np = None  # type: ignore
    NDArray = Any  # type: ignore

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MAX_FILES = 300
MAX_BYTES = 5_000_000
MAX_CHUNKS = 3000


class Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: object) -> Any: ...


@dataclass(frozen=True)
class Passage:
    source: str
    line: int
    text: str


@dataclass(frozen=True)
class Match:
    passage: Passage
    score: float


def chunk_document(source: str, text: str) -> list[Passage]:
    """Keep passages short enough for the embedding model; preserve starting lines."""
    passages: list[Passage] = []
    words: list[str] = []
    start = 1
    for line, content in enumerate(text.splitlines(), 1):
        if not words:
            start = line
        for word in content.split():
            if len(words) >= 80:
                passages.append(Passage(source, start, " ".join(words)))
                words, start = [], line
            words.append(word)
        if not content.strip() and words:
            passages.append(Passage(source, start, " ".join(words)))
            words = []
    if words:
        passages.append(Passage(source, start, " ".join(words)))
    return passages


def read_folder(folder: Path) -> list[Passage]:
    if not folder.is_dir():
        raise ValueError("Choose an existing folder containing .md or .txt files.")
    passages: list[Passage] = []
    count = total = 0
    for parent, directories, files in folder.walk(follow_symlinks=False):
        directories[:] = sorted(
            d
            for d in directories
            if not d.startswith(".") and d not in {"node_modules", "venv", "__pycache__"}
        )
        for filename in sorted(files):
            path = parent / filename
            if (
                path.is_symlink()
                or filename.startswith(".")
                or path.suffix.lower() not in {".md", ".txt"}
            ):
                continue
            count += 1
            total += path.stat().st_size
            if count > MAX_FILES or total > MAX_BYTES:
                raise ValueError("Choose a smaller folder: at most 300 files and 5 MB total.")
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError as exc:
                raise ValueError(f"{filename} is not UTF-8 text.") from exc
            passages.extend(chunk_document(path.relative_to(folder).as_posix(), text))
            if len(passages) > MAX_CHUNKS:
                raise ValueError("Choose fewer documents: at most 3,000 passages.")
    if not passages:
        raise ValueError("No readable text found. Add nonempty .md or .txt documents.")
    return passages


def rank(passages: list[Passage], scores: NDArray[np.floating], limit: int) -> list[Match]:
    return [
        Match(passages[int(i)], float(scores[i]))
        for i in np.argsort(-scores, kind="stable")[:limit]
    ]


def keyword_search(passages: list[Passage], query: str, limit: int = 5) -> list[Match]:
    if not query.strip():
        raise ValueError("Enter a search phrase.")
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        matrix = vectorizer.fit_transform([p.text for p in passages])
        scores = np.asarray((matrix @ vectorizer.transform([query]).T).toarray()).ravel()
        return [m for m in rank(passages, scores, limit) if m.score > 0]
    except ImportError:
        # Fallback keyword overlap scoring without scikit-learn
        q_tokens = set(query.lower().split())
        scored = []
        for p in passages:
            p_tokens = set(p.text.lower().split())
            overlap = len(q_tokens & p_tokens)
            if overlap > 0:
                scored.append(Match(p, float(overlap)))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:limit]
    except ValueError as exc:
        raise ValueError(
            "Documents need searchable words, not just punctuation or stop words."
        ) from exc


def semantic_search(
    passages: list[Passage], query: str, encoder: Encoder, cache: Path, limit: int = 5
) -> list[Match]:
    if not query.strip():
        raise ValueError("Enter a search phrase.")
    payload = json.dumps([MODEL, MODEL_REVISION, [(p.source, p.line, p.text) for p in passages]])
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (sha256(payload.encode()).hexdigest() + ".npy")
    matrix: NDArray[np.float32]
    if target.exists():
        matrix = np.load(target, allow_pickle=False)
    else:
        matrix = encoder.encode(
            [p.text for p in passages], normalize_embeddings=True, show_progress_bar=False
        )
        with NamedTemporaryFile(dir=cache, suffix=".tmp", delete=False) as temporary:
            np.save(temporary, matrix, allow_pickle=False)
        Path(temporary.name).replace(target)
    query_vector = encoder.encode([query], normalize_embeddings=True, show_progress_bar=False)
    return rank(passages, matrix @ query_vector[0], limit)


def load_encoder() -> Encoder:
    from sentence_transformers import SentenceTransformer

    return cast(
        Encoder,
        SentenceTransformer(MODEL, revision=MODEL_REVISION, device="cpu", trust_remote_code=False),
    )
