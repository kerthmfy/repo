#!/usr/bin/env python3
"""Render the static KMY Repo catalog from data/packages.json and docs/Packages.

The generated HTML lives beside the apt metadata so GitHub Pages can serve the
catalog and Cydia can read the same directory as a source. No framework, no
build service: this script is the whole site generator.
"""

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def parse_packages(text):
    """Parse Debian Packages text into a list of dictionaries.

    Stanzas are separated by blank lines. A line that starts with a space or
    tab continues the previous field, which is how long Description values are
    encoded in a Packages file.
    """
    packages = []
    current = {}
    last_key = None

    for raw_line in text.splitlines():
        if not raw_line.strip():
            if current:
                packages.append(current)
                current = {}
                last_key = None
            continue

        if raw_line[0] in (" ", "\t"):
            if last_key is None:
                continue
            current[last_key] = current[last_key] + "\n" + raw_line.strip()
            continue

        key, separator, value = raw_line.partition(":")
        if not separator:
            continue
        key = key.strip()
        current[key] = value.strip()
        last_key = key

    if current:
        packages.append(current)

    return packages


def load_manifest(path):
    """Read the hand-curated site manifest."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def find_package(manifest, package_id):
    """Return the manifest entry for a package ID, or None."""
    for package in manifest.get("packages", []):
        if package.get("package") == package_id:
            return package
    return None


def format_size(raw_value):
    """Turn a byte count from Packages into a short human-readable size."""
    try:
        size = int(raw_value)
    except (TypeError, ValueError):
        return str(raw_value)

    if size >= 1024 * 1024:
        return "%.1f MB" % (size / (1024.0 * 1024.0))
    return "%d KB" % max(1, int(round(size / 1024.0)))


def escape(value):
    """Escape text for HTML text and attribute contexts."""
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def site_url(repo, suffix=""):
    """Build an HTTPS site URL, keeping exactly one slash at the join."""
    base = repo.get("https_url", "").rstrip("/") + "/"
    return base + suffix


def install_link(repo):
    """Build the cydia:// share link that adds this source.

    Cydia's apt transport on iOS 6 can read the HTTPS GitHub Pages source even
    though the device's command-line curl only speaks TLS 1.0. The link uses
    the same HTTPS source so Cydia and the catalog stay in sync.
    """
    return (
        "cydia://url/https://cydia.saurik.com/api/share#?source="
        + quote(repo.get("url", ""), safe="")
    )


# ---------------------------------------------------------------------------
# Shared page chrome
# ---------------------------------------------------------------------------

def page_shell(repo, title, description, root, canonical, body):
    """Wrap page content in the iOS 6 styled document shell."""
    repo_name = escape(repo.get("name", "KMY Repo"))
    og_image = escape(site_url(repo, "assets/og.png"))
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="format-detection" content="telephone=no">
<title>%(title)s</title>
<meta name="description" content="%(description)s">
<link rel="canonical" href="%(canonical)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="%(repo_name)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(description)s">
<meta property="og:url" content="%(canonical)s">
<meta property="og:image" content="%(og_image)s">
<link rel="icon" type="image/png" href="%(root)sfavicon.png">
<link rel="apple-touch-icon" href="%(root)sCydiaIcon.png">
<link rel="stylesheet" href="%(root)sassets/styles.css">
</head>
<body>
<header class="nav">
  <div class="nav-inner">
    <a class="nav-brand" href="%(root)sindex.html">
      <span class="nav-mark">KMY</span>
      <span class="nav-title">%(repo_name)s</span>
    </a>
    <nav class="nav-links">
      <a class="nav-link" href="%(root)sindex.html">Home</a>
      <a class="nav-link" href="%(root)sindex.html#packages">Packages</a>
      <a class="nav-link" href="%(root)sindex.html#install">Install</a>
      <a class="nav-link" href="%(github)s">GitHub</a>
    </nav>
    <div class="clear"></div>
  </div>
</header>
%(body)s
%(footer)s
<script src="%(root)sassets/app.js"></script>
</body>
</html>
""" % {
        "title": escape(title),
        "description": escape(description),
        "canonical": escape(canonical),
        "repo_name": repo_name,
        "og_image": og_image,
        "root": root,
        "github": escape(repo.get("github", "")),
        "body": body,
        "footer": page_footer(repo, root),
    }


