#!/bin/bash
# Capture the current machine's configuration into this repository.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-}" in
  '') ;;
  -h|--help)
    printf 'Usage: %s\nUpdates Brewfile and configuration copies; does not commit or push.\n' "$0"
    exit 0 ;;
  *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

brew_bin="$(command -v brew || true)"
if [ -z "$brew_bin" ]; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$candidate" ]; then brew_bin="$candidate"; break; fi
  done
fi
if [ -z "$brew_bin" ]; then
  printf 'Homebrew was not found. Install Homebrew before syncing.\n' >&2
  exit 1
fi

# Finish export before updating repository files; clean up even on failure.
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-sync.XXXXXXXX")"
trap 'rm -rf "$staging_dir"' EXIT
"$brew_bin" bundle dump --file="$staging_dir/Brewfile"

sync_file() {
  local source="$1" target="$2"
  if [ ! -f "$source" ]; then
    printf 'Skipped missing source (repository copy retained): %s\n' "$source"
    return
  fi
  if [ -L "$target" ]; then
    printf 'Refusing to overwrite repository symlink: %s\n' "$target" >&2
    exit 1
  fi
  if [ -f "$target" ] && cmp -s "$source" "$target"; then
    printf 'Unchanged: %s\n' "${target#"$repo_dir/"}"
    return
  fi
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
  printf 'Updated: %s\n' "${target#"$repo_dir/"}"
}

sync_file "$staging_dir/Brewfile" "$repo_dir/Brewfile"
sync_file "$HOME/.zprofile" "$repo_dir/config/zprofile"
sync_file "$HOME/.zshrc" "$repo_dir/config/zshrc"
sync_file "$HOME/.gitconfig" "$repo_dir/config/gitconfig"
sync_file "$HOME/.config/mise/config.toml" "$repo_dir/config/mise/config.toml"

printf '\nGit status:\n'
git -C "$repo_dir" status --short
git -C "$repo_dir" diff --stat
printf '\nSync complete. Review git diff and any untracked files before committing.\n'
printf 'Update APPS.md manually for apps installed outside Homebrew.\n'
