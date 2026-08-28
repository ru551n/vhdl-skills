#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-}"
PROJECT="${2:-$(pwd)}"
PROJECT="$(cd "$PROJECT" && pwd)"

case "$TARGET" in
  maki)
    rm -rf "$PROJECT/.maki/skills"
    rm -f "$PROJECT/.maki/mcp.toml" "$PROJECT/AGENTS.md"
    ;;
  claude)
    rm -rf "$PROJECT/.claude/skills" "$PROJECT/.claude/agents"
    rm -f "$PROJECT/CLAUDE.md"
    ;;
  both)
    rm -rf "$PROJECT/.maki/skills" "$PROJECT/.claude/skills" "$PROJECT/.claude/agents"
    rm -f "$PROJECT/.maki/mcp.toml" "$PROJECT/AGENTS.md" "$PROJECT/CLAUDE.md"
    ;;
  *)
    echo "Usage: ./uninstall.sh <maki|claude|both> [project-dir]" >&2
    exit 2
    ;;
esac
echo "Removed installed VHDL skills for: $TARGET"
