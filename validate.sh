#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail=0

for skill in "$ROOT"/skills/*/SKILL.md; do
  [[ -f "$skill" ]] || { echo "Missing skill file: $skill"; fail=1; }
done

for f in \
  "$ROOT/shared/ModernVHDL.md" \
  "$ROOT/shared/CodingStyle.md" \
  "$ROOT/shared/CdcPolicy.md" \
  "$ROOT/shared/TypeResolutionPolicy.md" \
  "$ROOT/shared/InterfaceRecords.md" \
  "$ROOT/shared/Axi4.md" \
  "$ROOT/integrations/maki/AGENTS.md" \
  "$ROOT/integrations/maki/mcp.toml" \
  "$ROOT/integrations/claude/CLAUDE.md"
do
  [[ -f "$f" ]] || { echo "Missing: $f"; fail=1; }
done

if grep -R -n -E 'Preferred source order:' "$ROOT/shared/CdcPolicy.md" >/dev/null; then
  grep -A5 -n 'Preferred source order:' "$ROOT/shared/CdcPolicy.md"
fi

[[ "$fail" -eq 0 ]] || exit 1
echo "Validation OK"
