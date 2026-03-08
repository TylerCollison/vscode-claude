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

    def get_global_environment(self):
        """Get environment variables from global config"""
        config = self.load_global_config()
        return config.get("environment", {})

    def format_ide_address(self, port):
        """Format IDE address using the configured template"""
        config = self.load_global_config()
        template = config.get("ide_address_template", "http://localhost:{port}")
        return template.format(host="localhost", port=port)

    def get_enabled_volumes(self) -> list:
        """Get enabled volumes from global config"""
        config = self.load_global_config()
        return config.get("enabled_volumes", [])

    def get_include_docker_sock(self) -> bool:
        """Get Docker socket mount preference from global config"""
        config = self.load_global_config()
        return config.get("include_docker_sock", True)

    def validate_volume_paths(self, paths):
        """Validate that all volume paths start with /"""
        if not isinstance(paths, list):
            return False
        return all(path.startswith('/') for path in paths)