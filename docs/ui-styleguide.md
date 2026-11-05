# UI style guide

Every page the server renders (sign-in and consent, Documents API pages,
account, administration) shares one look and one set of rules. This guide is
normative for new pages (ADR 0004).

## Principles

1. **Server-rendered, works without JavaScript.** Every action is a form POST;
   JavaScript only makes things smoother (filtering, sorting, confirmation
   dialogs, copy buttons).
2. **One source of design.** Colours, type, spacing and radii come from
   `opencde/ui/static/css/tokens.css`; components from `components.css`. Never
   hard-code a colour or a pixel value in a template.
3. **Strict CSP.** No inline `<script>` or `style=`, no `on*` attributes, no
   `innerHTML` with server data, no CDN. Scripts are ES modules under
   `/static/js/`, loaded with `<script type="module">`.
4. **Secure by default.** Every form carries a signed `form_token`; pages that
   change data check it, the browser's `Sec-Fetch-Site`/`Origin`, and for
   dangerous actions the user's own password. Secrets are shown once.
5. **Accessible.** Semantic HTML, real `<label>`s, visible focus, WCAG 2.2 AA
   contrast, `aria-current`, `role="status"` for notices. Playwright with
   axe-core checks every admin page (`uv run pytest -m ui`).

## Layout

- `base.html`: header (brand + `{% block nav %}`), `<main id="main">`, footer.
  Use `page--narrow` as the body class for single-column forms.
- Admin pages extend `admin/_page.html`: side navigation (`admin_nav`), a
  notice area, then the page in `{% block admin %}`. Content is a column of
  `.card`s, each with one `<h2>`.
- Tables live in `.table-wrap > table.table`. Add `data-filterable` for a
  filter box (appears when there are more than five rows) and
  `data-sortable` for click-to-sort headers.

## Components (macros, available in every template)

| Macro | Use |
|---|---|
| `field(name, label, type, value, …)` | Text, password, e-mail, URL inputs with label and optional hint |
| `select_field(name, label, options, selected)` | `<select>`; `options` is a list of `(value, text)` |
| `textarea_field(name, label, value, rows)` | Multi-line input, one value per line for lists |
| `checkbox(name, label, checked)` | A boolean with its label |
| `confirm_password(form_id)` | The "your password" field dangerous forms need |
| `button(text, kind, name, value)` | `primary`, `secondary`, `danger`; `formnovalidate` for Cancel |
| `alert(kind, text, title)` | `error`, `success`, `warning`, `info` boxes |
| `notice_box(notice, kind)` | The result of the previous action (from `?notice=`) |
| `user_nav(web_user, signout_token)` | Signed-in user and sign-out form in the header |
| `when(iso)` | A `<time>` element for an ISO timestamp |

Badges: `.badge` (accent), `.badge--neutral`, `.badge--success`, `.badge--danger`.
Danger zones: `.card.card--danger` with one form per destructive action and
`data-confirm="question"` on the form.

## Tokens

Change the brand in `tokens.css` only: `--color-accent` and its `-strong` and
`-soft` variants. Light and dark follow the system setting. Type scale
`--text-xs … --text-xl`, spacing `--space-1 … --space-7`, radii `--radius-sm/md/lg`.

## Mark

The server's mark is the sibling of Dataspatium's: where Dataspatium shows
three stacked sheets, Kontroll shows three connected nodes (a graph): hollow
rings of radius 2.6, one at the middle left joined by two lines to the two at
the right, white on the same blue plate `#2b6cb0` with corner radius 7 in a
32-unit square, everything at the same stroke width 2.2. The white ink keeps
Dataspatium's margins exactly (x 7.4–24.6, y 5.08–26.92 of the box). The
source is
`opencde/ui/static/icon.svg`; `icon-32.png`, `icon-180.png`, `icon-192.png`,
`icon-512.png` and `favicon.ico` are rendered from it (the PNGs with Edge
headless on a transparent background, the ICO wrapping the 16, 32 and 48 px
PNGs). Use the SVG wherever the page can, keep the plate, and do not recolour
the mark.

## Writing

- Short headings that name the object: "Users", "New project", "Danger zone".
- Buttons say what happens: "Create user", "Rotate secret", not "OK".
- Hints explain consequences in one sentence next to the field.
- Error and notice texts never echo user input and never reveal whether an
  account exists ("The user name or password is not correct.").
- English in the UI; terms follow the specifications (topic, viewpoint,
  client, redirect URI, scope, role).

## JavaScript rules

- One entry module per page type (`admin.js`), importing small modules
  (`table.js`, `confirm.js`, `copy.js`). Build DOM with `createElement` and
  `textContent`.
- Enhance only what exists: read `data-*` attributes, never configuration
  from inline scripts.
- Keep behaviour reversible: a page must do the right thing if the module
  fails to load.