def page_footer(repo, root):
    """Charcoal tab-bar footer with plain text links."""
    return """<footer class="footer">
  <div class="footer-inner">
    <a class="tab" href="%(root)sindex.html"><span class="tab-icon">&#8962;</span>Home</a>
    <a class="tab" href="%(root)sindex.html#packages"><span class="tab-icon">&#9638;</span>Packages</a>
    <a class="tab" href="%(root)sindex.html#install"><span class="tab-icon">&#8595;</span>Install</a>
    <a class="tab" href="%(github)s"><span class="tab-icon tab-code">&lt;/&gt;</span>Source</a>
    <div class="footer-note">%(name)s &middot; Static, fast, iOS 6 friendly</div>
  </div>
</footer>""" % {
        "root": root,
        "github": escape(repo.get("github", "")),
        "name": escape(repo.get("name", "KMY Repo")),
    }


def source_row(repo):
    """Inset source URL field plus a copy button."""
    url = repo.get("url", "")
    return """<div class="source-row">
      <div class="source-field" id="source-url">%(url)s</div>
      <button type="button" class="btn btn-blue copy-btn" data-copy="%(url)s">Copy</button>
    </div>""" % {"url": escape(url)}


def install_card(repo, root):
    """The source field, Cydia button, and three-step instructions."""
    steps = [
        "Open <strong>Cydia</strong> and choose <strong>Sources</strong>.",
        "Tap <strong>Edit</strong>, then <strong>Add</strong>.",
        "Enter the source above, tap <strong>Add Source</strong>, then search for the app.",
    ]
    items = "".join(
        '<li><span class="step-number">%d</span>%s</li>' % (index + 1, step)
        for index, step in enumerate(steps)
    )
    return """<div class="card install-card">
    <p class="install-lead">Add the KMY source once. Cydia will then offer every app here, including updates.</p>
    %(source_row)s
    <p class="center"><a class="btn btn-green btn-wide" href="%(install_link)s">Add to Cydia</a></p>
    <p class="note">If Cydia warns that the source is unsigned, tap <strong>Add Anyway</strong>. The packages themselves are still installed normally.</p>
    <ol class="steps">%(items)s</ol>
  </div>""" % {
        "source_row": source_row(repo),
        "install_link": escape(install_link(repo)),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

def package_card(package, published):
    """One compact package row card used in the index grid."""
    slug = package.get("slug", "")
    metadata = published.get(package.get("package"), {})
    return """<a class="pkg-card" href="p/%(slug)s/index.html">
      <img class="app-icon" src="%(icon)s" alt="" width="56" height="56">
      <span class="pkg-card-body">
        <span class="pkg-name">%(name)s</span>
        <span class="pkg-tag">%(tag)s</span>
        <span class="pkg-meta">Version %(version)s</span>
      </span>
      <span class="chevron">&#8250;</span>
    </a>""" % {
        "slug": escape(slug),
        "icon": escape(package.get("icon", "")),
        "name": escape(metadata.get("Name", slug)),
        "tag": escape(package.get("tag", "")),
        "version": escape(metadata.get("Version", "")),
    }


def featured_card(package, published):
    """The large featured package card on the index."""
    slug = package.get("slug", "")
    metadata = published.get(package.get("package"), {})
    paragraphs = package.get("description", [])
    lede = escape(paragraphs[0]) if paragraphs else ""
    return """<div class="card featured">
    <img class="app-icon app-icon-lg" src="%(icon)s" alt="" width="96" height="96">
    <div class="featured-body">
      <div class="featured-heading">
        <h3>%(name)s</h3>
        <span class="version-chip">%(version)s</span>
      </div>
      <p class="pkg-tag">%(tag)s &middot; iOS %(minimum_os)s+</p>
      <p>%(lede)s</p>
      <p><a class="btn btn-blue" href="p/%(slug)s/index.html">View package &#8250;</a></p>
    </div>
    <div class="clear"></div>
  </div>""" % {
        "icon": escape(package.get("icon", "")),
        "name": escape(metadata.get("Name", slug)),
        "version": escape(metadata.get("Version", "")),
        "tag": escape(package.get("tag", "")),
        "minimum_os": escape(package.get("minimum_os", "")),
        "lede": lede,
        "slug": escape(slug),
    }


def index_page(repo, manifest, published):
    """Render the catalog home page."""
    repo_name = escape(repo.get("name", "KMY Repo"))
    tagline = escape(repo.get("tagline", ""))
    featured = [p for p in manifest.get("packages", []) if p.get("featured")]
    others = [p for p in manifest.get("packages", []) if not p.get("featured")]

    featured_html = ""
    if featured:
        featured_html = (
            '<h2 class="section-label">Featured package</h2>\n'
            + featured_card(featured[0], published)
        )

    grid_html = ""
    if others:
        grid_html = (
            '<h2 class="section-label">More packages</h2>\n<div class="pkg-grid">\n'
            + "\n".join(package_card(p, published) for p in others)
            + '\n<div class="clear"></div>\n</div>'
        )
    elif not featured:
        grid_html = (
            '<h2 class="section-label">Packages</h2>\n'
            '<div class="card empty-card">No packages have been published yet.</div>'
        )

    body = """<main class="wrap">
  <section class="hero card">
    <div class="monogram">KMY</div>
    <h1>%(name)s</h1>
    <p class="tagline">%(tagline)s</p>
    <p class="hero-buttons">
      <a class="btn btn-blue" href="#install">How to install</a>
      <a class="btn btn-cream" href="#packages">Browse packages</a>
    </p>
  </section>

  <h2 class="section-label" id="install">Add this source in Cydia</h2>
  %(install_card)s

  <div id="packages"></div>
  %(featured_html)s
  %(grid_html)s

  <div class="card about-strip">
    <h2>Built for old hardware</h2>
    <p>Every package here is made for iOS 6, with native UIKit controls and no modern runtime dependencies. The source and the catalog are plain static files, so they load quickly even on an iPhone 4S.</p>
  </div>
</main>""" % {
        "name": repo_name,
        "tagline": tagline,
        "install_card": install_card(repo, ""),
        "featured_html": featured_html,
        "grid_html": grid_html,
    }

    return page_shell(
        repo,
        "%s — %s" % (repo.get("name", "KMY Repo"), repo.get("tagline", "")),
        repo.get("tagline", ""),
        "",
        site_url(repo),
        body,
    )


# ---------------------------------------------------------------------------
# Package detail page
# ---------------------------------------------------------------------------

def package_page(repo, package, metadata):
    """Render one package detail page, two directories below the site root."""
    root = "../../"
    slug = package.get("slug", "")
    name = escape(metadata.get("Name", slug))
    version = escape(metadata.get("Version", ""))
    tag = escape(package.get("tag", ""))
    minimum_os = escape(package.get("minimum_os", ""))
    filename = metadata.get("Filename", "")
    deb_url = root + filename
    description_paragraphs = package.get("description", [])
    lede = (
        "<p>%s</p>" % escape(description_paragraphs[0])
        if description_paragraphs
        else ""
    )
    about = "".join(
        "<p>%s</p>" % escape(paragraph) for paragraph in description_paragraphs[1:]
    )
    about_html = ""
    if about:
        about_html = """<h2 class="section-label">About this package</h2>
  <div class="card">
    %(about)s
  </div>""" % {"about": about}

    shots = ""
    screenshot_html = ""
    screenshots = package.get("screenshots", [])
    if screenshots:
        for screenshot in screenshots:
            shots += """<div class="shot">
        <img src="%(root)s%(src)s" alt="%(name)s screenshot">
      </div>""" % {
                "root": root,
                "src": escape(screenshot),
                "name": name,
            }
        screenshot_html = """<h2 class="section-label">Screenshots</h2>
  <div class="card shots-card">
    <div class="shots">
      %(shots)s
      <div class="clear"></div>
    </div>
  </div>""" % {"shots": shots}

    changelog_html = ""
    if package.get("changelog"):
        entries = "".join(
            "<li>%s</li>" % escape(entry) for entry in package["changelog"]
        )
        changelog_html = """<h2 class="section-label">Version history</h2>
  <div class="card">
    <ul class="changelog">%(entries)s</ul>
  </div>""" % {"entries": entries}

    depends = metadata.get("Depends", "")
    requires = escape(depends) if depends else ("iOS %s+" % minimum_os)

    body = """<main class="wrap">
  <p class="back-link"><a href="%(root)sindex.html">&#8249; All packages</a></p>

  <section class="card package-head">
    <img class="app-icon app-icon-lg" src="%(root)s%(icon)s" alt="%(name)s icon" width="96" height="96">
    <div class="package-head-body">
      <h1>%(name)s <span class="version-chip">%(version)s</span></h1>
      <p class="package-tag">%(tag)s &middot; iOS %(minimum_os)s+</p>
      <div class="package-lede">%(lede)s</div>
      <p class="package-buttons">
        <a class="btn btn-green" href="%(install_link)s">Add to Cydia</a>
        <a class="btn btn-blue" href="%(deb_url)s">Download .deb</a>
      </p>
    </div>
    <div class="clear"></div>
  </section>

  %(screenshots)s

  %(about_html)s

  <h2 class="section-label">Install</h2>
  %(install_card)s

  <h2 class="section-label">Package details</h2>
  <div class="card">
    <table class="meta-table">
      <tbody>
        <tr><th>Package</th><td class="mono">%(package_id)s</td></tr>
        <tr><th>Version</th><td>%(version)s</td></tr>
        <tr><th>Section</th><td>%(section)s</td></tr>
        <tr><th>Architecture</th><td>%(architecture)s</td></tr>
        <tr><th>Size</th><td>%(size)s</td></tr>
        <tr><th>Requires</th><td>%(requires)s</td></tr>
        <tr><th>Source code</th><td><a href="%(source)s">%(source_label)s</a></td></tr>
      </tbody>
    </table>
  </div>

  %(changelog)s
</main>""" % {
        "root": root,
        "icon": escape(package.get("icon", "")),
        "name": name,
        "tag": tag,
        "minimum_os": minimum_os,
        "version": version,
        "lede": lede,
        "about_html": about_html,
        "install_link": escape(install_link(repo)),
        "deb_url": escape(deb_url),
        "screenshots": screenshot_html,
        "install_card": install_card(repo, root),
        "package_id": escape(package.get("package", "")),
        "section": escape(metadata.get("Section", "")),
        "architecture": escape(metadata.get("Architecture", "")),
        "size": escape(format_size(metadata.get("Size", ""))),
        "requires": requires,
        "source": escape(package.get("source", "")),
        "source_label": escape(package.get("source", "")),
        "changelog": changelog_html,
    }

    return page_shell(
        repo,
        "%s %s — %s" % (metadata.get("Name", slug), metadata.get("Version", ""), repo.get("name", "KMY Repo")),
        (package.get("description") or [repo.get("tagline", "")])[0],
        root,
        site_url(repo, "p/%s/" % slug),
        body,
    )


def not_found_page(repo):
    """A small, friendly 404 that still works without JavaScript."""
    body = """<main class="wrap">
  <section class="card empty-card">
    <h1>Page not found</h1>
    <p>That page is not part of the KMY repo. The source and package list are still one tap away.</p>
    <p><a class="btn btn-blue" href="index.html">Back to the catalog</a></p>
  </section>
</main>"""
    return page_shell(
        repo,
        "Page not found — %s" % repo.get("name", "KMY Repo"),
        "The requested page was not found in the KMY repo.",
        "",
        site_url(repo),
        body,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def write_site(repo_root):
    """Generate every HTML page and copy the static assets into docs/."""
    root = Path(repo_root).resolve()
    manifest = load_manifest(root / "data" / "packages.json")
    packages_path = root / "docs" / "Packages"
    published = {}
    for stanza in parse_packages(packages_path.read_text(encoding="utf-8")):
        package_id = stanza.get("Package")
        if package_id:
            if package_id in published:
                raise ValueError(
                    "duplicate package %s in docs/Packages; publish only one version"
                    % package_id
                )
            published[package_id] = stanza

    # The manifest is editorial; version/size/filename always come from the
    # generated Packages file so the catalog cannot drift from the archive.
    for package in manifest.get("packages", []):
        package_id = package.get("package", "")
        if package_id not in published:
            raise ValueError(
                "package %s is missing from %s; publish its .deb first"
                % (package_id, packages_path)
            )

    assets = root / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "site" / "styles.css", assets / "styles.css")
    shutil.copyfile(root / "site" / "app.js", assets / "app.js")

    (root / "docs" / "index.html").write_text(
        index_page(manifest.get("repo", {}), manifest, published), encoding="utf-8"
    )
    (root / "docs" / "404.html").write_text(
        not_found_page(manifest.get("repo", {})), encoding="utf-8"
    )

    for package in manifest.get("packages", []):
        page_dir = root / "docs" / "p" / package.get("slug", "")
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            package_page(manifest.get("repo", {}), package, published[package["package"]]),
            encoding="utf-8",
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the KMY Repo catalog.")
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the distribution repo root (default: current directory).",
    )
    args = parser.parse_args(argv)
    write_site(args.repo)
    print("Rendered site from %s" % (Path(args.repo).resolve() / "docs" / "Packages"))


if __name__ == "__main__":
    main()
