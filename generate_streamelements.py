"""Build overlay/fields.json from fields-base.json plus generated uma dropdowns."""

import json
import re
from pathlib import Path

from uma import ICONS_DIR, norm_char, slugify

ROOT = Path(__file__).parent
OVERLAY = ROOT / "overlay"
TEAMS = 3
UMAS_PER_TEAM = 3
LAYOUT_KEYS = [
    "boxWidth",
    "cellVerticalPadding",
    "boxSpacing",
    "xOffset",
    "yOffset",
    "iconBaseUrl",
]


def label_to_slug(label: str, data: dict, norm_to_cid: dict[str, str]) -> str:
    match = re.match(r"^(.+?)\s*\((.+)\)$", label)
    if match:
        char, variant = match.group(1).strip(), match.group(2).strip()
    else:
        char, variant = label, None
    cid = norm_to_cid.get(norm_char(char))
    char_slug = slugify(data[cid]["name"][1]) if cid else slugify(char)
    return char_slug if not variant else f"{char_slug}-{slugify(variant)}"


def build_options(data: dict, labels: list[str], icons: set[str]) -> dict[str, str]:
    norm_to_cid = {norm_char(c["name"][1]): cid for cid, c in data.items()}
    norm_to_cid.setdefault(norm_char("TM Opera O"), norm_to_cid.get(norm_char("T.M. Opera O")))

    options = {"": "— None —"}
    for label in labels:
        slug = label_to_slug(label, data, norm_to_cid)
        if slug in icons:
            options[slug] = label
    return options


def uma_dropdown(team: int, slot: int, options: dict[str, str]) -> dict:
    return {
        "type": "dropdown",
        "label": f"Trainer {team} - Uma {slot}",
        "value": "",
        "options": options,
    }


def assemble_fields(base: dict, options: dict[str, str]) -> dict:
    fields = {}
    for team in range(1, TEAMS + 1):
        fields[f"trainer{team}"] = base[f"trainer{team}"]
        fields[f"trainer{team}gates"] = base[f"trainer{team}gates"]
        for slot in range(1, UMAS_PER_TEAM + 1):
            fields[f"tr{team}uma{slot}"] = uma_dropdown(team, slot, options)

    for key in LAYOUT_KEYS:
        fields[key] = base[key]

    if "fontColor" not in base:
        fields["fontColor"] = {
            "type": "colorpicker",
            "label": "Font Color",
            "value": "#ffffff",
        }
    else:
        fields["fontColor"] = base["fontColor"]

    return fields


def main() -> None:
    base_path = OVERLAY / "fields-base.json"
    with base_path.open(encoding="utf-8") as f:
        base = json.load(f)

    with (ROOT / "umas.json").open(encoding="utf-8") as f:
        data = json.load(f)

    icons = {
        p.stem
        for p in ICONS_DIR.glob("*.png")
        if not p.name.startswith("trained_chr_icon_")
    }
    labels = [
        line.strip()
        for line in (ROOT / "umas_up_to_trackblazer_alphabetical.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    options = build_options(data, labels, icons)
    fields = assemble_fields(base, options)

    out_path = OVERLAY / "fields.json"
    out_path.write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(options) - 1} umas, {TEAMS * UMAS_PER_TEAM} dropdowns)")


if __name__ == "__main__":
    main()
