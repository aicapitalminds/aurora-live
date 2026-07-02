"""Local PC / media control connector for Aurora (Windows).

Safety model: Aurora can only trigger the explicit whitelist below — media keys,
volume nudges, and launching pre-approved apps. No arbitrary commands, paths,
or keystrokes.
"""

from __future__ import annotations

import ctypes
import os
import subprocess

# Apps Aurora may open by voice. Add your own; values are what gets launched.
# Plain names go through os.startfile (also supports URIs like "spotify:").
APP_WHITELIST: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "spotify": "spotify:",
    "obs": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
}

# Windows virtual-key codes for media/volume keys.
_VK = {
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_previous": 0xB1,
    "media_play_pause": 0xB3,
}

VOLUME_STEP_PRESSES = 5  # each press = 2% system volume, so 5 = ~10%

MEDIA_ACTIONS = sorted(_VK)


def _press_key(vk: int, times: int = 1) -> None:
    KEYEVENTF_KEYUP = 0x0002
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def pc_control(action: str, target: str = "") -> dict:
    """Execute a whitelisted PC action. Returns a result dict for the tool response."""
    action = (action or "").strip().lower()
    target = (target or "").strip().lower()

    if os.name != "nt":
        return {"ok": False, "error": "PC control is only available on Windows."}

    if action in _VK:
        presses = VOLUME_STEP_PRESSES if action in ("volume_up", "volume_down") else 1
        _press_key(_VK[action], presses)
        return {"ok": True, "action": action}

    if action == "open_app":
        if target not in APP_WHITELIST:
            return {
                "ok": False,
                "error": f"App {target!r} is not on the whitelist.",
                "allowed_apps": sorted(APP_WHITELIST),
            }
        launch = APP_WHITELIST[target]
        try:
            if launch.endswith(":") or "://" in launch or not launch.lower().endswith(".exe"):
                os.startfile(launch)  # URIs and registered names
            elif os.path.isabs(launch):
                subprocess.Popen([launch], cwd=os.path.dirname(launch))
            else:
                subprocess.Popen([launch])
            return {"ok": True, "action": "open_app", "app": target}
        except Exception as exc:
            return {"ok": False, "error": f"Failed to open {target!r}: {exc}"}

    return {
        "ok": False,
        "error": f"Unknown action {action!r}.",
        "allowed_actions": MEDIA_ACTIONS + ["open_app"],
    }
