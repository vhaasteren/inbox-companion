#!/usr/bin/env bash
set -euo pipefail

# Snapshot text files (with headers) to stdout.
# Defaults (overridable):
#   SNAPSHOT_EXCLUDES="node_modules .venv dist out *.patch"
#   INCLUDE_UNTRACKED=1  # include untracked-but-not-ignored files (git repos)

DEFAULT_EXCLUDES="node_modules .venv dist out *.patch"
EXCL_RAW="${SNAPSHOT_EXCLUDES:-$DEFAULT_EXCLUDES}"

is_text() {
  local f="$1" mime=""
  if mime=$(file -I -b "$f" 2>/dev/null); then
    case "$mime" in
      text/*|*json*|*xml*|*yaml*|*toml*|*javascript*|*x-shellscript*|*x-python*|*x-empty*|*inode/x-empty*) return 0 ;;
    esac
  elif mime=$(file -bi "$f" 2>/dev/null); then
    case "$mime" in
      text/*|*json*|*xml*|*yaml*|*toml*|*javascript*|*x-empty*|*inode/x-empty*) return 0 ;;
    esac
  fi
  LC_ALL=C grep -aqI . "$f"
}

in_git_repo=false
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  in_git_repo=true
fi

build_git_excludes() {
  local token
  local -a out=()
  for token in $EXCL_RAW; do
    if [[ "$token" == *"*"* || "$token" == *"?"* || "$token" == *"["* ]]; then
      out+=(":!$token")
    else
      out+=(":!$token/**")
    fi
  done
  printf '%s\0' "${out[@]}" 2>/dev/null || true
}

files=()

if $in_git_repo; then
  IFS= read -r -d '' -a EXCL_OPTS < <(build_git_excludes || printf '\0')
  if [ ${#EXCL_OPTS[@]} -gt 0 ]; then
    while IFS= read -r -d '' f; do files+=("$f"); done \
      < <(git ls-files -z -- . "${EXCL_OPTS[@]}")
  else
    while IFS= read -r -d '' f; do files+=("$f"); done \
      < <(git ls-files -z)
  fi
  if [ "${INCLUDE_UNTRACKED:-}" = "1" ]; then
    if [ ${#EXCL_OPTS[@]} -gt 0 ]; then
      while IFS= read -r -d '' f; do files+=("$f"); done \
        < <(git ls-files -z --others --exclude-standard -- . "${EXCL_OPTS[@]}")
    else
      while IFS= read -r -d '' f; do files+=("$f"); done \
        < <(git ls-files -z --others --exclude-standard)
    fi
  fi
fi

if [ ${#files[@]} -eq 0 ]; then
  SKIP="$EXCL_RAW"
  FIND_EXPR=(.)
  for s in $SKIP; do
    if [[ "$s" == *"*"* || "$s" == *"?"* || "$s" == *"["* ]]; then
      FIND_EXPR+=( -not -name "$s" )
    else
      FIND_EXPR+=( -not -path "*/$s/*" )
    fi
  done
  while IFS= read -r -d '' f; do files+=("$f"); done \
    < <(find "${FIND_EXPR[@]}" -type f -print0)
fi

for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  if is_text "$f"; then
    echo "===== $f ====="
    cat "$f"
    echo
    echo
  fi
done

