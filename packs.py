"""Pack model: discovers skills/plugins and reads/writes their on/off state."""
import glob
import json
import os
import re

CLAUDE_DIR = os.path.expanduser("~/.claude")
PACKS_FILE = os.path.join(CLAUDE_DIR, "skillpacks.json")
GLOBAL_SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")
MAX_DESC_CHARS = 1536
CHARS_PER_TOKEN = 4

ON, SLASH_ONLY, OFF = "on", "user-invocable-only", "off"
STATE_CYCLE = {ON: SLASH_ONLY, SLASH_ONLY: OFF, OFF: ON}

DEFAULT_PACKS = {
    "mine": ["caption-pop", "linkedin-content", "x-content", "thumbnail-concepts",
             "ziiro-precall-flow", "material-quote", "resume-ats-optimizer",
             "auto-research-engineer", "landing-page-optimizer", "auto-research"],
    "matt-pocock": ["grill-me", "grill-with-docs", "handoff", "setup-matt-pocock-skills",
                    "writing-for-agents", "wayfinder"],
    "addy-osmani": ["context-engineering", "spec-driven-development",
                    "incremental-implementation", "shipping-and-launch",
                    "frontend-ui-engineering"],
    "ecc": ["tdd-workflow", "context-budget", "security-scan", "ecc-*"],
    "design": ["design-taste-*", "gpt-taste", "high-end-visual-design", "minimalist-ui",
               "industrial-brutalist-ui", "redesign-existing-projects", "stitch-design-taste",
               "image-to-code", "imagegen-*", "ui-ux-pro-max", "impeccable", "brandkit",
               "full-output-enforcement", "ian-xiaohei-illustrations"],
    "video": ["hyperframes*", "media-use", "general-video", "remotion-best-practices",
              "watch", "analyze", "visual-media"],
    "cmux": ["cmux*"],
    "gortex": ["gortex-*"],
    "replica": ["replica-*"],
    "built-in": ["dataviz", "artifact-*", "update-config", "keybindings-help", "code-review",
                 "fewer-permission-prompts", "loop", "schedule", "claude-api",
                 "plugin-authoring", "init", "security-review", "simplify", "run"],
}


def _read_json(path, fallback):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _desc_tokens(md_path):
    try:
        with open(md_path, errors="ignore") as f:
            text = f.read(6000)
    except OSError:
        return 0
    m = re.search(r"^description:\s*(.*?)(?=^[\w-]+:|^---)", text, re.S | re.M)
    return min(len(m.group(1)) if m else 0, MAX_DESC_CHARS) // CHARS_PER_TOKEN


def discover_loose():
    """name -> token estimate for ~/.claude/skills and ~/.claude/commands."""
    found = {}
    for p in glob.glob(os.path.join(CLAUDE_DIR, "skills", "*", "SKILL.md")):
        found[p.split(os.sep)[-2]] = _desc_tokens(p)
    for p in glob.glob(os.path.join(CLAUDE_DIR, "commands", "*.md")):
        found[os.path.basename(p)[:-3]] = _desc_tokens(p)
    return found


def discover_plugins():
    """plugin key -> (token estimate, [skill names])."""
    installed = _read_json(os.path.join(CLAUDE_DIR, "plugins", "installed_plugins.json"), {})
    result = {}
    for key, entries in installed.get("plugins", {}).items():
        root = entries[0]["installPath"]
        files = glob.glob(f"{root}/skills/*/SKILL.md") + glob.glob(f"{root}/commands/*.md")
        names = sorted({f.split(os.sep)[-2] if f.endswith("SKILL.md") else os.path.basename(f)[:-3]
                        for f in files})
        result[key] = (sum(_desc_tokens(f) for f in files), names)
    return result


def load_pack_defs():
    if not os.path.exists(PACKS_FILE):
        write_json_atomic(PACKS_FILE, DEFAULT_PACKS)
    return _read_json(PACKS_FILE, DEFAULT_PACKS)


def _matches(name, pattern):
    return re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), name) is not None


def build_packs(settings):
    """Return ordered list of packs: {name, kind, items:[{name, kind, tokens}]}."""
    loose = discover_loose()
    bundled = {k for k in settings.get("skillOverrides", {}) if k not in loose}
    candidates = {**loose, **{b: 0 for b in bundled}}
    defs = load_pack_defs()
    claimed, packs = set(), []
    for pack, patterns in defs.items():
        # Literal names are kept even when not on disk: they may be bundled skills.
        literals = [p for p in patterns if "*" not in p]
        globbed = sorted(n for n in candidates
                         if any(_matches(n, p) for p in patterns if "*" in p))
        names = [n for n in dict.fromkeys(literals + globbed) if n not in claimed]
        claimed.update(names)
        items = [{"name": n, "kind": "skill", "tokens": candidates.get(n, 0)} for n in names]
        if items:
            packs.append({"name": pack, "kind": "skills", "items": items})
    rest = sorted(n for n in loose if n not in claimed)
    if rest:
        packs.append({"name": "misc", "kind": "skills",
                      "items": [{"name": n, "kind": "skill", "tokens": loose[n]} for n in rest]})
    for key, (tokens, names) in sorted(discover_plugins().items()):
        packs.append({"name": key.split("@")[0], "kind": "plugin", "key": key, "tokens": tokens,
                      "items": [{"name": n, "kind": "plugin-skill", "tokens": 0} for n in names]})
    return packs


def skill_state(settings, name):
    return settings.get("skillOverrides", {}).get(name, ON)


def plugin_on(settings, key):
    return bool(settings.get("enabledPlugins", {}).get(key, False))


def with_skill_state(settings, name, state):
    overrides = {k: v for k, v in settings.get("skillOverrides", {}).items() if k != name}
    if state != ON:
        overrides = {**overrides, name: state}
    return {**settings, "skillOverrides": overrides}


def with_plugin(settings, key, enabled):
    return {**settings, "enabledPlugins": {**settings.get("enabledPlugins", {}), key: enabled}}


def pack_status(settings, pack):
    """'on', 'off' or 'some'."""
    if pack["kind"] == "plugin":
        return ON if plugin_on(settings, pack["key"]) else OFF
    states = {skill_state(settings, i["name"]) != OFF for i in pack["items"]}
    return ON if states == {True} else OFF if states == {False} else "some"


def with_pack(settings, pack, enabled):
    if pack["kind"] == "plugin":
        return with_plugin(settings, pack["key"], enabled)
    result = settings
    for item in pack["items"]:
        result = with_skill_state(result, item["name"], ON if enabled else OFF)
    return result


def pack_tokens(settings, pack):
    if pack["kind"] == "plugin":
        return pack["tokens"] if plugin_on(settings, pack["key"]) else 0
    return sum(i["tokens"] for i in pack["items"] if skill_state(settings, i["name"]) == ON)
