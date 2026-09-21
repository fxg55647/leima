from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse
from playwright.sync_api import expect

from tests.test_integrity import download_package, repack, unpack

pytestmark = pytest.mark.browser


@pytest.mark.parametrize('width', [360, 1440])
def test_validate_then_detect_tampering(page, live_url, client, stamped, width):
    zip_bytes = download_package(client, stamped[0])
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/version?*', lambda route: route.fulfill(json={'tread': {'ok': True}}))
    page.route('**/tread-monitor?*', lambda route: route.fulfill(json={'ok': True}))
    page.goto(live_url + '/validate')
    page.locator('#input-package').set_input_files({
        'name': 'package.zip', 'mimeType': 'application/zip', 'buffer': zip_bytes})
    button = page.locator('#val-form').get_by_role('button', name='Validate')
    expect(button).to_be_in_viewport()
    button.click()
    expect(page.locator('#result')).to_contain_text('All checks passed')

    files = unpack(zip_bytes)
    files['source.pdf'] += b'x'
    tampered = repack(files)
    page.locator('#input-package').set_input_files({
        'name': 'package.zip', 'mimeType': 'application/zip', 'buffer': tampered})
    button.click()
    expect(page.locator('#result')).to_contain_text('Validation failed')
    expect(page.locator('#result')).not_to_contain_text('All checks passed')


@pytest.mark.parametrize('width', [360, 1440])
def test_standalone_validator_zip_flow(page, live_url, client, stamped, app_module, width):
    """validator.html is published standalone (not served by this app), but it must accept
    the same package.zip contract. Serve it from a throwaway route on the live test server
    so this exercises the real file's in-browser ZIP reader end to end."""
    validator_source = (Path(__file__).parent.parent.parent / 'validator.html').read_text(encoding='utf-8')
    route_path = '/__validator_under_test__'
    if not any(getattr(r, 'path', None) == route_path for r in app_module.app.router.routes):
        @app_module.app.get(route_path, response_class=HTMLResponse)
        async def _serve_validator_under_test():
            return HTMLResponse(validator_source)

    session, records = stamped
    zip_bytes = download_package(client, session)

    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/gateway.irys.xyz/**', lambda route: route.fulfill(json=records['test-transaction']))
    page.goto(live_url + route_path)
    page.locator('#inp-package').set_input_files({
        'name': 'package.zip', 'mimeType': 'application/zip', 'buffer': zip_bytes})
    page.get_by_role('button', name='Validate').click()
    expect(page.locator('#results')).to_contain_text('All checks passed')

    files = unpack(zip_bytes)
    files['verdict.pdf'] += b'x'
    tampered = repack(files)
    page.locator('#inp-package').set_input_files({
        'name': 'package.zip', 'mimeType': 'application/zip', 'buffer': tampered})
    page.get_by_role('button', name='Validate').click()
    expect(page.locator('#results')).to_contain_text('Validation failed')
    expect(page.locator('#results')).not_to_contain_text('All checks passed')
