---
name: Orqestra Design System
version: 1.0.0
status: canonical
supersedes: all prior design specs, Stitch theme variants, and ad-hoc tokens
---

# Orqestra Design System

Single source of truth for Orqestra's frontend visual language and component
patterns. This document supersedes the Stitch-generated `DESIGN.md`, all theme
variants (`orqestra`, `refined_theme`, `eleven_labs_theme`, `diagnostic_view`),
and any prior Tailwind class conventions in the codebase.

When this document conflicts with a Stitch screen, this document wins.
When a Stitch screen shows a UI surface not specified here, treat it as
reference for visual language only — not as a feature spec.

---

## 1. Product Context

Orqestra is enterprise infrastructure for **AI estate coherence**: detecting
and resolving contradictions across multi-agent AI systems in production.
The UI is a **diagnostic console for platform engineers, ML infra leads, and
AI services teams** — not a marketing surface, not a consumer dashboard.

Visual reference points: Datadog, Honeycomb, Grafana, Linear.
Anti-references: any SaaS marketing site, Notion, Slack.

**Tone:** terse, technical, declarative. No marketing voice. No exclamation
marks. No emoji anywhere in product UI. Precise domain vocabulary:
*contradiction, claim, canon, blast radius, lineage, LCA, agent, system,
entity, org, tenant*.

---

## 2. Color Tokens

### 2.1 Base Surfaces

| Token | Hex | Usage |
|-------|------|-------|
| `--surface-0` | `#0F0F0F` | Page background, canvas |
| `--surface-1` | `#1A1A1A` | Cards, sidebar, panels, table body |
| `--surface-2` | `#272727` | Header bars, row hover, active nav, tooltips |
| `--surface-3` | `#333333` | Pressed states, nested elevated containers |

### 2.2 Accent

| Token | Hex | Usage |
|-------|------|-------|
| `--accent` | `#8DB2F5` | Primary actions, links, active nav indicator, focus ring, derivation edges, claim IDs |
| `--accent-hover` | `#A8C3F8` | Hover state on accent surfaces |
| `--accent-pressed` | `#6E96E0` | Pressed/active state |

### 2.3 Severity (Contradiction & Status Signals)

| Token | Hex | Usage |
|-------|------|-------|
| `--sev-critical` | `#F87171` | Critical contradictions, error states, mismatch, contradiction edges |
| `--sev-high` | `#FB923C` | High-severity contradictions |
| `--sev-medium` | `#FBBF24` | Medium-severity contradictions, pending states |
| `--sev-low` | `#9CA3AF` | Low-severity contradictions, deprioritized rows |
| `--ok` | `#4ADE80` | Resolved, verified, success states, diff additions |

Severity colors are reserved for **data semantics only**. Never use them
decoratively. Tag fill: severity color at 15% opacity + 1px solid border of
the same color at 100% opacity. Tag text: severity color at 100% opacity.

### 2.4 Text

| Token | Hex | Usage |
|-------|------|-------|
| `--text-primary` | `#FFFFFF` | Headlines, large numerics, primary table content |
| `--text-body` | `#E4E4E7` | Body text, claim text, default UI text |
| `--text-secondary` | `#A1A1AA` | Secondary metadata, helper text, system names |
| `--text-tertiary` | `#71717A` | Timestamps, counts, low-priority labels |
| `--text-disabled` | `#52525B` | Disabled controls, empty-state icons |

### 2.5 Borders & Dividers

| Token | Hex | Usage |
|-------|------|-------|
| `--border-default` | `#272727` | Card edges, table row dividers, input default |
| `--border-strong` | `#3F3F46` | Emphasized borders, button outlines |
| `--border-accent` | `#8DB2F5` | Focused inputs, selected items, LCA highlight |

### 2.6 Deprecated (Do Not Use)

The following tokens are dead. Remove on sight if found in the codebase:

- ❌ slate-950 (`#020617`)
- ❌ indigo `#6366F1`, `#8082F5`, `#818CF8`, `#A5B4FC`
- ❌ violet `#8B5CF6`
- ❌ Carbon Blue 60 (`#0F62FE`) — Carbon is a structural reference, not a color reference
- ❌ Any "purple" active-nav state (visible in some Stitch variants)

---

## 3. Typography

Strict dichotomy between **interface text** (Inter) and **data text**
(JetBrains Mono). The mono/sans split is the product's technical voice.

### 3.1 Type Scale

