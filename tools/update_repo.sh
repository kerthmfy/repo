#!/bin/bash
# Regenerate the apt indexes and the catalog, then optionally commit and push.
#
# Run from anywhere: the script resolves the repo root from its own location.
# Usage: ./tools/update_repo.sh [--message MSG] [--push] [--no-commit]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

MESSAGE="update repo"
PUSH=0
COMMIT=1

usage() {
  cat <<'USAGE'
Usage: ./tools/update_repo.sh [options]

  --message MSG   Commit message (default: "update repo")
  --push          Push main after committing
  --no-commit     Regenerate files without committing
  -h, --help      Show this help
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --message)
      [ $# -ge 2 ] || { echo "--message needs a value" >&2; exit 2; }
      MESSAGE="$2"
      shift 2
      ;;
    --push)
      PUSH=1
      shift
      ;;
    --no-commit)
      COMMIT=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$PUSH" -eq 1 ] && [ "$COMMIT" -eq 0 ]; then
  echo "--push cannot be combined with --no-commit" >&2
  exit 2
fi

[ -d docs/debs ] || { echo "missing docs/debs" >&2; exit 1; }
[ -f data/packages.json ] || { echo "missing data/packages.json" >&2; exit 1; }
[ -d docs ] || { echo "missing docs/" >&2; exit 1; }

# One .deb per package. Two versions would make dpkg-scanpackages pick one
# arbitrarily, so stop before the indexes can disagree with the site.
DUPLICATES="$(find docs/debs -maxdepth 1 -name '*.deb' -exec basename {} \; |
  awk -F_ '{count[$1]++} END {for (p in count) if (count[p] > 1) print p}' |
  sort)"

if [ -n "$DUPLICATES" ]; then
  echo "multiple versions found; remove old .deb files:" >&2
  printf '  %s\n' $DUPLICATES >&2
  exit 1
fi

OVERRIDE="$(mktemp "${TMPDIR:-/tmp}/kmy-override.XXXXXX")"
trap 'rm -f "$OVERRIDE"' EXIT

# Build the override file from the packages themselves so the Section shown in
# Cydia always matches the .deb control metadata.
: > "$OVERRIDE"
for deb in docs/debs/*.deb; do
  [ -f "$deb" ] || continue
  package="$(dpkg-deb -f "$deb" Package)"
  section="$(dpkg-deb -f "$deb" Section 2>/dev/null || true)"
  [ -n "$section" ] || section="misc"
  printf '%s optional %s\n' "$package" "$section" >> "$OVERRIDE"
done

# Filename entries stay relative to docs/, which is also the site root.
(cd docs && dpkg-scanpackages debs "$OVERRIDE" > Packages)

(cd docs && bzip2 -9 -k -f Packages && gzip -9 -k -f Packages)

digest_line() {
  local algorithm="$1"
  local file="$2"
  local size hash
  size="$(wc -c < "docs/$file" | tr -d ' ')"
  hash="$(openssl dgst "-$algorithm" -r "docs/$file" | awk '{print $1}')"
  printf ' %s %s %s\n' "$hash" "$size" "$file"
}

{
  echo "Origin: KMY"
  echo "Label: KMY Repo"
  echo "Suite: stable"
  echo "Version: 1.0"
  echo "Codename: ios"
  echo "Architectures: iphoneos-arm"
  echo "Components: main"
  echo "Description: iOS 6 apps and tweaks by KMY."
  echo "Date: $(date -u '+%a, %d %b %Y %H:%M:%S UTC')"
  echo "MD5Sum:"
  digest_line md5 Packages
  digest_line md5 Packages.bz2
  digest_line md5 Packages.gz
  echo "SHA1:"
  digest_line sha1 Packages
  digest_line sha1 Packages.bz2
  digest_line sha1 Packages.gz
  echo "SHA256:"
  digest_line sha256 Packages
  digest_line sha256 Packages.bz2
  digest_line sha256 Packages.gz
} > docs/Release

python3 tools/build_site.py --repo "$REPO_ROOT"

if [ "$COMMIT" -eq 1 ]; then
  git add docs
  if git diff --cached --quiet; then
    echo "No generated changes to commit."
  else
    git commit -m "$MESSAGE"
  fi
  if [ "$PUSH" -eq 1 ]; then
    git push origin main
  fi
else
  echo "Generated files updated; git commit skipped (--no-commit)."
fi

echo "Repo indexes: $REPO_ROOT/docs/Packages"
