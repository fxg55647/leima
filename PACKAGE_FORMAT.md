# Leima package format (stamp_format_version 2)

A Leima package is a single ZIP file. It is the one artifact a user downloads, and the
one artifact `/validate`, the Bundle tab, `/check-correspondence`, and `validator.html`
all accept as input. Nothing needs to be unpacked by hand.

## Layout

Flat namespace, no subdirectories, these names only:

```
manifest.json
source.<ext>            # real extension: pdf, png, jpg, ...
verdict.pdf
verdict.txt
verdict.html
verdict.json
source-index.json       # present only for stamps of a web page
```

`source.<ext>` and the four `verdict.*` files are always required. `source-index.json`
is optional and only exists when the analysed input was a web page.

## manifest.json

```json
{
  "stamp_format_version": 2,
  "timestamp": "2026-05-12 10:00:00 UTC",
  "commit": "abcdef0",
  "source_file": "source.pdf",
  "files": {
    "source.pdf": "sha256:<64 hex chars>",
    "verdict.pdf": "sha256:<64 hex chars>",
    "verdict.txt": "sha256:<64 hex chars>",
    "verdict.html": "sha256:<64 hex chars>",
    "verdict.json": "sha256:<64 hex chars>",
    "source-index.json": "sha256:<64 hex chars>"
  },
  "stamp": { "tx_id": "...", "url": "https://gateway.irys.xyz/..." }
}
```

- `files` maps every *other* content file's name to its SHA-256. It never lists itself
  (`manifest.json`) or the ZIP.
- `stamp` is added locally only after the stamp-less manifest (everything above except
  `stamp`) has been published to Arweave. The published record never contains its own
  `tx_id` — that would be circular.
- Extra top-level fields (`tread`, `c2pa`, `email`) may be present depending on the
  analysed input type; readers ignore fields they don't recognize.

## Build order (one-way, no re-derivation later)

1. Compute all source and verdict bytes once (`source.<ext>`, `verdict.pdf/txt/html/json`,
   optionally `source-index.json`).
2. Build the `files` hash map from those exact bytes and finish the manifest's other
   fields.
3. Publish the manifest, minus `stamp`, to Arweave.
4. Add `stamp.tx_id`/`stamp.url` to the local manifest.
5. Pack the original bytes and the final local manifest into the ZIP.

A later download always re-packs the *same* stored bytes — it never regenerates
`verdict.txt/html/json` from scratch, so the package's file hashes always match the
manifest regardless of when it's downloaded.

## What a reader must check (`evidence_package.read()` / `validator.html`)

- Known format and version (`stamp_format_version == 2`); malformed input is a clean
  rejection, never a server error.
- Exactly one `manifest.json`, well under its size cap.
- The ZIP's member set matches `files` plus `manifest.json` exactly — no missing or
  extra files.
- All four verdict formats present; `source-index.json` optional.
- Every listed file's actual SHA-256 matches `files`.
- Reject: directories, duplicate names, absolute paths, `../` traversal, backslashes,
  symlinks, encrypted members, unsupported compression methods, duplicate JSON keys,
  too many members, oversized members/total/manifest.
- Never extract to disk; never execute or render package content.
- The ZIP shell itself (member order, compression level) is not part of the proof —
  only the content bytes and the manifest's hashes are. Re-zipping the same content
  differently must still validate.

## Limits

| Limit | Value |
|---|---|
| Compressed package | 50 MiB |
| Uncompressed, per member | 50 MiB |
| Uncompressed, total | 150 MiB |
| `manifest.json` | 1 MiB |
| Members | 8 |

Implemented once in `evidence_package.py` (Python, server-side) and mirrored in
`validator.html`'s in-browser ZIP reader (vanilla JS, no external library — uses the
browser's native `DecompressionStream('deflate-raw')`).

## Anchor check

A validator fetches the stamp record from the configured Arweave gateway by `tx_id` and
compares it to the local manifest with `stamp` removed. A gateway failure must be
reported as unverified, never as a silent pass. The package's own timestamps are not a
trusted stamping time — only the Arweave record is.
