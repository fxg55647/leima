"""Execute the actual scheduled script with fake HTTP and temporary output."""
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
import pytest
import requests

SCRIPT = Path(__file__).resolve().parents[1] / 'tread_check.py'
SHA = 'a' * 40


@pytest.mark.parametrize('scenario,expected', [
    ('healthy', True), ('mismatch', False), ('deploying', True),
    ('github_down', None), ('stale_cron', False), ('disabled_workflow', False),
])
def test_scheduled_status(monkeypatch, tmp_path, scenario, expected):
    monkeypatch.chdir(tmp_path)
    for key, value in {'VERCEL_TOKEN': 'test', 'VERCEL_PROJECT_ID': 'test',
                       'GITHUB_REPO': 'fxg55647/leima', 'GITHUB_BRANCH': 'main'}.items():
        monkeypatch.setenv(key, value)
    def get(url, **kwargs):
        body, status, text = {}, 200, ''
        if 'api.vercel.com' in url:
            live = SHA if scenario != 'mismatch' else 'b'*40
            deployments = [{'state': 'READY', 'target': 'production',
                            'meta': {'githubCommitSha': live}}]
            if scenario == 'deploying':
                deployments[0]['meta']['githubCommitSha'] = 'b'*40
                deployments.insert(0, {'state': 'BUILDING', 'meta': {
                    'githubCommitSha': SHA, 'githubOrg': 'fxg55647',
                    'githubRepo': 'leima', 'githubCommitRef': 'main'}})
            body = {'deployments': deployments}
        elif '/commits/main' in url:
            text = SHA
            status = 503 if scenario == 'github_down' else 200
        elif 'code_review.yml/runs' in url:
            body = {'workflow_runs': [{'status': 'completed', 'conclusion': 'success', 'head_sha': SHA}]}
        elif 'tread.yml/runs' in url:
            body = {'workflow_runs': [{'updated_at': '2000-01-01T00:00:00Z' if scenario == 'stale_cron' else '2099-01-01T00:00:00Z'}]}
        elif '/actions/workflows/tread.yml' in url:
            body = {'state': 'disabled_manually' if scenario == 'disabled_workflow' else 'active'}
        elif '/deployments' in url:
            body = []
        else:
            raise AssertionError(f'Unexpected URL: {url}')
        return SimpleNamespace(status_code=status, text=text, json=lambda: body,
                               raise_for_status=lambda: None)
    monkeypatch.setattr(requests, 'get', get)
    runpy.run_path(str(SCRIPT), run_name='__main__')
    result = json.loads((tmp_path / 'pages-output/status.json').read_text())
    assert result['ok'] is expected
    assert result['github_commit_unknown'] is (scenario == 'github_down')
    assert result['cron_fresh'] is (scenario != 'stale_cron')
    assert result['monitor_files']['tread_check.py']
