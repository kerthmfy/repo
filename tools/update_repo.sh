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

[ -d docs ] || { echo "missing docs/" >&2; exit 1; }
[ -d docs/debs ] || { echo "missing docs/debs" >&2; exit 1; }
[ -d data ] || { echo "missing data/" >&2; exit 1; }
[ -d site ] || { echo "missing site/" >&2; exit 1; }
[ -f data/packages.json ] || { echo "missing data/packages.json" >&2; exit 1; }

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/kmy-index.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

# Identify packages from their control metadata, not their filenames. A renamed
# .deb still counts as a second copy of the same package.
IDENTITY="$SCRATCH/debs.tsv"
: > "$IDENTITY"

for deb in docs/debs/*.deb; do
  [ -f "$deb" ] || continue
  ERR="$SCRATCH/dpkg.err"
  if ! PACKAGE="$(dpkg-deb -f "$deb" Package 2>"$ERR")"; then
    echo "cannot read package metadata from $deb:" >&2
    sed 's/^/  /' "$ERR" >&2
    exit 1
  fi
  PACKAGE="$(printf '%s' "$PACKAGE" | tr -d '\r')"
  if [ -z "$PACKAGE" ]; then
    echo "missing Package field in $deb" >&2
    exit 1
  fi
  printf '%s\t%s\n' "$PACKAGE" "$deb" >> "$IDENTITY"
done

# One .deb per package. Two versions, or two filenames for the same version,
# would make dpkg-scanpackages choose one arbitrarily.
DUPLICATES="$(awk -F '\t' '
  { count[$1]++; files[$1] = files[$1] " " $2 }
  END {
    for (package in count)
      if (count[package] > 1)
        print package ":" files[package]
  }
' "$IDENTITY" | sort)"

if [ -n "$DUPLICATES" ]; then
  echo "multiple .deb files provide the same package; keep one version per package:" >&2
  printf '%s\n' "$DUPLICATES" | sed 's/^/  /' >&2
  exit 1
fi

# Build the override file from the packages themselves so the Section shown in
# Cydia always matches the .deb control metadata.
OVERRIDE="$SCRATCH/override"
: > "$OVERRIDE"
while IFS=$'\t' read -r PACKAGE DEB; do
  [ -n "$PACKAGE" ] || continue
  SECTION="$(dpkg-deb -f "$DEB" Section 2>/dev/null || true)"
  SECTION="$(printf '%s' "$SECTION" | tr -d '\r')"
  [ -n "$SECTION" ] || SECTION="misc"
  printf '%s optional %s\n' "$PACKAGE" "$SECTION" >> "$OVERRIDE"
done < "$IDENTITY"

# Generate into a scratch directory first. Nothing in docs/ is replaced until
# dpkg-scanpackages has succeeded without warnings.
SCAN_ERR="$SCRATCH/scan.err"
if ! (cd docs && dpkg-scanpackages debs "$OVERRIDE" > "$SCRATCH/Packages" 2> "$SCAN_ERR"); then
  echo "dpkg-scanpackages failed:" >&2
  sed 's/^/  /' "$SCAN_ERR" >&2
  exit 1
fi

# "info: Wrote N entries" is normal; every other line is a warning or error.
if grep -v '^dpkg-scanpackages: info:' "$SCAN_ERR" | grep -q .; then
  echo "dpkg-scanpackages reported warnings; refusing to publish:" >&2
  grep -v '^dpkg-scanpackages: info:' "$SCAN_ERR" | sed 's/^/  /' >&2
  exit 1
fi

bzip2 -9 -c "$SCRATCH/Packages" > "$SCRATCH/Packages.bz2"
gzip -9 -c "$SCRATCH/Packages" > "$SCRATCH/Packages.gz"

digest_line() {
  local algorithm="$1"
  local file="$2"
  local name="$3"
  local size hash
  size="$(wc -c < "$file" | tr -d ' ')"
  hash="$(openssl dgst "-$algorithm" -r "$file" | awk '{print $1}')"
  printf ' %s %s %s\n' "$hash" "$size" "$name"
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
  digest_line md5 "$SCRATCH/Packages" Packages
  digest_line md5 "$SCRATCH/Packages.bz2" Packages.bz2
  digest_line md5 "$SCRATCH/Packages.gz" Packages.gz
  echo "SHA1:"
  digest_line sha1 "$SCRATCH/Packages" Packages
  digest_line sha1 "$SCRATCH/Packages.bz2" Packages.bz2
  digest_line sha1 "$SCRATCH/Packages.gz" Packages.gz
  echo "SHA256:"
  digest_line sha256 "$SCRATCH/Packages" Packages
  digest_line sha256 "$SCRATCH/Packages.bz2" Packages.bz2
  digest_line sha256 "$SCRATCH/Packages.gz" Packages.gz
} > "$SCRATCH/Release"

mv "$SCRATCH/Packages.bz2" docs/Packages.bz2
mv "$SCRATCH/Packages.gz" docs/Packages.gz
mv "$SCRATCH/Packages" docs/Packages
mv "$SCRATCH/Release" docs/Release

python3 tools/build_site.py --repo "$REPO_ROOT"

if [ "$COMMIT" -eq 1 ]; then
  # The manifest and theme are inputs to the generated site, so stage them too.
  git add docs data site
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
