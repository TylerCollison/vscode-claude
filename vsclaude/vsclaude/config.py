import json
import os
from pathlib import Path

class ConfigManager:
    def __init__(self, config_dir=None):
        self.config_dir = Path(config_dir or Path.home() / ".vsclaude")
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_global_config(self):
        config_file = self.config_dir / "global-config.json"
        if config_file.exists():
            with open(config_file) as f:
                return json.load(f)
        return self._default_global_config()

    def _default_global_config(self):
        return {
            "port_range": {"min": 8000, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {}
        }