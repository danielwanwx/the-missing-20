# Silver Solid-Spectrum Dashboard Theme

**Date:** 2026-09-05  
**Status:** Approved for implementation  
**Visual reference:** `.superpowers/brainstorm/29208-1788590273/content/silver-solid-spectrum-v3.html`

## Objective

Replace the current near-black command canvas with a light silver-gray workspace that is easier to read in a recorded demo. Preserve the existing information architecture, Agent workflow, interactions, and state model. Use saturated solid colors for important data channels and lifecycle stages so live activity remains visually prominent.

## Visual direction

The page uses a neutral silver-gray canvas rather than pure white. Top-level modules use opaque white or fog-white surfaces with restrained layered shadows. Structural separators remain low-contrast gray; large decorative borders are not introduced.

Primary text becomes deep charcoal. Secondary text uses a medium gray-blue that remains readable on white and silver surfaces. Dynamic quantities retain Geist Mono and tabular numerals. Disabled controls remain visibly inactive without becoming illegible.

The theme must not use rainbow gradients, translucent muddy colors, or broad neon glows. A short brightness pulse is allowed only when a real event activates a line, node, tool call, or timeline item. The resting state always returns to a flat solid color.

## Solid color semantics

| Solid color | Purpose |
| --- | --- |
| Cyan `#008CA0` | Control context and ERP evidence |
| Blue `#256CD3` | Business evidence and Airtable reads |
| Violet `#7550BD` | Integration evidence and Agent reasoning |
| Orange `#D76416` | Human approval and controlled execution |
| Lime `#85A900` | Successful verification and resolved outcome |
| Coral `#CF473C` | Incident, rejection, or blocked state |

Colors are assigned through semantic classes or variables, not through position-dependent selectors. The same source or lifecycle stage must use the same solid color in its node, connector, tool receipt, and timeline event.

## Surface hierarchy

1. The application background is a subtle, non-animated silver-gray field.
2. The navigation bar is an opaque light surface with a quiet divider.
3. Signals, Investigation, Agent, Manager Decision, and Outcome are independent white floating modules with soft elevation.
4. Inner metrics and tool rows use a cooler light-gray fill; they do not become additional framed cards.
5. Agent remains the strongest focal node using a pale lime surface with dark text. Source nodes remain white with a solid colored edge or label.

The approved borderless command-canvas structure remains intact. Modules may still be focused, dragged, resized, and reset. No module is wrapped in a new descriptive container.

## Connectors and live state

SVG connectors remain thin, smooth, and free of endpoint dots. Each connector inherits the solid color assigned to its source. Aligned nodes retain straight connectors; offset nodes retain direction-aware curves.

Live events may temporarily increase connector opacity or brightness. Motion remains event-driven and must stop when the stream is paused or disconnected. Reduced-motion users receive the same status through color and labels without animation.

## Component changes

- Replace dark global color tokens with silver-gray background, white surface, charcoal text, and readable gray-blue secondary text.
- Update top navigation, incident ribbon, command-canvas modules, atomic nodes, evidence rows, tool receipts, timeline events, decision controls, chat input, and resolution packet to the new surface hierarchy.
- Add semantic solid-color variants for ERPNext, Airtable, Celigo, Jira, Slack, Manager, verification, and incident states.
- Keep all existing DOM identifiers, event bindings, API contracts, local layout persistence, and state transitions unchanged.
- Keep local Geist and Geist Mono assets; no new dependency or remote asset is introduced.

## Responsive behavior

Desktop retains the three-column command canvas. Narrow layouts stack modules in the existing order. Shadows become lighter on small screens, while text contrast and the pure-color lifecycle encoding remain unchanged. Interactive controls keep the existing minimum hit areas.

## Accessibility

- Charcoal text on white/silver surfaces must meet normal-text contrast requirements.
- Solid state colors are never the only signal; labels and icons remain present.
- Focus-visible outlines use a high-contrast blue or lime appropriate to the local surface.
- Disabled, empty, loading, blocked, and verified states must remain distinguishable without animation.
- `prefers-reduced-motion` continues to disable non-essential pulses.

## Validation

Implementation is complete only after:

1. The dashboard is captured at the same 1440 × 1000 verified state as the existing dark-theme reference.
2. A side-by-side comparison confirms the silver-gray canvas, white module hierarchy, charcoal typography, and pure-color data encoding.
3. Normal, incident, diagnosis, manager review, execution, verification, disconnected, and narrow-screen states remain readable.
4. Node popovers, module focus, arrange/resize/reset, Agent chat, Manager approval, execution, and verification still work.
5. Browser smoke reports no console errors.
6. JavaScript and Python regression suites pass.

## Non-goals

- No workflow, backend, API, data-source, or Agent prompt redesign.
- No light/dark theme switcher in this change.
- No rainbow gradients, glassmorphism, decorative illustration, or additional explanatory copy.
- No new pages, routes, dependencies, or production write permissions.
