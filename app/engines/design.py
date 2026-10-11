"""Design Agent Engine for SwarmMojo by Buzburg AI.

High-craft UI, GUI, and Website generation engine:
- Buzburg Impeccable Craft Floor: WCAG AAA contrast, typographic measures, subtle depth, zero-halo shadows
- Buzburg Design System: enterprise tokens, components, banner layouts, responsive safe-zones
- Buzburg Multi-Stage Web Pipeline: PM -> Designer -> Developer -> Reviewer for single & multi-page websites
- Buzburg Enterprise Admin Panels: data tables, metric delta widgets, modern forms
- Buzburg UI Component Registry: cards, dialogs, navbars, charts, hero sections
- Buzburg Desktop & Web GUI canvas layout generation
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# -------------------------------------------------------------------------
# Impeccable Design Token System & Craft Floor
# -------------------------------------------------------------------------

@dataclass
class DesignTokens:
    font_sans: str = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    font_mono: str = "'JetBrains Mono', 'Fira Code', monospace"
    font_display: str = "'Plus Jakarta Sans', Inter, sans-serif"
    primary: str = "#6366F1"        # Indigo
    primary_hover: str = "#4F46E5"
    background: str = "#0B0F19"     # Deep slate void
    surface: str = "#111827"        # Card / panel surface
    surface_border: str = "#1F2937" # 1px subtle divider
    text_primary: str = "#F9FAFB"   # High contrast >=7:1
    text_secondary: str = "#9CA3AF" # Medium contrast >=4.5:1
    accent: str = "#06B6D4"         # Cyan highlight
    danger: str = "#EF4444"
    success: str = "#10B981"
    border_radius: str = "12px"
    shadow_card: str = "0 4px 20px -2px rgba(0, 0, 0, 0.4), 0 2px 6px -1px rgba(0, 0, 0, 0.2)"
    shadow_elevated: str = "0 10px 30px -4px rgba(0, 0, 0, 0.5), 0 4px 12px -2px rgba(0, 0, 0, 0.3)"

    def to_css(self) -> str:
        return f"""
:root {{
  --font-sans: {self.font_sans};
  --font-mono: {self.font_mono};
  --font-display: {self.font_display};
  --color-primary: {self.primary};
  --color-primary-hover: {self.primary_hover};
  --color-bg: {self.background};
  --color-surface: {self.surface};
  --color-surface-border: {self.surface_border};
  --color-text-primary: {self.text_primary};
  --color-text-secondary: {self.text_secondary};
  --color-accent: {self.accent};
  --color-danger: {self.danger};
  --color-success: {self.success};
  --radius-card: {self.border_radius};
  --shadow-card: {self.shadow_card};
  --shadow-elevated: {self.shadow_elevated};
}}
"""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -------------------------------------------------------------------------
# Component Registry & Layout Generator
# -------------------------------------------------------------------------

class UIComponentRegistry:
    """Standardized production UI component generator (HTML5 + Tailwind / Modern CSS)."""

    @classmethod
    def render_navbar(cls, brand_name: str, links: List[Dict[str, str]], cta_label: str = "Get Started") -> str:
        links_html = "\n".join([f'<a href="{l.get("href", "#")}" class="nav-link">{l.get("label", "")}</a>' for l in links])
        return f"""
<header class="site-header">
  <div class="header-container">
    <div class="brand">
      <span class="brand-logo">◆</span>
      <span class="brand-name">{brand_name}</span>
    </div>
    <nav class="nav-menu">
      {links_html}
    </nav>
    <div class="header-actions">
      <button class="btn btn-primary">{cta_label}</button>
    </div>
  </div>
</header>
"""

    @classmethod
    def render_hero(cls, badge: str, title: str, subtitle: str, primary_cta: str, secondary_cta: str) -> str:
        return f"""
<section class="hero-section">
  <div class="hero-glow"></div>
  <div class="hero-container">
    <div class="badge-pill">
      <span class="badge-dot"></span>
      <span class="badge-text">{badge}</span>
    </div>
    <h1 class="hero-title">{title}</h1>
    <p class="hero-subtitle">{subtitle}</p>
    <div class="hero-cta-group">
      <button class="btn btn-primary btn-lg">{primary_cta}</button>
      <button class="btn btn-secondary btn-lg">{secondary_cta}</button>
    </div>
  </div>
