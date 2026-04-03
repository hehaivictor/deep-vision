import re
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
SERVER_PATH = WEB_DIR / "server.py"
CONFIG_PATH = WEB_DIR / "config.py"
ENV_EXAMPLE_PATH = WEB_DIR / ".env.example"


def _parse_template_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        match = re.match(r"([A-Z][A-Z0-9_]+)\s*=", stripped)
        if match:
            keys.add(match.group(1))
            continue
        match = re.match(r"([A-Z][A-Z0-9_]+)=(.*)$", stripped)
        if match:
            keys.add(match.group(1))
    return keys


def _parse_server_cfg_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    keys = set(
        re.findall(
            r'_cfg_(?:get|int|float|bool|text|text_list|numeric_map)\(\s*"([A-Z][A-Z0-9_]+)"',
            text,
        )
    )
    # 生产入口还会直接读取这些环境变量。
    keys.update(
        {
            "CONFIG_RESOLUTION_MODE",
            "GUNICORN_WORKERS",
            "GUNICORN_THREADS",
            "GUNICORN_TIMEOUT",
            "GUNICORN_GRACEFUL_TIMEOUT",
            "GUNICORN_KEEPALIVE",
            "GUNICORN_WORKER_CLASS",
            "GUNICORN_LOG_LEVEL",
            "GUNICORN_ACCESSLOG",
            "GUNICORN_ERRORLOG",
            "GUNICORN_PRELOAD_APP",
        }
    )
    return keys


class ConfigTemplateConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(WEB_DIR))
        import server

        cls.server = server
        cls.server_keys = _parse_server_cfg_keys(SERVER_PATH)
        cls.config_keys = _parse_template_keys(CONFIG_PATH)
        cls.env_example_keys = _parse_template_keys(ENV_EXAMPLE_PATH)

    def test_config_keys_are_all_consumed_by_server(self):
        missing = sorted(key for key in self.config_keys if key not in self.server_keys)
        self.assertEqual(missing, [])

    def test_env_example_keys_are_all_consumed_by_server(self):
        missing = sorted(key for key in self.env_example_keys if key not in self.server_keys)
        self.assertEqual(missing, [])

    def test_config_does_not_contain_env_managed_only_keys(self):
        misplaced = sorted(
            key for key in self.config_keys if self.server._is_env_managed_config_key(key)
        )
        self.assertEqual(misplaced, [])

    def test_config_covers_all_strategy_keys(self):
        missing = sorted(
            key
            for key in self.server_keys
            if not key.startswith("GUNICORN_")
            if not self.server._is_env_managed_config_key(key)
            if key not in self.config_keys
        )
        self.assertEqual(missing, [])

    def test_env_example_covers_all_env_managed_keys(self):
        missing = sorted(
            key
            for key in self.server_keys
            if key.startswith("GUNICORN_") or self.server._is_env_managed_config_key(key)
            if key not in self.env_example_keys
        )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
