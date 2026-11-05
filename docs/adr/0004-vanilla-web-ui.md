# ADR 0004: Server-rendered pages with own CSS and vanilla JavaScript

Status: accepted (2026-11-05)

## Context

The server has user-facing pages (OAuth2 sign-in and consent, document
selection and metadata entry, document details) and an administration UI
(users, clients, projects). They must look like one product, be secure under
a strict Content-Security-Policy, be easy to understand and deploy, and not
depend on build tooling or CDNs. Vanilla JavaScript is a project requirement.

## Decision

- Pages are rendered by Jinja2 from a shared `base.html` and component macros.
- Styling is our own CSS: `tokens.css` (colour, type, spacing, radius, light
  and dark), `base.css`, `components.css`. No CSS framework.
- Behaviour is vanilla JavaScript in ES modules loaded from our origin, used
  only for progressive enhancement (`fetch` against JSON endpoints, `<dialog>`
  confirmations, table sort and filter, inline validation). Every page works
  without JavaScript.
- No inline scripts or styles, no `on*` attributes, no `eval`, no `innerHTML`
  with server data (`textContent` and `<template>` instead). CSP:
  `default-src 'self'; frame-ancestors 'none'`.
- Icons are inline SVG from Lucide (ISC), the only third-party asset.
- Accessibility target WCAG 2.2 AA; Playwright with axe-core checks each page.

## Consequences

- No npm, no bundler, no framework upgrades; a deployer serves static files
  from the image.
- More hand-written UI code than with a framework, offset by a small page
  count and shared components.
- The style guide (`docs/ui-styleguide.md`) is normative for new pages.
