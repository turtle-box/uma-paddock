import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
ICONS_DIR = ROOT / "icons"
UMA_LIST = ROOT / "uma_list.txt"


def sync_uma_list(path: Path = UMA_LIST) -> list[str]:
    """Read uma list, drop blanks, sort alphabetically, write back."""
    labels = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labels = sorted(labels, key=str.casefold)
    path.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
    return labels

ICON_PATTERN = re.compile(r"trained_chr_icon_(\d+)_(\d+)_01\.png$")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip("[]"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def norm_char(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def outfit_filename_map(data: dict) -> dict[str, str]:
    mapping = {}
    for character in data.values():
        char_slug = slugify(character["name"][1])
        for i, outfit_id in enumerate(sorted(character["outfits"])):
            if i == 0:
                stem = char_slug
            else:
                epithet = slugify(character["outfits"][outfit_id]["epithet"])
                stem = f"{char_slug}-{epithet}"
            mapping[outfit_id] = f"{stem}.png"
    return mapping


def parse_txt_list(path: Path) -> dict[str, dict]:
    chars: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(.+?)\s*\((.+)\)$", line)
        if match:
            char, variant = match.group(1).strip(), match.group(2).strip()
        else:
            char, variant = line, None
        key = norm_char(char)
        entry = chars.setdefault(key, {"name": char, "base": None, "variants": []})
        if variant:
            entry["variants"].append(variant)
        else:
            entry["base"] = char
    return chars


def _char_outfit_ids(
    char_id: str, icons_dir: Path, epithet_map: dict[str, str], txt_map: dict[str, str] | None = None
) -> list[str]:
    ids = set()
    name_to_oid = {v: k for k, v in epithet_map.items()}
    if txt_map:
        name_to_oid.update({v: k for k, v in txt_map.items()})
    for path in icons_dir.glob("*.png"):
        match = ICON_PATTERN.match(path.name)
        if match and match.group(1) == char_id:
            ids.add(match.group(2))
            continue
        outfit_id = name_to_oid.get(path.name)
        if outfit_id and outfit_id.startswith(char_id):
            ids.add(outfit_id)
    return sorted(ids)


def _build_txt_map(
    txt_chars: dict, data: dict, icons_dir: Path, epithet_map: dict[str, str], known: dict[str, str]
) -> dict[str, str]:
    norm_to_cid = {norm_char(c["name"][1]): cid for cid, c in data.items()}
    norm_to_cid.setdefault(norm_char("TM Opera O"), norm_to_cid.get(norm_char("T.M. Opera O")))

    mapping: dict[str, str] = {}
    for key, info in txt_chars.items():
        cid = norm_to_cid.get(key)
        if not cid:
            continue
        char_slug = slugify(data[cid]["name"][1])
        outfit_ids = _char_outfit_ids(cid, icons_dir, epithet_map, known | mapping)
        if not outfit_ids:
            continue

        base_id = f"{cid}01" if f"{cid}01" in outfit_ids else outfit_ids[0]
        if info["base"] is not None and base_id in outfit_ids:
            mapping[base_id] = f"{char_slug}.png"

        non_base = [oid for oid in outfit_ids if oid != base_id]
        for variant, oid in zip(sorted(info["variants"], key=slugify), non_base):
            mapping[oid] = f"{char_slug}-{slugify(variant)}.png"

    return mapping


def txt_filename_map(
    txt_path: Path, data: dict, icons_dir: Path, epithet_map: dict[str, str]
) -> dict[str, str]:
    txt_chars = parse_txt_list(txt_path)
    first = _build_txt_map(txt_chars, data, icons_dir, epithet_map, {})
    return _build_txt_map(txt_chars, data, icons_dir, epithet_map, first)


def _outfit_id_for_file(path: Path, epithet_map: dict[str, str], txt_map: dict[str, str]) -> str | None:
    match = ICON_PATTERN.match(path.name)
    if match:
        return match.group(2)
    txt_to_oid = {v: k for k, v in txt_map.items()}
    if path.name in txt_to_oid:
        return txt_to_oid[path.name]
    for outfit_id, filename in epithet_map.items():
        if filename == path.name:
            return outfit_id
    return None


def rename_icons(icons_dir: Path, mapping: dict[str, str], epithet_map: dict[str, str]) -> int:
    renames: list[tuple[Path, Path]] = []
    for path in icons_dir.glob("*.png"):
        outfit_id = _outfit_id_for_file(path, epithet_map, mapping)
        if not outfit_id:
            continue
        new_name = mapping.get(outfit_id)
        if not new_name or path.name == new_name:
            continue
        renames.append((path, path.with_name(new_name)))

    temp = [(src, src.with_name(f".rename_tmp_{i}.png")) for i, (src, _) in enumerate(renames)]
    for src, mid in temp:
        src.rename(mid)
    for (_, mid), (_, dst) in zip(temp, renames):
        mid.rename(dst)
    return len(renames)


if __name__ == "__main__":
    sync_uma_list()

    with (ROOT / "umas.json").open(encoding="utf-8") as f:
        data = json.load(f)

    epithet_map = outfit_filename_map(data)
    mapping = txt_filename_map(UMA_LIST, data, ICONS_DIR, epithet_map)
    count = rename_icons(ICONS_DIR, mapping, epithet_map)

    print(f"Renamed {count} files ({len(mapping)} outfits mapped)")
