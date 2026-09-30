#!/bin/bash
# Preview by default; --apply copies configuration and backs up existing files.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---dry-run}"
case "$mode" in
  --apply|--dry-run) ;;
  *) printf 'Usage: %s [--dry-run|--apply]\n' "$0" >&2; exit 2 ;;
esac
backup_dir=""
restore_file() {
  local source="$repo_dir/config/$1" target="$HOME/$2"
  if [ -f "$target" ] && cmp -s "$source" "$target"; then
    printf 'Unchanged: %s\n' "$target"
    return
  fi
  printf 'Copy: %s -> %s\n' "$source" "$target"
  [ "$mode" = --apply ] || return 0
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ -z "$backup_dir" ]; then
      mkdir -p "$HOME/.local/state/dotfiles"
      backup_dir="$(mktemp -d "$HOME/.local/state/dotfiles/backup.XXXXXXXX")"
    fi
    mkdir -p "$backup_dir/$(dirname "$2")"
    cp -Pp "$target" "$backup_dir/$2"
    # Replace a symlink itself, never overwrite its external target.
    if [ -L "$target" ]; then rm "$target"; fi
  fi
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
}
restore_file zprofile .zprofile
restore_file zshrc .zshrc
restore_file gitconfig .gitconfig
restore_file mise/config.toml .config/mise/config.toml
if [ -n "$backup_dir" ]; then printf 'Backups: %s\n' "$backup_dir"; fi
if [ "$mode" = --dry-run ]; then printf 'Preview only. Use --apply to restore.\n'; fi
