#!/usr/bin/env python3
"""Reproduce and inspect the unfinished lproj 3.4 -> 3.18.140 port.

Python owns file edits. Git supplies objects, three-way merging and the index.
No command pushes, resets an existing checkout, or resolves conflicts by policy.
A clean textual merge is not evidence of a working kernel.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SOURCE = "1327a704761cfa043f94e4fe6d1b35e604860b2a"
BASE = "76e10d158efb6d4516018846f60c2ab5501900bc"
TARGET = "6b1ae527b1fdee86e81da0cb26ced75731c6c0fa"
UPSTREAMS = (
    ("https://github.com/torvalds/linux.git", "v3.4", BASE),
    ("https://github.com/gregkh/linux.git", "v3.18.140", TARGET),
)
CONFIGS = (
    "lineage_m4_defconfig", "lineage_m4_nonfc_defconfig",
    "lineage_u0_defconfig", "lineage_u0_nonfc_defconfig",
    "lineage_u0_8m_defconfig", "lineage_v1_defconfig",
    "lineage_vee3_defconfig",
)
CRITICAL = ("ARCH_MSM7X27A", "MACH_LGE", "MSM_KGSL",
            "FB_MSM_MDP303", "MSM7X27A_AUDIO", "ANDROID_BINDER_IPC")
MARKERS = re.compile(rb"^(?:<{7} |>{7} |[|]{7} )", re.M)
VEE3_DEFCONFIG = "lineage_vee3_defconfig"
VEE3_REQUIRED = {
    "ARCH_MSM7X27A": "y", "MACH_LGE": "y", "MACH_MSM7X25A_V3": "y",
    "LGE_BOARD_HEADER_FILE": '"mach/lge/board_v3.h"', "CPU_V7": "y",
    "PHYS_OFFSET": "0x00200000", "MACH_LGE_2ND_GEN_KK_WORKAROUD": "y",
    "MSM_SMD": "y", "MSM_ONCRPCROUTER": "y", "MSM_KGSL": "y",
    "FB_MSM_MDP303": "y", "MSM7X27A_AUDIO": "y", "MSM_CAMERA_V4L2": "y",
    "TOUCHSCREEN_MELFAS_MMS128S": "y", "SENSORS_BMA2X2": "y",
    "SENSORS_BMM050": "y", "SENSOR_APDS9190": "y", "MMC_MSM": "y",
    "MMC_MSM_SDC1_SUPPORT": "y", "MTD_MSM_NAND": "y", "RTC_DRV_MSM": "y",
    "VOLANS_WLAN": "m", "ANDROID_BINDER_IPC": "y", "SERIAL_MSM": "y",
    "SERIAL_MSM_CONSOLE": "y",
}
VEE3_FORBIDDEN = ("MACH_MSM7X25A_M4", "MACH_MSM7X27A_U0",
                  "MACH_MSM7X25A_V1", "MACH_MSM8X25_V7", "SMP")


class PortError(RuntimeError):
    pass


def git(repo, *args, data=None, allowed=(0,)):
    result = subprocess.run(
        ["git", "-C", str(repo), *map(str, args)], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode not in allowed:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise PortError("git %s failed (%s): %s" %
                        (args[0], result.returncode, detail))
    return result


def oid(repo, ref):
    return git(repo, "rev-parse", "--verify", ref + "^{commit}").stdout.decode().strip()


def blob(repo, ref, path):
    return git(repo, "show", "%s:%s" % (ref, path)).stdout


def version(data):
    values = []
    for field in (b"VERSION", b"PATCHLEVEL", b"SUBLEVEL"):
        matches = re.findall(rb"^" + field + rb"[ \t]*=[ \t]*([0-9]+)[ \t]*$", data, re.M)
        if len(matches) != 1:
            raise PortError("Ambiguous or missing Makefile version field: " + field.decode())
        values.append(matches[0].decode())
    return ".".join(values)


def config_values(data):
    return dict(re.findall(r"^CONFIG_([A-Za-z0-9_]+)=(.+)$", data.decode(), re.M))


def validate_device_config(name, wanted, actual):
    """Reject dropped module/board selections and a mismatched Vee3 identity."""
    required = {key: value for key, value in wanted.items()
                if (key in CRITICAL or key.startswith("MACH_MSM7"))
                and value in ("y", "m")}
    forbidden = ()
    if name == VEE3_DEFCONFIG:
        required.update(VEE3_REQUIRED)
        forbidden = VEE3_FORBIDDEN
    failures = ["%s=%s (got %s)" % (key, expected, actual.get(key, "n"))
                for key, expected in sorted(required.items())
                if actual.get(key) != expected]
    failures.extend(key + " must be disabled for Vee3"
                    for key in forbidden if actual.get(key) in ("y", "m"))
    if failures:
        raise PortError("Required device configuration lost or changed: " + "; ".join(failures))


def source_configs(repo, ref):
    configs = {}
    for name in CONFIGS:
        cfg = config_values(blob(repo, ref, "arch/arm/configs/" + name))
        configs[name] = {
            key: val for key, val in cfg.items()
            if key in CRITICAL or key == "LGE_BOARD_HEADER_FILE"
            or (key.startswith("MACH_MSM7") and val == "y")
        }
    return configs


def parse_merge(raw):
    """Parse Git's NUL-delimited tree and unmerged index records."""
    tokens = raw.split(b"\0")
    tree = tokens.pop(0).decode("ascii")
    if not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        raise PortError("Unexpected merge-tree output; Git with --merge-base is required")
    stages = []
    while tokens and tokens[0]:
        record = tokens.pop(0)
        match = re.fullmatch(rb"([0-7]{6}) ([0-9a-f]{40,64}) ([123])\t(.+)", record, re.S)
        if not match:
            raise PortError("Invalid unmerged index record")
        mode, sha, stage, name = match.groups()
        stages.append({"mode": mode.decode(), "oid": sha.decode(),
                       "stage": int(stage), "path": os.fsdecode(name)})
    if not tokens:
        raise PortError("Missing merge-tree record terminator")
    return tree, stages


