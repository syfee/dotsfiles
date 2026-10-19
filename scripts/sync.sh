#!/bin/bash
# Capture the current machine's configuration into this repository.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_sources=("$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.gitconfig" "$HOME/.config/mise/config.toml")
config_paths=(config/zprofile config/zshrc config/gitconfig config/mise/config.toml)
output_dir="$repo_dir"
show_git_status=true
case "${1:-}" in
  '') ;;
  --list-files)
    [ "$#" -eq 1 ] || { printf 'Unexpected arguments.\n' >&2; exit 2; }
    printf '%s\n' Brewfile "${config_paths[@]}"
    exit 0 ;;
  --output-dir)
    if [ "$#" -ne 2 ] || [ -z "$2" ]; then
      printf 'Usage: %s --output-dir DIR\n' "$0" >&2
      exit 2
    fi
    mkdir -p "$2"
    output_dir="$(cd "$2" && pwd)"
    show_git_status=false ;;
  -h|--help)
    printf 'Usage: %s [--output-dir DIR | --list-files]\nUpdates Brewfile and configuration copies; does not commit or push.\n' "$0"
    printf '  --output-dir DIR  Write a snapshot to DIR instead of the repository.\n'
    printf '  --list-files      List managed repository-relative paths without exporting.\n'
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
  if [ ! -e "$source" ]; then
    printf 'Skipped missing source (existing copy retained): %s\n' "$source"
    return
  fi
  if [ ! -f "$source" ]; then
    printf 'Source is not a regular file: %s\n' "$source" >&2
    exit 1
  fi
  if [ -L "$target" ]; then
    printf 'Refusing to overwrite destination symlink: %s\n' "$target" >&2
    exit 1
  fi
  if [ -f "$target" ] && cmp -s "$source" "$target"; then
    printf 'Unchanged: %s\n' "${target#"$output_dir/"}"
    return
  fi
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
  printf 'Updated: %s\n' "${target#"$output_dir/"}"
}

sync_file "$staging_dir/Brewfile" "$output_dir/Brewfile"
for index in "${!config_paths[@]}"; do
  sync_file "${config_sources[$index]}" "$output_dir/${config_paths[$index]}"
done

if "$show_git_status"; then
  printf '\nGit status:\n'
  git -C "$repo_dir" status --short
  git -C "$repo_dir" diff --stat
  printf '\nSync complete. Review git diff and any untracked files before committing.\n'
  printf 'Update APPS.md manually for apps installed outside Homebrew.\n'
fi
