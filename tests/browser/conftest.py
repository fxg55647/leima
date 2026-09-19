import os
from pathlib import Path
import socket
import threading
import time
import pytest


@pytest.fixture
def live_url(app_module):
    import uvicorn
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app_module.app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Test server did not start')
            time.sleep(.01)
        yield f'http://127.0.0.1:{sock.getsockname()[1]}'
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


@pytest.fixture
def page(live_url, request):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = getattr(pw, os.getenv('TEST_BROWSER', 'chromium')).launch(
            headless=os.getenv('HEADED') != '1')
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        # Third-party assets are blocked. TREAD tests use the real inline JS.
        # HTMX is served from a pinned local fixture for form integration tests.
        def route(req):
            if req.request.url.startswith(live_url):
                req.continue_()
            elif req.request.url.startswith('https://unpkg.com/htmx.org@2.0.3'):
                req.fulfill(path=str(Path(__file__).parent / 'vendor/htmx-2.0.3.min.js'),
                            content_type='application/javascript')
            else:
                req.abort()
        page.route('**/*', route)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page
            assert not errors, errors
        finally:
            output = Path('test-results') / request.node.name.replace('/', '_').replace(':', '_')
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / 'screen.png'), full_page=True)
            context.tracing.stop(path=str(output / 'trace.zip'))
            context.close()
            browser.close()
