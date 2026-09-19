from datetime import datetime, timezone
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.browser


@pytest.fixture
def status(page):
    state = {'tread': {'ok': True, 'checked_at': '2026-09-20 10:00:00 UTC'},
             'monitor': {'ok': True, 'hashes': {'tread_check.py': 'original'}}}
    page.clock.install(time=datetime(2026, 9, 20, 10, 1, tzinfo=timezone.utc))
    page.route('**/version?*', lambda route: route.fulfill(json={'tread': state['tread']}))
    page.route('**/tread-monitor?*', lambda route: route.fulfill(json=state['monitor']))
    return state


def refresh(page):
    # Trigger the application's existing foreground refresh, without real waits.
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")


def test_normal_mismatch_recovery(page, live_url, status):
    page.goto(live_url + '/app')
    expect(page.locator('#tread-text')).to_contain_text('deploy matches git')
    status['tread']['ok'] = False
    status['monitor'] = {'ok': None}
    refresh(page)
    expect(page.locator('#tread-text')).to_contain_text('Danger')
    expect(page.locator('#tread-modal-overlay')).to_be_visible()
    page.locator('#tread-modal-close').click()
    status['tread']['ok'] = True
    status['monitor'] = {'ok': True}
    refresh(page)
    expect(page.locator('#tread-text')).to_contain_text('deploy matches git')


def test_acceptance_does_not_hide_new_mismatch(page, live_url, status):
    status['tread']['ok'] = False
    status['monitor'] = {'ok': None}
    page.goto(live_url + '/app')
    expect(page.locator('#tread-modal-overlay')).to_be_visible()
    page.locator('#tread-modal-how').click()
    page.locator('#tread-modal-accept').click()
    status['tread']['checked_at'] = '2026-09-20 10:01:00 UTC'
    refresh(page)
    expect(page.locator('#tread-modal-overlay')).to_be_visible()


@pytest.mark.parametrize('monitor,message', [
    ({'ok': True, 'unauthorized_deploy': True}, 'unauthorized deploy'),
    ({'ok': True, 'vercel_api_error': True}, 'Vercel API unavailable'),
    ({'ok': True, 'github_actions_error': True}, 'GitHub Actions API unavailable'),
    ({'ok': True, 'deploying': True}, 'Deploying'),
    ({'ok': True, 'deploy_incoming': True, 'review_in_progress': True}, 'code review in progress'),
])
def test_status_is_explained(page, live_url, status, monitor, message):
    status['monitor'] = monitor
    page.goto(live_url + '/app')
    expect(page.locator('#tread-text')).to_contain_text(message)


def test_changed_monitor_file_survives_reload(page, live_url, status):
    page.goto(live_url + '/app')
    expect(page.locator('#tread-text')).to_contain_text('deploy matches git')
    status['monitor']['hashes']['tread_check.py'] = 'changed'
    refresh(page)
    expect(page.locator('#tread-modal-body')).to_contain_text('tread_check.py')
    page.reload()
    expect(page.locator('#tread-text')).to_contain_text('github files changed')


def test_network_failure_is_not_green(page, live_url, status):
    page.route('**/version?*', lambda route: route.abort())
    page.goto(live_url + '/app')
    expect(page.locator('#tread-text')).to_contain_text('/version unreachable')


@pytest.mark.parametrize('path', ['/app', '/validate'])
@pytest.mark.parametrize('checked_at', ['2026-09-20 09:00:00 UTC', None, 'invalid'])
def test_old_or_missing_timestamp_cannot_be_green(page, live_url, status, path, checked_at):
    status['tread']['checked_at'] = checked_at
    page.goto(live_url + path)
    expect(page.locator('#tread-text')).to_contain_text('verification stale or timestamp unavailable')


def test_fresh_status_becomes_stale_without_updated_check(page, live_url, status):
    page.goto(live_url + '/app')
    expect(page.locator('#tread-text')).to_contain_text('deploy matches git')
    page.clock.fast_forward(11 * 60 * 1000)
    expect(page.locator('#tread-text')).to_contain_text('verification stale or timestamp unavailable')
