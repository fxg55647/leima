import pytest
from playwright.sync_api import expect
from tests.test_integrity import downloads

pytestmark = pytest.mark.browser


@pytest.mark.parametrize('width', [360, 1440])
def test_validate_then_detect_tampering(page, live_url, client, stamped, width):
    files = downloads(client, stamped[0])
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/version?*', lambda route: route.fulfill(json={'tread': {'ok': True}}))
    page.route('**/tread-monitor?*', lambda route: route.fulfill(json={'ok': True}))
    page.goto(live_url + '/validate')
    for field, filename, mime in [('source', 'source.pdf', 'application/pdf'),
                                  ('verdict', 'verdict.pdf', 'application/pdf'),
                                  ('manifest', 'manifest.json', 'application/json')]:
        page.locator('#input-' + field).set_input_files({
            'name': filename, 'mimeType': mime, 'buffer': files[filename]})
    button = page.locator('#val-form').get_by_role('button', name='Validate')
    expect(button).to_be_in_viewport()
    button.click()
    expect(page.locator('#result')).to_contain_text('All checks passed')
    page.locator('#input-source').set_input_files({
        'name': 'source.pdf', 'mimeType': 'application/pdf', 'buffer': files['source.pdf'] + b'x'})
    button.click()
    expect(page.locator('#result')).to_contain_text('Validation failed')
    expect(page.locator('#result')).not_to_contain_text('All checks passed')