def merge_result(repo, source=SOURCE, base=BASE, target=TARGET):
    source, base, target = (oid(repo, ref) for ref in (source, base, target))
    result = git(repo, "merge-tree", "--write-tree", "--messages", "-z",
                 "--merge-base=" + base, source, target, allowed=(0, 1))
    tree, stages = parse_merge(result.stdout)
    if bool(stages) != (result.returncode == 1):
        raise PortError("Conflict status inconsistent with merge records")
    return {"source": source, "comparison_base": base, "target": target,
            "merged_tree": tree, "stages": stages}


def audit(repo, result):
    paths = sorted({entry["path"] for entry in result["stages"]})
    source = result["source"]
    cfgs = source_configs(repo, source)
    required = set(CRITICAL)
    for cfg in cfgs.values():
        required.update(key for key, value in cfg.items()
                        if key.startswith("MACH_MSM7") and value == "y")
    definitions = set()
    output = git(repo, "grep", "-h", "-E", "^[[:space:]]*(menuconfig|config)[[:space:]]+",
                 result["target"], "--", "*Kconfig*", allowed=(0, 1)).stdout.decode()
    for line in output.splitlines():
        match = re.match(r"\s*(?:menuconfig|config)\s+(\w+)", line)
        if match:
            definitions.add(match.group(1))
    return {
        "status": "incomplete_unbuilt",
        "source_commit": source,
        "comparison_base_commit": result["comparison_base"],
        "comparison_base_note": "Explicit upstream v3.4 tree; not a verified LG merge ancestor.",
        "target_commit": result["target"],
        "source_version": version(blob(repo, source, "Makefile")),
        "target_version": version(blob(repo, result["target"], "Makefile")),
        "merged_tree": result["merged_tree"],
        "conflicted_files": len(paths),
        "conflicts_by_subsystem": dict(Counter("/".join(p.split("/")[:2]) for p in paths).most_common()),
        "conflict_paths": paths,
        "device_configs": cfgs,
        "required_symbols_absent_from_upstream_target": sorted(required - definitions),
        "compile_validation": "not_run",
        "hardware_validation": "not_run",
    }


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summary(report):
    return {key: report[key] for key in (
        "status", "source_version", "target_version", "conflicted_files",
        "compile_validation", "hardware_validation")}


