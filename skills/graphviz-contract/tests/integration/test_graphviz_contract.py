"""Exercise the contract commands against real Git staging areas."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "graphviz_contract.py"


class ContractIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.write("src/api/a.py", "original\n")
        self.write("src/config.py", "config\n")
        self.write("docs/graphviz-contracts/dot/api-request-flow.dot", "digraph {}\n")
        self.write("docs/graphviz-contracts/png/api-request-flow.png", "rendered\n")
        self.metadata = "docs/graphviz-contracts/metadata/api-request-flow.json"
        self.write(self.metadata, json.dumps({"paths": ["src/api/", "src/config.py"]}))
        self.write_router("api-request-flow")
        self.git("add", ".")
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.git("add", self.metadata)
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, name, contents):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents)

    def run_script(self, *args, expected):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(expected, result.returncode, result.stderr)
        return result

    def write_router(self, *names: str) -> None:
        rows = "".join(f"| {name} | Diagram description. |\n" for name in names)
        self.write("docs/graphviz-contracts/DIAGRAMS.md", "| Name | Description |\n| --- | --- |\n" + rows)

    def rename_diagram(self, old: str, new: str) -> None:
        for directory, extension in (("dot", "dot"), ("png", "png"), ("metadata", "json")):
            prefix = f"docs/graphviz-contracts/{directory}/"
            self.git("mv", prefix + old + "." + extension, prefix + new + "." + extension)
        self.write_router(new)
        self.git("add", "docs/graphviz-contracts/DIAGRAMS.md")

    def test_rejects_invalid_names_even_with_matching_files_and_router(self):
        invalid_names = (
            "request", "Api-request-flow", "api_request_flow", "api request-flow",
            "api--request-flow", "-api-request-flow", "api-request-flow-",
            "01-api-request-flow", "api-request-flow-20261027", "api-request-flow-v2",
            "api-request-flow-2026-10-27", "api-request-flow-2.1",
        )
        for name in invalid_names:
            with self.subTest(name=name):
                self.rename_diagram("api-request-flow", name)
                try:
                    result = self.run_script("check", expected=1)
                    self.assertIn(f"{name}: invalid diagram name", result.stderr)
                finally:
                    self.rename_diagram(name, "api-request-flow")
        self.run_script("check", expected=0)

    def test_accepts_scope_subject_names_and_digits_within_words(self):
        for name in ("system-overview", "agent-context-lifecycle", "s3-storage-flow"):
            with self.subTest(name=name):
                self.rename_diagram("api-request-flow", name)
                self.run_script("check", expected=0)
                self.rename_diagram(name, "api-request-flow")

    def test_router_names_must_match_staged_diagram_basenames(self):
        self.write_router("system-overview")
        self.run_script("check", expected=0)
        self.git("add", "docs/graphviz-contracts/DIAGRAMS.md")
        result = self.run_script("check", expected=1)
        self.assertIn("api-request-flow: missing router entry", result.stderr)
        self.assertIn("system-overview: router entry has no diagram", result.stderr)

    def test_router_rejects_duplicate_names_and_missing_router(self):
        self.write_router("api-request-flow", "api-request-flow")
        self.git("add", "docs/graphviz-contracts/DIAGRAMS.md")
        result = self.run_script("check", expected=1)
        self.assertIn("api-request-flow: duplicate router entry", result.stderr)
        self.git("rm", "-f", "docs/graphviz-contracts/DIAGRAMS.md")
        result = self.run_script("check", expected=1)
        self.assertIn("missing router", result.stderr)

    def test_router_format_errors_and_inline_code_names(self):
        router = "docs/graphviz-contracts/DIAGRAMS.md"
        for contents in ("", "# Diagrams\n", "| Name | Description |\n| --- | --- |\n| | Empty |\n"):
            with self.subTest(contents=contents):
                self.write(router, contents)
                self.git("add", router)
                result = self.run_script("check", expected=1)
                self.assertIn("expected a", result.stderr)
        self.write_router("`api-request-flow`")
        self.git("add", router)
        self.run_script("check", expected=0)

    def test_rejects_uppercase_extensions(self):
        original = "docs/graphviz-contracts/dot/api-request-flow.dot"
        renamed = "docs/graphviz-contracts/dot/api-request-flow.DOT"
        self.git("mv", original, renamed)
        result = self.run_script("check", expected=1)
        self.assertIn("use lowercase .dot extension", result.stderr)

    def test_checks_orphaned_and_nested_diagram_names(self):
        for filename in ("dot/Bad_Name.dot", "png/Bad_Name.png", "dot/nested/api-flow.dot"):
            with self.subTest(filename=filename):
                path = "docs/graphviz-contracts/" + filename
                self.write(path, "draft")
                self.git("add", path)
                result = self.run_script("check", expected=1)
                self.assertIn("invalid diagram name", result.stderr)
                self.git("rm", "-f", path)

    def test_hook_blocks_invalid_names_until_renamed(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" check\n')
        hook.chmod(0o755)
        self.rename_diagram("api-request-flow", "Bad_Name")
        result = subprocess.run(["git", "commit", "-m", "rename"], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid diagram name", result.stderr)
        self.rename_diagram("Bad_Name", "system-overview")
        self.git("commit", "-qm", "rename")

    def test_uses_staged_content_and_requires_checkpoint_to_be_staged(self):
        self.write("src/api/a.py", "staged\n")
        self.git("add", "src/api/a.py")
        self.write("src/api/a.py", "unstaged\n")
        self.run_script("check", expected=1)
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.run_script("check", expected=1)
        self.git("add", self.metadata)
        self.run_script("check", expected=0)
        self.git("add", "src/api/a.py")
        self.run_script("check", expected=1)

    def test_directory_add_delete_and_rename_are_matched(self):
        self.git("mv", "src/api/a.py", "src/api/b.py")
        result = self.run_script("find", "--staged", expected=0)
        self.assertEqual({"api-request-flow": ["src/api/a.py", "src/api/b.py"]}, json.loads(result.stdout))
        self.run_script("check", expected=1)
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.git("add", self.metadata)
        self.run_script("check", expected=0)
        self.git("rm", "-f", "src/api/b.py")
        self.run_script("check", expected=1)

    def test_explicit_paths_directory_boundaries_and_untracked_files(self):
        result = self.run_script("find", "src/api/new.py", "src/apix/other.py", expected=0)
        self.assertEqual({"api-request-flow": ["src/api/new.py"]}, json.loads(result.stdout))
        self.write("src/api/new.py", "new\n")
        self.run_script("check", expected=0)
        self.git("add", "src/api/new.py")
        self.run_script("check", expected=1)

    def test_rejects_unstaged_metadata_changes_and_unknown_diagrams(self):
        self.write(self.metadata, '{"paths": ["src/"]}')
        self.run_script("checkpoint", "api-request-flow", expected=2)
        self.run_script("checkpoint", "missing", expected=2)

    def test_path_changes_and_malformed_metadata(self):
        self.write("src/other/a.ts", "source\n")
        self.git("add", "src/other/a.ts")
        metadata = {"paths": ["src/api/", "src/config.py", "src/other/"]}
        self.write(self.metadata, json.dumps(metadata))
        self.git("add", self.metadata)
        self.run_script("check", expected=1)
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.git("add", self.metadata)
        self.run_script("check", expected=0)
        self.write(self.metadata, '{"paths": ["../outside"]}')
        self.git("add", self.metadata)
        self.run_script("check", expected=2)

    def test_index_metadata_not_working_tree_metadata_is_checked(self):
        self.write(self.metadata, "not json")
        self.run_script("check", expected=0)
        self.git("add", self.metadata)
        self.run_script("check", expected=2)

    def test_git_pre_commit_hook_blocks_until_checkpoint_is_staged(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" check\n')
        hook.chmod(0o755)
        self.write("src/api/a.py", "changed\n")
        self.git("add", "src/api/a.py")
        result = subprocess.run(["git", "commit", "-m", "change"], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("api-request-flow: covered staged files changed", result.stderr)
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.git("add", self.metadata)
        self.git("commit", "-qm", "change")

    def test_detects_missing_diagram_counterparts_in_staged_snapshot(self):
        self.write("docs/graphviz-contracts/dot/system-overview.dot", "digraph {}\n")
        self.git("add", "docs/graphviz-contracts/dot/system-overview.dot")
        result = self.run_script("check", expected=1)
        self.assertIn("system-overview: missing PNG render", result.stderr)
        self.assertIn("system-overview: missing metadata", result.stderr)
        self.git("rm", self.metadata)
        result = self.run_script("check", expected=1)
        self.assertIn("api-request-flow: missing metadata", result.stderr)

    def test_detects_metadata_without_source_or_render(self):
        self.git("rm", "docs/graphviz-contracts/dot/api-request-flow.dot")
        self.git("rm", "docs/graphviz-contracts/png/api-request-flow.png")
        result = self.run_script("check", expected=1)
        self.assertIn("api-request-flow: missing DOT source", result.stderr)
        self.assertIn("api-request-flow: missing PNG render", result.stderr)

    def test_detects_coverage_paths_without_staged_files(self):
        self.write(self.metadata, json.dumps({"paths": ["src/missing.ts", "src/empty/"]}))
        self.git("add", self.metadata)
        self.run_script("checkpoint", "api-request-flow", expected=0)
        self.git("add", self.metadata)
        result = self.run_script("check", expected=1)
        self.assertIn("coverage path matches no staged files: src/missing.ts", result.stderr)
        self.assertIn("coverage path matches no staged files: src/empty/", result.stderr)

    def test_diagram_health_reads_staging_area(self):
        (self.root / "docs/graphviz-contracts/png/api-request-flow.png").unlink()
        self.run_script("check", expected=0)
        self.git("add", "-u")
        result = self.run_script("check", expected=1)
        self.assertIn("api-request-flow: missing PNG render", result.stderr)


if __name__ == "__main__":
    unittest.main()
