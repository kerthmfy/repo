import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_site  # noqa: E402

PACKAGES_TEXT = """Package: com.kerthmfy.marquee.app
Name: Marquee
Version: 1.0
Architecture: iphoneos-arm
Section: Entertainment
Size: 1234567
Filename: debs/com.kerthmfy.marquee.app_1.0_iphoneos-arm.deb
Depends: firmware (>= 6.0)
Description: A standalone Simkl client.
"""

MANIFEST = {
    "repo": {
        "name": "KMY Repo",
        "tagline": "iOS 6 apps and tweaks, made to feel native.",
        "url": "https://kerthmfy.github.io/repo/",
        "https_url": "https://kerthmfy.github.io/repo/",
        "github": "https://github.com/kerthmfy/repo",
    },
    "packages": [
        {
            "slug": "marquee",
            "package": "com.kerthmfy.marquee.app",
            "tag": "Simkl client",
            "description": [
                "A standalone, native Simkl client for iOS 6.",
                "For You, Library, Search and Profile in an iOS 6 card stack.",
            ],
            "minimum_os": "6.0",
            "icon": "assets/icons/marquee.png",
            "screenshots": [
                "assets/screenshots/marquee/attachment-2.png",
                "assets/screenshots/marquee/attachment-1.png",
            ],
            "source": "https://github.com/kerthmfy/Marquee-ios6",
            "changelog": ["1.0 — Initial public release."],
            "featured": True,
        }
    ],
}


class BuildSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "site").mkdir()
        (self.root / "docs").mkdir()
        self.manifest = json.loads(json.dumps(MANIFEST))
        self.write_manifest()
        self.write_packages(PACKAGES_TEXT)
        (self.root / "site" / "styles.css").write_text(
            ".nav { background: -webkit-linear-gradient(top, #fff, #000); }\n",
            encoding="utf-8",
        )
        (self.root / "site" / "app.js").write_text("// copy helper\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self):
        (self.root / "data" / "packages.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def write_packages(self, text):
        (self.root / "docs" / "Packages").write_text(text, encoding="utf-8")

    def read(self, relative):
        return (self.root / relative).read_text(encoding="utf-8")

    def test_parse_packages_handles_blank_lines_and_continuation(self):
        text = (
            "Package: com.example.one\n"
            "Version: 1.0\n"
            "Description: first line\n"
            " second line\n"
            " .\n"
            "\n"
            "Package: com.example.two\n"
            "Version: 2.0\n"
        )

        packages = build_site.parse_packages(text)

        self.assertEqual(2, len(packages))
        self.assertEqual("com.example.one", packages[0]["Package"])
        self.assertEqual("1.0", packages[0]["Version"])
        self.assertEqual("first line\nsecond line\n.", packages[0]["Description"])
        self.assertEqual("com.example.two", packages[1]["Package"])

    def test_find_package_matches_by_package_id(self):
        manifest = {"packages": [{"package": "com.example.one", "slug": "one"}]}

        found = build_site.find_package(manifest, "com.example.one")

        self.assertIsNotNone(found)
        self.assertEqual("one", found["slug"])
        self.assertIsNone(build_site.find_package(manifest, "com.example.missing"))

    def test_write_site_creates_index_404_and_package_page(self):
        build_site.write_site(self.root)

        self.assertTrue((self.root / "docs" / "index.html").is_file())
        self.assertTrue((self.root / "docs" / "404.html").is_file())
        self.assertTrue((self.root / "docs" / "p" / "marquee" / "index.html").is_file())
        self.assertTrue((self.root / "docs" / "assets" / "styles.css").is_file())
        self.assertTrue((self.root / "docs" / "assets" / "app.js").is_file())
        self.assertIn("Page not found", self.read("docs/404.html"))

    def test_404_uses_absolute_links_for_nested_paths(self):
        build_site.write_site(self.root)

        page = self.read("docs/404.html")

        self.assertIn('href="https://kerthmfy.github.io/repo/index.html"', page)
        self.assertIn('href="https://kerthmfy.github.io/repo/assets/styles.css"', page)
        self.assertIn('src="https://kerthmfy.github.io/repo/assets/app.js"', page)

    def test_write_site_prunes_stale_package_pages(self):
        stale = self.root / "docs" / "p" / "old"
        stale.mkdir(parents=True)
        (stale / "index.html").write_text("old page", encoding="utf-8")

        build_site.write_site(self.root)

        self.assertFalse(stale.exists())

    def test_index_renders_every_featured_package(self):
        second = json.loads(json.dumps(self.manifest["packages"][0]))
        second.update(
            {
                "slug": "second",
                "package": "com.example.second",
                "tag": "Second app",
                "icon": "assets/icons/second.png",
                "screenshots": [],
                "featured": True,
            }
        )
        self.manifest["packages"].append(second)
        self.write_manifest()
        self.write_packages(
            PACKAGES_TEXT
            + "\n"
            + "Package: com.example.second\n"
            "Name: Second App\n"
            "Version: 2.0\n"
            "Architecture: iphoneos-arm\n"
            "Section: Utilities\n"
            "Size: 2048\n"
            "Filename: debs/com.example.second_2.0_iphoneos-arm.deb\n"
            "Description: Second app.\n"
        )

        build_site.write_site(self.root)

        index = self.read("docs/index.html")
        self.assertIn("Featured packages", index)
        self.assertIn("Marquee", index)
        self.assertIn("Second App", index)
        self.assertIn('href="p/second/index.html"', index)
        self.assertTrue((self.root / "docs" / "p" / "second" / "index.html").is_file())

    def test_index_has_repo_name_package_version_and_https_source(self):
        build_site.write_site(self.root)

        index = self.read("docs/index.html")

        self.assertIn("KMY Repo", index)
        self.assertIn("Marquee", index)
        self.assertIn("1.0", index)
        self.assertIn("https://kerthmfy.github.io/repo/", index)
        self.assertIn('data-copy="https://kerthmfy.github.io/repo/"', index)
        self.assertIn('href="assets/styles.css"', index)
        self.assertIn("-webkit-linear-gradient", self.read("docs/assets/styles.css"))
        self.assertIn("cydia://url/https://cydia.saurik.com/api/share#?source=", index)

    def test_package_page_links_deb_and_screenshot_with_parent_prefix(self):
        build_site.write_site(self.root)

        page = self.read("docs/p/marquee/index.html")

        self.assertIn(
            'href="../../debs/com.kerthmfy.marquee.app_1.0_iphoneos-arm.deb"', page
        )
        self.assertIn(
            'src="../../assets/screenshots/marquee/attachment-2.png"', page
        )
        self.assertIn("1.2 MB", page)
        self.assertIn("firmware (&gt;= 6.0)", page)

    def test_package_page_does_not_repeat_the_intro_paragraph(self):
        self.manifest["packages"][0]["description"] = [
            "First paragraph.",
            "Second paragraph.",
        ]
        self.write_manifest()

        build_site.write_site(self.root)

        page = self.read("docs/p/marquee/index.html")
        self.assertEqual(1, page.count("<p>First paragraph.</p>"))
        self.assertIn("<p>Second paragraph.</p>", page)

    def test_description_html_is_escaped(self):
        self.manifest["packages"][0]["description"] = ["<script>alert(1)</script>"]
        self.write_manifest()

        build_site.write_site(self.root)

        page = self.read("docs/p/marquee/index.html")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_missing_package_metadata_raises_with_package_id(self):
        self.write_packages("Package: com.example.other\nVersion: 9.9\n")

        with self.assertRaises(ValueError) as caught:
            build_site.write_site(self.root)

        self.assertIn("com.kerthmfy.marquee.app", str(caught.exception))
        self.assertIn("docs/Packages", str(caught.exception))

    def test_extra_packages_entry_without_manifest_raises(self):
        self.write_packages(
            PACKAGES_TEXT
            + "\n"
            + "Package: com.example.extra\n"
            "Version: 9.9\n"
        )

        with self.assertRaises(ValueError) as caught:
            build_site.write_site(self.root)

        self.assertIn("com.example.extra", str(caught.exception))
        self.assertIn("data/packages.json", str(caught.exception))

    def test_real_stylesheet_is_ios6_safe_and_displays_main(self):
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("main {", css)
        self.assertIn("display: block;", css)
        for feature in ("var(--", "display: grid", "display: flex", "flex-direction:"):
            self.assertNotIn(feature, css)


if __name__ == "__main__":
    unittest.main()
