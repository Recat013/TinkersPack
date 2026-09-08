#!/usr/bin/env python
"""
Builds the TinkersPack datapack from slot_deltas.txt and stat_overrides.txt.

Reads the stock tool definitions out of the extracted mod jars, applies the
per-item slot deltas and stat overrides, and writes the modified definitions
into ./TinkersPack.

Usage:  python build_pack.py             build into ./TinkersPack
        python build_pack.py --install   build, then mirror it into the game
        python build_pack.py --dist      build, then zip both halves into ./dist
"""
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SLOT_CONFIG = os.path.join(HERE, "slot_deltas.txt")
STAT_CONFIG = os.path.join(HERE, "stat_overrides.txt")
OUTPUT = os.path.join(HERE, "TinkersPack")

# hand-written datapack files (custom modifiers, their recipes and tags), copied
# over the generated output as-is
CUSTOM = os.path.join(HERE, "custom")

# the paired resource pack, which carries the lang keys for custom modifiers.
# Names and descriptions live in assets/, so a datapack alone cannot supply them.
RESOURCES = os.path.join(HERE, "resourcepack")

PACK_FORMAT = 15  # Minecraft 1.20.1
PACK_DESCRIPTION = "Extra modifier slots for the Tinkers' Construct mods"

# --install targets. The datapack goes in Moonlight's global folder so it applies
# to every world; the resource pack has to be enabled by hand in Options > Resource Packs.
INSTANCE = os.path.join(
    os.path.expanduser("~"), "curseforge", "minecraft", "Instances", "1.20.1 Modpack",
)
INSTALL_DIR = os.path.join(INSTANCE, "moonlight-global-datapacks", "TinkersPack")
RESOURCES_INSTALL_DIR = os.path.join(INSTANCE, "resourcepacks", "TinkersPack")

# Where the server serves the resource pack from. The /releases/latest/download/
# form always resolves to the newest release, so this URL never has to change --
# publish a new release and it picks it up. Only the sha1 below it moves, and
# --dist prints the replacement.
RELEASE_URL = ("https://github.com/USER/REPO/releases/latest/download/"
               "TinkersPack-resources.zip")
RESOURCE_PACK_PROMPT = "Modifier names and colors for the Tinkers' pack"

# namespace -> folder holding that namespace's stock tool definitions
SOURCES = {
    "tconstruct":         "TConstruct-1.20.1-3.11.2.166/data/tconstruct/tinkering/tool_definitions",
    "tinkers_things":     "Tinker-Things-1.20.1-1.3.3/data/tinkers_things/tinkering/tool_definitions",
    "tinkers_katanas":    "TinkersKatanas-1.20.1-1.4.5/data/tinkers_katanas/tinkering/tool_definitions",
    "tcompat":            "tcompat-1.20.1-2.0.3/data/tcompat/tinkering/tool_definitions",
    "tinkersjewelry":     "tinkersjewelry-1.2.0/data/tinkersjewelry/tinkering/tool_definitions",
    "tinkers_jewelry_ex": "tinkers_jewelry_ex-1.0.3/data/tinkers_jewelry_ex/tinkering/tool_definitions",
}

SLOT_MODULE = "tconstruct:modifier_slots"
SLOT_COLUMNS = ["abilities", "defense", "upgrades", "souls"]

# stat module name in the config -> (json module type, key holding the stat map)
STAT_MODULES = {
    "base_stats":     ("tconstruct:base_stats", "stats"),
    "multiply_stats": ("tconstruct:multiply_stats", "multipliers"),
}

# slimeknights.tconstruct.library.tools.stat.ToolStats
KNOWN_STATS = {
    "tconstruct:durability", "tconstruct:use_item_speed", "tconstruct:attack_damage",
    "tconstruct:attack_speed", "tconstruct:mining_speed", "tconstruct:harvest_tier",
    "tconstruct:armor", "tconstruct:armor_toughness", "tconstruct:knockback_resistance",
    "tconstruct:block_amount", "tconstruct:block_angle", "tconstruct:draw_speed",
    "tconstruct:velocity", "tconstruct:accuracy", "tconstruct:projectile_damage",
    "tconstruct:water_inertia", "tconstruct:sea_luck", "tconstruct:lure",
}
STRING_STATS = {"tconstruct:harvest_tier"}

