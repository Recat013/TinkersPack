# TinkersPack

A datapack that raises base modifier slot counts (abilities / defense /
upgrades / souls) and tweaks base stats on tinkerable items across the Tinkers'
Construct mods in the `1.20.1 Modpack` CurseForge instance.

Target: **Minecraft 1.20.1 / Forge**, pack format 15.

| Mod | Namespace | Items |
| --- | --- | --- |
| Tinkers' Construct 3.11.2.166 | `tconstruct` | 44 |
| Tinkers' Things 1.3.3 | `tinkers_things` | 15 |
| Tinkers' Katanas 1.4.5 | `tinkers_katanas` | 2 |
| tcompat 2.0.3 (glaive) | `tcompat` | 1 |
| Tinkers' Jewelry Ex 1.0.3 | `tinkers_jewelry_ex` | 5 |
| Tinkers' Jewelry 1.2.0 | `tinkersjewelry` | 1 |

68 items total. These are every mod in the instance that ships tool definitions;
`TinkerBetterCombat` and `twilight_construct` add none.

## Using it

1. Edit `slot_deltas.txt` (slot counts) and/or `stat_overrides.txt` (everything
   else). Each item is listed with its current values in a trailing comment.
2. Run `python build_pack.py --install`. It prints `before -> after` for
   everything it writes, then mirrors the pack into the game.
3. In game, `/reload`. Tinkers' re-reads tool definitions on reload and syncs
   them to clients, so you can iterate on numbers without restarting.

### About `--install`

Two things get installed:

```
<instance>/moonlight-global-datapacks/TinkersPack/   the datapack
<instance>/resourcepacks/TinkersPack/                the paired resource pack
```

Moonlight's global datapack folder applies to every world with no per-world
setup. The resource pack carries modifier names and descriptions — those are
lang keys under `assets/`, which a datapack cannot supply — so it has to be
enabled once under **Options > Resource Packs**.

`--install` **deletes the installed folder before copying**, and that matters.
When you set an item's deltas back to 0 it stops being written, but a plain
drag-and-drop copy would leave the old file sitting in the game folder, still
overriding the mod. Wiping first is the only way to make a removal actually take
effect. The path is `INSTALL_DIR` at the top of `build_pack.py`; change it if the
instance moves, or drop `--install` and copy `TinkersPack/` wherever you like —
`saves/<world>/datapacks/` also works, per world.

## Putting it on a server

The two halves go to different places, and only one of them is the server's job.

**The datapack is server-side only.** TConstruct syncs tool definitions
(`UpdateToolDefinitionDataPacket`) and modifiers (`UpdateModifiersPacket`, fired
from `OnDatapackSyncEvent`) to every client on join and on `/reload`, and recipes
sync through vanilla. Players do not need the datapack installed, and a client
that has it will be overridden by whatever the server sends.

**The resource pack is client-side only.** `assets/` never travels over the
network, so without it players see the raw key `modifier.tinkerspack.mending` in
white instead of a green "Mending".

Run `python build_pack.py --dist` to get both as zips in `dist/`, along with the
SHA-1 of each (the resource-pack one is needed if you serve it from a URL).

### Datapack, on the server

Same two choices as the client, so pick whichever matches how the server is set
up, unzip into it, and run `/reload`:

```
<server>/moonlight-global-datapacks/TinkersPack/    every world, needs Moonlight Lib
<server>/<level-name>/datapacks/TinkersPack/        one world; check /datapack list
```

`<level-name>` comes from `server.properties` and is usually `world`. Either way
the server needs the same mod versions as the client - the generated definitions
are copies of specific mod files.

### Resource pack, to players

Served from a GitHub release, so every player gets it automatically on join.

Set `RELEASE_URL` near the top of `build_pack.py` to your repo once. It uses the
`/releases/latest/download/` form, which always resolves to the newest release -
so **the URL never changes**, and publishing a new release is enough to push an
update. Only the SHA-1 moves, and `--dist` prints the replacement line and
writes the whole block to `dist/server.properties.txt`.

