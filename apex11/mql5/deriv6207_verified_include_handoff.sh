#!/usr/bin/env bash
# ABUTRON Milestone A — root-authorized, source-only MQL5 header handoff.
# Does NOT compile, start MT5, restart services, enable orders, or change sudo.
set -Eeuo pipefail
if [[ "$(id -u)" != 0 ]]; then
  echo "ROOT_REQUIRED_FOR_PROTECTED_HEADER_HANDOFF" >&2
  exit 10
fi
expected="e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44"
s1="/root/abutron_optionc_cutover/AdaptiveRiskProofV2.mqh"
s2="/var/backups/abutron-five-volatility-prechange-20261107T105218Z/candidate/AdaptiveRiskProofV2.mqh"
s3="/var/backups/abutron-option-c-v2-release-20261105/adaptive-existing-ea-cutover-with-native-v2-proof/AdaptiveRiskProofV2.mqh"
for path in "$s1" "$s2" "$s3"; do
  [[ -f "$path" && ! -L "$path" ]] || {
    echo "EXPECTED_HEADER_MISSING_OR_SYMLINK:$path" >&2
    exit 11
  }
  actual="$(sha256sum "$path" | cut -d' ' -f1)"
  [[ "$actual" == "$expected" ]] || {
    echo "NATIVE_HEADER_HASH_MISMATCH:$path" >&2
    exit 12
  }
done
getent group abutrongha >/dev/null || {
  echo "RUNNER_GROUP_MISSING" >&2
  exit 13
}
folder="/var/lib/abutron-apex11-source-handoff"
dest="$folder/AdaptiveRiskProofV2.mqh"
if [[ -e "$folder" && ( ! -d "$folder" || -L "$folder" ) ]]; then
  echo "HEADER_HANDOFF_FOLDER_UNSAFE" >&2
  exit 14
fi
if [[ -e "$dest" || -L "$dest" ]]; then
  [[ -f "$dest" && ! -L "$dest" ]] || exit 15
  [[ "$(sha256sum "$dest" | cut -d' ' -f1)" == "$expected" ]] || {
    echo "HANDOFF_EXISTS_DIFFERENT_CONTENT_NO_OVERWRITE" >&2
    exit 16
  }
else
  install -d -o root -g abutrongha -m 0750 "$folder"
  install -o root -g abutrongha -m 0640 "$s1" "$dest"
fi
[[ "$(stat -c '%U:%G %a' "$dest")" == "root:abutrongha 640" ]] || exit 17
[[ "$(sha256sum "$dest" | cut -d' ' -f1)" == "$expected" ]] || exit 18
if ! runuser -u abutrongha -- test -r "$dest"; then
  echo "HEADER_HANDOFF_RUNNER_READ_DENIED" >&2
  exit 19
fi
echo "ADAPTIVE_RISK_PROOF_HEADER_VERIFIED"
echo "SHA256=$expected"
echo "DEST=$dest"
echo "ALL_3_ORIGINALS_HASH_MATCH"
echo "NO_MQL5_COMPILATION_NO_MT5_TRADING_CHANGES"
