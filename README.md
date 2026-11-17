# uma-paddock

This is a StreamElements overlay meant to display 3 teams of 3 umas during a custom race. It was designed for Kayso's [twitch channel](https://www.twitch.tv/kaysov).

## Third-party assets

Character icons (`icons/`) and `umas.json` are derived from [alpha123/uma-tools](https://github.com/alpha123/uma-tools) (`icons/chara`), used under the [GNU General Public License v3.0](LICENSE).

Uma Musume Pretty Derby is © Cygames, Inc. This is an unofficial fan project and is not affiliated with or endorsed by Cygames.

## Repository layout

| Path | Description |
|------|-------------|
| `overlay/` | StreamElements custom overlay (HTML, CSS, JS, FIELDS JSON) |
| `icons/` | Character icon PNGs (slug filenames, e.g. `special_week.png`) |
| `umas.json` | Character/outfit metadata (from uma-tools) |
| `generate_streamelements.py` | Regenerates `overlay/fields.json` dropdown options |
| `slug.py` | Icon slug helpers and CLI |
| `uma.py` | Icon renaming utilities (optional) |
| `sync_umas.py` | Syncs the roster and icons from uma-tools |
| `event_aliases.txt` | Event names for event costumes (edit by hand) |
| `uma_list.txt` | Uma roster (dropdowns + icon renaming; auto-sorted when scripts run) |

## StreamElements setup

1. Create a custom overlay in the StreamElements overlay editor.
2. Paste each file from `overlay/` into its tab:
   - `uma-paddock.html` → HTML
   - `style.css` → CSS
   - `script.js` → JS
   - `fields.json` → FIELDS
3. Set **Icon base URL** in the overlay settings to the external URL where your uma icons are hosted (no trailing slash), e.g.:
   ```
   https://raw.githubusercontent.com/turtle-box/uma-paddock/main/icons
   ```
4. Configure trainer names, team umas, and starting gate positions in the left panel.

To change layout defaults (eg. sliders, gate placeholders), edit `overlay/fields-base.json`, then regenerate the dropdown fields using this command:

```bash
python generate_streamelements.py
```

Re-paste `overlay/fields.json` into StreamElements after regenerating.

## Custom fonts

In order to use custom fonts, the font must either be uploaded at some static link (e.g. under `fonts/` in this project, using the `raw.githubusercontent.com` direct link to the file) or installed locally to be fetched and rendered properly.

The font resolution order is as follows:

1. **Font file URL** — loaded via font loading script in `script.js`
2. **Local install** — if the URL fails or is empty, the browser tries a system font matching **Custom Font Name** in `fields.json`
3. **Montserrat** — Google Fonts (in `uma-paddock.html`)
4. **sans-serif** — generic fallback

CSS starts on Montserrat until JS runs. Set **Custom Font Name** to match your chosen alias (or the installed font's exact family name for local use). Make sure **Font file URL** is set to a direct HTTPS link (e.g. a `raw.githubusercontent.com` URL).

```bash
# example raw GitHub font URL
https://raw.githubusercontent.com/turtle-box/uma-paddock/main/fonts/my-font.woff2
```

## Hosting icons on GitHub

All uma icons used by the overlay should be hosted in the same place, at an HTTPS url that is publicly accessible.

By default, the project uses the `.png` files stored at `icons/`, and so the `Icon base URL` in the widget's fields is set to `https://raw.githubusercontent.com/turtle-box/uma-paddock/main/icons`.
You can change this base url to whichever host you are using, as long as all the icon files are stored there and follow the same naming convention as the images stored in this repository.

After pushing to this repository, verify a URL in your browser:

```
https://raw.githubusercontent.com/turtle-box/uma-paddock/main/icons/special_week.png

OR

https://<your-base-url>/special_week.png
```

## Syncing the roster

`sync_umas.py` pulls the latest Global roster and character icons from [alpha123/uma-tools](https://github.com/alpha123/uma-tools), so you don't have to add them manually. It reads these two files from that project, always using their newest version:

- [`umalator-global/umas.json`](https://github.com/alpha123/uma-tools/blob/master/umalator-global/umas.json), the list of characters and their outfits
- [`icons.json`](https://github.com/alpha123/uma-tools/blob/master/icons.json), which maps each outfit to its icon in [`icons/chara`](https://github.com/alpha123/uma-tools/tree/master/icons/chara)

To sync, just run:

```bash
python sync_umas.py
```

To see what would change without touching any files, add `--preview`:

```bash
python sync_umas.py --preview
```

The sync will add any new umas, costumes, and icons into the local project.

If new event outfits are detected, the sync will pause and allow you to give each one a custom nickname in the file `event_aliases.txt`. If you don't nickname an uma's costume, it will simply show up in the dropdown under its default name. Previously defined nicknames are preserved, and will not be affected by the sync.

Edit the file (or not) in a text editor, save your changes, and then press Enter.

It will then rebuild `overlay/fields.json` to reflect your aliases in the dropdown menus. You can paste this updated file into the FIELDS tab in StreamElements.

Afterwards, you will need to commit these changes to push these new icons to the GitHub repo if you rely on it to serve your images.

```bash
git add .
git commit -m "added new umas up to Nov 2026"
git push
```

Each sync prints which uma-tools commit it used. If the newest data ever breaks something, you can sync from an older commit instead:

```bash
python sync_umas.py --ref <commit-sha>
```

## Defining aliases for event costumes

Event costumes come from uma-tools with their in-game titles, like `[Precise Chocolatier]`, rather than event names like `Valentine`. `event_aliases.txt` lets you give each costume a friendlier label for the dropdown. Open it in any text editor; each line looks like this:

```
# Uma name: In-game title = Event name
Eishin Flash: Precise Chocolatier = Valentine
Gold Ship: RUN! RUIN! LAUNCHER! = Summer
```

- Type the event name after the `=`. The dropdown then shows it as `Eishin Flash (Valentine)`.
- **If you leave it blank, the costume's original in-game title is used by default.** A line with no `=`, or with nothing but spaces or symbols after it, is simply skipped.
- Matching is lenient: capital letters, accents, punctuation and extra spaces don't matter, and small typos in the uma name or title are still matched. The scripts tell you which costume each line matched, and list any line they couldn't match instead of guessing.

To change aliases later, you don't need to sync again. Edit the file, then rebuild the dropdowns with:

```bash
python generate_streamelements.py
```

Then paste the new `overlay/fields.json` into the FIELDS tab in StreamElements.

## Adding umas manually

If an uma isn't in uma-tools yet, you can still add one by hand:

1. Add an uma like `Aston Machan` to `uma_list.txt`, along with the event name in parentheses if applicable.
2. Upload the icon file to `icons/` or your custom host, making sure it follows the same naming convention as the other files.
   - if you're not sure how to name the file(s), you can generate the filename(s) using `slug.py`:
   ```bash
   python3 slug.py "Satono Diamond (New Year)"             # icon slug stem(s)
   python3 slug.py -e png "Aston Machan" "Daitaku Helios"  # icon filename(s) with extension(s)
   ```
3. Regenerate `overlay/fields.json` using:
```bash
python generate_streamelements.py
```
4. Commit and push all changes to the project if needed
5. Open your current overlay in the StreamElements overlay editor
6. Copy the contents of `overlay/fields.json` to the FIELDS tab and save your changes

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).

Icons and `umas.json` originate from [alpha123/uma-tools](https://github.com/alpha123/uma-tools), also licensed under GPL-3.0. When distributing this repository, retain the GPL license and this attribution.
