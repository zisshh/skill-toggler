#!/usr/bin/env python3
"""skillpacks: toggle Claude Code skill packs and the skills inside them.

  skillpacks                 interactive picker (global settings)
  skillpacks -p              interactive picker for this project only (.claude/settings.local.json)
  skillpacks list            show packs, state and token cost
  skillpacks on|off PACK...  enable/disable whole packs
  skillpacks on|off -s SKILL...  enable/disable single skills
Edit pack membership in ~/.claude/skillpacks.json.
"""
import argparse
import curses
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import packs as P  # noqa: E402

MARK = {P.ON: "[x]", P.OFF: "[ ]", "some": "[~]", P.SLASH_ONLY: "[/]"}


def settings_path(project):
    return os.path.join(os.getcwd(), ".claude", "settings.local.json") if project else P.GLOBAL_SETTINGS


def load(path):
    return P._read_json(path, {})


def save(path, settings):
    if os.path.exists(path):
        shutil.copy2(path, f"{path}.skillpacks.bak")
    P.write_json_atomic(path, settings)


def find_pack(packs, name):
    match = next((p for p in packs if p["name"] == name or p.get("key") == name), None)
    if match is None:
        sys.exit(f"unknown pack: {name}  (run `skillpacks list`)")
    return match


def cmd_list(settings, packs):
    total = 0
    for pack in packs:
        tokens = P.pack_tokens(settings, pack)
        total += tokens
        kind = "plugin" if pack["kind"] == "plugin" else f"{len(pack['items'])} skills"
        print(f"{MARK[P.pack_status(settings, pack)]} {pack['name']:<22} {kind:<11} ~{tokens} tok")
    print(f"\nactive skill listing ~{total} tokens (Claude Code caps it at ~1% of context)")


def cmd_toggle(settings, packs, names, enabled, single):
    result = settings
    for name in names:
        if single:
            result = P.with_skill_state(result, name, P.ON if enabled else P.OFF)
        else:
            result = P.with_pack(result, find_pack(packs, name), enabled)
    return result


# ---------- interactive UI ----------

HELP_PACKS = "↑↓ move  space toggle pack  enter open  s save  q quit"
HELP_ITEMS = "↑↓ move  space on/off  m slash-only  esc back  s save  q quit"


def draw(scr, title, rows, cursor, help_line, footer):
    scr.erase()
    height, width = scr.getmaxyx()
    scr.addnstr(0, 0, title, width - 1, curses.A_BOLD)
    view = height - 4
    top = max(0, cursor - view + 1)
    for i, row in enumerate(rows[top:top + view]):
        attr = curses.A_REVERSE if top + i == cursor else curses.A_NORMAL
        scr.addnstr(2 + i, 0, row, width - 1, attr)
    scr.addnstr(height - 1, 0, f"{help_line}   {footer}", width - 1, curses.A_DIM)
    scr.refresh()


def pack_rows(settings, packs):
    return [f"{MARK[P.pack_status(settings, p)]} {p['name']:<22} "
            f"{'plugin' if p['kind'] == 'plugin' else str(len(p['items'])) + ' skills':<11} "
            f"~{P.pack_tokens(settings, p)} tok" for p in packs]


def item_rows(settings, pack):
    if pack["kind"] == "plugin":
        state = P.ON if P.plugin_on(settings, pack["key"]) else P.OFF
        return [f"{MARK[state]} {i['name']}  (plugin skills switch with the whole plugin)"
                for i in pack["items"]] or ["(no skills)"]
    return [f"{MARK[P.skill_state(settings, i['name'])]} {i['name']:<34} ~{i['tokens']} tok"
            for i in pack["items"]]


