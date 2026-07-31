#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

die() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

need_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

need_command git
need_command python3

[[ -d .git ]] || die "Store publish_release.sh in the root of the Git repository."
[[ -f maplestory_idle_companion_optimizer.py ]] || die "Application source was not found."
[[ -f build_tools/release_metadata.py ]] || die "Release metadata tool was not found."
[[ -x build_tools/build_linux.sh ]] || die "build_tools/build_linux.sh is missing or not executable."
[[ -f .github/workflows/build-desktop-releases.yml ]] || die "GitHub release workflow was not found."

branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || die "Releases must be made from main. Current branch: ${branch:-detached HEAD}"
git remote get-url origin >/dev/null 2>&1 || die "The Git remote named origin is not configured."

printf 'Fetching origin/main and release tags...\n'
git fetch origin main --tags

if ! git merge-base --is-ancestor origin/main HEAD; then
    die "Local main has diverged from origin/main. Resolve the branch before publishing."
fi
if ! git merge-base --is-ancestor HEAD origin/main; then
    die "Local main is behind origin/main. Pull the latest changes before publishing."
fi

printf '\nUpdating and validating release metadata...\n'
python3 build_tools/release_metadata.py --write-windows-version
python3 build_tools/release_metadata.py --check
version="$(python3 build_tools/release_metadata.py --print-version)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Invalid APP_VERSION: $version"
tag="v${version}"

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "Local tag $tag already exists. Increase APP_VERSION for a new release."
fi
if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
    die "Remote tag $tag already exists. Increase APP_VERSION for a new release."
fi

printf '\nBuilding and testing the Linux release locally...\n'
printf 'This includes frozen startup tests for both the one-folder and single-file programs.\n'
./build_tools/build_linux.sh

printf '\nFiles that will be included in the release commit:\n'
git status --short

printf '\nPublishing %s will:\n' "$tag"
printf '  1. Commit all current repository changes as "Release %s"\n' "$version"
printf '  2. Push main to origin\n'
printf '  3. Push tag %s\n' "$tag"
printf '  4. Make GitHub build native Windows and Linux programs\n'
printf '  5. Publish both programs and checksums as a GitHub Release\n\n'

read -r -p "Build and publish $tag now? [y/N] " answer
case "$answer" in
    y|Y|yes|YES|Yes) ;;
    *) printf 'Release cancelled. Nothing was committed, pushed, or tagged.\n'; exit 0 ;;
esac

git add -A
if git diff --cached --quiet; then
    printf '\nNo uncommitted source changes were found; releasing the current commit.\n'
else
    git commit -m "Release $version"
fi

printf '\nPushing main...\n'
git push origin main

printf '\nCreating and pushing %s...\n' "$tag"
git tag -a "$tag" -m "Release $version"
git push origin "$tag"

printf '\n%s was pushed successfully.\n' "$tag"
printf 'GitHub Actions is now building the Windows EXE and Linux executable.\n'
printf 'After both packaged startup tests pass, the workflow will publish the release assets.\n'
