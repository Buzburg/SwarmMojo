---
name: autoresearch
title: Autonomous Research & Knowledge Synthesis SOP
description: Procedural playbook for conducting autonomous multi-hop research, evidence cross-verification, structured dossier synthesis, and self-compounding cartridge ingestion.
---

# Autonomous Research & Knowledge Synthesis SOP

Use this standard operating procedure when tasked with investigating, deep-diving, or synthesizing complex technical domains, policies, or architectures.

---

## 🎯 When to Use

### Triggers
- When the user asks to "deeply research", "conduct research on", "investigate", or "synthesize findings regarding" a topic.
- When cross-referencing multi-document policies, technical specifications, or codebase patterns.
- When generating comprehensive engineering dossiers, architecture trade-off analyses, or scientific summaries.
- When explicitly invoking `/autoresearch` or the `autoresearch` MCP tool.

### Anti-Triggers
- Simple one-line factual lookups (use standard `search_knowledge_base` or `search_grounded_context`).
- Direct single-file edits or simple tool calls without exploratory research.

---

## 🛠️ 5-Stage Autonomous Research Protocol

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     Stage 1     │ ──► │     Stage 2     │ ──► │     Stage 3     │ ──► │     Stage 4     │ ──► │     Stage 5     │
│   Deconstruct   │     │  Harvesting &   │     │ Cross-Verify &  │     │ Synthesis &     │     │ Compounding &   │
│   Topic Facets  │     │  Topic Routing  │     │ Claim Extraction│     │ Dossier Creation│     │ Ingestion       │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Stage 1: Topic Deconstruction
1. Break down the high-level research question into at least 3 distinct investigative angles:
   - **Core Mechanisms & Foundations**: What are the underlying rules, data structures, or algorithms?
   - **Edge Cases & Limitations**: What are the boundaries, failure modes, or exclusions?
   - **Operational Guidelines & Best Practices**: How should engineers or agents execute against this?

### Stage 2: Multi-Source Evidence Harvesting
1. **Topic-Routed Exploration**:
   - Query `list_topics` or `search_by_topic` to lock onto domain-specific subgraphs.
2. **Typo-Tolerant Lexical & Semantic Retrieval**:
   - Use `zg_search` to catch synonyms, typos, or partial keyword matches.
   - Use `search_knowledge_base` for dense embedding similarity.
3. Collect candidate chunks across all subqueries and deduplicate by source document ID.

### Stage 3: Cross-Verification & Fact Extraction
1. Extract concrete, verifiable claims (metrics, time windows, status rules, data schemas).
2. Cross-reference claims across multiple sources:
   - If two sources contradict, note the discrepancy and verify against `last_updated` timestamps in OKF frontmatter.
   - Discard unverified assumptions or hallucinated extrapolations.

### Stage 4: Synthesis & Dossier Construction
Structure the final research dossier using standard engineering format:
- **Executive Summary**: High-level problem formulation and findings.
- **Theoretical & Operational Foundations**: In-depth explanation of mechanics.
- **Verified Evidence Ledger**: Direct citations to source files (`[doc_id]`).
- **Strategic Recommendations**: Concrete, actionable guidance for implementation.

### Stage 5: Knowledge Compounding (Self-Learning)
1. Format the synthesized research as an Open Knowledge Format (OKF) Markdown document with YAML frontmatter:
   ```markdown
   ---
   okf_version: "0.2"
   type: "research"
   title: "AutoResearch: <Topic>"
   last_updated: "YYYY-MM-DD"
   owner: "Buzburg LLC"
   tags: ["research", "autoresearch"]
   ---
   ```
2. Save into `knowledge/research_<slug>.md`.
3. Verify that the ROMS background file watcher indexes the new document in <50ms, permanently augmenting the cartridge.

---

## ✅ Quality & Anti-Hallucination Checklist
- [ ] Are all factual statements cited with their source document ID?
- [ ] Were at least 3 distinct investigative sub-queries evaluated?
- [ ] Are quantitative claims (time windows, thresholds, benchmarks) explicitly quoted?
- [ ] Has the synthesized dossier been saved to `knowledge/` for future compounding?
