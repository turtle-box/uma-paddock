"""Offline tests for sync_umas.py. Network is not used; fixtures stand in for uma-tools."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate_streamelements
import sync_umas
from slug import build_norm_to_cid, label_to_icon_slug

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def png(token: str) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + token.encode("utf-8")


def snapshot(root: Path) -> dict[str, bytes]:
    data = {}
    if not root.exists():
        return data
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            data[path.relative_to(root).as_posix()] = path.read_bytes()
    return data


def write_source(source: Path, characters: list[dict], ref: str = "local") -> None:
    source.mkdir(parents=True, exist_ok=True)
    icon_dir = source / "icons"
    icon_dir.mkdir(exist_ok=True)
    umas = {}
    icons = {}
    for character in characters:
        cid = str(character["id"])
        outfits = {}
        for outfit in character["outfits"]:
            oid = str(outfit["id"])
            outfits[oid] = {"epithet": outfit["epithet"], "rarity": 3}
            stem = outfit.get("stem") or f"trained_chr_icon_{cid}_{oid}_01"
            (icon_dir / f"{stem}.png").write_bytes(outfit["png"])
            icons[oid] = [stem]
        umas[cid] = {"name": ["", character["name"]], "outfits": outfits}
    (source / "umas.json").write_bytes(json.dumps(umas, ensure_ascii=False).encode("utf-8"))
    (source / "icons.json").write_text(json.dumps(icons), encoding="utf-8", newline="\n")
    (source / "REF").write_text(ref + "\n", encoding="utf-8", newline="\n")


def minimal_base() -> dict:
    base = {}
    for team, name in ((1, "First"), (2, "Second"), (3, "Third")):
        base[f"trainer{team}"] = {"type": "text", "label": f"Trainer {team}", "value": name}
        base[f"trainer{team}gates"] = {"type": "text", "label": "Gates", "value": ""}
    base["iconBaseUrl"] = {"type": "text", "label": "Icon base URL", "value": "http://example/icons"}
    return base


class Project:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.source = Path(self.tmp.name) / "source"
        self.root.mkdir()
        (self.root / "overlay").mkdir()
        (self.root / "overlay" / "fields-base.json").write_text(
            json.dumps(minimal_base()), encoding="utf-8", newline="\n"
        )
        (self.root / "icons").mkdir()

    def close(self):
        self.tmp.cleanup()

    def uma_list(self, labels: list[str]) -> None:
        sync_umas.write_uma_list(self.root / "uma_list.txt", labels)

    def run(self, **kwargs) -> str:
        kwargs.setdefault("pause", False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sync_umas.run(self.root, source=self.source, **kwargs)
        if code != 0:
            raise AssertionError(f"sync returned {code}\n{buf.getvalue()}")
        return buf.getvalue()

    def options(self) -> dict[str, str]:
        fields = json.loads((self.root / "overlay" / "fields.json").read_text(encoding="utf-8"))
        return fields["tr1uma1"]["options"]


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.project = Project()

    def tearDown(self):
        self.project.close()

    def test_seed_preserves_today_slugs_and_labels(self):
        options = json.loads((FIXTURES / "original_options.json").read_text(encoding="utf-8"))
        uma_list = (FIXTURES / "original_uma_list.txt").read_text(encoding="utf-8")
        (self.project.root / "uma_list.txt").write_text(uma_list, encoding="utf-8", newline="\n")
        shutil.copy(REPO / "overlay" / "fields-base.json", self.project.root / "overlay" / "fields-base.json")

        groups: dict[str, dict] = {}
        for slug, label in options.items():
            if not slug:
                continue
            name, variant = sync_umas.split_label(label)
            group = groups.setdefault(name, {"base": None, "alts": []})
            if variant is None:
                group["base"] = (slug, label)
            else:
                group["alts"].append((slug, label, variant))

        characters = []
        for index, (name, group) in enumerate(sorted(groups.items(), key=lambda item: item[0].casefold()), start=1):
            self.assertIsNotNone(group["base"], name)
            cid = str(2000 + index)
            upstream_name = "T.M. Opera O" if name == "TM Opera O" else name
            outfits = []
            base_slug, _base_label = group["base"]
            outfits.append(
                {
                    "id": f"{cid}01",
                    "epithet": "[Rookie]",
                    "png": png(base_slug),
                }
            )
            (self.project.root / "icons" / f"{base_slug}.png").write_bytes(png(base_slug))
            for alt_index, (slug, _label, _variant) in enumerate(group["alts"], start=2):
                outfits.append(
                    {
                        "id": f"{cid}{alt_index:02d}",
                        "epithet": f"[Costume {alt_index}]",
                        "png": png(slug),
                    }
                )
                (self.project.root / "icons" / f"{slug}.png").write_bytes(png(slug))
            characters.append({"id": cid, "name": upstream_name, "outfits": outfits})
        write_source(self.project.source, characters, ref="fixture")

        # The fixture names have to reproduce today's slugs, or seeding would rename icons.
        umas = json.loads((self.project.source / "umas.json").read_text(encoding="utf-8"))
        norm = build_norm_to_cid(umas)
        for slug, label in options.items():
            if not slug:
                continue
            self.assertEqual(label_to_icon_slug(label, umas, norm), slug, label)

        before_icons = snapshot(self.project.root / "icons")
        output = self.project.run()
        fields = json.loads((self.project.root / "overlay" / "fields.json").read_text(encoding="utf-8"))
        for team in range(1, 4):
            for slot in range(1, 4):
                self.assertEqual(fields[f"tr{team}uma{slot}"]["options"], options)
        self.assertEqual(snapshot(self.project.root / "icons"), before_icons)
        roster = json.loads((self.project.root / "roster.json").read_text(encoding="utf-8"))
        self.assertEqual({entry["slug"] for entry in roster["outfits"].values()}, {slug for slug in options if slug})
        self.assertNotIn("event costumes were added.", output)
        self.assertIn("uma-tools commit fixture", output)
        aliases = (self.project.root / "event_aliases.txt").read_text(encoding="utf-8")
        self.assertIn("Gold Ship: Costume 2 = Summer\n", aliases)
        self.assertIn("TM Opera O: Costume 2 = New Year\n", aliases)
        self.assertNotIn("Special Week: Rookie", aliases)

    def test_new_base_and_alt_then_idempotent(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")}],
                }
            ],
        )
        first = self.project.run()
        self.assertNotIn("were added.", first)
        self.assertEqual(self.project.options()["special_week"], "Special Week")
        aliases = (self.project.root / "event_aliases.txt").read_text(encoding="utf-8")
        self.assertNotIn("Special Week:", aliases)

        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                },
                {
                    "id": "1087",
                    "name": "Aston Machan",
                    "outfits": [{"id": "108701", "epithet": "[Flare]", "png": png("aston")}],
                },
            ],
        )
        second = self.project.run()
        self.assertIn(
            "1 event costumes were added.\n"
            "You can assign aliases to them in event_aliases.txt, and these labels will show in the dropdown.\n",
            second,
        )
        options = self.project.options()
        self.assertEqual(options["special_week"], "Special Week")
        self.assertEqual(options["special_week-hoppn_happy_heart"], "Special Week [Hopp'n Happy Heart]")
        self.assertEqual(options["aston_machan"], "Aston Machan")
        self.assertTrue((self.project.root / "icons" / "aston_machan.png").is_file())
        self.assertTrue((self.project.root / "icons" / "special_week-hoppn_happy_heart.png").is_file())
        text = (self.project.root / "event_aliases.txt").read_text(encoding="utf-8")
        self.assertIn("Special Week: Hopp'n Happy Heart = \n", text)
        self.assertNotIn("Aston Machan:", text)
        self.assertEqual(text.count(sync_umas.STANDARD_HEADER), 1)

        frozen = snapshot(self.project.root)
        third = self.project.run()
        self.assertNotIn("were added.", third)
        self.assertEqual(snapshot(self.project.root), frozen)

    def test_aliases_preserved_across_runs(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        self.project.uma_list(["Special Week", "Special Week (Summer)"])
        (self.project.root / "icons" / "special_week.png").write_bytes(png("sw"))
        (self.project.root / "icons" / "special_week-summer.png").write_bytes(png("sw-alt"))
        self.project.run()
        alias_path = self.project.root / "event_aliases.txt"
        alias_path.write_text(
            "# Uma name: In-game title = Event name\n"
            "\n"
            "# keep this\n"
            "Special Week: Hopp'n Happy Heart = Beach\n",
            encoding="utf-8",
            newline="\n",
        )
        output = self.project.run()
        text = alias_path.read_text(encoding="utf-8")
        self.assertIn("# keep this\n", text)
        self.assertIn("Special Week: Hopp'n Happy Heart = Beach\n", text)
        self.assertEqual(self.project.options()["special_week-summer"], "Special Week (Beach)")
        self.assertNotIn("were added.", output)
        frozen = snapshot(self.project.root)
        self.project.run()
        self.assertEqual(snapshot(self.project.root), frozen)

    def test_preview_writes_nothing(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")}],
                }
            ],
        )
        self.project.run()
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        before = snapshot(self.project.root)
        output = self.project.run(preview=True)
        self.assertEqual(snapshot(self.project.root), before)
        self.assertIn("Preview only; no files were written.", output)
        self.assertNotIn("were added.", output)
        self.assertIn("New event costumes:", output)

    def test_missing_upstream_kept(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        self.project.uma_list(["Special Week", "Special Week (Summer)"])
        (self.project.root / "icons" / "special_week.png").write_bytes(png("sw"))
        (self.project.root / "icons" / "special_week-summer.png").write_bytes(png("sw-alt"))
        self.project.run()
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")}],
                }
            ],
        )
        output = self.project.run()
        self.assertTrue((self.project.root / "icons" / "special_week-summer.png").is_file())
        self.assertEqual((self.project.root / "icons" / "special_week-summer.png").read_bytes(), png("sw-alt"))
        roster = json.loads((self.project.root / "roster.json").read_text(encoding="utf-8"))
        self.assertEqual(roster["outfits"]["100102"]["status"], "missing-upstream")
        self.assertEqual(roster["outfits"]["100102"]["slug"], "special_week-summer")
        self.assertIn("Special Week: Hopp'n Happy Heart = Summer\n", (self.project.root / "event_aliases.txt").read_text(encoding="utf-8"))
        self.assertEqual(self.project.options()["special_week-summer"], "Special Week (Summer)")
        self.assertIn("Missing upstream, kept:", output)
        self.assertNotIn("were added.", output)

    def test_blank_and_no_equals_lines_are_ignored(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        (self.project.root / "event_aliases.txt").write_text(
            "# Uma name: In-game title = Event name\n"
            "\n"
            "Special Week: Hopp'n Happy Heart\n"
            "Special Week: Hopp'n Happy Heart = ???\n"
            "Special Week: Hopp'n Happy Heart = \n",
            encoding="utf-8",
            newline="\n",
        )
        output = self.project.run()
        self.assertNotIn("Could not match", output)
        self.assertNotIn("Ambiguous", output)
        self.assertNotIn("Matched alias", output)
        self.assertEqual(self.project.options()["special_week-hoppn_happy_heart"], "Special Week [Hopp'n Happy Heart]")
        text = (self.project.root / "event_aliases.txt").read_text(encoding="utf-8")
        self.assertIn("Special Week: Hopp'n Happy Heart\n", text)
        self.assertIn("Special Week: Hopp'n Happy Heart = ???\n", text)
        frozen = text
        self.project.run()
        self.assertEqual((self.project.root / "event_aliases.txt").read_text(encoding="utf-8"), frozen)

    def test_fuzzy_match_and_ambiguous_match(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        (self.project.root / "event_aliases.txt").write_text(
            "# Uma name: In-game title = Event name\n"
            "\n"
            "Specail Week: Hoppn Happy Heart = Beach\n"
            "Nope: Nothing Real = Beach\n",
            encoding="utf-8",
            newline="\n",
        )
        output = self.project.run()
        self.assertIn("Matched alias 'Specail Week: Hoppn Happy Heart = Beach' to Special Week: Hopp'n Happy Heart", output)
        self.assertIn("Could not match alias line, left unused: Nope: Nothing Real = Beach", output)
        self.assertEqual(self.project.options()["special_week-hoppn_happy_heart"], "Special Week (Beach)")
        text = (self.project.root / "event_aliases.txt").read_text(encoding="utf-8")
        self.assertIn("Special Week: Hopp'n Happy Heart = Beach\n", text)
        self.assertIn("Nope: Nothing Real = Beach\n", text)

        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Test Horse",
                    "outfits": [
                        {"id": "100101", "epithet": "[Rookie]", "png": png("base")},
                        {"id": "100102", "epithet": "[Summer Festivle]", "png": png("a")},
                        {"id": "100103", "epithet": "[Summer Festivel]", "png": png("b")},
                    ],
                }
            ],
        )
        # A different roster, so start clean.
        self.project.close()
        self.setUp()
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Test Horse",
                    "outfits": [
                        {"id": "100101", "epithet": "[Rookie]", "png": png("base")},
                        {"id": "100102", "epithet": "[Summer Festivle]", "png": png("a")},
                        {"id": "100103", "epithet": "[Summer Festivel]", "png": png("b")},
                    ],
                }
            ],
        )
        (self.project.root / "event_aliases.txt").write_text(
            "# Uma name: In-game title = Event name\n"
            "\n"
            "Test Horse: Summer Festival = Beach\n",
            encoding="utf-8",
            newline="\n",
        )
        output = self.project.run()
        self.assertIn("Ambiguous alias line, left unused: Test Horse: Summer Festival = Beach", output)
        options = self.project.options()
        self.assertNotIn("Beach", " ".join(options.values()))
        self.assertIn("Test Horse: Summer Festival = Beach\n", (self.project.root / "event_aliases.txt").read_text(encoding="utf-8"))

    def test_generate_picks_up_alias_without_sync(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        self.project.run()
        roster_bytes = (self.project.root / "roster.json").read_bytes()
        icon_bytes = (self.project.root / "icons" / "special_week-hoppn_happy_heart.png").read_bytes()
        alias_path = self.project.root / "event_aliases.txt"
        alias_path.write_text(
            alias_path.read_text(encoding="utf-8").replace("= ", "= Beach"),
            encoding="utf-8",
            newline="\n",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generate_streamelements.write_fields(self.project.root)
        self.assertEqual((self.project.root / "roster.json").read_bytes(), roster_bytes)
        self.assertEqual((self.project.root / "icons" / "special_week-hoppn_happy_heart.png").read_bytes(), icon_bytes)
        self.assertEqual(self.project.options()["special_week-hoppn_happy_heart"], "Special Week (Beach)")
        self.assertIn("Wrote", buf.getvalue())

    def test_pause_skipped_without_a_terminal(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        with mock.patch("sys.stdin.isatty", return_value=False), mock.patch(
            "builtins.input", side_effect=AssertionError("should not pause")
        ):
            output = self.project.run(pause=None)
        self.assertIn("1 event costumes were added.", output)
        self.assertNotIn("press Enter", output)
        self.assertEqual(self.project.options()["special_week-hoppn_happy_heart"], "Special Week [Hopp'n Happy Heart]")

        def fill_alias():
            path = self.project.root / "event_aliases.txt"
            path.write_text(path.read_text(encoding="utf-8").replace("= ", "= Beach"), encoding="utf-8", newline="\n")
            return ""

        self.project.close()
        self.setUp()
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")},
                        {"id": "100102", "epithet": "[Hopp'n Happy Heart]", "png": png("sw-alt")},
                    ],
                }
            ],
        )
        with mock.patch("builtins.input", side_effect=fill_alias):
            output = self.project.run(pause=True)
        self.assertIn("press Enter", output)
        self.assertEqual(self.project.options()["special_week-hoppn_happy_heart"], "Special Week (Beach)")

    def test_icon_hash_change_is_not_overwritten(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("original")}],
                }
            ],
        )
        self.project.run()
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("upstream-new")}],
                }
            ],
        )
        output = self.project.run()
        self.assertEqual((self.project.root / "icons" / "special_week.png").read_bytes(), png("original"))
        self.assertIn("left unchanged: icons/special_week.png", output)
        output = self.project.run(update_icons=True)
        self.assertEqual((self.project.root / "icons" / "special_week.png").read_bytes(), png("upstream-new"))
        self.assertIn("Replaced icons/special_week.png", output)

    def test_wrong_existing_icon_replaced_when_pairing_is_unique(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [
                        {"id": "100101", "epithet": "[Special Dreamer]", "png": png("base")},
                        {"id": "100102", "epithet": "[Precise Chocolatier]", "png": png("global-alt")},
                    ],
                }
            ],
        )
        self.project.uma_list(["Special Week", "Special Week (Valentine)"])
        (self.project.root / "icons" / "special_week.png").write_bytes(png("base"))
        (self.project.root / "icons" / "special_week-valentine.png").write_bytes(png("jp-alt"))
        output = self.project.run()
        self.assertEqual((self.project.root / "icons" / "special_week-valentine.png").read_bytes(), png("global-alt"))
        self.assertFalse((self.project.root / "icons" / "special_week-precise_chocolatier.png").exists())
        self.assertEqual(self.project.options()["special_week-valentine"], "Special Week (Valentine)")
        self.assertIn("Replaced icons/special_week-valentine.png", output)
        self.assertNotIn("were added.", output)

    def test_manual_entry_survives_and_generate_keeps_uma_list_addition(self):
        write_source(
            self.project.source,
            [
                {
                    "id": "1001",
                    "name": "Special Week",
                    "outfits": [{"id": "100101", "epithet": "[Special Dreamer]", "png": png("sw")}],
                }
            ],
        )
        self.project.run()
        (self.project.root / "icons" / "guest_star.png").write_bytes(png("guest"))
        sync_umas.write_uma_list(
            self.project.root / "uma_list.txt",
            sync_umas.read_uma_list(self.project.root / "uma_list.txt") + ["Guest Star"],
        )
        generate_streamelements.write_fields(self.project.root)
        self.assertEqual(self.project.options()["guest_star"], "Guest Star")
        self.assertIn("Guest Star", sync_umas.read_uma_list(self.project.root / "uma_list.txt"))
        self.project.run()
        roster = json.loads((self.project.root / "roster.json").read_text(encoding="utf-8"))
        self.assertEqual(roster["outfits"]["manual:guest_star"]["source"], "manual")
        self.assertEqual(roster["outfits"]["manual:guest_star"]["label"], "Guest Star")
        self.assertEqual(self.project.options()["guest_star"], "Guest Star")
        frozen = snapshot(self.project.root)
        self.project.run()
        self.assertEqual(snapshot(self.project.root), frozen)


if __name__ == "__main__":
    unittest.main()
