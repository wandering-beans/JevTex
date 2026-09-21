#!/bin/bash
# Project-local BasicTeX from the official Homebrew cask; no sudo or PATH changes.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
local_bin="$repo/.tools/texlive/bin/universal-darwin"
if [ ! -x "$local_bin/lualatex" ]; then
  if [ "$(uname -s)" != Darwin ]; then
    echo "macOS用です。LinuxではTeX Live（LuaLaTeX、日本語、SyncTeX）を導入してください。" >&2
    exit 1
  fi
  mkdir -p "$repo/.tools"
  brew fetch --cask basictex
  package=$(brew --cache --cask basictex)
  scratch=$(mktemp -d "$repo/.tools/basictex.XXXXXX")
  pkgutil --expand-full "$package" "$scratch/expanded"
  shopt -s nullglob
  roots=("$scratch"/expanded/*/Payload/usr/local/texlive/*basic)
  if [ "${#roots[@]}" != 1 ]; then
    echo "BasicTeXのパッケージ構造が変わっています。展開先を確認してください: $scratch" >&2
    exit 1
  fi
  mv "${roots[0]}" "$repo/.tools/texlive"
fi
"$local_bin/tlmgr" option repository https://mirror.ctan.org/systems/texlive/tlnet
"$local_bin/tlmgr" update --self
"$local_bin/tlmgr" install luatexja haranoaji
"$local_bin/lualatex" --version | head -n 1
echo "JevTexがローカルTeXを自動検出します: $local_bin"
