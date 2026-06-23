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

## Hosting icons on GitHub

The overlay loads PNGs over HTTPS. A **public** repository is required for `raw.githubusercontent.com` URLs to work in OBS/StreamElements without authentication.

After pushing, verify a URL in your browser:

```
https://raw.githubusercontent.com/turtle-box/uma-paddock/main/icons/special_week.png
```

## Adding umas to the roster
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