# where to insert a module the item doesn't have yet, matching how the mods order theirs
STATS_MODULES = {
    "tconstruct:part_stats",
    "tconstruct:default_materials",
    "tconstruct:base_stats",
    "tconstruct:multiply_stats",
}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def config_lines(path):
    """Yield (lineno, columns, raw) for each meaningful line, or fail if missing."""
    if not os.path.exists(path):
        fail(path + " not found")
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.split("#", 1)[0].strip()
            if line:
                yield lineno, line.split(), raw.strip()


def check_item(path, lineno, item):
    if ":" not in item:
        fail(f"{path}:{lineno}: '{item}' needs a namespace, e.g. tconstruct:{item}")
    namespace = item.split(":", 1)[0]
    if namespace not in SOURCES:
        known = ", ".join(sorted(SOURCES))
        fail(f"{path}:{lineno}: unknown namespace '{namespace}' (expected one of {known})")


def read_slot_deltas():
    """Parse slot_deltas.txt into [(item, {slot: delta}), ...] in config order."""
    entries = []
    seen = set()
    for lineno, parts, raw in config_lines(SLOT_CONFIG):
        if len(parts) != 5:
            fail(f"{SLOT_CONFIG}:{lineno}: expected an item plus 4 numbers, "
                 f"got {len(parts)} columns:\n  {raw}")
        item = parts[0]
        check_item(SLOT_CONFIG, lineno, item)
        if item in seen:
            fail(f"{SLOT_CONFIG}:{lineno}: '{item}' is listed more than once")
        seen.add(item)
        try:
            values = [int(p) for p in parts[1:]]
        except ValueError:
            fail(f"{SLOT_CONFIG}:{lineno}: slot deltas must be whole numbers:\n  {raw}")
        entries.append((item, dict(zip(SLOT_COLUMNS, values))))
    return entries


def read_stat_overrides():
    """Parse stat_overrides.txt into {item: {module: {stat: value}}}."""
    overrides = {}
    seen = set()
    for lineno, parts, raw in config_lines(STAT_CONFIG):
        if len(parts) != 4:
            fail(f"{STAT_CONFIG}:{lineno}: expected <item> <module> <stat> <value>, "
                 f"got {len(parts)} columns:\n  {raw}")
        item, module, stat, value = parts
        check_item(STAT_CONFIG, lineno, item)
        if module not in STAT_MODULES:
            fail(f"{STAT_CONFIG}:{lineno}: unknown module '{module}' "
                 f"(expected base_stats or multiply_stats)")
        if stat not in KNOWN_STATS:
            fail(f"{STAT_CONFIG}:{lineno}: unknown stat '{stat}'. Valid stats are:\n  "
                 + "\n  ".join(sorted(KNOWN_STATS)))
        if (item, module, stat) in seen:
            fail(f"{STAT_CONFIG}:{lineno}: {item} {module} {stat} is set more than once")
        seen.add((item, module, stat))
        if stat not in STRING_STATS:
            try:
                value = float(value)
            except ValueError:
                fail(f"{STAT_CONFIG}:{lineno}: '{stat}' takes a number, got '{value}'")
        overrides.setdefault(item, {}).setdefault(module, {})[stat] = value
    return overrides


