"""Design quality prompts — anti-AI-aesthetic checklist and frontend excellence."""

from __future__ import annotations


# The anti-AI design checklist encodes professional design principles
# that prevent the generic, repetitive aesthetic common in AI-generated UIs.
DESIGN_CHECKLIST = """
## Anti-AI Design Checklist (MANDATORY for all frontend work)

### Typography
- [ ] Line-height ≥ 1.4 on all body text (1.6 preferred for readability)
- [ ] Heading sizes follow a clear hierarchy (h1 > h2 > h3), never random
- [ ] Hero heading can be large (60-80px), but ALL other headings ≤ 48px
- [ ] Maximum 2 font families (1 for headings, 1 for body)
- [ ] Text has proper word-break and line-break consideration (no orphans)
- [ ] Letter-spacing is intentional (slightly wider for caps, tighter for large text)

### Spacing & Layout
- [ ] Consistent spacing scale (e.g., 4/8/12/16/24/32/48/64/96px)
- [ ] Generous whitespace between sections (minimum 64px, prefer 96-128px)
- [ ] Content width is constrained (max-width 1200-1400px for readability)
- [ ] Asymmetric layouts where appropriate (not everything centered)
- [ ] Grid system is consistent (12-column or similar)

### Visual Hierarchy & Section Design
- [ ] Each section is visually DISTINCT — alternate backgrounds, not all white
- [ ] At least 3 different section treatments (e.g., white, dark, gradient, image bg)
- [ ] Cards/features have subtle shadows, borders, OR background — not flat boxes
- [ ] Visual rhythm: alternate between text-heavy and visual-heavy sections
- [ ] Hero section has a strong visual anchor (image, 3D, gradient, or pattern)

### Color & Brand
- [ ] ALL colors from design tokens — ZERO hardcoded hex/rgb in components
- [ ] Maximum 5 brand colors (primary, secondary, accent, success, warning)
- [ ] Neutral palette with at least 8 shades (50-900)
- [ ] Sufficient contrast (WCAG AA minimum: 4.5:1 for text)
- [ ] Dark sections use lighter text with proper contrast

### Interaction & Motion
- [ ] Hover states on ALL interactive elements (buttons, links, cards)
- [ ] Smooth transitions (200-300ms, ease-out or cubic-bezier)
- [ ] Scroll-triggered animations for section reveals (subtle, not distracting)
- [ ] Button states: default, hover, active, disabled, loading
- [ ] Focus styles for keyboard navigation (visible, not just outline)

### Component Quality
- [ ] Loading states: skeleton screens or spinners for async data
- [ ] Empty states: meaningful messages with illustrations, not just "No data"
- [ ] Error states: user-friendly messages with recovery actions
- [ ] Responsive: mobile-first, works at 320px, 768px, 1024px, 1440px
- [ ] Images: lazy-loaded, properly sized, with fallbacks

### Anti-AI Aesthetic (CRITICAL)
- [ ] NO generic 3-column card grid as the default layout for everything
- [ ] NO uniform card heights when content varies — let it breathe
- [ ] NO gradient buttons everywhere — use solid colors as default
- [ ] NO oversized hero sections that push content below the fold
- [ ] NO icon-in-circle-with-text pattern repeated more than once per page
- [ ] Section layouts VARY — mix grid, offset, overlap, full-width, constrained
- [ ] Real visual interest through asymmetry, layering, or photography
"""


def design_quality_audit(task_id: str, task_title: str) -> str:
    """Prompt for frontend-specific design quality audit."""
    return (
        f'Design quality audit for task {task_id}: "{task_title}"\n\n'
        "**CRITICAL: You MUST use the Agent tool to spawn a NEW agent for this audit.**\n"
        "This agent must have ZERO context about how the UI was built.\n\n"
        "Call Agent with this prompt:\n\n"
        '  "You are a SENIOR UI/UX DESIGNER reviewing frontend code for design quality.\n'
        "  You are NOT checking functionality — you are checking VISUAL DESIGN EXCELLENCE.\n\n"
        "  1. Read the design brief at docs/refs/design-brief.md\n"
        "  2. Find all component/page files (*.tsx, *.jsx, *.vue, *.svelte, *.css)\n"
        "  3. Evaluate against this checklist:\n\n"
        f"{DESIGN_CHECKLIST}\n"
        "  4. For EACH checklist item, report: PASS / FAIL with specific file:line evidence\n"
        "  5. Overall verdict: PASS (80%+ items pass) or NEEDS_FIX\n"
        "  6. Top 3 most impactful improvements with specific code suggestions\n\n"
        '  Be STRICT. Generic AI aesthetic is an automatic FAIL."\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        f'{{"step":"design_audit","task_id":"{task_id}","auditor_id":"<agent-id>",'
        f'"verdict":"PASS"/"NEEDS_FIX","score":<0-100>,"issues":[...]}}'
    )


def design_brief_requirements() -> str:
    """Return the requirements for a design brief document."""
    return (
        "The design brief (docs/refs/design-brief.md) MUST contain:\n\n"
        "## 1. Color System\n"
        "- Primary, secondary, accent colors with hex values\n"
        "- Neutral palette (8+ shades from 50 to 900)\n"
        "- CSS custom properties for ALL colors (--color-primary, etc.)\n"
        "- Semantic colors: success, warning, error, info\n\n"
        "## 2. Typography\n"
        "- Font families (max 2: heading + body)\n"
        "- Size scale (xs, sm, base, lg, xl, 2xl, 3xl, 4xl)\n"
        "- Weight scale (regular 400, medium 500, semibold 600, bold 700)\n"
        "- Line-height values (tight 1.2, normal 1.5, relaxed 1.7)\n\n"
        "## 3. Spacing\n"
        "- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128px\n"
        "- Section padding: minimum 64px vertical\n"
        "- Content max-width: 1200-1400px\n\n"
        "## 4. Component Patterns\n"
        "- Button styles (primary, secondary, ghost, sizes)\n"
        "- Card variants (elevated, outlined, filled)\n"
        "- Input styles (default, focus, error, disabled)\n"
        "- Section backgrounds (at least 3 variants)\n\n"
        "## 5. Motion & Interaction\n"
        "- Transition duration: 200-300ms\n"
        "- Easing: ease-out or cubic-bezier(0.4, 0, 0.2, 1)\n"
        "- Hover scale/shadow patterns\n"
        "- Scroll animation triggers\n\n"
        "## 6. Anti-AI Aesthetic Rules\n"
        "- Vary section layouts (never repeat the same pattern)\n"
        "- Use asymmetry intentionally\n"
        "- Backgrounds must differ between adjacent sections\n"
        "- NO generic icon-in-circle grids\n"
    )
