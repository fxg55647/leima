"""Fictional source retrieval through the real bridge and archive, without a device."""
import hashlib

import pytest

from bridge.adb import Device
from bridge.archive import Archive
from bridge.client import read_package, read_screenshot, sync
from bridge.errors import BridgeError
from tests.test_bridge_browser import browser_package
from tests.test_bridge_packages import FakePackagePhone


@pytest.mark.parametrize("reader,code", [
    (read_package, "PACKAGE_TRANSFER_MISMATCH"),
    (read_screenshot, "SCREENSHOT_FAILED"),
])
@pytest.mark.parametrize("response", [
    {"offset": 0, "data_base64": "", "eof": False},
    {"offset": 0, "data_base64": "!!!", "eof": True},
    {"offset": 0, "data_base64": "YQ", "eof": True},
    {"offset": 0, "data_base64": "YQ==", "eof": "false"},
    {"offset": 0, "data_base64": "YQ=="},
    {"offset": 0, "data_base64": "YQ==", "eof": False},
])
def test_invalid_chunks_fail_promptly(reader, code, response):
    class Phone:
        calls = 0

        def request(self, *args, **kwargs):
            self.calls += 1
            assert self.calls == 1, "Transfer retried a chunk that cannot advance"
            return response

    meta = {"package_id": "browser:fictional", "screenshot_id": "fictional",
            "size": 1, "sha256": hashlib.sha256(b"a").hexdigest()}
    with pytest.raises(BridgeError) as error:
        reader(Phone(), meta)
    assert error.value.code == code


def test_fictional_source_batch_keeps_failed_source_and_archives_later_sources(tmp_path):
    complete = browser_package()
    partial = browser_package("partial", [{"file": "screenshot.png", "reason": "SCREENSHOT_BLOCKED"}],
                              screenshot=False)

    class Phone(FakePackagePhone):
        def request(self, method, params=None, timeout=None):
            if method == "packages.read" and params["package_id"] == "browser:broken":
                return {"offset": params["offset"], "data_base64": "YQ", "eof": False}
            result = super().request(method, params, timeout)
            if method == "packages.list":
                for package in result["packages"]:
                    package["kind"] = "browser"
            return result

    phone = Phone({"browser:broken": complete, "browser:complete": complete,
                   "browser:partial": partial}, chunk=37)
    archive = Archive(tmp_path)
    results = sync(phone, Device("SIMULATED", "device", "Fictional phone"), archive)
    assert [r["status"] for r in results] == ["failed", "archived", "archived"]
    assert set(phone.packages) == {"browser:broken"}
    assert phone.deleted == ["browser:complete", "browser:partial"]
    for result in results[1:]:
        assert archive.verify_entry(result["sha256"])["valid"]
    assert len(archive.archived()) == 2
