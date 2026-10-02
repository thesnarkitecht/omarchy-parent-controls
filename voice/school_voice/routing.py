from __future__ import annotations

import re
from .policy import catalog


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().strip().rstrip(".!?"))


def candidates(text: str, policy: dict) -> dict[str, str]:
    """Language evidence limits choices; the model cannot invent a target or direction.

    This is an interpretation aid. The independent action allowlist is the permission
    boundary. Unrecognized paraphrases fail closed instead of choosing a random action.
    """
    text = normalize(text)
    if re.search(r"\b(sudo|terminal|shell|command line|install|uninstall|delete|remove|password|parental|permissions|restrictions|ignore|override|bypass|disable|shutdown|reboot)\b", text):
        return {}
    if re.search(r"\b(don't|dont|do not|never|not|and|then)\b|[;\n]", text):
        return {}
    allowed = catalog(policy)
    choices = set()
    # Alias matching is bounded by words, so 'math' cannot match 'aftermath'.
    if re.search(r"\b(open|launch|start|bring|switch|show|go|back|use)\b", text):
        for key, app in policy["apps"].items():
            if any(re.search(r"(?<!\w)" + re.escape(normalize(a)) + r"(?!\w)", text) for a in app["aliases"]):
                focus = bool(re.search(r"\b(switch|back)\b|\bgo to\b", text))
                choices.add(("focus_" if focus else "open_") + key)
    if re.search(r"\b(volume|sound|speakers?|loud|louder|quiet|quieter|mute|unmute)\b", text):
        if re.search(r"\bunmute\b", text):
            choices.add("unmute")
        elif re.search(r"\bmute\b", text):
            choices.add("mute")
        else:
            down = bool(re.search(r"\b(down|lower|decrease|quieter|softer)\b|too loud", text))
            up = bool(re.search(r"\b(up|raise|increase|louder)\b|too quiet", text))
            if down != up:
                choices.add("volume_down" if down else "volume_up")
    if re.search(r"\b(music|video|song|playback)\b", text):
        pause = bool(re.search(r"\b(pause|stop)\b", text))
        play = bool(re.search(r"\b(play|resume|continue)\b", text))
        if pause != play:
            choices.add("media_pause" if pause else "media_play")
    if re.search(r"\b(window|app|application)\b", text):
        if re.search(r"\b(close|quit)\b", text):
            choices.add("close_window")
        elif re.search(r"\b(maximize|bigger|enlarge)\b", text):
            choices.add("maximize")
        elif re.search(r"\b(restore|normal)\b", text):
            choices.add("restore")
    if re.search(r"\b(workspace|desktop)\b", text):
        words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        for n in policy["workspaces"]:
            if re.search(r"\b(?:" + str(n) + "|" + words[n] + r")\b", text):
                choices.add(f"workspace_{n}")
    # Multiple possible actions are ambiguous; don't guess, chain or ask to confirm.
    if not choices and policy.get('parent_controls') and re.search(r"\b(want|like|help|practice|learn|draw|watch|write|calculate|study|read)\b", text):
        return {a: label for a, label in allowed.items() if a.startswith('open_')}
    if len(choices) != 1:
        return {}
    return {a: allowed[a] for a in choices if a in allowed}


def exact_action(text: str, policy: dict) -> str | None:
    """Full utterance matches only. Unrecognized instructions go to Laya."""
    names = {
        "volume up": "volume_up", "turn the volume up": "volume_up", "turn it up": "volume_up",
        "volume down": "volume_down", "turn the volume down": "volume_down", "turn it down": "volume_down",
        "mute": "mute", "mute the sound": "mute", "unmute": "unmute",
        "pause the music": "media_pause", "pause the video": "media_pause",
        "play the music": "media_play", "resume the video": "media_play",
        "close this window": "close_window", "close the window": "close_window",
        "make this bigger": "maximize", "maximize this window": "maximize",
        "restore this window": "restore",
    }
    for key, app in policy["apps"].items():
        for alias in app["aliases"]:
            for prefix in ("open ", "launch ", "start "):
                names[prefix + normalize(alias)] = "open_" + key
            for prefix in ("switch to ", "go to "):
                names[prefix + normalize(alias)] = "focus_" + key
    numbers = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    for n in policy["workspaces"]:
        for value in (str(n), numbers[n]):
            for prefix in ("workspace ", "go to workspace ", "desktop "):
                names[prefix + value] = f"workspace_{n}"
    action = names.get(normalize(text))
    return action if action in catalog(policy) else None