def prepare(repo, result, worktree, branch):
    worktree = Path(worktree).resolve()
    if worktree.exists():
        raise PortError("Worktree destination already exists: " + str(worktree))
    git(repo, "check-ref-format", "--branch", branch)
    if git(repo, "show-ref", "--verify", "--quiet", "refs/heads/" + branch,
           allowed=(0, 1)).returncode == 0:
        raise PortError("Branch already exists: " + branch)
    # Only the new worktree is changed. The source checkout may have local edits.
    git(repo, "worktree", "add", "--no-checkout", "-b", branch,
        worktree, result["source"])
    git(worktree, "read-tree", "--reset", "-u", result["merged_tree"])
    entries = bytearray()
    paths = sorted({entry["path"] for entry in result["stages"]})
    for path in paths:
        entries.extend(b"0 " + b"0" * 40 + b"\t" + os.fsencode(path) + b"\0")
    for entry in result["stages"]:
        prefix = "%s %s %d\t" % (entry["mode"], entry["oid"], entry["stage"])
        entries.extend(prefix.encode() + os.fsencode(entry["path"]) + b"\0")
    if entries:
        git(worktree, "update-index", "-z", "--index-info", data=bytes(entries))
    git(worktree, "update-ref", "ORIG_HEAD", result["source"])
    for name, content in (
        ("MERGE_HEAD", result["target"] + "\n"),
        ("MERGE_MODE", ""),
        ("MERGE_MSG", "Port lproj to Linux 3.18.140 (unfinished)\n\n"
         "Resolve and review the explicit v3.4 baseline merge before committing.\n"),
    ):
        path = Path(os.fsdecode(git(worktree, "rev-parse", "--git-path", name).stdout).strip())
        if not path.is_absolute():
            path = worktree / path
        path.write_text(content, encoding="utf-8")
    state_path = git(worktree, "rev-parse", "--git-path", "lproj-318-state.json").stdout.decode().strip()
    state_path = Path(state_path)
    if not state_path.is_absolute():
        state_path = worktree / state_path
    write_json(state_path, result)
    return worktree


def conflict_paths(worktree):
    records = git(worktree, "ls-files", "-u", "-z").stdout.split(b"\0")
    return sorted({os.fsdecode(r.split(b"\t", 1)[1]) for r in records if r})


def edit(worktree, manifest):
    """Apply reviewed exact replacements, with whole-file pre/post hashes.

    All preconditions are checked before any source file is changed. Unresolved
    files are staged only after every edit succeeds. There is no blanket choice
    of the upstream or vendor side.
    """
    root = Path(worktree).resolve()
    plans = []
    seen = set()
    tracked = {os.fsdecode(p) for p in git(root, "ls-files", "-z").stdout.split(b"\0") if p}
    for spec in manifest["files"]:
        relative = Path(spec["path"])
        if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts:
            raise PortError("Unsafe edit path: " + str(relative))
        path = root / relative
        if path.is_symlink() or root not in path.resolve().parents:
            raise PortError("Edit escapes worktree: " + str(relative))
        if spec["path"] not in tracked or spec["path"] in seen:
            raise PortError("Untracked or duplicate edit path: " + str(relative))
        seen.add(spec["path"])
        before = path.read_bytes()
        if hashlib.sha256(before).hexdigest() != spec["sha256_before"]:
            raise PortError("Preimage hash mismatch: " + str(relative))
        after = before
        for replacement in spec["replacements"]:
            old = replacement["before"].encode("utf-8")
            new = replacement["after"].encode("utf-8")
            if not old or after.count(old) != 1:
                raise PortError("Replacement must match exactly once: " + str(relative))
            after = after.replace(old, new, 1)
        if MARKERS.search(after):
            raise PortError("Conflict markers remain: " + str(relative))
        if hashlib.sha256(after).hexdigest() != spec["sha256_after"]:
            raise PortError("Postimage hash mismatch: " + str(relative))
        plans.append((path, before, after, spec["path"]))
    try:
        for path, before, after, relative in plans:
            path.write_bytes(after)
        if plans:
            git(root, "add", "--", *(item[3] for item in plans))
    except Exception:
        for path, before, after, relative in plans:
            path.write_bytes(before)
        raise
    return [item[3] for item in plans]


def status(worktree):
    paths = conflict_paths(worktree)
    return {"status": "conflicts_pending" if paths else "requires_build_and_hardware_validation",
            "makefile_version": version((Path(worktree) / "Makefile").read_bytes()),
            "conflicted_files": len(paths), "conflict_paths": paths,
            "compile_validation": "not_run", "hardware_validation": "not_run"}


