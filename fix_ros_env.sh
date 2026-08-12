#!/usr/bin/env bash
set -euo pipefail
WORKSPACE_ROOT="${1:-$HOME/ros2_ws}"
INSTALL_DIR="$WORKSPACE_ROOT/install"
for pkg in raspbot_base raspbot_bringup raspbot_vision; do
  share_dir="$INSTALL_DIR/$pkg/share/$pkg"
  if [ ! -d "$share_dir" ]; then
    continue
  fi
  mkdir -p "$INSTALL_DIR/$pkg/share/colcon-core/packages"
  case "$pkg" in
    raspbot_base)
      printf '' > "$INSTALL_DIR/$pkg/share/colcon-core/packages/$pkg"
      ;;
    raspbot_bringup)
      printf 'raspbot_base' > "$INSTALL_DIR/$pkg/share/colcon-core/packages/$pkg"
      ;;
    raspbot_vision)
      printf 'raspbot_base' > "$INSTALL_DIR/$pkg/share/colcon-core/packages/$pkg"
      ;;
  esac
  cat > "$share_dir/package.dsv" <<PKG
source;share/$pkg/local_setup.bash
source;share/$pkg/local_setup.dsv
source;share/$pkg/local_setup.sh
PKG
  cat > "$share_dir/local_setup.dsv" <<PKG
prepend-non-duplicate;AMENT_PREFIX_PATH;
prepend-non-duplicate;PYTHONPATH;lib/python3.12/site-packages
PKG
  cat > "$share_dir/local_setup.sh" <<'PKG'
_colcon_prepend_unique_value AMENT_PREFIX_PATH "$COLCON_CURRENT_PREFIX"
_colcon_prepend_unique_value PYTHONPATH "$COLCON_CURRENT_PREFIX/lib/python3.12/site-packages"
PKG
  cp "$share_dir/local_setup.sh" "$share_dir/local_setup.bash"
done

VISION_BIN_DIR="$INSTALL_DIR/raspbot_vision/lib/raspbot_vision"
if [ -d "$VISION_BIN_DIR" ]; then
  declare -A vision_entrypoints=(
    [line_follow_node]=raspbot_vision.line_follow_node
    [obstacle_avoid_node]=raspbot_vision.obstacle_avoid_node
    [ultrasonic_range_node]=raspbot_vision.ultrasonic_range_node
    [ir_obstacle_avoid_node]=raspbot_vision.ir_obstacle_avoid_node
    [person_detect_node]=raspbot_vision.person_detect_node
    [patrol_logger_node]=raspbot_vision.patrol_logger_node
    [patrol_scheduler_node]=raspbot_vision.patrol_scheduler_node
    [patrol_behavior_node]=raspbot_vision.patrol_behavior_node
    [compare_person_detectors]=raspbot_vision.compare_person_detectors
  )
  for exe in "${!vision_entrypoints[@]}"; do
    target="$VISION_BIN_DIR/$exe"
    module="${vision_entrypoints[$exe]}"
    if [ -f "$target" ]; then
      cat > "$target" <<PY
#!/usr/bin/python3
import os
import sys

prefix = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
workspace_root = os.path.dirname(os.path.dirname(prefix))
site_packages = os.path.join(prefix, 'lib', 'python3.12', 'site-packages')
build_pkg = os.path.join(workspace_root, 'build', 'raspbot_vision')
for path in (site_packages, build_pkg):
    if path not in sys.path:
        sys.path.insert(0, path)

from $module import main

if __name__ == '__main__':
    sys.exit(main())
PY
      chmod +x "$target"
    fi
  done
fi
