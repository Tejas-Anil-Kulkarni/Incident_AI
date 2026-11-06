# Dashboard Page Override — IncidentMind

> This page override takes precedence over the generated global palette. The
> user reference is the light Mecha Capital site at `https://mecha-xyz.webflow.io/`.

## Direction

Translate the reference's editorial restraint into an incident console: white
space, a strong wordmark, large serif hero headline, small uppercase metadata,
fine rules, numbered sections, and a custom technical line illustration.
Keep the dashboard calm and highly legible; use incident colors only for
meaningful severity and outcome states.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--paper` | `#F7F7F4` | Overall canvas |
| `--surface` | `#FFFFFF` | Interactive content surfaces |
| `--ink` | `#171715` | Primary text and controls |
| `--body` | `#3F3F3B` | Paragraphs and incident details |
| `--muted` | `#676761` | Secondary labels (maintain 4.5:1 contrast) |
| `--rule` | `#C9C9C2` | Section and table dividers |
| `--rule-strong` | `#85857D` | Control edges and selected states |
| `--danger` | `#8E241B` | Critical/failed state, paired with text |
| `--warning` | `#704800` | Degraded/partial state, paired with text |
| `--success` | `#185B3B` | Resolved state, paired with text |

No rounded dashboard tiles, gradients, glass effects, or soft decorative
shadows. Use square corners, clear dividers, and consistent 4/8 px spacing.

## Typography and layout

- Wordmark and controls: bold geometric sans-serif, uppercase and tracked.
- Hero heading: Georgia/system serif, large and lightly weighted.
- Body: system sans-serif, 12–15 px for core copy, with small monospace metadata used only for labels and IDs.
- IDs and timestamps: system monospace with tabular figures.
- Wide canvas capped around 1,440 px. Stack columns and retain all labels at
  narrow widths; no horizontal scrolling.
- Navigation uses labeled, keyboard-operable React tab controls and remains readable at narrow widths.

## Interaction and accessibility

- Use native buttons, select boxes, forms, and expanders with visible labels.
- Keep a visible 2 px focus outline and color contrast at least 4.5:1 for
  regular text. Status also uses a written label, never color alone.
- Async API actions show progress and return inline success/error feedback.
- Respect `prefers-reduced-motion`; transitions are limited to subtle opacity
  and color changes.
- Replay chart is shown only when enough measured values exist; always provide
  the raw step table and labels as an accessible alternative.
- Decorative SVG line art is hidden from assistive technology.
