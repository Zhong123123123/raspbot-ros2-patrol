#!/usr/bin/env bash
# ============================================================================
# build.sh — Build the ROS2 workspace and fix ament_python package discovery
#
# Usage:
#   ./build.sh                           # full build
#   ./build.sh --packages-select raspbot_vision  # single package
#
# Why this exists:
#   colcon's ament_python build type does NOT generate local_setup.* files,
#   so packages aren't added to AMENT_PREFIX_PATH. Without this fix, ros2
#   tooling (pkg list, launch, run) can't find raspbot_* packages.
# ============================================================================

set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Source ROS2 environment
if [ ! -f /opt/ros/jazzy/setup.bash ]; then
    echo "ERROR: /opt/ros/jazzy/setup.bash not found. Is ROS2 Jazzy installed?"
    exit 1
fi
set +u
source /opt/ros/jazzy/setup.bash
set -u

# 2. Build
echo "=== colcon build $* ==="
colcon build "$@"

# 3. Fix ament_python package discovery
echo "=== Fixing ament_python package discovery ==="
INSTALL_DIR="$SCRIPT_DIR/install"
PYTHON_SITE="lib/python3.12/site-packages"

for pkg in raspbot_base raspbot_bringup raspbot_vision; do
    share_dir="$INSTALL_DIR/$pkg/share/$pkg"
    if [ ! -d "$share_dir" ]; then
        continue
    fi

    # 3a. Ensure colcon-core package metadata exists
    mkdir -p "$INSTALL_DIR/$pkg/share/colcon-core/packages"
    deps_file="$INSTALL_DIR/$pkg/share/colcon-core/packages/$pkg"
    if [ "$pkg" = "raspbot_base" ]; then
        printf '' > "$deps_file"
    else
        printf 'raspbot_base' > "$deps_file"
    fi

    # 3b. Create local_setup.dsv (processed by colcon's DSV loader)
    cat > "$share_dir/local_setup.dsv" << EOF
prepend-non-duplicate;AMENT_PREFIX_PATH;
prepend-non-duplicate;PYTHONPATH;$PYTHON_SITE
EOF

    # 3c. Create local_setup.sh
    cat > "$share_dir/local_setup.sh" << 'SHELL'
_colcon_prepend_unique_value AMENT_PREFIX_PATH "$COLCON_CURRENT_PREFIX"
_colcon_prepend_unique_value PYTHONPATH "$COLCON_CURRENT_PREFIX/lib/python3.12/site-packages"
SHELL

    # 3d. Copy for other shells
    cp "$share_dir/local_setup.sh" "$share_dir/local_setup.bash"
    cp "$share_dir/local_setup.sh" "$share_dir/local_setup.zsh"

    # 3e. Update package.dsv to reference local_setup files (if not already done)
    dsv_file="$share_dir/package.dsv"
    if [ -f "$dsv_file" ] && ! grep -q "local_setup\." "$dsv_file" 2>/dev/null; then
        cp "$dsv_file" "$dsv_file.bak"
        {
            echo "source;share/$pkg/local_setup.bash"
            echo "source;share/$pkg/local_setup.dsv"
            echo "source;share/$pkg/local_setup.sh"
            echo "source;share/$pkg/local_setup.zsh"
            cat "$dsv_file.bak"
        } > "$dsv_file"
        rm -f "$dsv_file.bak"
        echo "  Patched $pkg/package.dsv ✓"
    fi

    echo "  Fixed $pkg ✓"
done

echo "=== Build complete ==="
echo "Run:  source install/setup.bash  (no more fix_ros_env.sh needed)"
