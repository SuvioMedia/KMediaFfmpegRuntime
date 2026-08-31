# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LegalResourceIsolationTest(unittest.TestCase):
    def test_android_and_desktop_artifacts_scope_auxiliary_legal_resources(self):
        modules = {
            "runtime-android/build.gradle.kts": "META-INF/kmediaffmpeg/legal",
            "runtime-desktop/build.gradle.kts": "META-INF/kmediaffmpeg/legal",
            "ass-runtime-android/build.gradle.kts": "META-INF/kmediaass/legal",
            "ass-runtime-desktop/build.gradle.kts": "META-INF/kmediaass/legal",
        }

        for relative_path, legal_root in modules.items():
            with self.subTest(module=relative_path):
                build_script = (ROOT / relative_path).read_text()
                self.assertIn(f'into("{legal_root}")', build_script)
                self.assertIn(f'into("{legal_root}/LICENSES")', build_script)
                self.assertNotIn(
                    'from(rootProject.file("THIRD_PARTY_NOTICES.md")) { into("META-INF") }',
                    build_script,
                )

        self.assertEqual(2, len(set(modules.values())))


if __name__ == "__main__":
    unittest.main()
