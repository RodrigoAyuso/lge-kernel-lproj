"""Integration tests use real Git indexes/worktrees, without network or a compiler."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "port_to_318.py"
spec = importlib.util.spec_from_file_location("port_to_318", SCRIPT)
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-port-318-", dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Port test")
        self.run_git("config", "user.email", "port-test@example.invalid")
        self.run_git("config", "commit.gpgsign", "false")
        self.run_git("config", "core.hooksPath", "/dev/null")
        self.put("Makefile", "VERSION = 3\nPATCHLEVEL = 4\nSUBLEVEL = 0\n")
        self.put("driver.c", "int shared;\nint feature = 0;\n")
        for name in port.CONFIGS:
            self.put("arch/arm/configs/" + name,
                     'CONFIG_ARCH_MSM7X27A=y\nCONFIG_MACH_LGE=y\nCONFIG_MACH_MSM7X25A_V1=y\n')
        self.put("arch/arm/mach-msm/Kconfig", "config ARCH_MSM7X27A\n bool\n")
        self.base = self.commit("base")
        self.run_git("checkout", "-q", "-b", "vendor")
        self.put("driver.c", "int shared;\nint feature = 1;\n")
        self.put("vendor-only.c", "int lge;\n")
        self.source = self.commit("vendor")
        self.run_git("checkout", "-q", "-b", "target", self.base)
        self.put("Makefile", "VERSION = 3\nPATCHLEVEL = 18\nSUBLEVEL = 140\n")
        self.put("driver.c", "int shared;\nint feature = 2;\n")
        self.put("target-only.c", "int new_core;\n")
        self.put("arch/arm/mach-msm/Kconfig", "config ARCH_MSM7X00A\n bool\n")
        self.target = self.commit("upstream")
        self.run_git("checkout", "-q", "vendor")
        self.result = port.merge_result(self.repo, self.source, self.base, self.target)
        self.worktree = self.root / "port"

    def run_git(self, *args, repo=None):
        result = subprocess.run(["git", "-C", str(repo or self.repo), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.decode().strip()

    def put(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, message):
        self.run_git("add", ".")
        self.run_git("commit", "-qm", message)
        return self.run_git("rev-parse", "HEAD")

    def prepare(self):
        return port.prepare(self.repo, self.result, self.worktree, "port-experiment")

    def edit_spec(self, name, before, after):
        return {"path": name, "sha256_before": hashlib.sha256(before).hexdigest(),
                "sha256_after": hashlib.sha256(after).hexdigest(),
                "replacements": [{"before": before.decode(), "after": after.decode()}]}

    def test_prepare_retains_both_trees_conflicts_and_dirty_source(self):
        self.put("driver.c", "uncommitted user changes\n")
        before = self.run_git("status", "--porcelain")
        self.prepare()
        self.assertEqual((self.repo / "driver.c").read_text(), "uncommitted user changes\n")
        self.assertEqual(self.run_git("status", "--porcelain"), before)
        self.assertTrue((self.worktree / "vendor-only.c").is_file())
        self.assertTrue((self.worktree / "target-only.c").is_file())
        self.assertEqual(port.conflict_paths(self.worktree), ["driver.c"])
        self.assertEqual(port.version((self.worktree / "Makefile").read_bytes()), "3.18.140")
        self.assertEqual(self.run_git("rev-parse", "HEAD", repo=self.worktree), self.source)
        self.assertEqual(self.run_git("rev-parse", "MERGE_HEAD", repo=self.worktree), self.target)

    def test_normal_git_abort_restores_vendor_tree(self):
        self.prepare()
        self.run_git("merge", "--abort", repo=self.worktree)
        self.assertEqual(self.run_git("status", "--porcelain", repo=self.worktree), "")
        self.assertEqual((self.worktree / "driver.c").read_bytes(),
                         (self.repo / "driver.c").read_bytes())
        self.assertFalse((self.worktree / "target-only.c").exists())

    def test_existing_destination_is_never_overwritten(self):
        self.worktree.mkdir()
        (self.worktree / "important").write_text("keep")
        with self.assertRaises(port.PortError):
            self.prepare()
        self.assertEqual((self.worktree / "important").read_text(), "keep")
        self.assertEqual(self.run_git("status", "--porcelain"), "")

    def test_existing_branch_is_not_moved(self):
        self.run_git("branch", "port-experiment", self.base)
        with self.assertRaises(port.PortError):
            self.prepare()
        self.assertEqual(self.run_git("rev-parse", "port-experiment"), self.base)
        self.assertFalse(self.worktree.exists())

    def test_bad_preimage_prevents_every_edit(self):
        self.prepare()
        before = (self.worktree / "driver.c").read_bytes()
        first = self.edit_spec("driver.c", before, b"int feature = 3;\n")
        second = self.edit_spec("vendor-only.c", b"stale", b"changed")
        with self.assertRaisesRegex(port.PortError, "Preimage"):
            port.edit(self.worktree, {"files": [first, second]})
        self.assertEqual((self.worktree / "driver.c").read_bytes(), before)
        self.assertEqual(port.conflict_paths(self.worktree), ["driver.c"])

    def test_reviewed_resolution_updates_index_and_can_create_merge_commit(self):
        self.prepare()
        before = (self.worktree / "driver.c").read_bytes()
        after = b"int shared;\nint feature = 3; /* reviewed vendor + upstream implementation */\n"
        port.edit(self.worktree, {"files": [self.edit_spec("driver.c", before, after)]})
        self.assertEqual(port.conflict_paths(self.worktree), [])
        self.run_git("commit", "-qm", "reviewed merge", repo=self.worktree)
        self.assertEqual(self.run_git("show", "-s", "--format=%P", "HEAD", repo=self.worktree),
                         self.source + " " + self.target)

    def test_escape_and_conflict_markers_are_rejected(self):
        self.prepare()
        before = (self.worktree / "driver.c").read_bytes()
        bad = self.edit_spec("../repo/driver.c", before, b"changed")
        with self.assertRaisesRegex(port.PortError, "Unsafe"):
            port.edit(self.worktree, {"files": [bad]})
        bad = self.edit_spec("driver.c", before, b">>>>>>> unresolved\n")
        with self.assertRaisesRegex(port.PortError, "markers"):
            port.edit(self.worktree, {"files": [bad]})
        self.assertEqual((self.worktree / "driver.c").read_bytes(), before)

    def test_build_does_not_run_while_merge_is_unresolved(self):
        self.prepare()
        output = self.root / "build"
        with self.assertRaisesRegex(port.PortError, "resolve all unmerged"):
            port.build(self.worktree, port.CONFIGS[0], "does-not-exist-", output, 1)
        self.assertFalse(output.exists())

    def test_changing_version_label_alone_cannot_authorize_a_build(self):
        self.put("Makefile", "VERSION = 3\nPATCHLEVEL = 18\nSUBLEVEL = 140\n")
        output = self.root / "build"
        with self.assertRaisesRegex(port.PortError, "target is not integrated"):
            port.build(self.repo, port.CONFIGS[0], "does-not-exist-", output, 1)
        self.assertFalse(output.exists())

    def test_resolved_real_merge_reaches_compiler_check(self):
        self.prepare()
        before = (self.worktree / "driver.c").read_bytes()
        port.edit(self.worktree, {"files": [self.edit_spec("driver.c", before, b"int feature = 3;\n")]})
        with patch.object(port, "TARGET", self.target):
            with self.assertRaisesRegex(port.PortError, "cross compiler unavailable"):
                port.build(self.worktree, port.CONFIGS[0], "does-not-exist-", self.root / "build", 1)

    def test_audit_reports_missing_hardware_without_claiming_success(self):
        report = port.audit(self.repo, self.result)
        self.assertEqual(report["conflicted_files"], 1)
        self.assertIn("ARCH_MSM7X27A", report["required_symbols_absent_from_upstream_target"])
        self.assertEqual(report["compile_validation"], "not_run")
        self.assertEqual(report["status"], "incomplete_unbuilt")


class Vee3ConfigurationTests(unittest.TestCase):
    def test_reference_profile_including_module_passes(self):
        values = dict(port.VEE3_REQUIRED)
        self.assertEqual(values["VOLANS_WLAN"], "m")
        port.validate_device_config(port.VEE3_DEFCONFIG, {}, values)

    def test_missing_wifi_module_is_rejected(self):
        values = dict(port.VEE3_REQUIRED)
        values.pop("VOLANS_WLAN")
        with self.assertRaisesRegex(port.PortError, "VOLANS_WLAN=m"):
            port.validate_device_config(port.VEE3_DEFCONFIG, {}, values)

    def test_another_board_cannot_masquerade_as_vee3(self):
        values = dict(port.VEE3_REQUIRED)
        values["MACH_MSM7X25A_M4"] = "y"
        values["LGE_BOARD_HEADER_FILE"] = '\"mach/lge/board_m4.h\"'
        with self.assertRaisesRegex(port.PortError, "LGE_BOARD_HEADER_FILE"):
            port.validate_device_config(port.VEE3_DEFCONFIG, {}, values)

    def test_edited_input_config_cannot_remove_required_hardware(self):
        with self.assertRaisesRegex(port.PortError, "MACH_MSM7X25A_V3=y"):
            port.validate_device_config(port.VEE3_DEFCONFIG, {}, {})


if __name__ == "__main__":
    unittest.main()
