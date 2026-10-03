"""leima-bridge: USB bridge between a local MCP client and the Leima Android app.

    python -m bridge devices            list USB devices seen by adb
    python -m bridge pair [--serial S]  pair this PC with the phone (approve on the phone)
    python -m bridge status [--serial S]
    python -m bridge unpair [--serial S]
    python -m bridge sync [--serial S] [--archive DIR] [--keep]   move packages to the PC archive
    python -m bridge verify <sha256>    re-verify an archived package
    python -m bridge tag <sha256> <tag>
    python -m bridge mcp                MCP server over stdio (Claude Desktop)
"""
import argparse
import json
import sys
from pathlib import Path

# mcp_server lives at the repository root; MCP clients may start us from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.adb import Adb  # noqa: E402
from bridge.archive import Archive  # noqa: E402
from bridge.client import pair, session, sync, unpair  # noqa: E402
from bridge.config import BridgeConfig  # noqa: E402
from bridge.errors import BridgeError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bridge", description="Leima USB-silta")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="listaa USB-laitteet")
    for name, text in (("pair", "parita tämä PC puhelimeen"), ("status", "näytä puhelimen tila"), ("unpair", "poista paritus")):
        commands.add_parser(name, help=text).add_argument("--serial", help="laitteen ADB-sarjanumero")
    sync_cmd = commands.add_parser("sync", help="siirrä paketit puhelimesta PC:n arkistoon")
    sync_cmd.add_argument("--serial", help="laitteen ADB-sarjanumero")
    sync_cmd.add_argument("--archive", help="arkistokansio (oletus: <repo>/evidence tai LEIMA_EVIDENCE_DIR)")
    sync_cmd.add_argument("--keep", action="store_true", help="älä poista paketteja puhelimesta")
    verify_cmd = commands.add_parser("verify", help="tarkista arkistoitu paketti uudelleen")
    verify_cmd.add_argument("sha256")
    verify_cmd.add_argument("--archive")
    tag_cmd = commands.add_parser("tag", help="liitä tagi arkistoituun pakettiin")
    tag_cmd.add_argument("sha256")
    tag_cmd.add_argument("tag")
    tag_cmd.add_argument("--archive")
    commands.add_parser("mcp", help="MCP-palvelin stdio:n yli")
    args = parser.parse_args(argv)
    # MCP messages must be UTF-8 whatever the Windows console code page is.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    if args.command == "mcp":
        from bridge.mcp_stdio import serve
        serve()
        return 0

    try:
        if args.command in ("verify", "tag"):
            archive = Archive(args.archive)
            if args.command == "verify":
                result = archive.verify_entry(args.sha256)
                print(f"Kunnossa ({result['kind']}): {result['path']}")
                print("Eheys suhteessa paketin manifestiin; laitetta, aikaa tai sisältöä ei ole todennettu.")
            else:
                row = archive.tag(args.sha256, args.tag)
                print(f"Tagi '{row['tag']}' lisätty paketille {row['sha256'][:12]}")
            return 0
        adb = Adb()
        if args.command == "devices":
            devices = adb.devices()
            if not devices:
                print("Ei USB-laitteita. Tarkista kaapeli ja USB-vianmääritys.")
            for d in devices:
                print(f"{d.serial}\t{d.state}\t{d.model}")
            return 0
        config = BridgeConfig()
        if args.command == "pair":
            def show(device, code):
                print(f"Paritetaan {device.model or device.serial}.")
                print(f"Hyväksy puhelimella vain, jos siinä näkyy koodi:  {code[:3]} {code[3:]}")
            device = pair(adb, config, args.serial, show)
            print(f"Paritettu: {device.model or device.serial}. Tunnus tallennettu: {config.path}")
        elif args.command == "status":
            with session(adb, config, args.serial) as (device, client):
                print(json.dumps({"serial": device.serial, **client.request("device_status")}, indent=2, ensure_ascii=False))
        elif args.command == "sync":
            archive = Archive(args.archive)
            labels = {"archived": "arkistoitu", "already_archived": "oli jo arkistossa", "failed": "EPÄONNISTUI"}

            def show(result):
                line = f"{labels[result['status']]:<18} {result['kind']:<10} {result['package_id']}"
                if result.get("path"):
                    line += f" -> {result['path']}"
                if result.get("error"):
                    line += f"  ({result['error']})"
                print(line)
            with session(adb, config, args.serial) as (device, client):
                results = sync(client, device, archive, delete=not args.keep, progress=show)
            failed = sum(r["status"] == "failed" for r in results)
            moved = len(results) - failed
            print(f"{moved} pakettia arkistossa {archive.root}" + (", poistettu puhelimesta." if not args.keep else ".")
                  + (f" {failed} epäonnistui ja jäi puhelimeen." if failed else ""))
            return 1 if failed else 0
        elif args.command == "unpair":
            device = unpair(adb, config, args.serial)
            print(f"Paritus poistettu: {device.model or device.serial}")
        return 0
    except BridgeError as e:
        print(f"Virhe {e.code}: {e.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
