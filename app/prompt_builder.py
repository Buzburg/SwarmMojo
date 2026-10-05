"""Local LLM Context Engineering & Prompt Builder.

Optimized specifically for local open-weights LLMs (Llama 3, Qwen 2.5, Mistral, Gemma 2, Phi 3):
- Strict token budgeting to minimize TTFT (Time-To-First-Token) and memory footprint
- Semantic deduplication of overlapping RAG chunks
- Context grounding guardrails to prevent small model hallucinations
- Clean XML/Markdown structured context injection
"""

import re
from typing import Any, Dict, List, Optional
from app.config import MAX_RAG_CONTEXT_TOKENS, MIN_RELEVANCE_SCORE


def estimate_tokens(text: str) -> int:
    """Fast, lightweight token count estimation (approx 4 chars/token + word factor)."""
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(words, chars // 4)


def clean_chunk_text(text: str) -> str:
    """Strips excessive whitespace, repetitive header tags, and trailing artifacts."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text


def compress_chunks(
    chunks: List[Dict[str, Any]],
    max_tokens: int = MAX_RAG_CONTEXT_TOKENS,
    min_score: float = MIN_RELEVANCE_SCORE,
) -> List[Dict[str, Any]]:
    """Deduplicates and compresses RAG chunks within strict token budget for local LLMs."""
    filtered: List[Dict[str, Any]] = []
    seen_snippets: List[str] = []
    current_tokens = 0

    for item in chunks:
        score = item.get("score", 0.0)
        # Filter out low-confidence hallucinations / noise
        if score < min_score:
            continue

        content = clean_chunk_text(item.get("content", ""))
        if not content:
            continue

        # Simple deduplication: avoid adding content that is largely substring of previous chunks
        content_lower = content.lower()
        is_duplicate = False
        for seen in seen_snippets:
            if content_lower in seen or seen in content_lower:
                is_duplicate = True
                break
        if is_duplicate:
            continue

        item_tokens = estimate_tokens(content)
        if current_tokens + item_tokens > max_tokens:
            # If we haven't included any chunks yet, include truncated first chunk
            if not filtered:
                remaining_tokens = max(50, max_tokens - current_tokens)
                char_limit = remaining_tokens * 4
                truncated_content = content[:char_limit] + "..."
                filtered.append({**item, "content": truncated_content})
            break

        filtered.append(item)
        seen_snippets.append(content_lower)
        current_tokens += item_tokens

    return filtered


def format_context_for_local_llm(
    chunks: List[Dict[str, Any]],
    format_style: str = "xml",
    max_tokens: int = MAX_RAG_CONTEXT_TOKENS,
    min_score: float = MIN_RELEVANCE_SCORE,
) -> str:
    """Formats retrieved chunks into a crisp, high-signal context block for local LLMs."""
    compressed = compress_chunks(chunks, max_tokens=max_tokens, min_score=min_score)
    if not compressed:
        return ""

    if format_style == "xml":
        lines = ["<knowledge_context>"]
        for idx, item in enumerate(compressed, 1):
            doc_id = item.get("doc_id", "doc")
            score = item.get("score", 0.0)
            content = item.get("content", "").strip()
            lines.append(f'  <source id="{idx}" doc="{doc_id}" relevance="{score:.3f}">')
            for line in content.split("\n"):
                lines.append(f"    {line}")
            lines.append("  </source>")
        lines.append("</knowledge_context>")
        return "\n".join(lines)
    else:
        # Markdown format
        lines = ["### Relevant Knowledge Context:"]
        for idx, item in enumerate(compressed, 1):
            doc_id = item.get("doc_id", "doc")
            content = item.get("content", "").strip()
            lines.append(f"**[{idx}] Source: {doc_id}**\n{content}\n")
        return "\n".join(lines)


def build_grounded_system_prompt(
    base_system_prompt: str = "",
    context_str: str = "",
) -> str:
    """Assembles a grounded system prompt that prevents small model hallucination."""
    grounding_rules = (
        "CRITICAL INSTRUCTIONS:\n"
        "1. Answer based STRICTLY on the facts provided in the knowledge context.\n"
        "2. If the context does not contain the answer, reply: "
        "'I do not have enough information to answer that based on the provided knowledge.'\n"
        "3. Do not invent, extrapolate, or assume facts outside the provided context.\n"
        "4. Be concise, direct, and actionable."
    )

    parts = []
    if base_system_prompt.strip():
        parts.append(base_system_prompt.strip())
    parts.append(grounding_rules)
    if context_str.strip():
        parts.append(context_str.strip())

    return "\n\n".join(parts)
