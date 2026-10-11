# Sovereign Coding Engine & PTRM Reviewer Verification

**Swarmojo by Buzburg AI**  
*Maintainer:* Buzburg AI (`buzburgai@gmail.com`)

This specification details the code review, symbol analysis, and patch validation architecture of the Swarmojo coding guild.

---

## 1. Native Coding Invariants

1. **Exact Substring Mutation (`PiCodingToolkit`)**:
   Replaces target blocks only when matching uniquely in the file. Multi-occurrence ambiguity raises immediate errors, accompanied by pre-edit snapshots via `mojo-agent-rewind`.
2. **Sub-20 µs Symbol & Call-Graph Indexing (`mojo-symdex`)**:
   Code symbols, callers, callees, and definitions are indexed in-memory using deterministic 256-dimensional unit embeddings.
3. **PTRM Reviewer Integration**:
   Validates report schemas, exact selected path sets, file/finding source hashes, line ranges, and declared truncation. Rejects malformed or mismatched evidence and verifies native worker fingerprints before and after review.
4. **Optimistic Concurrency Control (`statefresh`)**:
   Acquires atomic Compare-And-Swap (CAS) version leases before applying mutations, rejecting stale concurrent edits.

---

## 2. Verification Protocol

- Verifies patch validation, staged-review non-authority, context selectors, and prefrontal execution tools.
- Native worker hashes are pinned and verified per transaction.
- Regression tests operate against deterministic fixtures.
