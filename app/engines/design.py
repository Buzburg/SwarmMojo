"""Design Agent Engine for SwarmMojo.

High-craft UI, GUI, and Website generation engine inspired by:
- Impeccable (Craft Floor, WCAG AAA contrast, typographic measures, subtle depth, zero-halo shadows)
- UI-UX Pro Max (Design system tokens, components, banner layouts, responsive safe-zones)
- AgentSite (Multi-agent pipeline: PM -> Designer -> Developer -> Reviewer for single & multi-page websites)
- Filament 4.x (Enterprise admin panel schemas, data tables, metrics widgets, forms)
- UI Builder & Shadcn (Component registries: cards, dialogs, navbars, charts, hero sections)
- OSW Studio (Desktop Electron / web GUI canvas & layout generation)
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
        """Generates an enterprise Filament/Shadcn-style GUI dashboard layout."""
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
