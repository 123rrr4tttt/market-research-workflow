from __future__ import annotations

import unittest

import pytest

from app.settings import config as app_config
from app.services import settings_manager

pytestmark = pytest.mark.unit


class EnvSettingsFileAlignmentTestCase(unittest.TestCase):
    def test_settings_and_manager_use_same_backend_env_file(self):
        env_files = app_config.Settings.model_config.get("env_file")
        self.assertIsNotNone(env_files)

        if isinstance(env_files, (str, bytes)):
            env_file_candidates = {str(env_files)}
        else:
            env_file_candidates = {str(item) for item in env_files}

        self.assertIn(str(settings_manager.ENV_FILE), env_file_candidates)
        self.assertEqual(str(settings_manager.ENV_FILE), str(app_config.BACKEND_ROOT / ".env"))


if __name__ == "__main__":
    unittest.main()