</section>
"""

    @classmethod
    def render_feature_grid(cls, features: List[Dict[str, str]]) -> str:
        cards = []
        for f in features:
            cards.append(f"""
    <div class="feature-card">
      <div class="feature-icon">{f.get('icon', '⚡')}</div>
      <h3 class="feature-title">{f.get('title', 'Feature')}</h3>
      <p class="feature-desc">{f.get('description', '')}</p>
    </div>
""")
        return f"""
<section class="features-section">
  <div class="features-container">
    <div class="features-grid">
      {''.join(cards)}
    </div>
  </div>
</section>
"""

    @classmethod
    def render_metrics_panel(cls, metrics: List[Dict[str, str]]) -> str:
        items = []
        for m in metrics:
            items.append(f"""
    <div class="metric-item">
      <span class="metric-value">{m.get('value', '0')}</span>
      <span class="metric-label">{m.get('label', 'Metric')}</span>
    </div>
""")
        return f"""
<section class="metrics-section">
  <div class="metrics-container">
    {''.join(items)}
  </div>
</section>
"""


# -------------------------------------------------------------------------
# Complete Website & Admin Dashboard Page Builder
# -------------------------------------------------------------------------

class DesignAgentEngine:
    """Master UI, GUI, and Website design engine."""

    def __init__(self, workspace_root: str = "."):
        self.root = Path(workspace_root).resolve()
        self.output_dir = self.root / ".mojo_design"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tokens = DesignTokens()

    def build_landing_page(
        self,
        project_name: str,
        headline: str,
        subheadline: str,
        features: Optional[List[Dict[str, str]]] = None,
        metrics: Optional[List[Dict[str, str]]] = None,
        theme_primary: str = "#6366F1",
    ) -> Dict[str, Any]:
        """Generates a complete, responsive, dark-mode landing page with Impeccable craft."""
        self.tokens.primary = theme_primary
        self.tokens.primary_hover = theme_primary

        feature_list = features or [
            {"icon": "⚡", "title": "Microsecond Execution", "description": "Native Mojo-accelerated kernels delivering sub-10 µs symbol indices and tool triage."},
            {"icon": "🛡️", "title": "StateFresh OCC", "description": "Optimistic concurrency control with cryptographic fingerprinting to prevent stale overwrites."},
            {"icon": "🧠", "title": "Associative Memory", "description": "512-dimensional phase-vector memory with surprise-gated Titans test-time learning."},
            {"icon": "🎬", "title": "Directorial Studio", "description": "Multimodal video pipelines with 70mm camera rigs and ComfyUI graph synthesis."},
        ]

        metric_list = metrics or [
            {"value": "15x", "label": "Faster Tool Triage"},
            {"value": "99.9%", "label": "Concurrency Safety"},
            {"value": "<20µs", "label": "Call Graph Lookup"},
            {"value": "0-Token", "label": "Offline Rehearsals"},
        ]

        nav = UIComponentRegistry.render_navbar(
            brand_name=project_name,
            links=[
                {"label": "Features", "href": "#features"},
                {"label": "Architecture", "href": "#architecture"},
                {"label": "Docs", "href": "#docs"},
            ],
            cta_label="Explore Harness",
        )

        hero = UIComponentRegistry.render_hero(
            badge="SwarmMojo Autonomous Engine",
            title=headline,
            subtitle=subheadline,
            primary_cta="Get Started Free",
            secondary_cta="View Architecture",
        )

        metrics_html = UIComponentRegistry.render_metrics_panel(metric_list)
        features_html = UIComponentRegistry.render_feature_grid(feature_list)

        css_styles = f"""
{self.tokens.to_css()}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: var(--font-sans);
  background-color: var(--color-bg);
  color: var(--color-text-primary);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

.site-header {{
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(12px);
  background-color: rgba(11, 15, 25, 0.8);
  border-bottom: 1px solid var(--color-surface-border);
}}

.header-container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

