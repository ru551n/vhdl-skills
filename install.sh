#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./install.sh --target <maki|claude|both> [--project DIR] [--mode copy|link] [--with-mcp]

Options:
  --target      Integration to install.
  --project     Destination project directory. Default: current directory.
  --mode        copy (default) or link.
                link creates symlinks back to this repository where practical.
  --with-mcp    Install/copy the project MCP configuration too.
  -h, --help    Show this help.

Examples:
  ./install.sh --target maki --project ~/src/my_fpga --with-mcp
  ./install.sh --target claude --project . --mode link
  ./install.sh --target both --project ../design --with-mcp
EOF
}

TARGET=""
PROJECT="$(pwd)"
MODE="copy"
WITH_MCP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --with-mcp) WITH_MCP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ "$TARGET" =~ ^(maki|claude|both)$ ]] || { echo "--target must be maki, claude, or both" >&2; exit 2; }
[[ "$MODE" =~ ^(copy|link)$ ]] || { echo "--mode must be copy or link" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(mkdir -p "$PROJECT" && cd "$PROJECT" && pwd)"

copy_or_link_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  rm -f "$dst"
  if [[ "$MODE" == "link" ]]; then
    ln -s "$src" "$dst"
  else
    cp "$src" "$dst"
  fi
}

copy_or_link_dir() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  rm -rf "$dst"
  if [[ "$MODE" == "link" ]]; then
    ln -s "$src" "$dst"
  else
    cp -R "$src" "$dst"
  fi
}

install_skills_to() {
  local dst="$1"
  mkdir -p "$dst"
  for skill in "$ROOT"/skills/*; do
    [[ -d "$skill" ]] || continue
    local name
    name="$(basename "$skill")"
    copy_or_link_dir "$skill" "$dst/$name"
  done
  copy_or_link_dir "$ROOT/shared" "$dst/shared"
}

install_maki() {
  echo "Installing Maki integration into $PROJECT"
  mkdir -p "$PROJECT/.maki"
  install_skills_to "$PROJECT/.maki/skills"
  copy_or_link_file "$ROOT/integrations/maki/AGENTS.md" "$PROJECT/AGENTS.md"

  if [[ "$WITH_MCP" -eq 1 ]]; then
    copy_or_link_file "$ROOT/integrations/maki/mcp.toml" "$PROJECT/.maki/mcp.toml"
  fi
}

install_claude() {
  echo "Installing Claude Code integration into $PROJECT"
  mkdir -p "$PROJECT/.claude"
  install_skills_to "$PROJECT/.claude/skills"
  copy_or_link_file "$ROOT/integrations/claude/CLAUDE.md" "$PROJECT/CLAUDE.md"
  copy_or_link_dir "$ROOT/integrations/claude/agents" "$PROJECT/.claude/agents"

  if [[ "$WITH_MCP" -eq 1 ]]; then
    echo "Note: Claude MCP registration is CLI/user-config driven."
    echo "See $ROOT/MCP_SETUP.md for the MCP server setup commands."
  fi
}

case "$TARGET" in
  maki) install_maki ;;
  claude) install_claude ;;
  both) install_maki; install_claude ;;
esac

echo
echo "Installed successfully."
echo "Project: $PROJECT"
echo "Mode:    $MODE"