def load_definition(item):
    namespace, name = item.split(":", 1)
    path = os.path.join(HERE, SOURCES[namespace], name + ".json")
    if not os.path.exists(path):
        fail(f"no stock definition for '{item}' at {path}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def find_or_create(modules, module_type, payload_key):
    """Return the named module, inserting an empty one where the mods put it."""
    module = None
    for existing in modules:
        if existing.get("type") == module_type:
            module = existing
            break
    if module is None:
        insert_at = 0
        for index, existing in enumerate(modules):
            if existing.get("type") in STATS_MODULES:
                insert_at = index + 1
        module = {"type": module_type, payload_key: {}}
        modules.insert(insert_at, module)
    module.setdefault(payload_key, {})
    return module


def apply_slot_deltas(item, modules, deltas):
    """Bump the modifier_slots module in place. Returns (before, after)."""
    module = find_or_create(modules, SLOT_MODULE, "slots")
    before = dict(module["slots"])

    after = {}
    for slot in SLOT_COLUMNS:
        total = before.get(slot, 0) + deltas.get(slot, 0)
        if total < 0:
            fail(f"{item}: {slot} would end up at {total}; "
                 f"the base value is {before.get(slot, 0)}")
        if total > 0:
            after[slot] = total
    # preserve any slot type we don't manage, in case a future version adds one
    for slot, value in before.items():
        if slot not in SLOT_COLUMNS:
            after[slot] = value

    module["slots"] = after
    return before, after


def apply_stat_overrides(modules, overrides):
    """Set stats outright. Returns [(module, stat, old, new), ...]."""
    changes = []
    for module_name, stats in overrides.items():
        module_type, payload_key = STAT_MODULES[module_name]
        module = find_or_create(modules, module_type, payload_key)
        for stat, value in stats.items():
            old = module[payload_key].get(stat)
            module[payload_key][stat] = value
            changes.append((module_name, stat, old, value))
    return changes


def describe(slots):
    if not slots:
        return "none"
    ordered = [s for s in SLOT_COLUMNS if s in slots]
    ordered += [s for s in slots if s not in SLOT_COLUMNS]
    return ", ".join(f"{s} {slots[s]}" for s in ordered)


def check_inputs():
    """Refuse to build if a source folder is missing.

    custom/ and resourcepack/ are build INPUTS, not part of the shipped pack.
    If one goes missing the build would quietly produce a pack without the
    custom modifiers, and a following --install would then wipe the last
    surviving copy out of the game. So stop before anything is deleted.
    """
    for folder, holds in ((CUSTOM, "the hand-written modifier, recipe and tag files"),
                          (RESOURCES, "the modifier names, descriptions and colors")):
        if not os.path.isdir(folder):
            fail(f"{folder} is missing.\n"
                 f"It holds {holds}, so building without it would silently drop them.\n"
                 f"Restore it. A previously installed copy under\n"
                 f"  {INSTANCE}\n"
                 f"is a good source, or create an empty folder there if you really\n"
                 f"have no such files.")


def copy_custom():
    """Copy the hand-written datapack files over the generated output.

    Checked by check_inputs() before anything is deleted.
    """
    copied = []
    for root, _, files in os.walk(CUSTOM):
        for name in files:
            source = os.path.join(root, name)
            relative = os.path.relpath(source, CUSTOM)
            target = os.path.join(OUTPUT, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            copied.append(relative.replace(os.sep, "/"))
    return sorted(copied)


def count_files(folder):
    return sum(len(files) for _, _, files in os.walk(folder))


def mirror(source, target, label):
    """Replace target with source outright, and say what changed.

    A plain copy would leave behind files you have since removed from the build,
    and those stale files keep overriding the mod. Wiping first is the point.
    """
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        fail(f"install folder not found: {parent}\n"
             f"Edit INSTANCE in {os.path.basename(__file__)} if the instance moved.")

    stale = count_files(target) if os.path.isdir(target) else 0
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(source, target)
    print(f"  {label}: {stale} file(s) -> {count_files(target)}  {target}")


def dist():
    """Zip both halves for transfer to another machine.

    Minecraft wants pack.mcmeta at the root of the archive, which is what
    make_archive gives us when the source folder is the archive root.
    """
    out = os.path.join(HERE, "dist")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    print(f"Wrote {out}")
    hashes = {}
    for source, name, note in (
        (OUTPUT, "TinkersPack-datapack", "server only; clients receive it over the network"),
        (RESOURCES, "TinkersPack-resources", "upload to the GitHub release"),
    ):
        archive = shutil.make_archive(os.path.join(out, name), "zip", source)
        size = os.path.getsize(archive)
        sha1 = hashlib.sha1(open(archive, "rb").read()).hexdigest()
        hashes[name] = sha1
        print(f"  {os.path.basename(archive):<28} {size:>8,} bytes   {note}")
        print(f"  {'':<28} sha1 {sha1}")

    # the two lines that change per release, ready to paste
    snippet = (
        f"resource-pack={RELEASE_URL}\n"
        f"resource-pack-sha1={hashes['TinkersPack-resources']}\n"
        f"resource-pack-prompt={RESOURCE_PACK_PROMPT}\n"
        f"require-resource-pack=false\n"
    )
    path = os.path.join(out, "server.properties.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(snippet)

    print()
    print("server.properties (also written to dist/server.properties.txt):")
    for line in snippet.rstrip("\n").split("\n"):
        print(f"  {line}")
    if "USER/REPO" in RELEASE_URL:
        print()
        print("  ^ set RELEASE_URL near the top of this script to your actual repo.")


def install():
    print(f"Installed to {INSTANCE}")
    mirror(OUTPUT, INSTALL_DIR, "datapack  ")
    if os.path.isdir(RESOURCES):
        mirror(RESOURCES, RESOURCES_INSTALL_DIR, "resources ")
    print()
    print("  /reload in game picks up the datapack.")
    print("  The resource pack carries modifier names; enable 'TinkersPack' under")
    print("  Options > Resource Packs if it isn't already (only needed once).")


def main():
    if set(sys.argv[1:]) - {"--install", "--dist"}:
        fail(f"usage: python {os.path.basename(__file__)} [--install] [--dist]")

    check_inputs()
    slot_entries = read_slot_deltas()
    stat_overrides = read_stat_overrides()

    known = set(item for item, _ in slot_entries)
    for item in stat_overrides:
        if item not in known:
            fail(f"{STAT_CONFIG}: '{item}' is not listed in slot_deltas.txt")

    todo = [(item, deltas) for item, deltas in slot_entries
            if any(deltas.values()) or item in stat_overrides]

    if os.path.isdir(OUTPUT):
        shutil.rmtree(OUTPUT)
    os.makedirs(OUTPUT)

    meta = {"pack": {"pack_format": PACK_FORMAT, "description": PACK_DESCRIPTION}}
    with open(os.path.join(OUTPUT, "pack.mcmeta"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2)
        handle.write("\n")

    for item, deltas in todo:
        namespace, name = item.split(":", 1)
        definition = load_definition(item)
        modules = definition.get("modules")
        if not isinstance(modules, list):
            fail(item + ": definition has no 'modules' list")

        before, after = apply_slot_deltas(item, modules, deltas)
        stat_changes = apply_stat_overrides(modules, stat_overrides.get(item, {}))

        folder = os.path.join(OUTPUT, "data", namespace, "tinkering", "tool_definitions")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name + ".json"), "w",
                  encoding="utf-8", newline="\n") as handle:
            json.dump(definition, handle, indent=2)
            handle.write("\n")

        if any(deltas.values()):
            print(f"  {item:<36} {describe(before)}  ->  {describe(after)}")
        else:
            print(f"  {item:<36} slots unchanged ({describe(before)})")
        for module_name, stat, old, new in stat_changes:
            shown = "unset" if old is None else old
            label = stat.split(":", 1)[1]
            print(f"  {'':<36}   {module_name} {label}: {shown} -> {new}")

    custom = copy_custom()
    for relative in custom:
        print(f"  custom: {relative}")

    print()
    if todo:
        print(f"Wrote {len(todo)} of {len(slot_entries)} tool definitions"
              f"{f' plus {len(custom)} custom file(s)' if custom else ''} to {OUTPUT}")
    else:
        print(f"No slot or stat changes; wrote {len(custom)} custom file(s) to {OUTPUT}")

    if "--install" in sys.argv[1:]:
        print()
        install()

    if "--dist" in sys.argv[1:]:
        print()
        dist()


if __name__ == "__main__":
    main()
