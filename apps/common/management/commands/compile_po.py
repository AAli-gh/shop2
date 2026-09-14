"""Compile locale/<lang>/LC_MESSAGES/*.po files to .mo in pure Python.

Django's compilemessages needs GNU gettext (msgfmt), which isn't installed on Windows;
this does the same for the simple single/multi-line entries used in this project.
"""
import ast
import struct
from array import array
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def parse_po(text: str) -> dict[str, str]:
    """msgid -> msgstr for every translated entry (the empty-msgid header included)."""
    messages: dict[str, str] = {}
    entry = {"msgid": None, "msgstr": None}
    field = None

    def flush():
        if entry["msgid"] is not None and entry["msgstr"]:
            messages[entry["msgid"]] = entry["msgstr"]
        entry["msgid"] = entry["msgstr"] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            field = "msgid"
            entry["msgid"] = ast.literal_eval(line[len("msgid "):])
        elif line.startswith("msgstr "):
            field = "msgstr"
            entry["msgstr"] = ast.literal_eval(line[len("msgstr "):])
        elif line.startswith('"') and field:
            entry[field] += ast.literal_eval(line)
    flush()
    return messages


def build_mo(messages: dict[str, str]) -> bytes:
    """GNU .mo binary (same layout as CPython's Tools/i18n/msgfmt.py)."""
    keys = sorted(messages)
    ids = strs = b""
    offsets = []
    for key in keys:
        key_bytes, value_bytes = key.encode("utf-8"), messages[key].encode("utf-8")
        offsets.append((len(ids), len(key_bytes), len(strs), len(value_bytes)))
        ids += key_bytes + b"\0"
        strs += value_bytes + b"\0"

    header_size = 7 * 4
    key_start = header_size + 16 * len(keys)
    value_start = key_start + len(ids)
    key_table, value_table = [], []
    for id_offset, id_len, str_offset, str_len in offsets:
        key_table += [id_len, id_offset + key_start]
        value_table += [str_len, str_offset + value_start]

    header = struct.pack(
        "Iiiiiii", 0x950412DE, 0, len(keys), header_size, header_size + 8 * len(keys), 0, 0,
    )
    return header + array("i", key_table).tobytes() + array("i", value_table).tobytes() + ids + strs


class Command(BaseCommand):
    help = "Compile .po translation files under LOCALE_PATHS to .mo (no GNU gettext needed)"

    def handle(self, *args, **options):
        compiled = 0
        for locale_dir in settings.LOCALE_PATHS:
            for po_path in Path(locale_dir).rglob("*.po"):
                messages = parse_po(po_path.read_text(encoding="utf-8"))
                po_path.with_suffix(".mo").write_bytes(build_mo(messages))
                self.stdout.write(f"{po_path} -> {len(messages) - ('' in messages)} messages")
                compiled += 1
        if not compiled:
            self.stdout.write("no .po files found")