def run_ui(scr, settings, packs, path):
    curses.curs_set(0)
    state = {"settings": settings, "dirty": False}
    cursor, open_pack, item_cursor = 0, None, 0
    while True:
        s = state["settings"]
        footer = f"{'UNSAVED ' if state['dirty'] else ''}{path}  total ~{sum(P.pack_tokens(s, p) for p in packs)} tok"
        if open_pack is None:
            draw(scr, "skillpacks", pack_rows(s, packs), cursor, HELP_PACKS, footer)
        else:
            draw(scr, f"skillpacks › {open_pack['name']}", item_rows(s, open_pack),
                 item_cursor, HELP_ITEMS, footer)
        key = scr.getch()
        if key == ord("q"):
            if not state["dirty"] or confirm_quit(scr):
                return state
            continue
        if key == ord("s"):
            save(path, state["settings"])
            state = {**state, "dirty": False}
            continue
        if open_pack is None:
            cursor, open_pack, state = handle_pack_key(key, cursor, packs, state)
            item_cursor = 0
        else:
            item_cursor, open_pack, state = handle_item_key(key, item_cursor, open_pack, state)


def confirm_quit(scr):
    height, width = scr.getmaxyx()
    scr.addnstr(height - 1, 0, "Unsaved changes. Quit anyway? (y/n)".ljust(width - 1), width - 1,
                curses.A_BOLD)
    return scr.getch() == ord("y")


def handle_pack_key(key, cursor, packs, state):
    if key in (curses.KEY_UP, ord("k")):
        return max(0, cursor - 1), None, state
    if key in (curses.KEY_DOWN, ord("j")):
        return min(len(packs) - 1, cursor + 1), None, state
    pack = packs[cursor]
    if key == ord(" "):
        enable = P.pack_status(state["settings"], pack) != P.ON
        return cursor, None, {"settings": P.with_pack(state["settings"], pack, enable), "dirty": True}
    if key in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT):
        return cursor, pack, state
    return cursor, None, state


def handle_item_key(key, cursor, pack, state):
    items = pack["items"]
    if key in (27, curses.KEY_LEFT, curses.KEY_BACKSPACE, 127):
        return 0, None, state
    if key in (curses.KEY_UP, ord("k")):
        return max(0, cursor - 1), pack, state
    if key in (curses.KEY_DOWN, ord("j")):
        return min(max(len(items) - 1, 0), cursor + 1), pack, state
    s = state["settings"]
    if pack["kind"] == "plugin":
        if key == ord(" "):
            return cursor, pack, {"settings": P.with_plugin(s, pack["key"], not P.plugin_on(s, pack["key"])),
                                  "dirty": True}
        return cursor, pack, state
    if not items:
        return cursor, pack, state
    name = items[cursor]["name"]
    current = P.skill_state(s, name)
    if key == ord(" "):
        new = P.OFF if current != P.OFF else P.ON
    elif key == ord("m"):
        new = P.ON if current == P.SLASH_ONLY else P.SLASH_ONLY
    else:
        return cursor, pack, state
    return cursor, pack, {"settings": P.with_skill_state(s, name, new), "dirty": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-p", "--project", action="store_true", help="edit ./.claude/settings.local.json")
    parser.add_argument("-s", "--skill", action="store_true", help="names are single skills, not packs")
    parser.add_argument("action", nargs="?", choices=["list", "on", "off"])
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()

    path = settings_path(args.project)
    settings = load(path)
    if args.project:
        # Seed the project file with the global toggles so it pins a full, visible state.
        glob_s = load(P.GLOBAL_SETTINGS)
        settings = {**settings, **{k: {**glob_s.get(k, {}), **settings.get(k, {})}
                                   for k in ("enabledPlugins", "skillOverrides")}}
    view = settings
    packs = P.build_packs(view)

    if args.action == "list":
        return cmd_list(view, packs)
    if args.action in ("on", "off"):
        if not args.names:
            sys.exit("give at least one pack or skill name")
        save(path, cmd_toggle(settings, packs, args.names, args.action == "on", args.skill))
        return print(f"saved {path} — restart Claude Code to apply")
    os.environ.setdefault("ESCDELAY", "25")
    result = curses.wrapper(run_ui, settings, packs, path)
    if result is not None:
        print("done — restart Claude Code (or start a new session) to apply")


if __name__ == "__main__":
    main()