.brand {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.25rem;
}}

.brand-logo {{
  color: var(--color-primary);
}}

.nav-menu {{
  display: flex;
  gap: 2rem;
}}

.nav-link {{
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 0.95rem;
  font-weight: 500;
  transition: color 0.2s;
}}

.nav-link:hover {{
  color: var(--color-text-primary);
}}

.btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.6rem 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}}

.btn-primary {{
  background-color: var(--color-primary);
  color: #FFFFFF;
}}

.btn-primary:hover {{
  background-color: var(--color-primary-hover);
  box-shadow: 0 0 16px rgba(99, 102, 241, 0.4);
}}

.btn-secondary {{
  background-color: var(--color-surface);
  color: var(--color-text-primary);
  border: 1px solid var(--color-surface-border);
}}

.btn-secondary:hover {{
  border-color: var(--color-text-secondary);
}}

.btn-lg {{
  padding: 0.85rem 1.75rem;
  font-size: 1.05rem;
}}

.hero-section {{
  position: relative;
  padding: 6rem 1.5rem 4rem;
  text-align: center;
  overflow: hidden;
}}

.hero-glow {{
  position: absolute;
  top: -20%;
  left: 50%;
  transform: translateX(-50%);
  width: 600px;
  height: 400px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, rgba(11, 15, 25, 0) 70%);
  pointer-events: none;
}}

.hero-container {{
  max-width: 860px;
  margin: 0 auto;
  position: relative;
}}

.badge-pill {{
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.85rem;
  border-radius: 9999px;
  background-color: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  margin-bottom: 1.5rem;
}}

.badge-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-primary);
}}

.badge-text {{
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-primary);
}}

.hero-title {{
  font-family: var(--font-display);
  font-size: 3.5rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.15;
  margin-bottom: 1.5rem;
}}

.hero-subtitle {{
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  max-width: 700px;
  margin: 0 auto 2.5rem;
}}

.hero-cta-group {{
  display: flex;
  justify-content: center;
  gap: 1rem;
}}

.metrics-section {{
  border-top: 1px solid var(--color-surface-border);
  border-bottom: 1px solid var(--color-surface-border);
  background-color: rgba(17, 24, 39, 0.5);
  padding: 2.5rem 1.5rem;
}}

.metrics-container {{
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 2rem;
  text-align: center;
}}

.metric-value {{
  display: block;
  font-family: var(--font-display);
  font-size: 2.5rem;
  font-weight: 800;
  color: var(--color-text-primary);
}}

.metric-label {{
  font-size: 0.95rem;
  color: var(--color-text-secondary);
}}

.features-section {{
  padding: 5rem 1.5rem;
  max-width: 1200px;
  margin: 0 auto;
}}

.features-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.5rem;
}}

.feature-card {{
  background-color: var(--color-surface);
  border: 1px solid var(--color-surface-border);
  border-radius: var(--radius-card);
  padding: 2rem;
  box-shadow: var(--shadow-card);
  transition: transform 0.2s, border-color 0.2s;
}}

.feature-card:hover {{
  transform: translateY(-4px);
  border-color: var(--color-primary);
}}

.feature-icon {{
  font-size: 2rem;
  margin-bottom: 1rem;
}}

.feature-title {{
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}}

