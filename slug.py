"""Icon slug helpers for uma filenames and StreamElements dropdown values."""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip("[]"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def norm_char(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def build_norm_to_cid(data: dict) -> dict[str, str]:
    norm_to_cid = {norm_char(c["name"][1]): cid for cid, c in data.items()}
    norm_to_cid.setdefault(norm_char("TM Opera O"), norm_to_cid.get(norm_char("T.M. Opera O")))
    return norm_to_cid


def label_to_icon_slug(label: str, data: dict, norm_to_cid: dict[str, str]) -> str:
    match = re.match(r"^(.+?)\s*\((.+)\)$", label)
    if match:
        char, variant = match.group(1).strip(), match.group(2).strip()
    else:
        char, variant = label, None
    cid = norm_to_cid.get(norm_char(char))
    char_slug = slugify(data[cid]["name"][1]) if cid else slugify(char)
    return char_slug if not variant else f"{char_slug}-{slugify(variant)}"


def format_slug_output(slug: str, ext: str | None) -> str:
    if not ext:
        return slug
    ext = ext.lstrip(".")
    return f"{slug}.{ext}" if ext else slug


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print icon slug(s) for uma labels.")
    parser.add_argument("labels", nargs="+", help="Uma label(s), e.g. 'Gold Ship (Summer)'")
    parser.add_argument("-e", "--ext", metavar="EXT", help="Append .EXT to each slug")
    args = parser.parse_args(argv)

    with (ROOT / "umas.json").open(encoding="utf-8") as f:
        data = json.load(f)
    norm_to_cid = build_norm_to_cid(data)

    for label in args.labels:
        slug = label_to_icon_slug(label, data, norm_to_cid)
        print(format_slug_output(slug, args.ext))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
