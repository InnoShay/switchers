#!/usr/bin/env bash
# Prints ticket status from merged/open PR titles. Requires gh CLI logged in.
# Portable to bash 3.2 (macOS): no associative arrays.
set -euo pipefail
owner_of() {
  case "$1" in
    01|03|05|07|10|12|14|16) echo Lakshay ;;
    *) echo Yash ;;
  esac
}
merged=$(gh pr list --state merged --limit 200 --json title -q '.[].title' | grep -oE '^RS-[0-9]{2}' | sort -u || true)
open=$(gh pr list --state open --limit 200 --json title -q '.[].title' | grep -oE '^RS-[0-9]{2}' | sort -u || true)
printf "%-6s %-8s %-8s\n" TICKET OWNER STATUS
for n in $(seq -w 1 16); do
  id="RS-$n"; s="todo"
  grep -qx "$id" <<<"$open" && s="in-PR"
  grep -qx "$id" <<<"$merged" && s="merged"
  printf "%-6s %-8s %-8s\n" "$id" "$(owner_of "$n")" "$s"
done
