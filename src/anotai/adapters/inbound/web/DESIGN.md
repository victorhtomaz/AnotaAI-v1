---
name: Academic Temporal Studio
colors:
  surface: '#fcf9f2'
  surface-dim: '#dcdad3'
  surface-bright: '#fcf9f2'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3ec'
  surface-container: '#f0eee7'
  surface-container-high: '#eae8e1'
  surface-container-highest: '#e4e2db'
  on-surface: '#1b1c18'
  on-surface-variant: '#404849'
  inverse-surface: '#30312c'
  inverse-on-surface: '#f3f1ea'
  outline: '#707979'
  outline-variant: '#bfc8c9'
  surface-tint: '#2a676c'
  primary: '#00464b'
  on-primary: '#ffffff'
  primary-container: '#1f5e63'
  on-primary-container: '#9ad5db'
  inverse-primary: '#95d1d6'
  secondary: '#0e696f'
  on-secondary: '#ffffff'
  secondary-container: '#a4eff7'
  on-secondary-container: '#1a6f76'
  tertiary: '#593710'
  on-tertiary: '#ffffff'
  tertiary-container: '#744e25'
  on-tertiary-container: '#f6c18f'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b1edf2'
  primary-fixed-dim: '#95d1d6'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#064f54'
  secondary-fixed: '#a4eff7'
  secondary-fixed-dim: '#88d3da'
  on-secondary-fixed: '#002022'
  on-secondary-fixed-variant: '#004f55'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#f0bd8b'
  on-tertiary-fixed: '#2c1600'
  on-tertiary-fixed-variant: '#623f18'
  background: '#fcf9f2'
  on-background: '#1b1c18'
  surface-variant: '#e4e2db'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 44px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  transcript-focus:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 24px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  timestamp-tag:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.04em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.25rem
  margin: 1rem
  margin-desktop: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

The design system establishes a high-performance academic workspace designed for deep cognitive focus, cross-media verification, and temporal synthesis. It caters to university students, academic researchers, and lifelong learners navigating complex lecture recordings paired with dense textbook chapters and presentation slides.

The aesthetic fuses **Modern Academic Ergonomics** with **Instrumental Utility**:
- **Tone & Demeanor:** Methodical, sharp, erudite, and reliable. It rejects gamified distraction in favor of institutional clarity and technical precision.
- **Visual Stance:** Grounded in a parchment-and-slate foundation that emulates high-grade archival paper while retaining the crisp operational efficiency of modern developer and transcription environments.
- **Temporal Fluidity:** Visual cues prioritize chronological alignment, bidirectional hyperlinking (audio transcript to slide page), and atomic bookmarking.

## Colors

The palette balances clinical legibility with warm, paper-inspired undertones to counteract eye fatigue during multi-hour lecture analysis.

- **Primary (`#1f5e63` - Pine Cyan):** Represents authority, structural navigation, primary action affordances, and active video scrub states.
- **Secondary (`#2a7a81` - Lighter Teal):** Used for interactive hovered nodes, secondary highlights, active audio frequency representations, and transcript focus spans.
- **Tertiary (`#d4a373` - Warm Amber):** Reserved strictly for semantic bookmarks, highlighted transcript notes, citation anchors, and user-generated marginalia.
- **Dark Neutral (`#1e293b` - Slate Dark):** High-contrast typography base ensuring readability across dense textual transcripts and metadata labels.
- **Canvas Base (`#e8e6df` - Warm Parchment):** The foundation framing layer for outer borders, split-pane dividers, and structural chassis.
- **Surface Elevation (`#f8f8f6` - Pure Field):** High-purity white stone applied to PDF viewers, transcript blocks, and search cards to isolate primary reading tasks from the utility chrome.

## Typography

Typography governs information density across three distinct functional roles:

1. **Structural Headers (`Plus Jakarta Sans`):** Warm geometric construction with tight apertures, lending an authoritative yet modern stance to document titles, lecture series, and module hierarchies.
2. **Dense Reading & Synthesized Text (`Inter`):** Neutral grotesque proportions designed for sustained reading across transcripts, OCR extractions, and AI-generated concept syntheses.
3. **Temporal Markers & System Telemetry (`JetBrains Mono`):** Fixed-width baseline adherence for playback timecodes (`00:14:22.04`), slide synchronization indexes (`p. 182 -> [00:43:10]`), keyboard shortcuts, and confidence metrics. Ensures scrub indicators and numerical metrics do not cause horizontal layout jitter.

## Layout & Spacing

The system implements a rigid **Multi-Pane Modular Workspace Studio** optimized for wide-gamut monitors and dual-viewport reference:

- **Desktop (>=1280px):** 3-column asymmetric layout:
  - *Left Pane (Collapsible, 280px-340px):* Knowledge graph index, lecture outline, search query results.
  - *Center-Left Pane (Fluid 40-50%):* Synchronized AV media player docked above an interactive waveform/event timeline.
  - *Center-Right Pane (Fluid 50-60%):* Dual-state PDF slide reader / interactive transcript with bidirectional scroll anchoring.
