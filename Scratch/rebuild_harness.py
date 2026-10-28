"""Rebuild the Stage E harness from the session transcript.

The scratch directory under %LOCALAPPDATA%\\Temp was cleared by the OS, taking
h.py, fixtures.py, hardening_a.py and hardening_b.py with it. Every one of them
was authored through Write/Edit tool calls recorded in the session jsonl, so the
files can be replayed: a Write replaces the whole body, an Edit applies one
literal replacement in order.
"""

import json
import sys
from pathlib import Path

TRANSCRIPT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
MARKER = "poa_stageE_be026"


def iter_records(path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except ValueError:
                continue


def walk_tool_uses(node):
    """Yield (name, input) for every tool_use block anywhere in a record."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and "name" in node:
            yield node.get("name"), node.get("input") or {}
        for value in node.values():
            yield from walk_tool_uses(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_tool_uses(value)


def main():
    files = {}
    calls = []
    for line_number, record in iter_records(TRANSCRIPT):
        for name, tool_input in walk_tool_uses(record):
            file_path = str(tool_input.get("file_path") or "")
            if MARKER not in file_path or name not in ("Write", "Edit", "NotebookEdit"):
                continue
            calls.append((line_number, name, file_path, tool_input))

    bodies = {}
    for line_number, name, file_path, tool_input in calls:
        key = Path(file_path).name
        if name == "Write":
            bodies[key] = tool_input.get("content") or ""
        elif name == "Edit":
            old = tool_input.get("old_string") or ""
            new = tool_input.get("new_string") or ""
            body = bodies.get(key)
            if body is None:
                print(f"  ! edit at line {line_number} for {key} has no base body")
                continue
            if old not in body:
                print(f"  ! edit at line {line_number} for {key} does not match")
                continue
            if tool_input.get("allow_multiple"):
                bodies[key] = body.replace(old, new)
            else:
                bodies[key] = body.replace(old, new, 1)
        files[key] = None

    OUT.mkdir(parents=True, exist_ok=True)
    for key, body in sorted(bodies.items()):
        destination = OUT / key
        destination.write_text(body, encoding="utf-8", newline="\n")
        print(f"restored {destination} ({len(body)} chars)")
    print(f"tool calls replayed: {len(calls)}")
    print(f"files rebuilt: {len(bodies)}")


if __name__ == "__main__":
    main()
