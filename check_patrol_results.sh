#!/usr/bin/env bash

set -euo pipefail

DB_PATH="${1:-$HOME/ros2_ws/data/patrol/patrol_events.db}"
LIMIT="${2:-10}"
MODE="${3:-final}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "database not found: $DB_PATH" >&2
  exit 1
fi

if [[ "$MODE" == "observations" ]]; then
  sqlite3 -header -column "$DB_PATH" "
SELECT
  patrol_id,
  scan_position,
  detected,
  person_count,
  printf('%.2f', max_confidence) AS max_confidence,
  raw_image_path,
  debug_image_path,
  timestamp_utc
FROM patrol_observations
ORDER BY id DESC
LIMIT $LIMIT;
"
  exit 0
fi

sqlite3 -header -column "$DB_PATH" "
SELECT
  patrol_id,
  final_decision,
  max_person_count,
  printf('%.2f', max_confidence) AS max_confidence,
  occupied_positions,
  finished_at_utc
FROM patrol_final_results
ORDER BY id DESC
LIMIT $LIMIT;
"