.feature-desc {{
  font-size: 0.95rem;
  color: var(--color-text-secondary);
}}
"""

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project_name} — {headline}</title>
  <style>
{css_styles}
  </style>
</head>
<body>
  {nav}
  {hero}
  {metrics_html}
  {features_html}
</body>
</html>
"""

        out_file = self.output_dir / "index.html"
        out_file.write_text(full_html, encoding="utf-8")

        return {
            "status": "ready",
            "file": str(out_file),
            "project_name": project_name,
            "headline": headline,
            "html_length": len(full_html),
            "tokens": self.tokens.to_dict(),
        }

    def build_admin_dashboard(
        self,
        dashboard_title: str,
        stats: List[Dict[str, str]],
        recent_activity: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Generates an enterprise Buzburg GUI dashboard layout."""
        stat_cards = []
        for s in stats:
            stat_cards.append(f"""
      <div class="dash-stat-card">
        <span class="stat-title">{s.get('label', 'Stat')}</span>
        <span class="stat-number">{s.get('value', '0')}</span>
        <span class="stat-delta">{s.get('delta', '+0%')}</span>
      </div>
""")

        activity_rows = []
        for a in recent_activity:
            activity_rows.append(f"""
        <tr class="activity-row">
          <td class="col-agent">{a.get('agent', 'Agent')}</td>
          <td class="col-action">{a.get('action', 'Action')}</td>
          <td class="col-status"><span class="badge-status {a.get('status', 'ok')}">{a.get('status', 'ok')}</span></td>
          <td class="col-time">{a.get('time', 'Just now')}</td>
        </tr>
""")

        dash_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{dashboard_title} — Admin Dashboard</title>
  <style>
{self.tokens.to_css()}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: var(--font-sans);
  background-color: var(--color-bg);
  color: var(--color-text-primary);
  display: flex;
  height: 100vh;
  overflow: hidden;
}}

.sidebar {{
  width: 260px;
  background-color: var(--color-surface);
  border-right: 1px solid var(--color-surface-border);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
}}

.sidebar-brand {{
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 2rem;
  color: var(--color-primary);
}}

.sidebar-menu {{
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}}

.sidebar-item {{
  padding: 0.75rem 1rem;
  border-radius: 8px;
  color: var(--color-text-secondary);
  text-decoration: none;
  font-weight: 500;
  transition: all 0.2s;
}}

.sidebar-item.active, .sidebar-item:hover {{
  background-color: rgba(99, 102, 241, 0.1);
  color: var(--color-text-primary);
}}

.main-content {{
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}}

.top-bar {{
  padding: 1rem 2rem;
  border-bottom: 1px solid var(--color-surface-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.dash-title {{
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
}}

.content-body {{
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}}

.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.5rem;
}}

.dash-stat-card {{
  background-color: var(--color-surface);
  border: 1px solid var(--color-surface-border);
  border-radius: var(--radius-card);
  padding: 1.5rem;
  box-shadow: var(--shadow-card);
}}

.stat-title {{
  display: block;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}}

.stat-number {{
  display: block;
  font-size: 2rem;
  font-weight: 700;
  font-family: var(--font-display);
  margin-bottom: 0.25rem;
}}

.stat-delta {{
  font-size: 0.85rem;
  color: var(--color-success);
}}

.table-card {{
  background-color: var(--color-surface);
  border: 1px solid var(--color-surface-border);
  border-radius: var(--radius-card);
  padding: 1.5rem;
  box-shadow: var(--shadow-card);
}}

.table-title {{
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 1rem;
}}

table {{
  width: 100%;
  border-collapse: collapse;
}}

th {{
  text-align: left;
  padding: 0.75rem 1rem;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-surface-border);
}}

td {{
  padding: 0.85rem 1rem;
  font-size: 0.95rem;
  border-bottom: 1px solid rgba(31, 41, 55, 0.5);
}}

.badge-status {{
  padding: 0.25rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}}

.badge-status.success, .badge-status.ok {{
  background-color: rgba(16, 185, 129, 0.15);
  color: var(--color-success);
}}
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-brand">◆ {dashboard_title}</div>
    <nav class="sidebar-menu">
      <a href="#" class="sidebar-item active">Overview</a>
      <a href="#" class="sidebar-item">Agents</a>
      <a href="#" class="sidebar-item">Workflows</a>
      <a href="#" class="sidebar-item">Settings</a>
    </nav>
  </aside>
  <main class="main-content">
    <header class="top-bar">
      <h1 class="dash-title">Workspace Operations</h1>
    </header>
    <div class="content-body">
      <div class="stats-grid">
        {''.join(stat_cards)}
      </div>
      <div class="table-card">
        <h2 class="table-title">Recent Activity</h2>
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Action</th>
              <th>Status</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {''.join(activity_rows)}
          </tbody>
        </table>
      </div>
    </div>
  </main>
</body>
</html>
"""

        out_file = self.output_dir / "dashboard.html"
        out_file.write_text(dash_html, encoding="utf-8")

        return {
            "status": "ready",
            "file": str(out_file),
            "dashboard_title": dashboard_title,
            "html_length": len(dash_html),
        }

    def build_herald_hud(
        self,
        system_title: str = "SwarmMojo Sovereign OS",
        agents_roster: Optional[List[Dict[str, Any]]] = None,
        live_dag_milestones: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Generates an ultra-sleek, deep-blue glassmorphism operating desktop HUD with real-time agent telemetry and DAG milestones."""
        roster = agents_roster or [
            {"id": "atlas", "name": "Atlas", "role": "Meta Coordinator", "status": "active", "load": "12%", "model": "deepseek-r1", "avatar": "⚡"},
            {"id": "daedalus", "name": "Daedalus", "role": "DeepCode Architect", "status": "busy", "load": "78%", "model": "qwen-coder", "avatar": "🛠️"},
            {"id": "vitruvius", "name": "Vitruvius", "role": "UI/UX Designer", "status": "idle", "load": "4%", "model": "qwen-coder", "avatar": "🎨"},
            {"id": "lumiere", "name": "Lumiere", "role": "Studio Director", "status": "rendering", "load": "94%", "model": "flux-dev", "avatar": "🎬"},
            {"id": "orwell", "name": "Orwell", "role": "Ghost Scribe", "status": "active", "load": "32%", "model": "qwen-coder", "avatar": "✍️"},
            {"id": "aegis", "name": "Aegis", "role": "Security Auditor", "status": "monitoring", "load": "8%", "model": "llama3", "avatar": "🛡️"},
        ]

        milestones = live_dag_milestones or [
            {"id": "m1", "title": "DAG Ingestion & Triage", "engine": "fastgate", "latency": "8µs", "state": "complete"},
            {"id": "m2", "title": "DeepCode Recursive Subagent Fork", "engine": "deepcode-recursion", "latency": "14ms", "state": "running"},
            {"id": "m3", "title": "Mojo Angular Drift Evaluation", "engine": "mojo-drift", "latency": "42µs", "state": "pending"},
            {"id": "m4", "title": "StateFresh OCC File Write Lease", "engine": "statefresh", "latency": "6µs", "state": "pending"},
        ]

        roster_cards = []
        for a in roster:
            status_cls = a.get("status", "idle")
            roster_cards.append(f"""
        <div class="hud-agent-card {status_cls}">
          <div class="agent-avatar">{a.get('avatar', '🤖')}</div>
          <div class="agent-info">
            <div class="agent-name-row">
              <span class="agent-name">{a.get('name')}</span>
              <span class="agent-badge {status_cls}">{status_cls}</span>
            </div>
            <span class="agent-role">{a.get('role')}</span>
            <div class="agent-meta">
              <span class="meta-tag">{a.get('model')}</span>
              <span class="meta-load">Load: {a.get('load')}</span>
            </div>
          </div>
        </div>
""")

        dag_items = []
        for m in milestones:
            st = m.get("state", "pending")
            dag_items.append(f"""
        <div class="dag-step {st}">
          <div class="step-indicator"></div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">{m.get('title')}</span>
              <span class="step-engine">{m.get('engine')} ({m.get('latency')})</span>
            </div>
            <span class="step-state">{st.upper()}</span>
          </div>
        </div>
""")

        hud_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{system_title} — Autonomous Operations HUD</title>
  <style>
:root {{
  --bg-deep: #070B14;
  --bg-glass: rgba(13, 21, 38, 0.72);
  --border-glass: rgba(99, 102, 241, 0.22);
  --border-glow: rgba(99, 102, 241, 0.5);
  --accent-cyan: #06B6D4;
  --accent-indigo: #6366F1;
  --accent-emerald: #10B981;
  --text-main: #F8FAFC;
  --text-dim: #94A3B8;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  background-color: var(--bg-deep);
  background-image: 
    radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.18) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.15) 0px, transparent 50%);
  color: var(--text-main);
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}

/* Top Menu Bar (Herald OS style) */
.hud-menubar {{
  height: 44px;
  background: rgba(7, 11, 20, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border-glass);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.5rem;
  font-size: 0.85rem;
  z-index: 100;
}}

.menubar-left {{
  display: flex;
  align-items: center;
  gap: 1.5rem;
}}

.system-brand {{
  font-weight: 800;
  letter-spacing: 0.05em;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}

.system-brand span {{
  color: var(--accent-cyan);
}}

.menubar-right {{
  display: flex;
  align-items: center;
  gap: 1.25rem;
  color: var(--text-dim);
}}

.live-indicator {{
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--accent-emerald);
  font-weight: 600;
  font-size: 0.8rem;
}}

.pulse-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--accent-emerald);
  box-shadow: 0 0 10px var(--accent-emerald);
  animation: pulse 2s infinite;
}}

@keyframes pulse {{
  0% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.4; transform: scale(0.85); }}
  100% {{ opacity: 1; transform: scale(1); }}
}}

/* Main Desktop Workspace */
.hud-workspace {{
  flex: 1;
  display: grid;
  grid-template-columns: 340px 1fr 380px;
  gap: 1.25rem;
  padding: 1.25rem;
  overflow: hidden;
}}

/* Glassmorphism Panel */
.glass-panel {{
  background: var(--bg-glass);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-glass);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}}

.panel-header {{
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-glass);
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.panel-title {{
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}

.panel-body {{
  flex: 1;
  padding: 1.25rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}}

/* Left Column: Agent Swarm Roster */
.hud-agent-card {{
  background: rgba(17, 27, 49, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 0.85rem;
  display: flex;
  gap: 0.85rem;
  transition: all 0.2s ease;
}}

.hud-agent-card:hover {{
  border-color: var(--border-glow);
  transform: translateY(-2px);
  background: rgba(23, 36, 66, 0.8);
}}

.agent-avatar {{
  font-size: 1.5rem;
  background: rgba(99, 102, 241, 0.15);
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.2);
}}

.agent-info {{
  flex: 1;
}}

.agent-name-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.agent-name {{
  font-weight: 700;
  font-size: 0.95rem;
}}

.agent-role {{
  font-size: 0.8rem;
  color: var(--text-dim);
  display: block;
  margin-bottom: 0.4rem;
}}

.agent-meta {{
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-dim);
}}

.meta-tag {{
  background: rgba(255, 255, 255, 0.06);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
}}

.agent-badge {{
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
}}

.agent-badge.active, .agent-badge.running {{
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-emerald);
}}

.agent-badge.busy, .agent-badge.rendering {{
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}}

.agent-badge.idle {{
  background: rgba(148, 163, 184, 0.15);
  color: var(--text-dim);
}}

/* Center Console: Causal Loop Simulation & Visual Output */
.center-viewport {{
  display: grid;
  grid-template-rows: 240px 1fr;
  gap: 1.25rem;
}}

.telemetry-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}}

.telemetry-card {{
  background: rgba(17, 27, 49, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}

.telemetry-val {{
  font-size: 2rem;
  font-weight: 800;
  color: var(--text-main);
  letter-spacing: -0.02em;
}}

.telemetry-val.cyan {{ color: var(--accent-cyan); }}
.telemetry-val.emerald {{ color: var(--accent-emerald); }}
.telemetry-val.indigo {{ color: var(--accent-indigo); }}

.telemetry-lbl {{
  font-size: 0.8rem;
  color: var(--text-dim);
}}

.live-terminal {{
  background: #04070F;
  border: 1px solid var(--border-glass);
  border-radius: 12px;
  padding: 1rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: #38BDF8;
  line-height: 1.5;
  overflow-y: auto;
}}

/* Right Panel: Live DAG Execution Milestones */
.dag-step {{
  display: flex;
  gap: 0.85rem;
  position: relative;
}}

.step-indicator {{
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-top: 4px;
  background: var(--text-dim);
}}

.dag-step.complete .step-indicator {{
  background: var(--accent-emerald);
  box-shadow: 0 0 8px var(--accent-emerald);
}}

.dag-step.running .step-indicator {{
  background: var(--accent-cyan);
  box-shadow: 0 0 8px var(--accent-cyan);
  animation: pulse 1.5s infinite;
}}

.step-content {{
  flex: 1;
  background: rgba(17, 27, 49, 0.4);
  padding: 0.75rem;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.04);
}}

.step-header {{
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}}

.step-title {{
  font-weight: 700;
  font-size: 0.85rem;
}}

.step-engine {{
  font-size: 0.75rem;
  color: var(--accent-cyan);
}}

.step-state {{
  font-size: 0.7rem;
  color: var(--text-dim);
}}
  </style>
</head>
<body>
  <div class="hud-menubar">
    <div class="menubar-left">
      <div class="system-brand">◆ SWARM<span>MOJO</span> // SOVEREIGN-OS</div>
      <div>Session: 0x8F94-AEON</div>
      <div>Kernel: Native Mojo v25.1</div>
    </div>
    <div class="menubar-right">
      <div class="live-indicator"><div class="pulse-dot"></div> ORCHESTRATOR ONLINE</div>
      <div>MEM: 412 MB / 800 TOKENS</div>
      <div>LATENCY: 12 µs</div>
    </div>
  </div>

  <div class="hud-workspace">
    <!-- Left Panel: Agent Swarm Roster -->
    <div class="glass-panel">
      <div class="panel-header">
        <span class="panel-title">👥 SPECIALIST ROSTER</span>
        <span style="font-size: 0.8rem; color: var(--text-dim);">{len(roster)} Agents Active</span>
      </div>
      <div class="panel-body">
        {''.join(roster_cards)}
      </div>
    </div>

    <!-- Center Viewport: Telemetry & Interactive Terminal -->
    <div class="center-viewport">
      <div class="glass-panel" style="padding: 1.25rem;">
        <div class="telemetry-grid">
          <div class="telemetry-card">
            <span class="telemetry-lbl">SUB-10µs SYMBOL LOOKUPS</span>
            <span class="telemetry-val cyan">142,800</span>
            <span class="telemetry-lbl">Symdex In-Memory Speed</span>
          </div>
          <div class="telemetry-card">
            <span class="telemetry-lbl">PARALLEL CONCURRENCY</span>
            <span class="telemetry-val emerald">99.98%</span>
            <span class="telemetry-lbl">StateFresh OCC Collision-Free</span>
          </div>
          <div class="telemetry-card">
            <span class="telemetry-lbl">ANGULAR TRAJECTORY DRIFT</span>
            <span class="telemetry-val indigo">4.2°</span>
            <span class="telemetry-lbl">Target Threshold &lt; 65°</span>
          </div>
        </div>
      </div>

      <div class="glass-panel">
        <div class="panel-header">
          <span class="panel-title">⚡ REAL-TIME HARNESS PIPELINE</span>
          <span style="font-size: 0.8rem; color: var(--accent-cyan);">TriggerTangle Offline Rehearsal</span>
        </div>
        <div class="panel-body">
          <div class="live-terminal">
[00:00:01.004] [AtlasCoordinator] Objective received: Multi-agent studio &amp; coding convergence.
[00:00:01.018] [FastgateTriage] 256-dim phase vector router mapped tools in 18 µs.
[00:00:01.042] [DaedalusArchitect] Pi exact substring edit committed with Rewind snapshot #snap-482.
[00:00:01.065] [VitruviusDesign] Sovereign glassmorphism theme compiled with Impeccable contrast floor.
[00:00:01.092] [LumiereStudio] ComfyUI Flux graph exported for 16:9 4K render.
[00:00:01.115] [OrwellScribe] Ghost Protocol passed: 0 banned clichés, sentence variance = 8.4.
[00:00:01.128] [MojoDrift] Angular trajectory: 4.2° (SAFE &lt; 65°). Status: VERIFIED.
          </div>
        </div>
      </div>
    </div>

    <!-- Right Panel: Live DAG Execution Milestones -->
    <div class="glass-panel">
      <div class="panel-header">
        <span class="panel-title">🕸️ ACTIVE TASK DAG</span>
        <span style="font-size: 0.8rem; color: var(--accent-emerald);">Verified WorkflowProof</span>
      </div>
      <div class="panel-body">
        {''.join(dag_items)}
      </div>
    </div>
  </div>
</body>
</html>
"""

        out_file = self.output_dir / "herald_hud.html"
        out_file.write_text(hud_html, encoding="utf-8")

        return {
            "status": "ready",
            "file": str(out_file),
            "system_title": system_title,
            "total_agents": len(roster),
            "total_milestones": len(milestones),
            "html_length": len(hud_html),
        }


# -------------------------------------------------------------------------
# Photocraft Layered Canvas Engine & Liquid Glass Material System
# -------------------------------------------------------------------------

@dataclass
class CanvasLayer:
    layer_id: str
    name: str
    kind: str             # "background", "vector", "typography", "asset", "filter", "overlay"
    x: int
    y: int
    width: int
    height: int
    opacity: float = 1.0  # [0.0, 1.0]
    blend_mode: str = "normal"  # "normal", "multiply", "screen", "overlay", "soft_light"
    z_index: int = 0
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiquidGlassMaterial:
    """Optical glassmorphism material specifications with dynamic refraction."""
    blur_px: int = 24
    transparency: float = 0.65
    refraction_index: float = 1.48
    specular_highlight: str = "rgba(255, 255, 255, 0.15)"
    surface_tint: str = "rgba(17, 24, 39, 0.70)"
    border_glow: str = "1px solid rgba(255, 255, 255, 0.12)"
    shadow_profile: str = "0 8px 32px 0 rgba(0, 0, 0, 0.37)"

    def to_css(self, class_name: str = "liquid-glass") -> str:
        return f"""
.{class_name} {{
  background: {self.surface_tint};
  backdrop-filter: blur({self.blur_px}px) saturate(180%);
  -webkit-backdrop-filter: blur({self.blur_px}px) saturate(180%);
  border: {self.border_glow};
  box-shadow: {self.shadow_profile}, inset 0 1px 1px 0 {self.specular_highlight};
  border-radius: 16px;
}}
"""


class PhotocraftCanvasEngine:
    """Layered digital canvas composer for UI assets, app icons, and marketing layouts."""

    PRESETS = {
        "app_icon": (1024, 1024, "iOS / macOS / Android Application Icon"),
        "social_banner": (1200, 630, "OpenGraph Social Preview Banner"),
        "hero_canvas": (1920, 1080, "High-Resolution 16:9 Hero Canvas"),
        "card_asset": (800, 1000, "Vertical Product / Card Visual"),
    }

    def __init__(self, output_dir: str | Path = "workspace_design"):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.layers: List[CanvasLayer] = []

    def create_canvas(self, preset: str = "hero_canvas", custom_dimensions: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        w, h, desc = (custom_dimensions[0], custom_dimensions[1], "Custom Canvas") if custom_dimensions else self.PRESETS.get(preset, (1920, 1080, "Default"))
        self.layers = [
            CanvasLayer(
                layer_id="layer_bg",
                name="Deep Canvas Background",
                kind="background",
                x=0,
                y=0,
                width=w,
                height=h,
                blend_mode="normal",
                z_index=0,
                properties={"fill": "#0B0F19", "gradient": "linear-gradient(135deg, #0B0F19 0%, #111827 100%)"},
            )
        ]
        return {"preset": preset, "width": w, "height": h, "description": desc, "layers": len(self.layers)}

    def add_layer(
        self,
        name: str,
        kind: str,
        x: int,
        y: int,
        width: int,
        height: int,
        blend_mode: str = "normal",
        opacity: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ) -> CanvasLayer:
        layer = CanvasLayer(
            layer_id=f"layer_{len(self.layers) + 1}",
            name=name,
            kind=kind,
            x=x,
            y=y,
            width=width,
            height=height,
            opacity=opacity,
            blend_mode=blend_mode,
            z_index=len(self.layers),
            properties=properties or {},
        )
        self.layers.append(layer)
        return layer

    def export_spec(self, title: str = "Photocraft Spec") -> Dict[str, Any]:
        return {
            "title": title,
            "total_layers": len(self.layers),
            "layers": [l.to_dict() for l in sorted(self.layers, key=lambda l: l.z_index)],
        }

