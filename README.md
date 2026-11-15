# mi repo

Cydia source and catalog for my iOS 6 apps/tweaks.

- Source (iOS 6 Cydia): https://kerthmfy.github.io/repo/
- Site: https://kerthmfy.github.io/repo/

Marquee (`com.kerthmfy.marquee.app`) is the first package. The layout accepts
more apps and tweaks without changing the source URL.

## How the repo works

`docs/` is both the GitHub Pages root and the apt root. Everything Cydia reads
lives there:

```text
docs/
  Packages              generated apt index
  Packages.bz2          compressed copy
  Packages.gz           compressed copy
  Release               checksums and repo metadata
  CydiaIcon.png         source icon shown by Cydia
  index.html            generated catalog
  404.html              generated not-found page
  p/<slug>/index.html   generated package pages
  debs/*.deb            one published version per package
  assets/               generated CSS/JS plus icons and screenshots
```

The editable sources are outside `docs/`:

```text
data/packages.json      editorial package manifest
site/styles.css         iOS 6 theme source
site/app.js             copy-button behavior
tools/build_site.py     catalog generator
tools/update_repo.sh    apt index, Release, and catalog pipeline
tests/                  Python and shell tests
```

`docs/assets/styles.css` and `docs/assets/app.js` are generated copies. Edit
`site/`, not `docs/assets/`.

### Generated metadata

`tools/update_repo.sh` is the single entry point for regenerating the repo:

1. Refuse to continue if one package has two `.deb` files. `dpkg-scanpackages`
   would otherwise choose one arbitrarily.
2. Run `dpkg-scanpackages` over `docs/debs` and write `docs/Packages`.
3. Compress it to `Packages.bz2` and `Packages.gz`.
4. Write `docs/Release` with MD5, SHA1, and SHA256 checksums.
5. Run `tools/build_site.py` to render the catalog from `data/packages.json`
   and `docs/Packages`.
6. Commit `docs/` and, with `--push`, push `main`.

`data/packages.json` carries the editorial copy, slug, icon, screenshots,
source link, and changelog. Version, size, filename, section, and architecture
always come from the published `.deb`, so the site cannot drift from the
archive.

## Add the source in Cydia

On the iOS 6 device:

1. Open Cydia and choose **Sources**.
2. Tap **Edit**, then **Add**.
3. Enter `https://kerthmfy.github.io/repo/` and tap **Add Source**.
4. Open the KMY repo, choose Marquee, and install it.

Cydia's apt transport on iOS 6 can fetch this HTTPS source. The device's
command-line `curl` only speaks TLS 1.0 and cannot fetch GitHub Pages, so use
Cydia or APT for installs and updates; `curl` is not a meaningful test there.

GitHub Pages requires HTTPS for `github.io` sites, so the source URL must keep
its `https://` prefix. An `http://` URL redirects and will not work in Cydia.

## Publishing a release

The publisher expects the app checkout and this repo as siblings:

```text
~/Documents/
  marquee-worktree/   # app repo
  repo/               # this repo
```

From the app repo:

1. Make the app change.
2. Bump `Version:` in `control`.
3. Bump `CFBundleShortVersionString` and `CFBundleVersion` in
   `Marquee/Resources/Info.plist`.
4. Run the publisher:

```sh
./tools/publish-cydia.sh --push
```

The publisher builds with Theos, verifies the `.deb` package ID and version,
copies the package and app art into this repo, then runs `update_repo.sh`.
It refuses to overwrite an already-published version. `--replace` exists only
for correcting the same version before anyone depends on it; normal updates
must use a higher version.

`REPO_DIR=/path/to/repo` overrides the sibling location. `--no-push` leaves the
generated commit local for review.

## Adding another app

1. Copy `tools/publish-cydia.sh` and `tools/publish.conf.example` into the new
   app repo as `tools/publish-cydia.sh` and `tools/publish.conf`.
2. Set `REPO_SLUG`, `REPO_ICON_SOURCE`, and `REPO_SCREENSHOTS_SOURCE` in
   `publish.conf`.
3. Add a matching entry to `data/packages.json` in this repo. The `package`
   field must exactly match the app's `Package:` control field, and `slug` must
   match the asset folder and page URL.
4. Bump the app version and run its publisher.

The publisher fails before building if the manifest has no entry for the
package. The site generator fails if a manifest package is missing from
`docs/Packages`, and names the package and file in the error.

## Local checks

```sh
cd ~/Documents/repo
./tests/run_tests.sh
python3 tools/build_site.py --repo .
python3 -m http.server 8000 --directory docs
```

Open <http://localhost:8000/> for the catalog. The test suite covers stanza
parsing, page links, HTML escaping, duplicate-version rejection, checksums, and
the generated files.

## Troubleshooting

**Cydia still shows the old version.** Pull down on Changes to refresh, or use
Sources → Refresh. Cydia caches indexes; a normal refresh picks up the new
`Packages` and `Release`.

**Cydia cannot add the source.** Use the exact HTTPS URL with the trailing
slash: `https://kerthmfy.github.io/repo/`. An HTTP URL redirects to HTTPS and
fails on iOS 6. The device's `curl` also fails against GitHub Pages because it
only supports TLS 1.0, but Cydia's apt transport works.

**The publisher says a version is already published.** Bump `Version:` in the
app's `control` and `Info.plist`. Use `--replace` only to correct the same
version before release.

**`update_repo.sh` says multiple versions were found.** Remove the old `.deb`
from `docs/debs/`, or let the publisher replace it. The repo intentionally
keeps one `.deb` per package.

**The site is missing a package.** Add its entry to `data/packages.json`, or
publish the `.deb` first. `build_site.py` refuses to render a partial catalog.

**Pages shows a 404.** Check Settings → Pages: source `Deploy from a branch`,
branch `main`, folder `/docs`. Wait for the deployment to finish. The
`docs/.nojekyll` file keeps Jekyll from rewriting the generated files.

**Cydia warns the repo is unsigned.** That is expected in this pass. Tap
**Add Anyway** or ignore the warning; the packages install normally. GPG
signing can be added later without changing package URLs.

## Brand assets

The repo mark is a layered KMY monogram: a dark rounded square with a glossy
blue top, white letters, and a small `REPO` caption.

- `docs/CydiaIcon.png` — 512 px source icon shown by Cydia.
- `docs/favicon.png` — 64 px browser icon.
- `docs/assets/og.png` — 1200×630 Open Graph card.

The PNGs are committed; ImageMagick is only needed if the artwork changes.
