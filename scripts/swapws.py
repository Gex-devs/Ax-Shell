#!/usr/bin/env python3
"""
swap_workspaces.py — Swap the contents of two Hyprland workspaces.

Usage:
    python swap_workspaces.py <workspace_a> <workspace_b>

Example:
    python swap_workspaces.py 1 2   # swap workspace 1 and workspace 2

How it works:
    1. Get all window addresses on workspace A and workspace B.
    2. Move A's windows to a temp workspace (9999) so the slot is free.
    3. Move B's windows into workspace A.
    4. Move temp (formerly A's) windows into workspace B.

The temp workspace (9999) is chosen to be safely out of range of any
normal workspace layout. If you use workspace 9999 for something, change
TEMP_WORKSPACE to any other unused number.
"""

import json
import subprocess
import sys


TEMP_WORKSPACE = 9999


def hyprctl(*args: str) -> str:
    result = subprocess.run(
        ["hyprctl", *args],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def get_windows_on_workspace(workspace_id: int) -> list[str]:
    clients = json.loads(hyprctl("clients", "-j"))
    return [
        c["address"]
        for c in clients
        if c["workspace"]["id"] == workspace_id
    ]


def move_window_to_workspace(address: str, workspace_id: int):
    hyprctl(
        "dispatch",
        f'hl.dsp.window.move({{ workspace = {workspace_id}, window = "address:{address}" }})'
    )


def find_safe_temp_workspace() -> int:
    """Find a workspace number that's genuinely empty right now,
    falling back to TEMP_WORKSPACE if none of the candidates are in use."""
    try:
        workspaces = json.loads(hyprctl("workspaces", "-j"))
        used_ids = {w["id"] for w in workspaces}
        if TEMP_WORKSPACE not in used_ids:
            return TEMP_WORKSPACE
        # find first unused id above 9000
        candidate = 9000
        while candidate in used_ids:
            candidate += 1
        return candidate
    except Exception:
        return TEMP_WORKSPACE


def swap_workspaces(ws_a: int, ws_b: int):
    if ws_a == ws_b:
        print(f"[swap_workspaces] workspaces are the same ({ws_a}), nothing to do.")
        return

    temp = find_safe_temp_workspace()
    print(f"[swap_workspaces] swapping workspace {ws_a} <-> {ws_b} (temp={temp})")

    windows_a = get_windows_on_workspace(ws_a)
    windows_b = get_windows_on_workspace(ws_b)

    print(f"[swap_workspaces] ws {ws_a} has {len(windows_a)} window(s): {windows_a}")
    print(f"[swap_workspaces] ws {ws_b} has {len(windows_b)} window(s): {windows_b}")

    if not windows_a and not windows_b:
        print("[swap_workspaces] both workspaces are empty, nothing to swap.")
        return

    # Step 1: A's windows -> temp
    for addr in windows_a:
        move_window_to_workspace(addr, temp)

    # Step 2: B's windows -> A
    for addr in windows_b:
        move_window_to_workspace(addr, ws_a)

    # Step 3: temp (A's original windows) -> B
    for addr in windows_a:
        move_window_to_workspace(addr, ws_b)

    print(f"[swap_workspaces] done.")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        # single argument: swap current workspace with the given one
        try:
            b = int(sys.argv[1])
        except ValueError:
            print(f"Error: workspace number must be an integer")
            sys.exit(1)
        current_json = json.loads(hyprctl("activeworkspace", "-j"))
        a = current_json["id"]
        swap_workspaces(a, b)

    elif len(sys.argv) == 3:
        # two arguments: swap the two named workspaces explicitly
        try:
            a, b = int(sys.argv[1]), int(sys.argv[2])
        except ValueError:
            print(f"Error: workspace numbers must be integers")
            sys.exit(1)
        swap_workspaces(a, b)

    else:
        print(f"Usage: {sys.argv[0]} <workspace_b>  OR  {sys.argv[0]} <workspace_a> <workspace_b>")
        sys.exit(1)