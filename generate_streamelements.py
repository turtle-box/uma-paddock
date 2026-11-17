"""Build overlay/fields.json from fields-base.json plus generated uma dropdowns."""

import json
from pathlib import Path

from slug import build_norm_to_cid, label_to_icon_slug
from uma import sync_uma_list

import sync_umas

ROOT = Path(__file__).resolve().parent
TEAMS = 3
UMAS_PER_TEAM = 3


def _trainer_keys() -> set[str]:
    keys = set()
    for team in range(1, TEAMS + 1):
        keys.add(f"trainer{team}")
        keys.add(f"trainer{team}gates")
    return keys


def uma_dropdown(team: int, slot: int, options: dict[str, str]) -> dict:
    return {
        "type": "dropdown",
        "label": f"Trainer {team} - Uma {slot}",
        "value": "",
        "options": options,
    }


def assemble_fields(base: dict, options: dict[str, str]) -> dict:
    reserved = _trainer_keys()
    fields = {}
    for team in range(1, TEAMS + 1):
        fields[f"trainer{team}"] = base[f"trainer{team}"]
        fields[f"trainer{team}gates"] = base[f"trainer{team}gates"]
        for slot in range(1, UMAS_PER_TEAM + 1):
            fields[f"tr{team}uma{slot}"] = uma_dropdown(team, slot, options)

    for key, value in base.items():
        if key not in reserved:
            fields[key] = value

    return fields


def _present_icons(root: Path) -> set[str]:
    return {
        path.stem
        for path in (root / "icons").glob("*.png")
        if not path.name.startswith("trained_chr_icon_") and not path.name.startswith(".")
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _write_fields_from_list(root: Path) -> None:
    labels = sync_uma_list(root / "uma_list.txt")
    overlay = root / "overlay"
    with (overlay / "fields-base.json").open(encoding="utf-8") as handle:
        base = json.load(handle)
    with (root / "umas.json").open(encoding="utf-8") as handle:
        data = json.load(handle)
    icons = _present_icons(root)
    norm = build_norm_to_cid(data)
    options = {"": "— None —"}
    for label in labels:
        slug = label_to_icon_slug(label, data, norm)
        if slug in icons:
            options[slug] = label
    fields = assemble_fields(base, options)
    out_path = overlay / "fields.json"
    _write_json(out_path, fields)
    print(f"Wrote {out_path} ({len(options) - 1} umas, {TEAMS * UMAS_PER_TEAM} dropdowns)")


def _write_fields_from_roster(root: Path) -> None:
    roster = sync_umas.load_roster(root / "roster.json")
    entries = sync_umas.iter_outfit_entries(roster)
    alias_map, messages = sync_umas.resolve_alias_file(root / "event_aliases.txt", entries)
    for message in messages:
        print(message)
    umas_path = root / "umas.json"
    umas = json.loads(umas_path.read_text(encoding="utf-8")) if umas_path.is_file() else {}
    known = {entry.get("slug") for entry in entries if entry.get("slug")}
    present = _present_icons(root)
    pairs = []
    for entry in entries:
        if entry.get("enabled") is False:
            continue
        if entry.get("status") not in (None, "active", "missing-upstream"):
            continue
        slug = entry.get("slug") or ""
        if slug not in present:
            continue
        pairs.append((slug, sync_umas.outfit_label(entry, alias_map.get(entry["id"]))))
    for slug, label in sync_umas.find_extra_labels(
        sync_umas.read_uma_list(root / "uma_list.txt"), known, umas, root / "icons"
    ):
        pairs.append((slug, label))
    pairs.sort(key=lambda item: item[1].casefold())
    sync_umas.write_uma_list(root / "uma_list.txt", [label for _slug, label in pairs])
    options = {"": "— None —"}
    options.update(pairs)
    overlay = root / "overlay"
    with (overlay / "fields-base.json").open(encoding="utf-8") as handle:
        base = json.load(handle)
    fields = assemble_fields(base, options)
    out_path = overlay / "fields.json"
    _write_json(out_path, fields)
    print(f"Wrote {out_path} ({len(options) - 1} umas, {TEAMS * UMAS_PER_TEAM} dropdowns)")


def write_fields(root: Path | None = None) -> None:
    root = Path(root) if root is not None else ROOT
    if (root / "roster.json").is_file():
        _write_fields_from_roster(root)
    else:
        _write_fields_from_list(root)


def main() -> None:
    write_fields(ROOT)


if __name__ == "__main__":
    main()
