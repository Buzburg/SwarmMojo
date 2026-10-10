---
name: impeccable_design
title: Impeccable UI Design & Anti-Slop SOP
description: Deterministic design principles, layout heuristics, and anti-slop detector rules for creating production-grade web interfaces and desktop widgets in Omarchy OS.
---

# Impeccable UI Design & Anti-Slop SOP

Buzburg Sovereign UI Design & Anti-Slop Specification:
Use this procedure whenever generating, styling, or reviewing user interfaces (HTML/CSS, React, Svelte, or Quickshell QML widgets) for Omarchy OS.

---

## 🎯 Core Design Tenets

1. **Anti-Slop Imperative**:
   - Never generate generic centered floating cards with purple-blue gradients, oversized rounded corners (`border-radius: 9999px`), and low-contrast grey text.
   - Design for functional information density, deliberate typography, and high visual hierarchy.

2. **60-30-10 Color Architecture**:
   - **60% Dominant Base**: Neutral, calm background (e.g. Omarchy dark slate `#0f141c` or crisp clean surface `#161f2e`).
   - **30% Structural Secondary**: Surfaces, panels, card borders, and dividers (`#1e293b`, `#334155`).
   - **10% Intentional Accent**: High-contrast focal point for primary actions, badges, and alerts (`#38bdf8` sky, `#10b981` emerald, `#f59e0b` amber).

3. **Deterministic Contrast & Accessibility (WCAG 2.1 AA)**:
   - Body text MUST exceed **4.5:1** contrast ratio against its direct background.
   - Large headings (>18pt/bold) MUST exceed **3:1** contrast ratio.
   - Never use placeholder text as a substitute for form field labels.

4. **Typography Hierarchy**:
   - Maximum of 2 font families (one clean sans-serif for UI, one monospace for code/logs).
   - Use modular scale: `12px` (caption/meta), `14px` (dense UI/data), `16px` (body), `20px` (subheading), `28px` (section title), `36px+` (display hero).
   - Line height: `1.2–1.3` for headings; `1.5–1.6` for readable body prose.

5. **Spacing Rhythm (8pt Grid)**:
   - All padding, margins, and gaps must follow standard 4px/8px increments: `4px` (tight), `8px` (compact), `16px` (standard), `24px` (generous), `32px` (section boundary).
