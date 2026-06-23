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
| `uma.py` | Icon renaming utilities (optional) |
| `umas_up_to_trackblazer*.txt` | Trackblazer roster lists |

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
4. Configure trainer names, gate positions, and uma dropdowns in the left panel.

To change layout defaults (sliders, gate placeholders), edit `overlay/fields-base.json`, then regenerate the dropdown fields using this command:

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

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).

Icons and `umas.json` originate from [alpha123/uma-tools](https://github.com/alpha123/uma-tools), also licensed under GPL-3.0. When distributing this repository, retain the GPL license and this attribution.
