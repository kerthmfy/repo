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


if __name__ == "__main__":
    unittest.main()
