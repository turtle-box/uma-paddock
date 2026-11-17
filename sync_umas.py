"""Sync the Global Uma Musume roster and icons from alpha123/uma-tools.

A plain run applies changes. ``--preview`` prints the plan and writes nothing.
Existing icon slugs are kept. Event nicknames live in ``event_aliases.txt`` and
never rename an icon. Nothing is deleted: an outfit that disappears upstream is
kept and reported.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from slug import build_norm_to_cid, label_to_icon_slug, norm_char, slugify

ROOT = Path(__file__).resolve().parent
REPO = "alpha123/uma-tools"
USER_AGENT = "uma-paddock-sync"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
STANDARD_HEADER = "# Uma name: In-game title = Event name"
MATCH_THRESHOLD = 0.86
MATCH_MARGIN = 0.04
LABEL_RE = re.compile(r"^(.+?)\s*\((.+)\)$")


def epithet_title(epithet: str) -> str:
    text = (epithet or "").strip()
    if text.startswith("[") and text.endswith("]") and len(text) >= 2:
        text = text[1:-1]
    return text.strip()


def alias_is_blank(alias: str) -> bool:
    return not any(ch.isalnum() for ch in alias)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def split_label(label: str) -> tuple[str, str | None]:
    match = LABEL_RE.match(label.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return label.strip(), None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_uma_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_uma_list(path: Path, labels: list[str]) -> None:
    unique = sorted(set(labels), key=str.casefold)
    text = "\n".join(unique)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8", newline="\n")


def load_roster(path: Path) -> dict:
    if not path.exists():
        return {"upstream": {}, "outfits": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("upstream", {})
    data.setdefault("outfits", {})
    return data


def iter_outfit_entries(roster: dict) -> list[dict]:
    entries = []
    for oid, entry in roster.get("outfits", {}).items():
        item = dict(entry)
        item["id"] = oid
        entries.append(item)
    return entries


def outfit_label(entry: dict, alias: str | None) -> str:
    if entry.get("source") == "manual":
        return entry.get("label") or entry.get("name") or entry.get("slug") or ""
    name = entry.get("name") or ""
    if entry.get("base"):
        return name
    if alias and not alias_is_blank(alias):
        return f"{name} ({alias})"
    title = epithet_title(entry.get("epithet") or "")
    if title:
        return f"{name} [{title}]"
    return name


def find_extra_labels(
    labels: list[str], known_slugs: set[str], umas: dict, icons_dir: Path
) -> list[tuple[str, str]]:
    """Uma-list lines whose icon is on disk but which are not in the roster."""
    norm = build_norm_to_cid(umas) if umas else {}
    extras = []
    seen = set(known_slugs)
    for label in labels:
        if umas:
            slug = label_to_icon_slug(label, umas, norm)
        else:
            name, variant = split_label(label)
            slug = slugify(name) if not variant else f"{slugify(name)}-{slugify(variant)}"
        if not slug or slug in seen:
            continue
        if not (icons_dir / f"{slug}.png").is_file():
            continue
        extras.append((slug, label))
        seen.add(slug)
    return extras


def _oid_key(oid: str):
    return (0, int(oid)) if str(oid).isdigit() else (1, str(oid))


def _english_name(character: dict) -> str:
    name = character.get("name", ["", ""])
    if isinstance(name, list) and len(name) > 1 and name[1]:
        return str(name[1])
    if isinstance(name, str):
        return name
    return ""


def trained_stem(entry) -> str | None:
    if isinstance(entry, list) and entry and isinstance(entry[0], str):
        return entry[0]
    return None


def unique_slug(slug: str, used: set[str]) -> str:
    if slug not in used:
        return slug
    number = 2
    while f"{slug}_{number}" in used:
        number += 1
    return f"{slug}_{number}"


def best_match(query: str, items: list, texts_of):
    """Return (item, status) where status is exact, fuzzy, ambiguous, or none."""
    query_norm = normalize(query)
    if not query_norm or not items:
        return None, "none"
    scored = []
    for item in items:
        best = 0.0
        exact = False
        for text in texts_of(item):
            norm = normalize(text)
            if norm and norm == query_norm:
                exact = True
                best = 1.0
            elif norm:
                best = max(best, difflib.SequenceMatcher(None, query_norm, norm).ratio())
        scored.append((best, exact, item))
    exacts = [row for row in scored if row[1]]
    if len(exacts) == 1:
        return exacts[0][2], "exact"
    if len(exacts) > 1:
        return None, "ambiguous"
    scored.sort(key=lambda row: row[0], reverse=True)
    if scored[0][0] < MATCH_THRESHOLD:
        return None, "none"
    if len(scored) > 1 and scored[1][0] >= MATCH_THRESHOLD and scored[0][0] - scored[1][0] < MATCH_MARGIN:
        return None, "ambiguous"
    return scored[0][2], "fuzzy"


def _parse_alias_line(raw: str) -> dict:
    if ":" not in raw:
        return {"kind": "noop" if "=" not in raw else "alias", "name": "", "title": "", "alias": "", "raw": raw, "broken": "=" in raw}
    name, rest = raw.split(":", 1)
    name = name.strip()
    if "=" not in rest:
        return {"kind": "noop", "name": name, "title": rest.strip(), "alias": "", "raw": raw, "broken": False}
    title, alias = rest.split("=", 1)
    title = title.strip()
    alias = alias.strip()
    if not name or alias_is_blank(alias):
        return {"kind": "noop", "name": name, "title": title, "alias": "", "raw": raw, "broken": False}
    return {"kind": "alias", "name": name, "title": title, "alias": alias, "raw": raw, "broken": False}


def _parse_alias_text(text: str) -> tuple[list[str], list[dict], list[str]]:
    header: list[str] = []
    entries: list[dict] = []
    pending: list[str] = []
    trailing: list[str] = []
    in_header = True
    for line in text.splitlines():
        stripped = line.strip()
        if in_header:
            if not stripped:
                in_header = False
                continue
            if stripped.startswith("#"):
                header.append(line.rstrip())
                continue
            in_header = False
        if not stripped:
            continue
        if stripped.startswith("#"):
            pending.append(line.rstrip())
            continue
        entries.append({"comments": pending, "parsed": _parse_alias_line(line)})
        pending = []
    trailing = pending
    return header, entries, trailing


def _char_groups(outfits: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for outfit in outfits:
        if outfit.get("base") or outfit.get("source") == "manual":
            continue
        cid = outfit.get("chara") or ""
        group = groups.setdefault(cid, {"chara": cid, "name": outfit.get("name") or "", "outfits": []})
        group["name"] = outfit.get("name") or group["name"]
        group["outfits"].append(outfit)
    return list(groups.values())


def _match_alias(parsed: dict, groups: list[dict]):
    char, status = best_match(parsed["name"], groups, lambda group: [group["name"]])
    if status in ("none", "ambiguous") or char is None:
        return None, status if status == "ambiguous" else "none"
    outfit, title_status = best_match(
        parsed["title"], char["outfits"], lambda item: [epithet_title(item.get("epithet") or "")]
    )
    if title_status in ("none", "ambiguous") or outfit is None:
        return None, "ambiguous" if title_status == "ambiguous" else "none"
    how = "exact" if status == "exact" and title_status == "exact" else "fuzzy"
    return outfit, how


def _alias_line(name: str, title: str, alias: str) -> str:
    return f"{name}: {title} = {alias}"


def _render_alias_file(header: list[str], entries: list[dict], trailing: list[str]) -> str:
    header = list(header)
    if STANDARD_HEADER not in header:
        header.insert(0, STANDARD_HEADER)
    lines = list(header)
    lines.append("")
    entries = sorted(
        entries,
        key=lambda entry: (
            entry["sort_name"].casefold(),
            entry["sort_title"].casefold(),
            entry["line"].casefold(),
        ),
    )
    for entry in entries:
        lines.extend(entry["comments"])
        lines.append(entry["line"])
    lines.extend(trailing)
    return "\n".join(lines) + "\n"


def merge_aliases(existing: str | None, outfits: list[dict], seed: dict[str, str]) -> tuple[str, dict[str, str], list[str]]:
    """Merge event_aliases.txt. Returns (text, outfit-id -> alias, messages)."""
    groups = _char_groups(outfits)
    alts = [outfit for group in groups for outfit in group["outfits"]]
    by_id = {outfit["id"]: outfit for outfit in alts}
    messages: list[str] = []
    alias_map: dict[str, str] = {}
    covered: set[str] = set()
    entries: list[dict] = []

    if existing is None:
        header = [STANDARD_HEADER]
        trailing: list[str] = []
        for outfit in alts:
            alias = seed.get(outfit["id"], "")
            if alias_is_blank(alias):
                alias = ""
            else:
                alias_map[outfit["id"]] = alias
            title = epithet_title(outfit.get("epithet") or "")
            name = outfit.get("name") or ""
            covered.add(outfit["id"])
            entries.append(
                {
                    "comments": [],
                    "line": _alias_line(name, title, alias),
                    "sort_name": name,
                    "sort_title": title,
                }
            )
        return _render_alias_file(header, entries, trailing), alias_map, messages

    header, parsed_entries, trailing = _parse_alias_text(existing)
    for item in parsed_entries:
        parsed = item["parsed"]
        comments = item["comments"]
        raw = parsed["raw"]
        if parsed["kind"] == "noop" and not parsed.get("broken"):
            outfit, how = _match_alias(parsed, groups) if parsed["name"] and parsed["title"] else (None, "none")
            if outfit is not None and how == "exact" and outfit["id"] not in covered:
                covered.add(outfit["id"])
                entries.append(
                    {
                        "comments": comments,
                        "line": raw,
                        "sort_name": outfit.get("name") or parsed["name"],
                        "sort_title": epithet_title(outfit.get("epithet") or ""),
                    }
                )
            else:
                entries.append(
                    {
                        "comments": comments,
                        "line": raw,
                        "sort_name": parsed["name"] or raw,
                        "sort_title": parsed["title"],
                    }
                )
            continue
        if parsed["kind"] != "alias" or parsed.get("broken"):
            messages.append(f"Could not match alias line, left unused: {raw}")
            entries.append(
                {"comments": comments, "line": raw, "sort_name": raw, "sort_title": ""}
            )
            continue
        outfit, how = _match_alias(parsed, groups)
        title = epithet_title(outfit.get("epithet") or "") if outfit else ""
        name = outfit.get("name") or "" if outfit else ""
        if outfit is None or how in ("none", "ambiguous"):
            if how == "ambiguous":
                messages.append(f"Ambiguous alias line, left unused: {raw}")
            else:
                messages.append(f"Could not match alias line, left unused: {raw}")
            entries.append(
                {
                    "comments": comments,
                    "line": raw,
                    "sort_name": parsed["name"] or raw,
                    "sort_title": parsed["title"],
                }
            )
            continue
        if outfit["id"] in covered or outfit["id"] in alias_map:
            messages.append(f"Ambiguous alias line, left unused: {raw}")
            entries.append(
                {
                    "comments": comments,
                    "line": raw,
                    "sort_name": parsed["name"] or raw,
                    "sort_title": parsed["title"],
                }
            )
            continue
        alias_map[outfit["id"]] = parsed["alias"]
        covered.add(outfit["id"])
        if how == "fuzzy":
            messages.append(f"Matched alias '{raw}' to {name}: {title}")
        entries.append(
            {
                "comments": comments,
                "line": _alias_line(name, title, parsed["alias"]),
                "sort_name": name,
                "sort_title": title,
            }
        )

    for outfit in alts:
        if outfit["id"] in covered:
            continue
        name = outfit.get("name") or ""
        title = epithet_title(outfit.get("epithet") or "")
        entries.append(
            {
                "comments": [],
                "line": _alias_line(name, title, ""),
                "sort_name": name,
                "sort_title": title,
            }
        )
        covered.add(outfit["id"])
    return _render_alias_file(header, entries, trailing), alias_map, messages


def resolve_alias_file(path: Path, entries: list[dict]) -> tuple[dict[str, str], list[str]]:
    if not path.exists():
        return {}, []
    text = path.read_text(encoding="utf-8")
    _rendered, alias_map, messages = merge_aliases(text, entries, {})
    return alias_map, messages


def fetch_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Failed to download {url}: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
    raise SystemExit(f"Failed to download {url}: {last_error}")


def resolve_sha(ref: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        return ref.lower()
    url = f"https://api.github.com/repos/{REPO}/commits/{quote(ref, safe='')}"
    payload = json.loads(fetch_bytes(url).decode("utf-8"))
    sha = payload.get("sha")
    if not isinstance(sha, str) or not sha:
        raise SystemExit(f"Could not resolve uma-tools ref {ref}")
    return sha


def _check_pngs(blobs: dict[str, bytes]) -> None:
    for stem, data in blobs.items():
        if not data.startswith(PNG_MAGIC):
            raise SystemExit(f"Refusing {stem}: uma-tools did not return a PNG.")


def load_source(source: Path) -> tuple[str, bytes, dict, dict, dict[str, bytes]]:
    source = Path(source)
    umas_path = source / "umas.json"
    icons_path = source / "icons.json"
    if not umas_path.is_file() or not icons_path.is_file():
        raise SystemExit(f"Source {source} needs umas.json and icons.json.")
    umas_bytes = umas_path.read_bytes()
    umas = json.loads(umas_bytes.decode("utf-8"))
    icons_doc = json.loads(icons_path.read_text(encoding="utf-8"))
    ref_path = source / "REF"
    sha = ref_path.read_text(encoding="utf-8").strip() if ref_path.is_file() else "local"
    icon_dir = source / "icons" / "chara"
    if not icon_dir.is_dir():
        icon_dir = source / "icons"
    blobs = {}
    if icon_dir.is_dir():
        for path in icon_dir.glob("*.png"):
            blobs[path.stem] = path.read_bytes()
    _check_pngs(blobs)
    return sha, umas_bytes, umas, icons_doc, blobs


def load_network(ref: str) -> tuple[str, bytes, dict, dict, dict[str, bytes]]:
    sha = resolve_sha(ref)
    base = f"https://raw.githubusercontent.com/{REPO}/{sha}"
    print(f"Fetching roster from uma-tools {sha}...")
    umas_bytes = fetch_bytes(f"{base}/umalator-global/umas.json")
    icons_doc = json.loads(fetch_bytes(f"{base}/icons.json").decode("utf-8"))
    umas = json.loads(umas_bytes.decode("utf-8"))
    stems = []
    for character in umas.values():
        for oid in character.get("outfits", {}):
            stem = trained_stem(icons_doc.get(str(oid)))
            if stem and stem not in stems:
                stems.append(stem)
    print(f"Fetching {len(stems)} icons...")
    blobs = {}
    for stem in stems:
        blobs[stem] = fetch_bytes(f"{base}/icons/chara/{quote(stem)}.png")
    _check_pngs(blobs)
    return sha, umas_bytes, umas, icons_doc, blobs


def _upstream_outfits(umas: dict, icons_doc: dict) -> list[dict]:
    outfits = []
    for cid, character in umas.items():
        name = _english_name(character)
        raw = character.get("outfits") or {}
        oids = sorted((str(oid) for oid in raw), key=_oid_key)
        if not oids:
            continue
        base_id = oids[0]
        for oid in oids:
            info = raw[oid] if oid in raw else raw.get(int(oid), {})
            epithet = ""
            if isinstance(info, dict):
                epithet = str(info.get("epithet") or "")
            outfits.append(
                {
                    "id": oid,
                    "chara": str(cid),
                    "upstream_name": name,
                    "epithet": epithet,
                    "base": oid == base_id,
                    "icon": trained_stem(icons_doc.get(oid)),
                }
            )
    return outfits


def build_plan(root: Path, sha: str, umas: dict, icons_doc: dict, blobs: dict[str, bytes], *, update_icons: bool) -> dict:
    icons_dir = root / "icons"
    prev = load_roster(root / "roster.json")
    prev_outfits = prev.get("outfits", {})
    uma_labels = read_uma_list(root / "uma_list.txt")
    alias_path = root / "event_aliases.txt"
    upstream = _upstream_outfits(umas, icons_doc)
    by_id = {outfit["id"]: outfit for outfit in upstream}
    messages: list[str] = []

    local_files = {}
    local_hash = {}
    if icons_dir.is_dir():
        for path in icons_dir.glob("*.png"):
            if path.name.startswith("."):
                continue
            local_files[path.stem] = path
            local_hash[path.stem] = sha256(path.read_bytes())
    preexisting = set(local_files)

    hash_to_oids: dict[str, list[str]] = {}
    for outfit in upstream:
        data = blobs.get(outfit["icon"] or "")
        if data is None:
            continue
        outfit["hash"] = sha256(data)
        hash_to_oids.setdefault(outfit["hash"], []).append(outfit["id"])

    assigned: dict[str, str] = {}
    used: set[str] = set()
    for oid, entry in prev_outfits.items():
        slug = entry.get("slug") or ""
        if slug:
            used.add(slug)
        if entry.get("source") == "manual":
            continue
        if slug:
            assigned[oid] = slug

    for stem, digest in sorted(local_hash.items()):
        if stem in used:
            continue
        oids = [oid for oid in hash_to_oids.get(digest, []) if oid not in assigned]
        if len(oids) == 1:
            assigned[oids[0]] = stem
            used.add(stem)
        elif len(oids) > 1:
            messages.append(f"Icon {stem}.png matches more than one outfit; left it unused.")

    norm_map = build_norm_to_cid(umas)
    name_to_cid = {}
    for outfit in upstream:
        name_to_cid.setdefault(norm_char(outfit["upstream_name"]), outfit["chara"])

    display: dict[str, str] = {}
    for entry in prev_outfits.values():
        cid = entry.get("chara") or ""
        if cid and entry.get("name") and entry.get("source") != "manual":
            display.setdefault(cid, entry["name"])
    prev_display = set(display)

    base_names: dict[str, str] = {}
    alt_names: dict[str, str] = {}
    for label in uma_labels:
        char_name, variant = split_label(label)
        cid = name_to_cid.get(norm_char(char_name))
        if not cid:
            continue
        if variant is None:
            base_names[cid] = char_name
        else:
            alt_names.setdefault(cid, char_name)
        slug = label_to_icon_slug(label, umas, norm_map)
        if slug in used or slug not in local_files:
            continue
        if variant is None:
            candidates = [outfit for outfit in upstream if outfit["chara"] == cid and outfit["base"] and outfit["id"] not in assigned]
        else:
            candidates = [outfit for outfit in upstream if outfit["chara"] == cid and not outfit["base"] and outfit["id"] not in assigned]
        if len(candidates) == 1:
            assigned[candidates[0]["id"]] = slug
            used.add(slug)
        else:
            messages.append(f"Could not pair existing icon {slug}.png for {label}; kept the file.")

    for cid, name in alt_names.items():
        if cid not in prev_display:
            display.setdefault(cid, name)
    for cid, name in base_names.items():
        if cid not in prev_display:
            display[cid] = name
    for outfit in upstream:
        display.setdefault(outfit["chara"], outfit["upstream_name"])

    for outfit in upstream:
        if outfit["id"] in assigned:
            continue
        if outfit["base"]:
            slug = slugify(display.get(outfit["chara"]) or outfit["upstream_name"])
        else:
            base = next(item for item in upstream if item["chara"] == outfit["chara"] and item["base"])
            char_slug = assigned.get(base["id"]) or slugify(outfit["upstream_name"])
            slug = f"{char_slug}-{slugify(epithet_title(outfit['epithet']))}"
        slug = unique_slug(slug, used)
        assigned[outfit["id"]] = slug
        used.add(slug)

    roster_outfits: dict[str, dict] = {}
    for outfit in upstream:
        prev_entry = prev_outfits.get(outfit["id"])
        if prev_entry and prev_entry.get("source") != "manual":
            name = prev_entry.get("name") or display[outfit["chara"]]
            enabled = prev_entry.get("enabled", True)
        else:
            name = display[outfit["chara"]]
            enabled = True
        roster_outfits[outfit["id"]] = {
            "chara": outfit["chara"],
            "name": name,
            "epithet": outfit["epithet"],
            "slug": assigned[outfit["id"]],
            "icon": outfit["icon"] or "",
            "base": outfit["base"],
            "source": "upstream",
            "enabled": enabled,
            "status": "active",
        }

    missing = []
    for oid, entry in prev_outfits.items():
        if entry.get("source") == "manual":
            roster_outfits[oid] = dict(entry)
            continue
        if oid in by_id:
            continue
        kept = dict(entry)
        kept["status"] = "missing-upstream"
        roster_outfits[oid] = kept
        label = kept.get("name") or kept.get("slug") or oid
        missing.append(f"{label} ({kept.get('slug') or oid})")

    known_slugs = {entry.get("slug") for entry in roster_outfits.values() if entry.get("slug")}
    for slug, label in find_extra_labels(uma_labels, known_slugs, umas, icons_dir):
        name, variant = split_label(label)
        roster_outfits[f"manual:{slug}"] = {
            "chara": "",
            "name": name,
            "label": label,
            "epithet": "",
            "slug": slug,
            "icon": "",
            "base": variant is None,
            "source": "manual",
            "enabled": True,
            "status": "active",
        }
        known_slugs.add(slug)

    entries = []
    for oid in sorted(roster_outfits, key=_oid_key):
        item = dict(roster_outfits[oid])
        item["id"] = oid
        entries.append(item)

    seed: dict[str, str] = {}
    if not alias_path.exists():
        slug_to_oid = {}
        for oid, slug in assigned.items():
            slug_to_oid.setdefault(slug, oid)
        for label in uma_labels:
            _name, variant = split_label(label)
            if not variant:
                continue
            slug = label_to_icon_slug(label, umas, norm_map)
            oid = slug_to_oid.get(slug)
            if oid and not by_id.get(oid, {}).get("base", True):
                seed[oid] = variant

    existing_alias = alias_path.read_text(encoding="utf-8") if alias_path.exists() else None
    alias_text, alias_map, alias_messages = merge_aliases(existing_alias, entries, seed)
    messages.extend(alias_messages)

    icon_writes = []
    replaced = []
    for outfit in upstream:
        entry = roster_outfits[outfit["id"]]
        slug = entry["slug"]
        stem = outfit.get("icon")
        data = blobs.get(stem or "")
        if not data:
            messages.append(f"No uma-tools icon for {entry['name']} outfit {outfit['id']}.")
            continue
        digest = sha256(data)
        current = local_hash.get(slug)
        if current is None:
            icon_writes.append((slug, data))
            continue
        if current == digest:
            continue
        if update_icons or outfit["id"] not in prev_outfits:
            icon_writes.append((slug, data))
            replaced.append((slug, outfit["id"], outfit["epithet"], entry["name"]))
        else:
            messages.append(f"Icon bytes differ from uma-tools and were left unchanged: icons/{slug}.png")

    new_bases = []
    new_events = []
    for outfit in upstream:
        entry = roster_outfits[outfit["id"]]
        slug = entry["slug"]
        if outfit["id"] in prev_outfits or slug in preexisting:
            continue
        if outfit["base"]:
            new_bases.append((entry["name"], slug))
        else:
            new_events.append((entry["name"], epithet_title(outfit["epithet"]), slug))
    new_bases.sort(key=lambda item: item[0].casefold())
    new_events.sort(key=lambda item: (item[0].casefold(), item[1].casefold()))

    blank = 0
    for entry in entries:
        if entry.get("base") or entry.get("source") == "manual":
            continue
        if entry["id"] not in alias_map:
            blank += 1

    roster = {
        "upstream": {
            "repo": REPO,
            "ref": sha,
            "umas": "umalator-global/umas.json",
            "icons": "icons.json",
        },
        "outfits": {oid: roster_outfits[oid] for oid in sorted(roster_outfits, key=_oid_key)},
    }
    labels = []
    for entry in entries:
        if entry.get("enabled") is False:
            continue
        slug = entry.get("slug") or ""
        # An icon counts as present when it is already on disk or this run will write it.
        will_write = any(item[0] == slug for item in icon_writes)
        if slug not in local_files and not will_write:
            continue
        if entry.get("status") not in ("active", "missing-upstream"):
            continue
        labels.append(outfit_label(entry, alias_map.get(entry["id"])))

    return {
        "messages": messages,
        "roster": roster,
        "alias_text": alias_text,
        "icon_writes": icon_writes,
        "replaced": replaced,
        "new_bases": new_bases,
        "new_events": new_events,
        "missing": missing,
        "blank_aliases": blank,
        "labels": labels,
        "sha": sha,
    }


def _print_summary(plan: dict, preview: bool) -> None:
    if preview:
        print("Preview only; no files were written.")
    for slug, oid, epithet, name in plan["replaced"]:
        verb = "Would replace" if preview else "Replaced"
        print(f"{verb} icons/{slug}.png with uma-tools outfit {oid} {epithet} ({name}).")
    if plan["new_bases"]:
        print("New umas:")
        for name, slug in plan["new_bases"]:
            print(f"  {name} ({slug})")
    if plan["new_events"]:
        print("New event costumes:")
        for name, title, slug in plan["new_events"]:
            print(f"  {name}: {title} ({slug})")
    if plan["missing"]:
        print("Missing upstream, kept:")
        for line in plan["missing"]:
            print(f"  {line}")
    if plan["blank_aliases"]:
        print(f"{plan['blank_aliases']} event costumes have no event name in event_aliases.txt.")
    outfit_count = len(plan["roster"]["outfits"])
    print(f"Roster: {outfit_count} outfits ({len(plan['missing'])} missing upstream).")


def _apply(root: Path, plan: dict, umas_bytes: bytes) -> None:
    icons_dir = root / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    (root / "umas.json").write_bytes(umas_bytes)
    for slug, data in plan["icon_writes"]:
        (icons_dir / f"{slug}.png").write_bytes(data)
    roster_path = root / "roster.json"
    roster_path.write_text(
        json.dumps(plan["roster"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "event_aliases.txt").write_text(plan["alias_text"], encoding="utf-8", newline="\n")
    write_uma_list(root / "uma_list.txt", plan["labels"])


def run(
    root: Path | None = None,
    *,
    source: Path | None = None,
    ref: str = "master",
    preview: bool = False,
    update_icons: bool = False,
    pause: bool | None = None,
) -> int:
    root = Path(root) if root is not None else ROOT
    if source is not None:
        sha, umas_bytes, umas, icons_doc, blobs = load_source(source)
    else:
        sha, umas_bytes, umas, icons_doc, blobs = load_network(ref)
    print(f"uma-tools commit {sha}")
    plan = build_plan(root, sha, umas, icons_doc, blobs, update_icons=update_icons)
    for message in plan["messages"]:
        print(message)
    _print_summary(plan, preview)
    if preview:
        return 0
    _apply(root, plan, umas_bytes)
    new_events = len(plan["new_events"])
    if new_events:
        print(f"{new_events} event costumes were added.")
        print("You can assign aliases to them in event_aliases.txt, and these labels will show in the dropdown.")
        if pause is None:
            pause = sys.stdin.isatty()
        if pause:
            print("Edit event_aliases.txt, save, then press Enter; or just press Enter to skip.")
            input()
    from generate_streamelements import write_fields

    write_fields(root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the Global uma roster and icons from uma-tools.")
    parser.add_argument("--preview", action="store_true", help="Show what would change without writing files")
    parser.add_argument("--ref", default="master", help="uma-tools commit or branch (default: newest master)")
    parser.add_argument("--source", type=Path, help="Read uma-tools JSON and icons from this directory instead of the network")
    parser.add_argument("--update-icons", action="store_true", help="Overwrite icons whose bytes differ from uma-tools")
    args = parser.parse_args(argv)
    return run(ROOT, source=args.source, ref=args.ref, preview=args.preview, update_icons=args.update_icons)


if __name__ == "__main__":
    raise SystemExit(main())
