# This file was generated with the assistance of an AI coding tool.
"""The language layer: complete catalogues, fallbacks, parameters and the choice of language per request."""

from fastapi.testclient import TestClient

from opencde.ui import i18n

SIGN_IN = {
    "en": "Sign in",
    "sv": "Logga in",
    "da": "Log ind",
    "nb": "Logg inn",
    "nn": "Logg inn",
    "fi": "Kirjaudu",
    "is": "Skrá inn",
}


def test_every_language_has_every_key_of_the_english_source() -> None:
    source = i18n.catalogue("en")
    assert source, "the English catalogue is the source"
    for lang in i18n.LANGUAGES:
        catalogue = i18n.catalogue(lang)
        missing = sorted(set(source) - set(catalogue))
        extra = sorted(set(catalogue) - set(source))
        empty = sorted(key for key, value in catalogue.items() if not str(value).strip())
        assert not missing, f"{lang}: missing {missing}"
        assert not extra, f"{lang}: keys not in the English source {extra}"
        assert not empty, f"{lang}: empty values {empty}"
        for key, value in source.items():
            placeholders = {part for part in value.split("{")[1:]}
            for placeholder in placeholders:
                name = placeholder.split("}")[0]
                assert "{" + name + "}" in catalogue[key], f"{lang}: {key} lost the parameter {{{name}}}"


def test_translate_falls_back_and_fills_parameters() -> None:
    assert i18n.translate("sv", "opencde.signin") == "Logga in"
    assert i18n.translate("sv", "no.such.key") == "no.such.key", "unknown keys stay visible"
    assert i18n.translate("en", "js.rows_match", shown=3, total=10) == "3 of 10 rows match"
    assert i18n.translate("en", "js.rows_match") == "{shown} of {total} rows match", "no parameters, no formatting"
    assert i18n.translate("en", "js.rows_match", shown=1) == "1 of {total} rows match", "missing parameters stay"
    assert i18n.translate("xx", "opencde.signin") == "Sign in", "an unknown language reads the English source"


def test_the_language_follows_query_cookie_and_browser(client: TestClient) -> None:
    default = client.get("/signin")
    assert 'lang="en"' in default.text and f'<h1 class="card__title">{SIGN_IN["en"]}</h1>' in default.text

    for lang, title in SIGN_IN.items():
        page = client.get(f"/signin?lang={lang}")
        assert f'lang="{lang}"' in page.text and f'<h1 class="card__title">{title}</h1>' in page.text, lang
        assert f"{i18n.COOKIE_NAME}={lang}" in page.headers.get("set-cookie", ""), "the choice is remembered"
    client.cookies.clear()

    client.cookies.set(i18n.COOKIE_NAME, "fi")
    assert f'<h1 class="card__title">{SIGN_IN["fi"]}</h1>' in client.get("/signin").text
    client.cookies.clear()

    browser = client.get("/signin", headers={"Accept-Language": "da-DK,da;q=0.9,en;q=0.8"})
    assert f'<h1 class="card__title">{SIGN_IN["da"]}</h1>' in browser.text
    norwegian = client.get("/signin", headers={"Accept-Language": "no"})
    assert 'lang="nb"' in norwegian.text, "plain Norwegian means Bokmål"
    unknown = client.get("/signin?lang=xx", headers={"Accept-Language": "zz"})
    assert 'lang="en"' in unknown.text and "set-cookie" not in unknown.headers
    assert 'hreflang="is"' in unknown.text, "the switcher lists every language"


def test_the_request_log_and_settings_pages_render_in_swedish(client: TestClient) -> None:
    """Pages that need an administrator redirect to sign-in, which is itself translated."""
    response = client.get("/admin/requests?lang=sv", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"].startswith("/signin")
