# Template conventions & styling

Conventions for Django/Wagtail HTML templates. The **markup/JS conventions**
below apply to every template (admin and public frontend); the **CSS custom
property** rules are context-specific (admin vs. frontend). The running example
is the health dashboard panels under `ingestion/templates/capagg_ingestion/`,
which extend `wagtailadmin/base.html`.

## Markup & JS conventions

- **No inline styles** — never use `style="..."` attributes. Extract all CSS into
  a `{% block extra_css %}<style>…</style>{% endblock %}` block and give elements
  semantic class names.
- **Modern JS** — use `const` and `let`; never `var`.
- **JS placement** — all JavaScript goes in `{% block extra_js %}…{% endblock %}`
  at the bottom of the template. Wrap code in
  `document.addEventListener('DOMContentLoaded', function () { … })` rather than
  an IIFE `(function () { … }())`.

## CSS custom properties: which to use

| Context                                                          | Variables     | Where defined                                |
|------------------------------------------------------------------|---------------|----------------------------------------------|
| **Wagtail admin** templates (`extends "wagtailadmin/base.html"`) | `--w-color-*` | Wagtail 7 admin CSS                          |
| **Public frontend** (Vue/MapLibre SPA, non-admin templates)      | `--color-*`   | Our own frontend CSS (project design tokens) |

**Never mix token families.** The two contexts are separate CSS worlds:

- In **admin** templates, use Wagtail 7's `--w-color-*` tokens only. Wagtail 7
  removed the old unprefixed `--color-*` aliases entirely, so a bare `--color-*`
  in an admin template resolves to nothing and falls back to the browser default.
- In the **public frontend**, define and use our own `--color-*` design tokens
  (declared in the frontend's own CSS, per the `extra_css` convention in
  `docs/design.md` §9). Never reference Wagtail's `--w-color-*` tokens here —
  they aren't loaded outside the admin.

> The public frontend is still a stub (`docs/design.md` §9 pages are TODO). The
> concrete `--color-*` token set isn't established in code yet; when the SPA
> styling lands, list the canonical tokens here the way the admin tokens are
> listed below.

## Key `--w-color-*` tokens

- **Borders:** `--w-color-border-furniture`
- **Muted / secondary text:** `--w-color-grey-400`
- **Subtle backgrounds / panel-header bg:** `--w-color-grey-50`, `--w-color-grey-100`
- **Menus & surfaces:** `--w-color-surface-menus`, `--w-color-surface-field`, `--w-color-surface-page`
- **Labels / primary text:** `--w-color-text-label`
- **White:** `--w-color-white`
- **Status colours:** `--w-color-info-100`, `--w-color-positive-100`, `--w-color-warning-100`, `--w-color-critical-200`
