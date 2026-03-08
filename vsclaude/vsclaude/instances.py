import json
from pathlib import Path

class InstanceManager:
    def __init__(self, config_dir=None):
        self.config_dir = Path(config_dir or Path.home() / ".vsclaude")
        self.instances_dir = self.config_dir / "instances"
        self.instances_dir.mkdir(parents=True, exist_ok=True)

    def create_instance_config(self, name, port, profile="default", environment=None):
        instance_dir = self.instances_dir / name
        instance_dir.mkdir(exist_ok=True)

        config = {
            "name": name,
            "port": port,
            "profile": profile,
            "environment": environment or {}
        }

        config_file = instance_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        return config