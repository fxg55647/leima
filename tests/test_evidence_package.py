import io
import json
import zipfile

import pytest

import evidence_package as ep


def _valid_manifest_and_files():
    manifest = ep.build_manifest(
        timestamp='2026-01-01 00:00:00 UTC', commit='abc123',
        source_filename='source.pdf', source_bytes=b'%PDF-1.4 source',
        verdict_pdf=b'%PDF-1.4 verdict', verdict_txt=b'verdict text',
        verdict_html=b'<html>verdict</html>', verdict_json=b'{"claim": "x"}',
    )
    zip_bytes = ep.pack(
        manifest, 'source.pdf', b'%PDF-1.4 source', b'%PDF-1.4 verdict',
        b'verdict text', b'<html>verdict</html>', b'{"claim": "x"}',
    )
    return manifest, zip_bytes


def _rezip(contents):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in contents.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _unzip(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _set_encrypted_flag(zip_bytes: bytes, name: str) -> bytes:
    """zipfile.writestr silently clears a manually-set flag_bits, so exercising the
    encrypted-member rejection path means patching the general-purpose flag bit directly
    in both the local header and central directory copies of the raw ZIP bytes."""
    data = bytearray(zip_bytes)
    name_b = name.encode()

    idx = data.find(b'PK\x03\x04')
    while idx != -1:
        name_len = int.from_bytes(data[idx + 26:idx + 28], 'little')
        if bytes(data[idx + 30:idx + 30 + name_len]) == name_b:
            flags = int.from_bytes(data[idx + 6:idx + 8], 'little') | 0x1
            data[idx + 6:idx + 8] = flags.to_bytes(2, 'little')
            break
        idx = data.find(b'PK\x03\x04', idx + 4)

    idx = data.find(b'PK\x01\x02')
    while idx != -1:
        name_len = int.from_bytes(data[idx + 28:idx + 30], 'little')
        extra_len = int.from_bytes(data[idx + 30:idx + 32], 'little')
        comment_len = int.from_bytes(data[idx + 32:idx + 34], 'little')
        if bytes(data[idx + 46:idx + 46 + name_len]) == name_b:
            flags = int.from_bytes(data[idx + 8:idx + 10], 'little') | 0x1
            data[idx + 8:idx + 10] = flags.to_bytes(2, 'little')
            break
        idx = data.find(b'PK\x01\x02', idx + 46 + name_len + extra_len + comment_len)

    return bytes(data)


def test_pack_read_roundtrip():
    manifest, zip_bytes = _valid_manifest_and_files()
    pkg = ep.read(zip_bytes)
    assert pkg.manifest == manifest
    assert pkg.source_bytes == b'%PDF-1.4 source'
    assert pkg.verdict('pdf') == b'%PDF-1.4 verdict'
    assert pkg.source_index_bytes is None


def test_optional_source_index_round_trips():
    manifest = ep.build_manifest(
        timestamp='t', commit='c', source_filename='source.png', source_bytes=b'PNGDATA',
        verdict_pdf=b'PDF', verdict_txt=b'TXT', verdict_html=b'HTML', verdict_json=b'{}',
        source_index_bytes=b'{"format_version": 1}',
    )
    zip_bytes = ep.pack(
        manifest, 'source.png', b'PNGDATA', b'PDF', b'TXT', b'HTML', b'{}',
        b'{"format_version": 1}',
    )
    pkg = ep.read(zip_bytes)
    assert pkg.source_index_bytes == b'{"format_version": 1}'


def test_empty_upload_rejected():
    with pytest.raises(ep.PackageFormatError):
        ep.read(b'')


def test_oversized_upload_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    with pytest.raises(ep.PackageFormatError):
        ep.read(zip_bytes, max_bytes=10)


def test_corrupt_zip_rejected():
    with pytest.raises(ep.PackageFormatError):
        ep.read(b'not a zip file' * 5)


def test_missing_manifest_rejected():
    with pytest.raises(ep.PackageFormatError, match='manifest'):
        ep.read(_rezip({'verdict.pdf': b'x'}))


def test_hash_mismatch_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    contents['verdict.pdf'] += b'tampered'
    with pytest.raises(ep.PackageFormatError, match='Hash mismatch'):
        ep.read(_rezip(contents))


@pytest.mark.parametrize('bad_name', ['../evil.txt', '/etc/passwd', 'a\\b.txt', 'sub/dir.txt', 'dir/'])
def test_unsafe_names_rejected(bad_name):
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    contents[bad_name] = contents.pop('verdict.pdf')
    manifest = json.loads(contents['manifest.json'])
    manifest['files'][bad_name] = manifest['files'].pop('verdict.pdf')
    contents['manifest.json'] = json.dumps(manifest).encode()
    with pytest.raises(ep.PackageFormatError):
        ep.read(_rezip(contents))


def test_duplicate_member_name_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in contents.items():
            zf.writestr(name, data)
        zf.writestr('verdict.pdf', contents['verdict.pdf'])  # duplicate
    with pytest.raises(ep.PackageFormatError, match='Duplicate'):
        ep.read(buf.getvalue())


def test_encrypted_member_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    tampered = _set_encrypted_flag(zip_bytes, 'verdict.pdf')
    with pytest.raises(ep.PackageFormatError, match='Encrypted'):
        ep.read(tampered)


def test_unsupported_compression_method_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, data in contents.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_BZIP2 if name == 'verdict.pdf' else zipfile.ZIP_STORED
            zf.writestr(info, data)
    with pytest.raises(ep.PackageFormatError, match='Unsupported compression'):
        ep.read(buf.getvalue())


def test_missing_required_verdict_format_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    del contents['verdict.txt']
    manifest = json.loads(contents['manifest.json'])
    del manifest['files']['verdict.txt']
    contents['manifest.json'] = json.dumps(manifest).encode()
    with pytest.raises(ep.PackageFormatError):
        ep.read(_rezip(contents))


def test_wrong_stamp_format_version_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    manifest = json.loads(contents['manifest.json'])
    manifest['stamp_format_version'] = 1
    contents['manifest.json'] = json.dumps(manifest).encode()
    with pytest.raises(ep.PackageFormatError):
        ep.read(_rezip(contents))


def test_duplicate_json_keys_in_manifest_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    contents['manifest.json'] = b'{"stamp_format_version": 2, "stamp_format_version": 2}'
    with pytest.raises(ep.PackageFormatError):
        ep.read(_rezip(contents))


def test_too_many_members_rejected():
    _, zip_bytes = _valid_manifest_and_files()
    contents = _unzip(zip_bytes)
    for i in range(ep.MAX_MEMBERS):
        contents[f'extra{i}.txt'] = b'x'
    with pytest.raises(ep.PackageFormatError):
        ep.read(_rezip(contents))