def build(worktree, config, cross_compile, output, jobs):
    root = Path(worktree).resolve()
    if conflict_paths(root):
        raise PortError("Build blocked: resolve all unmerged index entries first")
    pending = git(root, "rev-parse", "--verify", "MERGE_HEAD^{commit}",
                  allowed=(0, 128)).stdout.decode().strip()
    integrated = git(root, "merge-base", "--is-ancestor", TARGET, "HEAD",
                     allowed=(0, 1, 128)).returncode == 0
    if pending != TARGET and not integrated:
        raise PortError("Build blocked: pinned Linux 3.18.140 target is not integrated")
    if not version((root / "Makefile").read_bytes()).startswith("3.18."):
        raise PortError("Build blocked: source tree is not Linux 3.18")
    markers = git(root, "grep", "-l", "-E", "^(<<<<<<< |>>>>>>> |[|]{7} )",
                  "--", "*.c", "*.h", "*.S", "*Kconfig*", "*Makefile*", allowed=(0, 1))
    if markers.returncode == 0:
        raise PortError("Build blocked: tracked conflict markers remain")
    if not shutil.which(cross_compile + "gcc"):
        raise PortError("ARM cross compiler unavailable: " + cross_compile + "gcc")
    output = Path(output).resolve()
    if output == root or root in output.parents:
        raise PortError("Use a build directory outside the source worktree")
    if output.exists() and any(output.iterdir()):
        raise PortError("Build output must be empty to avoid reusing another configuration")
    output.mkdir(parents=True, exist_ok=True)
    command = ["make", "-C", str(root), "O=" + str(output), "ARCH=arm",
               "CROSS_COMPILE=" + cross_compile]
    wanted = config_values((root / "arch/arm/configs" / config).read_bytes())
    with (output / "build.log").open("wb") as log:
        for targets in ([config], ["olddefconfig"]):
            result = subprocess.run(command + targets, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise PortError("Configuration failed; inspect " + str(output / "build.log"))
        actual = config_values((output / ".config").read_bytes())
        validate_device_config(config, wanted, actual)
        result = subprocess.run(command + ["-j" + str(jobs), "zImage", "modules"],
                                stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise PortError("Build failed; inspect " + str(output / "build.log"))
    return {"compile_validation": "passed", "hardware_validation": "not_run",
            "zImage": str(output / "arch/arm/boot/zImage"), "log": str(output / "build.log")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="Fetch and verify the two pinned upstream tags")
    check = sub.add_parser("audit", help="Compute merge and report; source checkout is unchanged")
    prep = sub.add_parser("prepare", help="Materialize merge in a NEW worktree, retaining conflicts")
    for child in (check, prep):
        child.add_argument("--report", required=True, type=Path)
    prep.add_argument("--worktree", type=Path, required=True)
    prep.add_argument("--branch", default="port/linux-3.18.140")
    edits = sub.add_parser("edit", help="Apply a reviewed JSON edit manifest using Python")
    edits.add_argument("--worktree", type=Path, required=True)
    edits.add_argument("--manifest", type=Path, required=True)
    state = sub.add_parser("status")
    state.add_argument("--worktree", type=Path, required=True)
    vee3_check = sub.add_parser("check-vee3-config", help="Validate Vee3 hardware selections in a .config")
    vee3_check.add_argument("--config", type=Path, required=True)
    compile_cmd = sub.add_parser("build", help="Build only after merge and config guards pass")
    compile_cmd.add_argument("--worktree", type=Path, required=True)
    compile_cmd.add_argument("--defconfig", choices=CONFIGS, default=VEE3_DEFCONFIG,
                             help="Device configuration (default: Vee3)")
    compile_cmd.add_argument("--cross-compile", required=True)
    compile_cmd.add_argument("--output", type=Path, required=True)
    compile_cmd.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 8))
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            for url, tag, expected in UPSTREAMS:
                ref = "refs/lproj-port/" + tag
                git(args.repo, "fetch", "--depth=1", "--no-tags", url, "refs/tags/" + tag + ":" + ref)
                if oid(args.repo, ref) != expected:
                    raise PortError("Upstream tag does not match pinned commit: " + tag)
            response = {"comparison_base": BASE, "target": TARGET}
        elif args.command in ("audit", "prepare"):
            result = merge_result(args.repo)
            report = audit(args.repo, result)
            if args.command == "prepare":
                report["worktree"] = str(prepare(args.repo, result, args.worktree, args.branch))
            write_json(args.report, report)
            response = summary(report)
            response["report"] = str(args.report.resolve())
        elif args.command == "edit":
            response = {"edited_paths": edit(args.worktree, json.loads(args.manifest.read_text()))}
        elif args.command == "status":
            response = status(args.worktree)
            response.pop("conflict_paths")
        elif args.command == "check-vee3-config":
            values = config_values(args.config.read_bytes())
            validate_device_config(VEE3_DEFCONFIG, {}, values)
            response = {"device": "vee3", "configuration": "valid",
                        "checked_required_symbols": len(VEE3_REQUIRED),
                        "scope": "configuration_only"}
        else:
            if args.jobs < 1:
                raise PortError("--jobs must be positive")
            response = build(args.worktree, args.defconfig, args.cross_compile, args.output, args.jobs)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0
    except (PortError, OSError, ValueError, KeyError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
