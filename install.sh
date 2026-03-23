#!/usr/bin/env bash
# install.sh — installs the lustre-topology Claude skills into a target project
#
# Usage:
#   ./install.sh                  # installs into current directory
#   ./install.sh /path/to/project # installs into specified project root
#
# What gets installed:
#   .claude/commands/lustre_background.md
#   .claude/commands/topology.md
#   .claude/commands/plan_lustre_test.md
#   scripts/collect_lustre_topology.py
#
# Requirements: Python 3, Vagrant, VirtualBox (on the target machine)

set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$(pwd)}"

if [[ ! -d "$TARGET" ]]; then
  echo "error: target directory does not exist: $TARGET" >&2
  exit 1
fi

if [[ "$(realpath "$TARGET")" == "$(realpath "$BUNDLE_DIR")" ]]; then
  echo "error: target must not be the bundle directory itself" >&2
  exit 1
fi

echo "Installing lustre-topology skills into: $TARGET"

install_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    echo "  overwrite  $dst"
  else
    echo "  install    $dst"
  fi
  cp "$src" "$dst"
}

install_file "$BUNDLE_DIR/skills/lustre_background.md"  "$TARGET/.claude/commands/lustre_background.md"
install_file "$BUNDLE_DIR/skills/topology.md"          "$TARGET/.claude/commands/topology.md"
install_file "$BUNDLE_DIR/skills/plan_lustre_test.md"  "$TARGET/.claude/commands/plan_lustre_test.md"
install_file "$BUNDLE_DIR/scripts/collect_lustre_topology.py" "$TARGET/scripts/collect_lustre_topology.py"

echo ""
echo "Done. Installed 4 files."
echo ""
echo "Skills available in Claude Code:"
echo "  /topology          — collect Lustre topology from Vagrant VMs"
echo "  /plan_lustre_test  — plan a Lustre performance test (calls /topology if needed)"
echo ""
echo "Commit the installed files to your project:"
echo "  git -C \"$TARGET\" add .claude/commands/lustre_background.md \\"
echo "                       .claude/commands/topology.md \\"
echo "                       .claude/commands/plan_lustre_test.md \\"
echo "                       scripts/collect_lustre_topology.py"
