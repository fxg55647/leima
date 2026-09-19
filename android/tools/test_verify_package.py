import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from verify_package import verify


class PackageVerificationTest(unittest.TestCase):
    def make_package(self, path, tamper=None):
        files = {"photo.jpg": b"sample image bytes", "metadata.json": b'{"schemaVersion":1}'}
        manifest = json.dumps({"schemaVersion": 1, "algorithm": "SHA-256", "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        }}).encode()
        checksum = hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"
        if tamper in files:
            files[tamper] += b"changed"
        if tamper == "manifest.json":
            manifest += b" "
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr("manifest.json", manifest)
            archive.writestr("manifest.sha256", checksum)

    def test_intact_and_modified_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.zip"
            self.make_package(path)
            verify(path)
            for name in ("photo.jpg", "metadata.json", "manifest.json"):
                with self.subTest(modified=name):
                    self.make_package(path, name)
                    with self.assertRaises(ValueError):
                        verify(path)


if __name__ == "__main__":
    unittest.main()
