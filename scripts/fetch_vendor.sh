#!/usr/bin/env bash
# Clone the five sibling projects at the commits this desk was built against.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/vendor"
clone() {
  local name="$1" url="$2" rev="$3" branch="${4:-}"
  local dest="$root/vendor/$name"
  if [[ -d "$dest/.git" ]]; then
    git -C "$dest" fetch --depth 1 origin "$rev"
    git -C "$dest" checkout "$rev"
    return
  fi
  if [[ -n "$branch" ]]; then
    git clone --depth 1 --branch "$branch" "$url" "$dest"
  else
    git clone --depth 1 "$url" "$dest"
  fi
  git -C "$dest" fetch --depth 1 origin "$rev"
  git -C "$dest" checkout "$rev"
}
clone truthgraph https://github.com/nishanttyagi28/truthgraph.git 2ac10fbd8d50a444da9151bd23d45711d63f627f
clone promptgate https://github.com/nishanttyagi28/promptgate.git 9f74eb567a71cf360ebc6d1ec079f77e88f871f3 master
clone agenteval https://github.com/nishanttyagi28/agenteval.git 5a8e1cfcfbab41dda282d4db21813fae09dba196
clone agentic-data-analyst https://github.com/nishanttyagi28/agentic-data-analyst.git 8fc22fa6e821507e8cc96d31d98f220c9f491054
echo "vendor ready"