**The repo has to be public.** Release assets on a private repo need an
authenticated request, and the Minecraft client sends none.

Per release:

1. `python build_pack.py --dist`
2. Upload `dist/TinkersPack-resources.zip` as an asset on a new GitHub release
3. Paste the two changed lines from `dist/server.properties.txt` into the
   server's `server.properties`
4. Restart the server, or `/reload` won't pick it up - resource-pack settings
   are read at startup

The SHA-1 must match the file actually being served, or clients re-download on
every join. It only changes when the resource pack's contents do, so rebuilding
without touching `resourcepack/` leaves it alone.

Note there is only one server-resource-pack slot. This one is free, but if the
modpack ever claims it, that route is gone and players install manually.

None of this blocks the datapack: without the resource pack, modifiers still
work, their names just render as raw translation keys.

## How this works

Tinkers' Construct builds each tinkerable item from a JSON "tool definition" at
`data/<namespace>/tinkering/tool_definitions/<item>.json`. The interesting
modules are:

```json
{ "type": "tconstruct:modifier_slots", "slots": { "abilities": 1, "upgrades": 3 } }
{ "type": "tconstruct:base_stats",     "stats":  { "tconstruct:attack_damage": 1.0 } }
{ "type": "tconstruct:multiply_stats", "multipliers": { "tconstruct:durability": 1.15 } }
```

These are loaded by a plain `SimpleJsonResourceReloadListener`, which means
**whole-file replacement** — the highest-priority datapack providing a given
path wins outright, and there is no per-field merging the way vanilla tags get
merged. So a datapack that wants to bump one number has to ship the entire
definition file.

That's what `build_pack.py` does: it reads the stock definition out of the
extracted mod folder, applies your changes to the relevant module, and writes
the complete file back out. Nothing else is touched — the build is checked so
that every other module comes through byte-identical and in the same order.

## Custom modifiers

`custom/` holds hand-written datapack files that are copied over the generated
output verbatim, and `resourcepack/` holds the matching lang entries and colors.

**Both are build inputs, not part of the shipped pack.** `build_pack.py` wipes
and regenerates `TinkersPack/` on every run, so anything dropped straight into
the output is lost on the next build - put it in `custom/` instead. Deleting
either folder is checked for and refused before anything else happens, because
building without them would silently produce a pack missing every custom
modifier, and the following `--install` would then wipe the last surviving copy
out of the game.

TConstruct's modifiers are fully data-driven — all 222 of its own are plain JSON
with no Java loader behind them — so a datapack can add new ones. Each needs
three or four pieces:

| File | Purpose |
| --- | --- |
| `tinkering/modifiers/<name>.json` | what the modifier does, as a list of modules |
| `recipes/tools/modifiers/<slot>/<name>.json` | how it's applied, and its slot cost |
| `tinkering/tags/modifiers/<slot>/general.json` | sorts it into the station's category list |
| `assets/<ns>/lang/en_us.json` | display name, flavour text, description |
| `assets/<ns>/mantle/colors.json` | the color its name is drawn in |

There are 105 distinct module types available (`stat_boost`, `attribute`,
`protection`, `mob_effect`, `constant_enchantment`, `modifier_slot`, and so on).
Anything expressible as a composition of those needs no mod.

### Mending

A one-tier ability that repairs the tool from experience you pick up, ported
back from older Tinkers'. It works by handing the tool a constant
`minecraft:mending` enchantment:

```json
{ "type": "tconstruct:constant_enchantment", "level": 1, "name": "minecraft:mending" }
```

`ModifiableItem` overrides Forge's `getEnchantmentLevel` / `getAllEnchantments`
and `getDamage` / `setDamage`, so vanilla's experience-orb repair sees the
enchantment and routes the repair through Tinkers' own durability handling.

