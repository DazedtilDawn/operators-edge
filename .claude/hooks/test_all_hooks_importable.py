#!/usr/bin/env python3
"""
Meta-test: Verify all hook modules can be imported.

This catches facade breakage, circular imports, and missing dependencies
BEFORE they break enforcement rails in production.

"Even our enforcement layer is tested: every hook must be importable.
If a refactor breaks the rail, CI catches it before the user does."
"""
import os
import sys
import glob
import importlib.util
import unittest

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))


class TestAllHooksImportable(unittest.TestCase):
    """Verify every non-test .py file in hooks/ can be imported."""

    def test_all_hooks_importable(self):
        """All hook modules should import without error."""
        sys.path.insert(0, HOOK_DIR)

        failed = []
        passed = 0

        for path in sorted(glob.glob(os.path.join(HOOK_DIR, "*.py"))):
            name = os.path.basename(path)[:-3]

            # Skip test files and __init__
            if name.startswith("test_") or name in ("__init__",):
                continue

            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                passed += 1
            except Exception as e:
                failed.append((name, str(e)))

        # Report all failures at once for better debugging
        if failed:
            failure_report = "\n".join(f"  {name}: {err}" for name, err in failed)
            self.fail(f"Failed to import {len(failed)} modules:\n{failure_report}")

        # Sanity check: we should have found some modules
        self.assertGreater(passed, 30, f"Only found {passed} modules - expected 40+")

    def test_edge_utils_facade_complete(self):
        """edge_utils.py should re-export all expected symbols."""
        sys.path.insert(0, HOOK_DIR)
        import edge_utils

        # Critical symbols that hooks depend on
        critical_symbols = [
            # Path utilities
            "get_project_dir",
            "get_state_dir",
            "get_proof_dir",
            # State utilities
            "load_yaml_state",
            "file_hash",
            "respond",
            # Config
            "SessionContext",
        ]

        missing = [s for s in critical_symbols if not hasattr(edge_utils, s)]

        if missing:
            self.fail(f"edge_utils missing critical symbols: {missing}")


if __name__ == "__main__":
    unittest.main()
