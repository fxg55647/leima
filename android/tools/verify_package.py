"""Verify local Leima capture hashes. This does not authenticate the device or time."""
import hashlib
import json
import sys
import zipfile


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        if any(info.file_size > 100 * 1024 * 1024 for info in archive.infolist()):
            raise ValueError("Entry exceeds 100 MiB verification limit")
        manifest_bytes = archive.read("manifest.json")
        expected = archive.read("manifest.sha256").decode("utf-8").strip()
        if expected != hashlib.sha256(manifest_bytes).hexdigest() + "  manifest.json":
            raise ValueError("Manifest checksum mismatch")
        manifest = json.loads(manifest_bytes)
        if manifest.get("schemaVersion") != 1 or manifest.get("algorithm") != "SHA-256":
            raise ValueError("Unsupported manifest")
        files = manifest["files"]
        if set(files) not in ({"photo.jpg", "metadata.json"}, {"screenshot.png", "metadata.json"}):
            raise ValueError("Unexpected payload files")
        if set(names) != set(files) | {"manifest.json", "manifest.sha256"}:
            raise ValueError("Unexpected ZIP entries")
        for name, digest in files.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        json.loads(archive.read("metadata.json"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python verify_package.py evidence.zip")
    try:
        verify(sys.argv[1])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"INVALID: {error}")
    print("Hashes valid. Package is unsigned; origin and timestamps are not authenticated.")