| Token | Family | Size | Weight | Line | Usage |
|-------|--------|------|--------|------|-------|
| `headline-lg` | Inter | 24px | 600 | 32px | Page titles, drill-in entity name |
| `headline-md` | Inter | 18px | 600 | 24px | Panel titles, modal headers |
| `body-md` | Inter | 14px | 400 | 20px | Default UI text, claim text, nav |
| `body-sm` | Inter | 12px | 400 | 16px | Helper text, captions |
| `label-caps` | Inter | 11px | 700 | 16px | Table headers, section labels (uppercase, +0.05em tracking) |
| `data-lg` | JetBrains Mono | 16px | 500 | 24px | Large numerics (dollar totals, stat tiles) |
| `data-md` | JetBrains Mono | 13px | 500 | 18px | Claim IDs, table data cells, entity names |
| `data-sm` | JetBrains Mono | 11px | 500 | 14px | Tag content, timestamps, hashes (+0.02em tracking) |

### 3.2 What Goes in Mono (non-negotiable)

- All identifiers (claim id, agent id, system id, entity id, contradiction id)
- All dollar amounts in tables and dashboards
- All timestamps
- All hashes
- All status pills / tag content
- All code, JSON, query input

### 3.3 What Stays in Inter

- Navigation labels
- Headlines and section titles
- Claim text content (the *meaning*, not the *identifier*)
- Helper text, descriptions, empty-state copy
- Button labels

---

## 4. Spacing & Layout

### 4.1 Baseline

- **4px baseline grid.** All spacing in multiples of 4.
- **Container padding:** 16px default, 12px in dense table cells.
- **Stack spacing:** 8px compact, 16px default, 24px section separator.
- **Gutter between panels:** 1px solid `--border-default` (NOT wide whitespace).

### 4.2 Sidebar & Page

- **Sidebar width:** 240px (collapsed: 48px icon rail).
- **Page max-width:** none — content fills available width.
- **Header height:** 48px.

### 4.3 Table Density

- **Row height:** 40px default, 32px compact.
- **Cell padding:** 12px horizontal, 8px vertical.
- **Header padding:** 12px horizontal, 10px vertical.
- **No zebra striping.** Ever. Row hover only.

### 4.4 Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Desktop | ≥1440px | Full 240px sidebar + multi-panel |
| Laptop | 1024–1439px | 240px sidebar + single panel |
| Tablet | 768–1023px | Icon rail (48px) + fluid panels |
| Mobile | <768px | Single column, sidebar in drawer |

Tablet and mobile are **degraded experiences**, not first-class. Orqestra is a
desktop product.

---

## 5. Shape & Elevation

### 5.1 Corner Radius

- **0px** (sharp corners) on all primary UI: buttons, cards, inputs, tags,
  tables, panels.
- **Exceptions:** circular avatars, circular status dots, severity-color dots.
- No `rounded-md`, no `rounded-lg`, no `rounded-xl`. Ever.

### 5.2 Elevation

Depth via **tonal layering**, not shadows. Shadows muddy high-density UI.

