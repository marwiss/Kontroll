# UI style guide

Every page the server renders (sign-in and consent, Documents API pages,
account, administration) shares one look and one set of rules. This guide is
normative for new pages (ADR 0004).

## Principles

1. **Server-rendered, works without JavaScript.** Every action is a form POST;
   JavaScript only makes things smoother (filtering, sorting, confirmation
   dialogs, copy buttons).
2. **One source of design, and it is Dataspatium's.** The owner decided that
   the server's pages and the Dataspatium app share one look, based on
   Dataspatium's, and as Dataspatium's copyright holder permitted Dataregium to
   use that design despite the different licences (2026-11-05). Colours,
   type, spacing and radii come from `opencde/ui/static/css/tokens.css`,
   which carries Dataspatium's tokens with their `--dm-*` names; components
   from `components.css`, which expresses Dataspatium's components on the
   server's plain HTML. Never hard-code a colour or a pixel value in a
   template, and when Dataspatium's tokens change, change ours the same way.
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

Badges: `.badge` (accent), `.badge--neutral`, `.badge--success`,
`.badge--warning`, `.badge--danger`. Danger zones: `.card.card--danger` with
one form per destructive action and `data-confirm="question"` on the form.

## Tokens and the shared look

`tokens.css` is Dataspatium's token file (`src/ui/design/tokens.css` there)
minus the data palette and the panel layout the app alone needs. The names
are the same, `--dm-*`, so that a value can be compared line by line:

- Type: Inter (self-hosted under `/static/fonts/`, SIL Open Font License,
  weights 400, 500 and 600), scale `--dm-text-xs` 12 px … `--dm-text-2xl`
  24 px, body 15 px, line height 1.45.
- Spacing: the 4 px scale `--dm-s-1` … `--dm-s-12`.
- Shape: `--dm-radius-sm` 6 px for controls, `--dm-radius-md` 10 px for cards
  and dialogs; shadows only on dialogs.
- Colour: the neutral scale, the semantic surfaces and text, the accent
  (`#2b6cb0`, the mark's blue), the status colours `ok`/`warn`/`error`, each
  with a `-soft` background, and the dark theme under
  `:root[data-theme="dark"]` and `prefers-color-scheme: dark`.
- Layout: the top bar is `--dm-topbar-h` 48 px, the footer `--dm-statusbar-h`
  28 px, the administration's side navigation `--dm-panel-min-w` 200 px;
  below 760 px the layout stacks and controls grow to 44 px touch targets.

The components map onto Dataspatium's like this:

| Dataregium class | Dataspatium component | Look |
|---|---|---|
| `.btn`, `--primary`, `--secondary`, `--ghost`, `--danger`, `--small` | `dm-button` with `variant` and `size` | 32 px (26 px small), radius 6 px, 13 px medium text; primary filled accent; danger red text, red on hover |
| `.input`, `.select`, `.textarea`, `.field__label`, `.field__hint` | `.dm-field`, `.dm-label`, `.dm-help` | 32 px, input border, focus ring inside; textareas monospace |
| `.badge` | `dm-badge` | pill, 12 px medium |
| `.card` | `dm-panel[card]`, `.dm-card` | surface, border, radius 10 px, no shadow |
| `.table` in `.table-wrap` | `dm-table` | 13 px, header on surface-2 at 34 px, 30 px rows, sorted header in accent |
| `.nav a`, `.sidenav__list a` | `.dm-list-item` | 13 px, radius 6 px, hover surface, current accent-soft |
| `.alert` | `.dm-toast` | surface with a 3 px coloured left edge |
| `dialog` | `dialog.dm-dialog` | 560 px, radius 10 px, large shadow, backdrop |
| `.consent` | `.dm-course-task` | surface-2 with an accent left edge |
| `.stat` | a card with `--dm-text-2xl` | tabular numbers |

Dataspatium's rules hold on the server's pages too: at most one primary
button per view; destructive actions use the danger variant and a
confirmation dialog; numbers right-aligned with tabular figures; dates
`YYYY-MM-DD`, times `HH:MM`; everything reachable by keyboard with a visible
focus ring; no animation beyond short transitions, none at all under
`prefers-reduced-motion`.

## Mark

The server's mark is the sibling of Dataspatium's: where Dataspatium shows
three stacked sheets, Dataregium shows three connected nodes (a graph): hollow
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
- Every text comes from the language catalogues through `t("key")` (see
  "Language layer" below); English is the source and the other six languages
  follow Dataspatium's glossary. Terms follow the specifications (topic,
  viewpoint, client, redirect URI, scope, role) and API terms stay as they
  are in every language.

## Language layer

The pages exist in the seven languages of the README. The mechanics are
Dataspatium's: one flat catalogue per language in `opencde/ui/i18n/<lang>.json`
with dotted keys and `{name}` parameters, the same key names where the two
products share a concept (`opencde.signin`, `opencde.signout`,
`opencde.project`, `opencde.kind.topics`, `common.cancel`, `common.save` …),
and our own areas for the rest (`nav.*`, `account.*`, `docs.*`, `admin.*`,
`notice.*`, `js.*`).

- Templates and macros call `t("key")` or `t("key", name=value)`; the
  language of the request sits in a context variable that `render()` sets,
  so imported macros translate too. Python code that builds a page text
  before rendering uses `tr(request, "key")`.
- The language is chosen per request: `?lang=xx` (remembered in the
  `opencde_lang` cookie for a year), the cookie, the browser's
  `Accept-Language` (plain `no` means Bokmål), English. The footer of every
  page carries the switcher.
- Scripts never hold texts: `base.html` puts the few strings the scripts need
  in `data-t-*` attributes on `<html>` (filter box, row counts, the
  confirmation dialog, copy feedback).
- A missing key in another language falls back to English; a key missing
  everywhere renders as the key itself. The unit test
  `test_every_language_has_every_key_of_the_english_source` keeps the seven
  catalogues identical in their key sets and parameters, so add every new key
  to all of them in the same commit.
- The messages that the account, project and client code raise on invalid
  input (`UserFacingError` with a key and parameters, shared with the CLI)
  are translated at the page boundary with `tr_error(request, exc)`; the CLI
  and the API keep the English text.

## JavaScript rules

- One entry module per page type (`admin.js`), importing small modules
  (`table.js`, `confirm.js`, `copy.js`). Build DOM with `createElement` and
  `textContent`.
- Enhance only what exists: read `data-*` attributes, never configuration
  from inline scripts.
- A form that stays on its page can carry `data-inline` (`inline.js`): it saves with `fetch`, and the `main` element of the page the server answers with replaces the old one. The page is parsed whole with `DOMParser`, so the server's escaping holds, and the form is sent the ordinary way if anything goes wrong.
- Keep behaviour reversible: a page must do the right thing if the module
  fails to load.
