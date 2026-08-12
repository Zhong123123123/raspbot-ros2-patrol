#!/usr/bin/env bash
# ============================================================================
# generate_route_preview.sh — Generate route YAML draft from description
# ============================================================================
# Purpose: Generate a route YAML draft file for human review.
#          The generated route is NEVER executed automatically.
#          Must be manually reviewed and added to whitelist_routes.
#
# Safety:  Output goes to routes/generated_route_preview.yaml (draft only).
#          Does NOT modify config or whitelist.
#          Does NOT publish any ROS2 commands.
#
# Usage:   ./generate_route_preview.sh "from start to door, then to desk"
#          ./generate_route_preview.sh --name my_route --steps "door,desk"
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTES_DIR="/home/ubuntu/ros2_ws/routes"
mkdir -p "$ROUTES_DIR"

OUTPUT_FILE="$ROUTES_DIR/generated_route_preview.yaml"
ROUTE_NAME="generated_route"
DESCRIPTION=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DESCRIPTION]

Generate a route YAML draft for human review. NEVER auto-executes.

Options:
  --name NAME        Route name (default: generated_route)
  --output FILE      Output YAML path (default: routes/generated_route_preview.yaml)
  --help             Show this help

Example:
  $(basename "$0") --name office_loop "from start to door, scan, then to desk, scan"
  $(basename "$0") "patrol at start, then move forward 1.5s, patrol at waypoint"
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)
            ROUTE_NAME="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            echo "Unknown option: $1"
            usage
            exit 2
            ;;
        *)
            DESCRIPTION="$*"
            break
            ;;
    esac
done

if [ -z "$DESCRIPTION" ]; then
    DESCRIPTION="default patrol route"
fi

# Sanitize route name
ROUTE_NAME=$(echo "$ROUTE_NAME" | sed 's/[^a-zA-Z0-9_-]//g')
if [ -z "$ROUTE_NAME" ]; then
    ROUTE_NAME="generated_route"
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Generate a template YAML from the description
cat > "$OUTPUT_FILE" <<YAML_EOF
# =============================================================================
# ROUTE DRAFT — DO NOT EXECUTE WITHOUT HUMAN REVIEW
# =============================================================================
# Generated: ${TIMESTAMP}
# Description: ${DESCRIPTION}
# Status: DRAFT — needs human review and whitelist addition
#
# To activate:
#   1. Review each step for safety
#   2. Verify durations and speeds
#   3. Add route name to whitelist_routes in config/agent_command_gateway.yaml
#   4. Test with架空轮子 (wheels elevated) first
#   5. Test低速 (low speed) on ground
# =============================================================================

route_name: ${ROUTE_NAME}
description: "${DESCRIPTION}"
generated_at: "${TIMESTAMP}"
status: draft

steps:
YAML_EOF

# Parse description keywords to generate rough steps
# This is a template generator — the actual step details need human review
IFS=',' read -ra KEYWORDS <<< "$DESCRIPTION"
STEP_COUNTER=0

for keyword in "${KEYWORDS[@]}"; do
    keyword=$(echo "$keyword" | xargs)  # trim whitespace
    STEP_COUNTER=$((STEP_COUNTER + 1))

    case "$keyword" in
        *start*|*起点*|*begin*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: start_scan_${STEP_COUNTER}
    action: patrol
    # Scans at starting position with gimbal
YAML_EOF
            ;;
        *door*|*门口*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: move_to_door_${STEP_COUNTER}
    action: move
    linear_x: 0.06
    duration_sec: 1.5
    # WARNING: Verify duration and speed before executing
  - name: door_scan_${STEP_COUNTER}
    action: patrol
    # Scan at door position
YAML_EOF
            ;;
        *desk*|*桌子*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: move_to_desk_${STEP_COUNTER}
    action: move
    linear_x: 0.06
    duration_sec: 1.5
    # WARNING: Verify duration and speed before executing
  - name: desk_scan_${STEP_COUNTER}
    action: patrol
    # Scan at desk position
YAML_EOF
            ;;
        *turn*|*转向*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: turn_${STEP_COUNTER}
    action: turn
    angular_z: 0.30
    duration_sec: 0.9
    # WARNING: Verify angle and duration before executing
YAML_EOF
            ;;
        *wait*|*等待*|*pause*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: wait_${STEP_COUNTER}
    action: wait
    duration_sec: 1.0
YAML_EOF
            ;;
        *scan*|*patrol*|*巡检*|*检查*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: scan_${STEP_COUNTER}
    action: patrol
    # Patrol scan at waypoint
YAML_EOF
            ;;
        *stop*|*停止*)
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: stop_${STEP_COUNTER}
    action: stop
YAML_EOF
            ;;
        *)
            # Generic: add a move + scan for unrecognized keywords
            cat >> "$OUTPUT_FILE" <<YAML_EOF
  - name: waypoint_${STEP_COUNTER}
    action: move
    linear_x: 0.06
    duration_sec: 1.0
    # WARNING: Auto-generated waypoint for: "${keyword}"
    # Review duration and speed before executing
  - name: scan_${STEP_COUNTER}
    action: patrol
YAML_EOF
            ;;
    esac
done

# Always end with stop
cat >> "$OUTPUT_FILE" <<YAML_EOF

  # Final stop — always end routes with stop
  - name: final_stop
    action: stop

# =============================================================================
# IMPORTANT: This is a DRAFT only.
# Add "${ROUTE_NAME}" to whitelist_routes in config/agent_command_gateway.yaml
# AFTER human review and架空测试 (elevated wheel test).
# =============================================================================
YAML_EOF

echo "{\"status\": \"route_draft_generated\", \"route_name\": \"${ROUTE_NAME}\", \"output\": \"${OUTPUT_FILE}\", \"steps\": ${STEP_COUNTER}}"
echo ""
echo "=== Generated Route Draft ==="
cat "$OUTPUT_FILE"
