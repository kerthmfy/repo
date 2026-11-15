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
    "url": "https://example.test/repo/",
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

git -C "$TMP" init -q
git -C "$TMP" symbolic-ref HEAD refs/heads/main
git -C "$TMP" config user.name "KMY Test"
git -C "$TMP" config user.email "test@example.com"
git -C "$TMP" config commit.gpgsign false
git -C "$TMP" add .
git -C "$TMP" commit -qm "fixture"

make_deb() {
  local version="$1"
  local name="${2:-com.example.test_${version}_iphoneos-arm.deb}"
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
  dpkg-deb -b "$src" "$TMP/docs/debs/$name" >/dev/null
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

# Every Release section must cover every index with a matching digest and size.
python3 - "$TMP/docs" <<'PY' || fail "Release checksums are incomplete or wrong"
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
algorithms = {"MD5Sum:": "md5", "SHA1:": "sha1", "SHA256:": "sha256"}
sections = {}
current = None
for line in (root / "Release").read_text(encoding="utf-8").splitlines():
    if line in algorithms:
        current = algorithms[line]
        sections[current] = {}
    elif current and line.startswith(" ") and line.strip():
        parts = line.split()
        if len(parts) == 3:
            digest, size, name = parts
            sections[current][name] = (digest, int(size))
    elif not line.strip():
        current = None

for algorithm in ("md5", "sha1", "sha256"):
    entries = sections.get(algorithm, {})
    for name in ("Packages", "Packages.bz2", "Packages.gz"):
        if name not in entries:
            raise SystemExit("missing %s in %s section" % (name, algorithm))
        expected, expected_size = entries[name]
        data = (root / name).read_bytes()
        actual = hashlib.new(algorithm, data).hexdigest()
        if actual != expected:
            raise SystemExit("%s %s digest mismatch" % (algorithm, name))
        if len(data) != expected_size:
            raise SystemExit("%s %s size mismatch" % (algorithm, name))
print("release checksums: OK")
PY

assert_contains "$TMP/docs/Release" "Architectures: iphoneos-arm"

[ -s "$TMP/docs/index.html" ] || fail "missing docs/index.html"
[ -s "$TMP/docs/p/example/index.html" ] || fail "missing example package page"
[ ! -e "$TMP/docs/p/marquee/index.html" ] || fail "unexpected marquee page"
assert_contains "$TMP/docs/index.html" "Example App"

# Duplicate detection must use control metadata: this second .deb has a
# completely different filename but the same Package field.
make_deb 1.1 example-latest.deb
BEFORE_DUPLICATE="$(shasum -a 256 "$PACKAGES" | awk '{print $1}')"
set +e
OUTPUT="$(cd "$TMP" && ./tools/update_repo.sh --no-commit 2>&1)"
STATUS=$?
set -e

[ "$STATUS" -ne 0 ] || fail "duplicate packages should fail"
case "$OUTPUT" in
  *"multiple .deb files provide the same package"*) ;;
  *) fail "duplicate failure did not name metadata identity: $OUTPUT" ;;
esac
[ "$(shasum -a 256 "$PACKAGES" | awk '{print $1}')" = "$BEFORE_DUPLICATE" ] ||
  fail "duplicate failure changed docs/Packages"
rm -f "$TMP/docs/debs/example-latest.deb"

# A single renamed .deb is legal: identity comes from the archive, not the name.
mv "$TMP/docs/debs/com.example.test_1.0_iphoneos-arm.deb" \
  "$TMP/docs/debs/example-latest.deb"
(cd "$TMP" && ./tools/update_repo.sh --no-commit) || fail "renamed deb was rejected"
assert_contains "$PACKAGES" "Filename: debs/example-latest.deb"
mv "$TMP/docs/debs/example-latest.deb" \
  "$TMP/docs/debs/com.example.test_1.0_iphoneos-arm.deb"

# Any dpkg-scanpackages warning must stop the publish. Shim the command so the
# test can produce the same warning shape on any dpkg-scanpackages version.
REAL_SCAN="$(command -v dpkg-scanpackages)"
mkdir -p "$TMP/fakebin"
cat > "$TMP/fakebin/dpkg-scanpackages" <<SHIM
#!/bin/bash
"$REAL_SCAN" "\$@"
STATUS=\$?
if [ "\$STATUS" -eq 0 ]; then
  echo "dpkg-scanpackages: warning: synthetic warning" >&2
fi
exit "\$STATUS"
SHIM
chmod +x "$TMP/fakebin/dpkg-scanpackages"
BEFORE_WARNING="$(shasum -a 256 "$PACKAGES" | awk '{print $1}')"
set +e
OUTPUT="$(cd "$TMP" && PATH="$TMP/fakebin:$PATH" ./tools/update_repo.sh --no-commit 2>&1)"
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "scan warnings should fail the update"
case "$OUTPUT" in
  *"dpkg-scanpackages reported warnings"*) ;;
  *) fail "scan warning failure was not explained: $OUTPUT" ;;
esac
[ "$(shasum -a 256 "$PACKAGES" | awk '{print $1}')" = "$BEFORE_WARNING" ] ||
  fail "scan warning failure changed docs/Packages"
rm -rf "$TMP/fakebin"

# The commit must stage the generated site plus its manifest and theme inputs.
python3 - "$TMP/data/packages.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)
manifest["repo"]["tagline"] = "A tiny repo used by the staging test."
with open(path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
PY
printf '\n/* staging test */\n' >> "$TMP/site/styles.css"

(cd "$TMP" && ./tools/update_repo.sh --message "staging test") ||
  fail "update_repo commit failed"

COMMITTED="$(git -C "$TMP" show --pretty=format: --name-only HEAD)"
for expected in \
  "docs/Packages" \
  "docs/Release" \
  "docs/index.html" \
  "data/packages.json" \
  "site/styles.css"
do
  case "$COMMITTED" in
    *"$expected"*) ;;
    *) fail "commit did not stage $expected" ;;
  esac
done

echo "test_update_repo: PASS"
