# SPDX-License-Identifier: LGPL-2.1-or-later

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_native_output", ROOT / "scripts/verify_native_output.py"
)
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)


class WindowsDependencyClosureTest(unittest.TestCase):
    def test_accepts_packaged_core_system_and_api_set_imports(self):
        VERIFY.verify_windows_dependency_closure(
            {
                "runtime.dll": [
                    "dependency.dll",
                    "KERNEL32.dll",
                    "OLE32.dll",
                    "api-ms-win-crt-runtime-l1-1-0.dll",
                ],
                "dependency.dll": ["bcrypt.dll"],
            },
            {"runtime.dll", "dependency.dll"},
            "test runtime",
        )

    def test_accepts_windows_schannel_and_network_system_imports(self):
        VERIFY.verify_windows_dependency_closure(
            {
                "runtime.dll": [
                    "CRYPT32.dll",
                    "ncrypt.dll",
                    "Secur32.dll",
                    "WS2_32.dll",
                ],
            },
            {"runtime.dll"},
            "test runtime",
        )

    def test_rejects_toolchain_dll_available_only_through_path(self):
        with self.assertRaisesRegex(ValueError, "libgcc_s_seh-1.dll"):
            VERIFY.verify_windows_dependency_closure(
                {"runtime.dll": ["libgcc_s_seh-1.dll"]},
                {"runtime.dll"},
                "test runtime",
            )

    def test_rejects_non_os_redist_dll(self):
        with self.assertRaisesRegex(ValueError, "vcruntime140.dll"):
            VERIFY.verify_windows_dependency_closure(
                {"runtime.dll": ["vcruntime140.dll"]},
                {"runtime.dll"},
                "test runtime",
            )

    def test_rejects_incomplete_dependency_graph(self):
        with self.assertRaisesRegex(ValueError, "differs from its DLL inventory"):
            VERIFY.verify_windows_dependency_closure(
                {"runtime.dll": ["KERNEL32.dll"]},
                {"runtime.dll", "missing.dll"},
                "test runtime",
            )

    def test_rejects_empty_objdump_result(self):
        with self.assertRaisesRegex(ValueError, "reported no imports"):
            VERIFY.verify_windows_dependency_closure(
                {"runtime.dll": []},
                {"runtime.dll"},
                "test runtime",
            )


if __name__ == "__main__":
    unittest.main()
