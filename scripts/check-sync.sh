#!/bin/bash
# Read-only comparison of the machine's configuration with repository copies.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_path=""
case "${1:-}" in
  '') ;;
  --report)
    if [ "$#" -ne 2 ] || [ -z "$2" ]; then
      printf 'Usage: %s [--report PATH]\n' "$0" >&2
      exit 2
    fi
    report_path="$2" ;;
  -h|--help)
    printf 'Usage: %s [--report PATH]\nChecks configuration drift without syncing, committing or pushing.\n' "$0"
    exit 0 ;;
  *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-check.XXXXXXXX")"
trap 'rm -rf "$staging_dir"' EXIT
changed=0
missing=0
errors=0

check_file() {
  local source="$1" target="$2" label="$3" result
  if [ ! -e "$source" ]; then
    printf '源文件缺失，需人工确认是否保留仓库副本：%s\n' "$label"
    missing=$((missing + 1))
  elif [ ! -f "$source" ] || [ ! -r "$source" ]; then
    printf '无法读取源文件：%s\n' "$label"
    errors=$((errors + 1))
  elif [ -L "$target" ]; then
    printf '仓库副本为软链接，需人工检查：%s\n' "$label"
    errors=$((errors + 1))
  elif [ ! -e "$target" ]; then
    printf '需要新增仓库副本：%s\n' "$label"
    changed=$((changed + 1))
  elif cmp -s "$source" "$target"; then
    printf '一致：%s\n' "$label"
  else
    result=$?
    if [ "$result" -eq 1 ]; then
      printf '需要同步：%s\n' "$label"
      changed=$((changed + 1))
    else
      printf '比较失败：%s\n' "$label"
      errors=$((errors + 1))
    fi
  fi
}

{
  printf '配置同步检查 — %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z %z')"
  printf '仓库：%s\n\n' "$repo_dir"
  brew_bin="$(command -v brew || true)"
  if [ -z "$brew_bin" ] && [ -x /opt/homebrew/bin/brew ]; then
    brew_bin=/opt/homebrew/bin/brew
  fi
  if [ -n "$brew_bin" ] && HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ANALYTICS=1 \
    "$brew_bin" bundle dump --file="$staging_dir/Brewfile" >"$staging_dir/brew.log" 2>&1; then
    check_file "$staging_dir/Brewfile" "$repo_dir/Brewfile" Brewfile
  else
    printf 'Homebrew 清单导出失败；未将本次检查判定为无变化。请手动检查 brew bundle dump。\n'
    errors=$((errors + 1))
  fi
  check_file "$HOME/.zprofile" "$repo_dir/config/zprofile" config/zprofile
  check_file "$HOME/.zshrc" "$repo_dir/config/zshrc" config/zshrc
  check_file "$HOME/.gitconfig" "$repo_dir/config/gitconfig" config/gitconfig
  check_file "$HOME/.config/mise/config.toml" "$repo_dir/config/mise/config.toml" config/mise/config.toml

  printf '\n结果：%s 项需要同步，%s 项源文件缺失，%s 项检查失败。\n' "$changed" "$missing" "$errors"
  printf '\n仓库未提交修改（与本机配置是否已同步分别判断）：\n'
  if git -C "$repo_dir" status --short >"$staging_dir/git-status" 2>/dev/null; then
    if [ -s "$staging_dir/git-status" ]; then
      cat "$staging_dir/git-status"
    else
      printf '无。\n'
    fi
  else
    printf '无法读取 Git 状态。\n'
    errors=$((errors + 1))
  fi
  printf '\n本检查不修改配置、不同步、不提交、不推送，不输出配置内容。\n'
  printf '检查范围与 scripts/sync.sh 一致；其他应用及其配置需人工核对 APPS.md。\n'
} >"$staging_dir/report.txt"

if [ -n "$report_path" ]; then
  mkdir -p "$(dirname "$report_path")"
  (umask 077; cat "$staging_dir/report.txt" >"$report_path")
fi
cat "$staging_dir/report.txt"
if [ "$errors" -gt 0 ]; then exit 1; fi
