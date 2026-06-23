"""Build overlay/fields.json from fields-base.json plus generated uma dropdowns."""

import json
from pathlib import Path

from slug import build_norm_to_cid, label_to_icon_slug
from uma import ICONS_DIR, UMA_LIST, sync_uma_list

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


def build_options(data: dict, labels: list[str], icons: set[str]) -> dict[str, str]:
    norm_to_cid = build_norm_to_cid(data)

    options = {"": "— None —"}
    for label in labels:
        slug = label_to_icon_slug(label, data, norm_to_cid)
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
    labels = sync_uma_list(UMA_LIST)

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

    options = build_options(data, labels, icons)
    fields = assemble_fields(base, options)

    out_path = OVERLAY / "fields.json"
    out_path.write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(options) - 1} umas, {TEAMS * UMAS_PER_TEAM} dropdowns)")


if __name__ == "__main__":
    main()
