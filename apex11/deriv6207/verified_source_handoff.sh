#!/usr/bin/env bash
# ABUTRON 6207 source-only handoff to least-privilege read-only runner.
# This file never compiles, deploys, restarts MT5, or places broker orders.
set -Eeuo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "ROOT_SOURCE_HANDOFF_REQUIRED" >&2
  exit 10
fi
src="/var/backups/abutron-five-volatility-prechange-20261107T105218Z/adaptive_bridge.mq5"
expected="dfc436a42d5210e93f51652e1ac95c65820a3b906cf2629808f9c93850998bc3"
destdir="/var/lib/abutron-apex11-source-handoff"
dest="$destdir/adaptive_bridge.mq5"
if [[ ! -f "$src" || -L "$src" ]]; then
  echo "SOURCE_MISSING_OR_SYMLINKED" >&2
  exit 11
fi
actual="$(sha256sum "$src" | awk '{print $1}')"
if [[ "$actual" != "$expected" ]]; then
  echo "SOURCE_SHA_CHANGED_REFUSE" >&2
  exit 12
fi
if ! getent group abutrongha >/dev/null; then
  echo "RUNNER_GROUP_NOT_FOUND" >&2
  exit 13
fi
if [[ -e "$destdir" && ( ! -d "$destdir" || -L "$destdir" ) ]]; then
  echo "HANDOFF_PATH_UNSAFE" >&2
  exit 14
fi
if [[ -e "$dest" || -L "$dest" ]]; then
  echo "HANDOFF_DESTINATION_EXISTS_REFUSE_REPLACE" >&2
  exit 15
fi
install -d -o root -g abutrongha -m 0750 "$destdir"
install -o root -g abutrongha -m 0640 "$src" "$dest"
chmod 0750 "$destdir"
chmod 0640 "$dest"
if ! cmp -s "$src" "$dest" || [[ "$(sha256sum "$dest" | awk '{print $1}')" != "$expected" ]]; then
  rm -f "$dest"
  echo "HANDOFF_POSTCOPY_HASH_FAILED" >&2
  exit 16
fi
if runuser -u abutrongha -- test -r "$dest"; then
  echo "SOURCE_HANDOFF_VERIFIED_READONLY"
  echo "SHA256=$expected"
  echo "PATH=$dest"
  echo "NO_SERVICE_CHANGES_NO_EA_REPLACEMENT_NO_BROKER_ORDERS"
else
  rm -f "$dest"
  echo "RUNNER_CANNOT_READ_COPY" >&2
  exit 17
fi