- **Level 0** `--surface-0` (#0F0F0F): page bg
- **Level 1** `--surface-1` (#1A1A1A): cards, sidebar, panels
- **Level 2** `--surface-2` (#272727): headers, active states, tooltips
- **Level 3** `--surface-3` (#333333): pressed states

The **only** shadow permitted: floating tooltips and modal scrims may use a
subtle `0 4px 12px rgba(0,0,0,0.4)` to lift above canvas.

### 5.3 Borders

1px solid `--border-default` separates containers. For active/selected
elements: 2px left-border or bottom-border in `--accent`.

---

## 6. Component Specs

### 6.1 Buttons

| Variant | Background | Text | Border | Use |
|---------|------------|------|--------|-----|
| Primary | `--accent` | `#0F0F0F` | none | Single most important action per surface |
| Secondary | `--surface-2` | `--text-body` | 1px `--border-strong` | Default action |
| Tertiary | transparent | `--accent` | none | Inline / link-style |
| Destructive | `--surface-2` | `--sev-critical` | 1px `--sev-critical` | Override, reject, escalate |

**States:** hover lifts background one level (e.g. primary `--accent` →
`--accent-hover`); focus adds 2px outline at `--border-accent` with 2px
offset; disabled drops opacity to 0.4 and removes pointer.

**Size:** 32px height default, 12px horizontal padding, `body-md` weight 500.
Icon buttons: 32×32px square.

### 6.2 Tags & Pills

**Severity tag:**
```
background: <severity-color> at 15% opacity
border: 1px solid <severity-color> at 100%
text: <severity-color>, data-sm, uppercase
padding: 2px 6px
shape: sharp 0px corners
```

**Status pill:** same anatomy, mapped colors:
- `pending` → `--sev-medium`
- `in-review` → `--accent`
- `resolved` → `--ok`
- `overridden` → `--text-tertiary`

**Agent / system chip:** `--surface-2` background, 1px `--border-default`,
`data-sm` mono text, 2px 6px padding.

### 6.3 Tables

- Sticky header on `--surface-2`, `label-caps` text.
- Body rows on `--surface-1`, 1px `--border-default` bottom divider.
- Row hover → `--surface-2`.
- Row selected → `--surface-2` + 2px left border `--accent`.
- Expanded row: pushes content down within same row container, no animation
  beyond 120ms ease-out height transition.
- Numeric / mono columns right-aligned. Text columns left-aligned.
- No zebra striping under any circumstance.

### 6.4 Inputs

- Background `--surface-1`, 1px `--border-default`.
- Focus: 1px `--border-accent` border + 2px outline `--border-accent` at 30%
  opacity, 2px offset.
- Placeholder text: `--text-tertiary`.
- Height 32px, padding 8px 12px.
- Filter inputs prefix with a lucide search icon at `--text-tertiary`.

### 6.5 Navigation (Left Rail)

- Width 240px, `--surface-1` background.
- Org switcher at top: 56px height, displays slug in `data-md` + caret.
- Nav items: 40px height, lucide icon (18px) + Inter `body-md` label.
- Active state: `--surface-2` background, 2px left border `--accent`, text
  `--text-primary`. Inactive text: `--text-body`.
- Hover (inactive): text → `--text-primary`, background unchanged.
- Bottom of rail: Docs link + org settings, separated by 1px divider.

The four nav items are: **Feed, Resolutions, Graph, Explorer.** No others.

### 6.6 Modals & Side Panels

- Side panel preferred over centered modal for detail views.
- Side panel: 480px wide, slides from right, `--surface-1` background, 1px
  `--border-default` left edge.
- Scrim: `#0F0F0F` at 60% opacity, dismissible by click.
- Header: 56px, panel title in `headline-md`, close icon (lucide X, 20px)
  top-right.
- Footer (if actions): 64px, 1px `--border-default` top, primary action
  right-aligned.

### 6.7 Toasts / Notifications

- Bottom-right anchored, 320px wide, `--surface-2` background, 1px
  `--border-default`.
- 4px left border in severity color (or `--accent` for info).
- Auto-dismiss 4s default, 8s for errors, never for critical.
- Stack vertically with 8px gap.

### 6.8 Empty States

- Centered vertically and horizontally in container.
- Single lucide icon, 20px stroke at `--text-disabled`.
- Headline: Inter `body-md` weight 500 at `--text-body`.
- Subtext: Inter `body-sm` at `--text-secondary`.
- One text-link action at `--accent`. Optional.
- **No illustrations, no emoji, no decorative elements.**

### 6.9 Loading States

- Skeleton shimmer on `--surface-1` blocks: 0% `--surface-1`, 50% `--surface-2`,
  100% `--surface-1`, 1.4s linear infinite.
- Inline spinners: lucide `loader-2` at `--accent`, 16px, `animate-spin`.
- Never block the full page; load surface-by-surface.

---

## 7. Domain Components

These are Orqestra-specific, not generic. They are first-class.

### 7.1 Severity Tag

See 6.2. Always includes severity label in caps (`CRITICAL`, `HIGH`, `MEDIUM`,
`LOW`). Never abbreviated to P0/P1/P2/P3 — that vocabulary is not used in the
codebase, API, or YAML presets.

### 7.2 Blast-Radius Tree

The single highest-value visual asset in the pitch. Renders the dollar
propagation from a root contradiction across descendant claims.

**Anatomy:**
- Root node at top: claim id (`data-md` mono, `--accent`), entity, $ amount
  (`data-md` mono, right-aligned, `--text-primary`).
- Descendants: indented 16px per level (max visible depth: 5).
- Decay visualization: each level's $ amount opacity decays per org config
  (consumer 0.50, clinical 0.70, finance 0.65, policy 0.60, general 0.50).
- Each node: claim id, agent chip, $ contribution.
- Footer summary line: `$<root> root → $<total> across <N> descendants (<×>)`
  in `data-md` mono.

**Surfaces:** `--surface-1` panel, 1px `--border-default`, 16px padding.

### 7.3 Lineage Node (ReactFlow)

Used in `/graph` canvas and `ContradictionLineageTree.tsx`.

**Anatomy:** ~140×60px tile, `--surface-1`, 1px `--border-default`, sharp
corners.

- Top row: claim id (`data-sm` mono, `--accent`) + agent chip
- Middle: entity name (`body-sm`, `--text-body`)
- Bottom: derivation type label (`data-sm` mono, `--text-tertiary`)

**Border color by claim type:**
- Default claim: `--border-default`
- Derived claim: `--accent` (1px)
- Canonical claim: `--text-primary` (1.5px)
- LCA: `--accent` (1.5px) + small `LCA` badge top-right

**Edge colors:**
- Contradiction: `--sev-critical`
- Derivation: `--accent`
- Canon link: `--text-primary`

Edge labels: `data-sm` mono mid-edge, `--text-secondary`.

### 7.4 Canon Resolution Card

Used wherever `GET /canon/resolve` output is rendered.

- Entity name in `data-md` mono, `--text-primary`.
- Consensus strength badge: `none | weak | emerging | strong | definitive`.
  Color ramp: `--text-tertiary → --sev-medium → --accent → --ok → --text-primary`.
- Canonical value in `body-md`, `--text-body`.
- Source count: "Derived from N claims across M agents" in `body-sm`,
  `--text-secondary`.

### 7.5 Diff View (Resolution Approval)

Used in Resolutions queue when approving a `CANON_UPDATE`.

- Two-column or unified view (toggle).
- Background `--surface-0`, mono font, 1px `--border-default`.
- Removed lines: `--sev-critical` at 15% opacity background, `--sev-critical`
  text strikethrough.
- Added lines: `--ok` at 15% opacity background, `--ok` text.
- Line numbers: `--text-tertiary`, `data-sm`.

### 7.6 Org Switcher

Top of left rail. Always visible. Multi-tenancy is a first-class concept.

- Current org slug in `data-md` mono.
- Dropdown caret right-aligned.
- On click: dropdown lists all orgs the user has access to (slug + name).
- Demo default: `demo-fitness`.

---

## 8. Route-by-Route Mapping

### 8.1 `/` — Contradiction Feed

**File:** `frontend/src/routes/ContradictionFeed.tsx`
**Endpoint:** `GET /contradictions`

**Layout:**
- Left rail (240px) + main content
- Header: page title "Contradiction Feed" (`headline-lg`) + count pill
  ("7 contradictions • $2,200 total exposure", `data-md` mono)
- Filter bar: severity multi-select, agent filter, entity filter, time range,
  search input — all on `--surface-1`
- Table:

| Column | Type | Width | Align |
|--------|------|-------|-------|
| Severity | Tag | 80px | left |
| Entity | mono | flex 1 | left |
| Claim summary | text | flex 2 | left |
| Agents | chips | 180px | left |
| Exposure ($) | mono | 120px | right |
| Detected | mono | 100px | right |
| Status | Pill | 100px | left |

- Row click → opens detail in side panel (preferred) or `/contradictions/:id`
  route.

### 8.2 `/contradictions/:id` — Drill-in

**File:** `frontend/src/routes/ContradictionDetail.tsx` (to be created)
**Endpoints:** `GET /contradictions/:id`, `GET /contradictions/:id/blast-radius`

**Layout:**
- Header: entity name (`headline-lg` mono), severity tag, total exposure
- Left column (60%): two stacked claim cards (the conflicting claims) with
  agent / system chips, confidence, claim text, timestamp
- Right column (40%): Blast-Radius Tree (see 7.2)
- Bottom: Resolution Actions (Accept canonical / Override / Escalate)
- "Lineage →" link opens `/graph?focus=:id` or modal

### 8.3 `/graph` — Knowledge Graph

**File:** `frontend/src/routes/KnowledgeGraph.tsx`
**Endpoint:** `GET /contradictions/:id/lineage-graph` (or full graph endpoint)

**Layout:**
- Collapsed nav rail (48px icon-only) for max canvas
- Full-bleed ReactFlow on `--surface-0` with 1px dot grid at `--surface-1`,
  24px spacing
- Floating panels (all on `--surface-1`, 1px `--border-default`):
  - Top-left: legend
  - Top-right: filters (entity, time window, depth slider 1–5)
  - Bottom-right: minimap
- Selected node: floating inspector tooltip with full claim text

### 8.4 `/resolutions` — Resolution Queue

**File:** `frontend/src/routes/Resolutions.tsx`
**Endpoints:** `GET /resolutions`, `PATCH /resolutions/:id` (when shipped)

**Layout:**
- 4 stat tiles at top: Pending / In review / Resolved today / Avg time
- Table:

| Column | Type | Align |
|--------|------|-------|
| Ticket ID | mono | left |
| Resolution Type | Badge | left |
| Entity | mono | left |
| Proposed action | text | left |
| Reviewer | chip | left |
| Status | Pill | left |
| Age | mono | right |

- Selected row opens side panel with: metadata, diff view (if `CANON_UPDATE`),
  reviewer comments, Approve / Reject actions

### 8.5 `/explorer` — Database Explorer

**File:** `frontend/src/routes/DatabaseExplorer.tsx`
**Endpoint:** filter-based queries against existing API endpoints

**NOT a SQL runner.** This is a power-user filter UI, not a query interface.
The Stitch screen showing "Filter by 'entity_id'..." is correct; any screen
implying SQL execution is hallucination.

**Layout:**
- Left rail (240px): collapsible tree of tables (claims, contradictions,
  resolutions, agents, systems, entities, events). Selected table highlighted
  with `--surface-2` + 2px left border `--accent`.
- Main: filter bar at top, result count, paginated table
- Row expand → inline JSON viewer (mono, `--surface-0` bg, syntax-highlighted)
- Top-right: Export CSV / Export JSON

---

## 9. What NOT to Do

- ❌ No marketing voice. No "Let's get started." No "Welcome to Orqestra."
- ❌ No emoji in product UI.
- ❌ No illustrative imagery in empty states.
- ❌ No rounded corners (except circles).
- ❌ No gradients.
- ❌ No glassmorphism, no backdrop-blur as decoration.
- ❌ No drop shadows (except tooltip/modal lift).
- ❌ No zebra striping.
- ❌ No P0/P1/P2/P3 severity vocabulary. Use `critical / high / medium / low`.
- ❌ No "Deploy Node," no "Logout" branding, no aspirational nav items.
- ❌ No "real-time" copy — Orqestra is near-real-time (Celery-backed).
- ❌ No reference to "distributed agent ecosystems." Use *multi-system
  AI estates* or *multi-agent AI systems*.
- ❌ No Carbon component imports (`@carbon/react`). Carbon is structural
  reference; implement via Tailwind.

---

## 10. Open Questions

These are not yet specified and should be raised before implementation:

1. **Auth surface.** No frontend auth currently. Pre-NeuralCraft pitch this
   is fine; for production it isn't.
2. **Toast positioning on mobile.** Bottom-right doesn't work on narrow
   viewports — needs spec if mobile becomes a real target.
3. **Hover preview for Blast-Radius Tree nodes.** Should clicking a descendant
   navigate to its own drill-in?
4. **Graph performance ceiling.** ReactFlow handles ~500 nodes well; beyond
   that needs virtualization. Out-of-scope for v1.

---

## Appendix A: Tailwind Token Mapping

For implementation in Tailwind 4 via `@theme`:

```css
@theme {
  --color-surface-0: #0F0F0F;
  --color-surface-1: #1A1A1A;
  --color-surface-2: #272727;
  --color-surface-3: #333333;

  --color-accent: #8DB2F5;
  --color-accent-hover: #A8C3F8;
  --color-accent-pressed: #6E96E0;

  --color-sev-critical: #F87171;
  --color-sev-high:     #FB923C;
  --color-sev-medium:   #FBBF24;
  --color-sev-low:      #9CA3AF;
  --color-ok:           #4ADE80;

  --color-text-primary:    #FFFFFF;
  --color-text-body:       #E4E4E7;
  --color-text-secondary:  #A1A1AA;
  --color-text-tertiary:   #71717A;
  --color-text-disabled:   #52525B;

  --color-border-default: #272727;
  --color-border-strong:  #3F3F46;
  --color-border-accent:  #8DB2F5;

  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  --radius: 0;
}
```

## Appendix B: lucide-react Icon Usage

- Stroke width: 1.5px default (Carbon-adjacent feel).
- Sizes: 16px (inline), 18px (nav), 20px (empty state), 24px (large affordance).
- Default color: inherit from text token.
- No filled icons. Outline only.
