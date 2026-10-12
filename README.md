# skill-toggler

Toggle Claude Code skills on and off before a session, grouped into packs.

Every enabled skill puts its description into the skill listing. That listing is capped at about 1% of context, and descriptions past the cap get truncated. `skillpacks` lets you switch whole packs of skills on or off at once, or toggle single skills inside a pack. It shows the token cost of each pack as you go.

Pure Python 3 standard library: no dependencies.

## Install

```bash
git clone https://github.com/zisshh/skill-toggler ~/.claude/tools/skillpacks
ln -sf ~/.claude/tools/skillpacks/skillpacks.py ~/.local/bin/skillpacks
```

## Usage

```bash
skillpacks                     # interactive picker (edits ~/.claude/settings.json)
skillpacks -p                  # picker for this project only (.claude/settings.local.json)
skillpacks list                # packs, state, token cost
skillpacks on|off PACK...      # whole packs
skillpacks on|off -s SKILL...  # single skills
```

Picker keys:

| Key | In the pack list | Inside a pack |
|---|---|---|
| `↑` `↓` (or `j` `k`) | move | move |
| `space` | toggle the whole pack | toggle the skill on/off |
| `enter` | open the pack | — |
| `m` | — | set the skill to slash-command only |
| `esc` | — | back to the pack list |
| `s` | save | save |
| `q` | quit (asks first if you have unsaved changes) | quit |

Restart Claude Code after saving. Toggles apply at session start.

## How it works

- **Loose and bundled skills** (`~/.claude/skills/*`, `~/.claude/commands/*.md`) are toggled through `skillOverrides` in settings. Each skill can be:
  - `on`
  - `user-invocable-only`: hidden from the model's listing, but you can still call it with `/name`
  - `off`
- **Plugins** are toggled through `enabledPlugins`. Claude Code switches plugin skills only with their whole plugin, so a plugin is a pack you can open but whose skills can't be toggled one by one.
- **Packs** are defined in `~/.claude/skillpacks.json`, which is created on first run. Each pack is a list of skill names or glob patterns (`"gortex-*"`). Skills that no pack claims land in `misc`.
- **Saving** writes the settings file atomically and keeps a `.skillpacks.bak` copy of the previous version.
- **Token cost** is estimated as the length of each skill's `description` (capped at 1536 characters) divided by 4.

## License

MIT