- **Tablet (768px-1279px):** Split-view vertical stack: AV player pinned to top 40vh; tabbed switcher beneath toggling between PDF Reader and Live Transcript.
- **Mobile (<768px):** Linear stacked stream: 16:9 sticky player at viewport ceiling; compact timeline scrub strip; swipeable card interface for slides and context transcript.
- **Rhythm:** An 8px base rhythm (`space-xs` = 4px, `space-sm` = 8px, `space-md` = 12px, `space-lg` = 20px, `space-xl` = 32px) controls internal pane padding, avoiding excessive whitespace to maximize data surface area.

## Elevation & Depth

Visual hierarchy uses **Architectural Paneling with Low-Contrast Hairline Outlines** rather than heavy floating drop shadows:

- **Surface Tiers:**
  - *Base Layer (`#e8e6df`):* The outer workbench canvas and split-pane dividers.
  - *Pane Surfaces (`#f8f8f6`):* Inset panels with a `1px solid rgba(30, 41, 59, 0.12)` boundary.
  - *Active Reading Focus:* Highlighted transcript blocks switch from pure transparent to `#ffffff` with a subtle left accent border (`3px solid #1f5e63`).
- **Overlays & Drawers:** High-utility slide-overs (AI Semantic Search, Citations, Marginalia Notes) feature a faint atmospheric drop shadow: `0 8px 24px -4px rgba(20, 66, 70, 0.12), 0 2px 6px -1px rgba(20, 66, 70, 0.06)`, framed with a crisp boundary outline.
- **Scrubber & Temporal Cursors:** Playheads and current slide badges float above media elements with zero blur, leveraging pure color contrast (`#d4a373` and `#144246`) to maintain distinct visual planes.

## Shapes

The geometric architecture is **Soft (Level 1)** to preserve an engineered, document-first aesthetic:

- **Base Radius (4px / 0.25rem):** Applied to buttons, input fields, timestamp badges, code blocks, and tab switches. Maintains maximum perimeter efficiency for dense UI layouts.
- **Medium Panels (8px / 0.5rem):** Modals, search dropdown menus, docked video containers, and thumbnail slide cards.
- **Outer Shells (12px / 0.75rem):** Main workspace viewport viewports and floating dock controls.
- **Pill Exceptions:** Restricted exclusively to interactive audio scrubber thumbs and active recording status indicators.

## Components

### Buttons & Interactive Controls
- **Primary Studio Action:** Deep Teal background (`#1f5e63`), white text, 4px border radius, subtle hover shift to `#144246`. Height: 32px (compact studio standard) or 40px (prominent).
- **Secondary Tool Button:** Transparent background, `1px solid rgba(30, 41, 59, 0.2)`, slate text (`#1e293b`). On hover: `#e8e6df` fill.
- **Icon Action Utilities:** 28x28px click targets for split-screen orientation toggles, PDF zoom steps, and playback rate controllers.

### Timestamp Badges & Temporal Chips
- Built with `JetBrains Mono` font tokens.
- **Synced Audio Node:** Background `#e8e6df`, text `#1f5e63`, 4px radius, `padding: 2px 6px`. Clicking immediately drives AV playback to the correlated second.
- **Active Timestamp Node:** Background `#1f5e63`, text `#ffffff`.
- **Bookmark / Marginalia Tag:** Background `rgba(212, 163, 115, 0.15)`, text `#8a5a2b`, bordered with `#d4a373`.

### Transcript Stream & Annotation Lists
- Continuous scroll stream aligned with time offsets.
- Inactive speaker text: Slate dark (`#1e293b`), opacity 0.85, line-height 1.6.
- Active playing span: Marked with a `#2a7a81` soft background highlight tint and solid `#1f5e63` margin line.
- Text selection triggers an inline context menu: "Link to Slide", "Generate AI Summary", "Save to Flashcards".

### Synchronized Timeline Track
- Horizontal multi-tier scrub bar:
  - *Tier 1:* Audio waveform amplitude map.
  - *Tier 2:* PDF slide transition markers (numbered pips matching slide document sequence).
  - *Tier 3:* User bookmark flags (`#d4a373`).

### PDF Viewer Frame
- Clean parchment-white matting with page boundary shadows eliminated in favor of a clean hairline frame (`#e8e6df`).
- Dual-indicator cursor showing OCR bounding boxes mapped directly to words spoken within the active 5-second video window.

### Form Inputs & Search Bar
- Studio Search Input: Hairline border with inset background `#ffffff`. Focused state switches border to `#1f5e63` with a zero-blur outline ring (`2px solid rgba(31, 94, 99, 0.2)`). Accompanied by fixed-width keyboard command badges (`⌘K` rendered in `label-sm`).