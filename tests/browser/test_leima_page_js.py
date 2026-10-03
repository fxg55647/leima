"""The Android page script (android/app/src/main/assets/leima_page.js) run in real Chromium."""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

SCRIPT = (Path(__file__).resolve().parents[2] / "android/app/src/main/assets/leima_page.js").read_text("utf-8")
KEY = "__leima_test_key"

PAGE = """<!DOCTYPE html><html><head><title>Test form</title><meta name="csrf-token" content="secret-csrf"></head>
<body>
  <h1>Kirjaudu</h1>
  <p>Visible paragraph text.</p>
  <a href="/next">Seuraava sivu</a>
  <label for="user">Käyttäjä</label><input id="user" value="matti">
  <input id="pw" type="password" value="hunter2" aria-label="Salasana">
  <input id="otp" autocomplete="one-time-code" value="123456" aria-label="Koodi">
  <input type="hidden" name="csrf" value="hidden-token">
  <textarea id="note" aria-label="Viesti"></textarea>
  <button id="go" onclick="document.body.dataset.clicked='yes'">Lähetä</button>
  <button disabled>Pois käytöstä</button>
  <div style="display:none"><button>Piilotettu</button></div>
  <input type="checkbox" id="agree" checked aria-label="Hyväksyn">
  <iframe src="https://example.com/"></iframe>
  <canvas></canvas>
</body></html>"""


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.fulfill(body="<html><body>frame</body></html>", content_type="text/html"))
        page.set_content(PAGE)
        yield page
        browser.close()


def run(page, command, **args):
    return json.loads(page.evaluate(f"([c, a]) => ({SCRIPT})(c, a)", [command, {"key": KEY, **args}]))


def by_name(observation, name):
    return next(e for e in observation["elements"] if e["name"] == name)


def test_observe_lists_visible_interactive_elements_without_secrets(page):
    obs = run(page, "observe", observation_id="obs_1")
    names = [e["name"] for e in obs["elements"]]
    assert obs["title"] == "Test form" and "Visible paragraph text." in obs["visible_text"]
    assert {"Seuraava sivu", "Käyttäjä", "Salasana", "Koodi", "Viesti", "Lähetä", "Pois käytöstä", "Hyväksyn"} <= set(names)
    assert "Piilotettu" not in names
    assert by_name(obs, "Käyttäjä")["value"] == "matti"
    password = by_name(obs, "Salasana")
    assert password["sensitive"] and password["has_value"] and "value" not in password
    assert by_name(obs, "Koodi")["sensitive"]
    assert by_name(obs, "Pois käytöstä")["enabled"] is False
    assert by_name(obs, "Hyväksyn")["checked"] is True
    assert by_name(obs, "Seuraava sivu")["role"] == "link"
    serialized = json.dumps(obs)
    assert "hunter2" not in serialized and "123456" not in serialized and "hidden-token" not in serialized
    codes = {limitation["code"] for limitation in obs["limitations"]}
    assert {"CROSS_ORIGIN_IFRAMES", "CANVAS"} <= codes or {"IFRAMES_NOT_TRAVERSED", "CANVAS"} <= codes


def test_click_and_type_use_the_latest_observation_only(page):
    first = run(page, "observe", observation_id="obs_1")
    go = by_name(first, "Lähetä")["element_id"]
    second = run(page, "observe", observation_id="obs_2")
    assert run(page, "click", observation_id="obs_1", element_id=go) == {"error": "STALE_OBSERVATION"}
    assert run(page, "click", observation_id="obs_2", element_id=by_name(second, "Lähetä")["element_id"])["ok"]
    assert page.evaluate("document.body.dataset.clicked") == "yes"
    assert run(page, "click", observation_id="obs_2", element_id="el_999") == {"error": "UNKNOWN_ELEMENT"}
    assert run(page, "click", observation_id="obs_2", element_id=by_name(second, "Pois käytöstä")["element_id"]) == {"error": "ELEMENT_DISABLED"}

    user = by_name(second, "Käyttäjä")["element_id"]
    page.evaluate("document.getElementById('user').addEventListener('input', () => document.body.dataset.input = 'seen')")
    assert run(page, "type", observation_id="obs_2", element_id=user, text="liisa", replace=True)["ok"]
    assert page.evaluate("document.getElementById('user').value") == "liisa"
    assert page.evaluate("document.body.dataset.input") == "seen"
    assert run(page, "type", observation_id="obs_2", element_id=user, text="!", replace=False)["ok"]
    assert page.evaluate("document.getElementById('user').value") == "liisa!"
    assert run(page, "type", observation_id="obs_2", element_id=by_name(second, "Salasana")["element_id"], text="x", replace=True) == {"error": "SENSITIVE_FIELD"}
    assert run(page, "type", observation_id="obs_2", element_id=by_name(second, "Lähetä")["element_id"], text="x", replace=True) == {"error": "NOT_TEXT_INPUT"}


def test_removed_element_is_stale(page):
    obs = run(page, "observe", observation_id="obs_1")
    page.evaluate("document.getElementById('go').remove()")
    assert run(page, "click", observation_id="obs_1", element_id=by_name(obs, "Lähetä")["element_id"])["error"] == "STALE_OBSERVATION"


def test_masks_cover_sensitive_fields(page):
    result = run(page, "masks")
    assert len(result["rects"]) == 2  # password + one-time-code
    assert all(r["width"] > 0 and r["height"] > 0 for r in result["rects"])
    assert result["viewport"]["width"] > 0


def test_dom_snapshot_redacts_secrets(page):
    page.evaluate("document.getElementById('pw').setAttribute('value', 'attr-secret')")
    result = run(page, "dom")
    html = result["html"]
    assert html.startswith("<!DOCTYPE html>") and "Visible paragraph text." in html
    for secret in ("attr-secret", "hunter2", "hidden-token", "secret-csrf"):
        assert secret not in html
    assert result["redactions"]["sensitive_inputs"] >= 1 and result["redactions"]["hidden_inputs"] == 1
    assert result["redactions"]["csrf_meta"] == 1


def test_element_store_is_not_enumerable(page):
    run(page, "observe", observation_id="obs_1")
    assert page.evaluate(f"Object.keys(window).includes('{KEY}')") is False


def test_human_action_hints(page):
    hints = {h["code"] for h in run(page, "observe", observation_id="obs_1")["human_action_hints"]}
    assert hints == {"LOGIN_FORM", "ONE_TIME_CODE"}
    page.set_content('<div class="g-recaptcha" data-sitekey="x"></div><p>Plain page</p>')
    assert [h["code"] for h in run(page, "observe", observation_id="obs_2")["human_action_hints"]] == ["CAPTCHA"]
    page.set_content("<p>Nothing to do</p>")
    assert run(page, "observe", observation_id="obs_3")["human_action_hints"] == []
