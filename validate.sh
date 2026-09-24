#!/usr/bin/env bash
# Checks skills, shared docs, agents and plugin manifests for the mistakes that
# have actually happened: dangling shared/ references, descriptions that don't
# say when to trigger, agents naming missing skills, and invented tool names.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
err() { echo "ERROR: $*"; fail=1; }

for dir in "$ROOT"/skills/*/; do
  name="$(basename "$dir")"
  [[ "$name" == shared ]] && continue
  f="$dir/SKILL.md"
  [[ -f "$f" ]] || { err "$name: missing SKILL.md"; continue; }
  grep -q "^name: $name\$" "$f" || err "$name: frontmatter name does not match its folder"
  grep -qE '^description: Use when ' "$f" || err "$name: description must start with 'Use when'"
  (( $(grep -m1 '^description: ' "$f" | wc -c) <= 1024 )) || err "$name: description over 1024 characters"
  while IFS= read -r ref; do
    [[ -f "$dir/$ref" ]] || err "$name: SKILL.md points at missing $ref"
  done < <(grep -oE '`[a-z-]+\.md`' "$f" | tr -d '`' | sort -u)
done

while IFS= read -r ref; do
  [[ -f "$ROOT/skills/shared/$ref" ]] || err "dangling reference: shared/$ref"
done < <(grep -rhoE 'shared/[A-Za-z0-9_.-]+\.md' "$ROOT/skills" "$ROOT/agents" | sort -u | sed 's|^shared/||')

for a in "$ROOT"/agents/*.md; do
  while IFS= read -r s; do
    [[ -f "$ROOT/skills/$s/SKILL.md" ]] || err "$(basename "$a"): unknown skill '$s'"
  done < <(awk '/^skills:/{f=1;next} f&&/^  - /{print $2;next} f{exit}' "$a")
done

# Documented `vhdl-tools <group> <command>` invocations must exist in the CLI.
if command -v uv >/dev/null 2>&1; then
  for group in vunit synth wave; do
    known="$("$ROOT/skills/shared/bin/vhdl-tools" "$group" --help 2>/dev/null | sed -n 's/^    \([a-z][a-z-]*\).*/\1/p')"
    [[ -n "$known" ]] || { err "could not list vhdl-tools $group commands"; continue; }
    while IFS= read -r cmd; do
      grep -qx "$cmd" <<<"$known" || err "documented command does not exist: vhdl-tools $group $cmd"
    done < <(grep -rhoE "\`vhdl-tools $group [a-z][a-z-]*" "$ROOT/skills" "$ROOT/agents" "$ROOT/README.md" "$ROOT/SETUP.md" \
               --include='*.md' --exclude-dir=tools | awk '{print $3}' | sort -u)
  done
fi

# Tool names of the retired vunit-mcp/tsfpga-mcp/peeper-mcp servers must not come back.
if grep -rnE '\b(vunit|tsfpga|peeper)_(status|list_tests|list_files|compile|elaborate|run_tests|get_report|get_test_log|get_test_waveform|export_json|test_dependencies|synthesize|inspect|hierarchy|targets|project_[a-z_]+|open|search|values|value_at|analyze|latency|find|plot)\b' \
     "$ROOT/skills" "$ROOT/agents" --include='*.md' --exclude-dir=tools; then
  err "retired MCP tool names found above; use vhdl-tools commands"
fi

if command -v claude >/dev/null 2>&1; then
  for m in plugin marketplace; do
    claude plugin validate --strict "$ROOT/.claude-plugin/$m.json" >/dev/null 2>&1 \
      || err "claude plugin validate --strict failed for $m.json"
  done
fi

[[ "$fail" -eq 0 ]] || exit 1
echo "Validation OK"