Its name is drawn in XP-orb green via Mantle's color system. `ResourceColorManager`
collects `mantle/colors.json` from every namespace in every loaded resource pack,
flattens nested keys with dots, and hands the value to vanilla's
`TextColor.parseColor` - so a `#RRGGBB` hex works directly:

```json
{ "modifier.tinkerspack": { "mending": "#70E838" } }
```

The key that comes out of that is `modifier.tinkerspack.mending`, matching the
lang key. Without an entry a modifier falls back to white.

Costs 1 ability slot, applies to anything in `tconstruct:modifiable/durability`
(all three addon mods contribute to that tag, so katanas, glaives and Tinkers'
Things gear are all covered). Recipe, on the Tinker's Anvil: 1 golden apple,
2 dragon's breath, 2 blocks of diamond.

## Config files

### `slot_deltas.txt`

Four columns of **deltas** — how much to add to the item's current counts:

```
tconstruct:pickaxe                   1   0   1   0     # abilities 1, upgrades 3
#                                   ab  def  up  souls
```

Deltas may be negative but can't take a count below 0. Adding to a slot type an
item doesn't have creates it; so does adding to an item with no slots at all.

Slot types are `abilities`, `defense`, `upgrades`, `souls`. The first three are
what these mods hand out; `souls` is valid but nothing here starts with any.

### `stat_overrides.txt`

Four columns setting a stat **outright** (not a delta — that's how stats read
in-game):

```
tinkers_katanas:katana    base_stats    tconstruct:attack_damage    0.8
```

`<module>` is `base_stats` (flat values) or `multiply_stats` (multipliers, where
1.0 is no change). Unknown stat names are rejected with the valid list. An item
listed here gets a file written even if its slot deltas are all 0.

## What's currently applied

Newer Tinkers' spends an upgrade slot per tier of most effects, so upgrade and
defense bumps are +2 rather than +1. Abilities stay at +1.

- **Tinkers' Construct** — weapons and tools +1 ability / +2 upgrades;
  Traveler's armor +1 ability / +2 upgrades; Plate armor +1 ability /
  +2 defense; Slime armor +1 ability only (it already has 5 upgrades).
- **Tinkers' Things** — Laminar armor +1 ability / +3 defense (it has no defense
  slots by default, so this creates them); Halberd +1 ability / +2 defense /
  +2 upgrades; other weapons and tools +1 ability / +2 upgrades.
- **Tinkers' Katanas** — both items +1 ability / +2 upgrades; katana base stats
  dropped to 0.8 attack damage and 1.4 attack speed (from 1.0 / 1.8).
- **tcompat** — glaive +1 ability / +2 upgrades, following the weapon pattern.

Deliberately left alone: arrows, shuriken, throwing axes, all four TConstruct
staves, the melting pan, flint and brick, the Tinkers' Things sack / amethyst
staff / chisel, Makeshift armor, and all six jewelry items. They're all still
listed in `slot_deltas.txt` at 0 so the knob is there when you want it.

## When a mod updates

The generated files are frozen copies of the mod's own definitions, so if an
update rebalances a tool — new trait, different stats, different base slots —
your override will silently keep serving the old version.

To resync: replace the extracted mod folder with the new one, update its path in
`SOURCES` in `build_pack.py`, and re-run. Slot deltas are relative so they carry
over onto the new baselines; stat overrides are absolute, so check those. The
`before -> after` output is the quickest way to spot a base value that shifted
underneath you.

## Files

- `slot_deltas.txt` — modifier slot deltas. One line per item, four numbers.
- `stat_overrides.txt` — base stat values. One line per stat.
- `build_pack.py` — reads both configs, writes the datapack, and with
  `--install` mirrors it into the game. No dependencies.
- `custom/` — hand-written datapack files, copied over the generated output.
- `resourcepack/` — lang entries for custom modifiers; installed alongside.
- `TinkersPack/` — generated output. Safe to delete; rebuilt from scratch each run.
- `*-<version>/` — extracted mod jars, used as the source of stock definitions.
