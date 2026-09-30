#!/bin/bash
# Apply only preferences explicitly selected on the source Mac.
set -euo pipefail
case "${1:---dry-run}" in
  --dry-run)
    printf '%s\n' 'Would disable automatic spelling correction, smart quotes and smart dashes.'
    printf '%s\n' 'Use --apply to change these settings.'
    ;;
  --apply)
    defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false
    defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
    defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false
    printf '%s\n' 'Applied. Reopen applications to load the new preferences.'
    ;;
  *) printf 'Usage: %s [--dry-run|--apply]\n' "$0" >&2; exit 2 ;;
esac
