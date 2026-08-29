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
  "$ROOT/shared/Vunit.md" \
  "$ROOT/integrations/maki/AGENTS.md" \
  "$ROOT/integrations/maki/mcp.toml" \
  "$ROOT/integrations/claude/CLAUDE.md"
do
  [[ -f "$f" ]] || { echo "Missing: $f"; fail=1; }
done

if grep -R -n -E 'Preferred source order:' "$ROOT/shared/CdcPolicy.md" >/dev/null; then
  grep -A5 -n 'Preferred source order:' "$ROOT/shared/CdcPolicy.md"
fi

# Every shared/<file>.md referenced from a skill must exist in shared/
# (third-party installs that drop the shared/ directory break these refs).
while IFS= read -r ref; do
  if [[ ! -f "$ROOT/shared/$ref" ]]; then
    echo "Dangling shared/ reference in skills/: $ref"
    fail=1
  fi
done < <(grep -rhoE 'shared/[A-Za-z0-9_.-]+\.md' "$ROOT"/skills/ | sort -u | sed 's|^shared/||')

[[ "$fail" -eq 0 ]] || exit 1
echo "Validation OK"
