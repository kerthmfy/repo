#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/kmy-repo-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  grep -qF "$2" "$1" || fail "expected '$2' in $1"
}

cp -R "$ROOT/tools" "$TMP/tools"
cp -R "$ROOT/site" "$TMP/site"
cp -R "$ROOT/data" "$TMP/data"
mkdir -p "$TMP/docs/debs"
cp "$ROOT/docs/.nojekyll" "$TMP/docs/.nojekyll"

cat > "$TMP/data/packages.json" <<'JSON'
{
  "repo": {
    "name": "KMY Test Repo",
    "tagline": "A tiny repo used by the tests.",
    "url": "http://example.test/repo/",
    "https_url": "https://example.test/repo/",
    "github": "https://github.com/example/repo"
  },
  "packages": [
    {
      "slug": "example",
      "package": "com.example.test",
      "tag": "Test app",
      "description": ["A fake package for the integration test."],
      "minimum_os": "6.0",
      "icon": "assets/icons/example.png",
      "screenshots": [],
      "source": "https://github.com/example/test",
      "changelog": ["1.0 - Test release."],
      "featured": false
    }
  ]
}
JSON

make_deb() {
  local version="$1"
  local src="$TMP/build-$version"
  rm -rf "$src"
  mkdir -p "$src/DEBIAN"
  cat > "$src/DEBIAN/control" <<CONTROL
Package: com.example.test
Name: Example App
Version: $version
Architecture: iphoneos-arm
Section: Utilities
Maintainer: Test <test@example.com>
Description: A test package.
CONTROL
  dpkg-deb -b "$src" \
    "$TMP/docs/debs/com.example.test_${version}_iphoneos-arm.deb" >/dev/null
}

make_deb 1.0

(cd "$TMP" && ./tools/update_repo.sh --no-commit) || fail "update_repo failed"

PACKAGES="$TMP/docs/Packages"
for expected in \
  "Package: com.example.test" \
  "Version: 1.0" \
  "Filename: debs/com.example.test_1.0_iphoneos-arm.deb" \
  "Section: Utilities"
do
  assert_contains "$PACKAGES" "$expected"
done

SIZE="$(awk '/^Size:/{print $2; exit}' "$PACKAGES")"
[ -n "$SIZE" ] || fail "Size field missing"
[ "$SIZE" -gt 0 ] || fail "Size is not positive: $SIZE"

for generated in Packages.bz2 Packages.gz Release; do
  [ -s "$TMP/docs/$generated" ] || fail "missing or empty docs/$generated"
done

assert_contains "$TMP/docs/Release" "Architectures: iphoneos-arm"
assert_contains "$TMP/docs/Release" "SHA256:"
EXPECTED_SHA="$(cd "$TMP/docs" && shasum -a 256 Packages | awk '{print $1}')"
assert_contains "$TMP/docs/Release" "$EXPECTED_SHA"

[ -s "$TMP/docs/index.html" ] || fail "missing docs/index.html"
[ -s "$TMP/docs/p/example/index.html" ] || fail "missing example package page"
[ ! -e "$TMP/docs/p/marquee/index.html" ] || fail "unexpected marquee page"
assert_contains "$TMP/docs/index.html" "Example App"

make_deb 1.1

set +e
OUTPUT="$(cd "$TMP" && ./tools/update_repo.sh --no-commit 2>&1)"
STATUS=$?
set -e

[ "$STATUS" -ne 0 ] || fail "duplicate versions should fail"
case "$OUTPUT" in
  *"multiple versions"*) ;;
  *) fail "duplicate failure did not explain the problem: $OUTPUT" ;;
esac

echo "test_update_repo: PASS"
