#!/usr/bin/env python3
"""OpenClaw natural-language entry point.

Modes:
  --text TEXT        Natural-language command
  --execute          Execute the mapped local tool
  --json             Emit JSON description of the mapping
  --prompt           Print the skill prompt

Examples:
  ros2 run raspbot_vision openclaw_agent_entry -- --text "去门口巡检一下" --execute
  ros2 run raspbot_vision openclaw_agent_entry -- --text "最近有没有检测到人？" --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from raspbot_vision.openclaw_router import build_skill_prompt, command_preview, detect_intent, script_path_for
else:
    from .openclaw_router import build_skill_prompt, command_preview, detect_intent, script_path_for


def _run_script(path: Path, args: list[str]) -> int:
    if not path.exists():
        print(json.dumps({'error': 'tool_not_found', 'path': str(path)}, ensure_ascii=False), file=sys.stderr)
        return 1
    if not path.is_file():
        print(json.dumps({'error': 'tool_not_a_file', 'path': str(path)}, ensure_ascii=False), file=sys.stderr)
        return 1

    proc = subprocess.run([str(path), *args], check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='OpenClaw natural-language entry point')
    parser.add_argument('--text', '-t', default='', help='Natural-language request')
    parser.add_argument('--execute', action='store_true', help='Execute the mapped tool')
    parser.add_argument('--json', action='store_true', help='Output mapping as JSON')
    parser.add_argument('--prompt', action='store_true', help='Print the skill prompt')
    args = parser.parse_args(argv)

    if args.prompt:
        print(build_skill_prompt())
        return 0

    routed = detect_intent(args.text)
    preview = command_preview(routed)
    preview['input_text'] = routed.input_text
    preview['normalized_text'] = routed.normalized_text

    if args.json or not args.execute:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    script = script_path_for(routed)
    return _run_script(script, routed.script_args)


if __name__ == '__main__':
    raise SystemExit(main())
