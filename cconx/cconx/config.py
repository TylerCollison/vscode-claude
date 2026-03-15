import json
import os
from pathlib import Path
from typing import Optional, List
import ipaddress

class ConfigManager:
    def __init__(self, config_dir=None):
        self.config_dir = Path(config_dir or Path.home() / ".cconx")
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_global_config(self):
        config_file = self.config_dir / "global-config.json"
        if config_file.exists():
            with open(config_file) as f:
                return json.load(f)
        return self._default_global_config()


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

    def get_default_image(self) -> str:
        """Get default docker image from global config"""
        config = self.load_global_config()
        return config.get("default_image", "tylercollison2089/vscode-claude:latest")

    def get_docker_network(self) -> Optional[str]:
        """Get docker network from global config"""
        config = self.load_global_config()
        return config.get("docker_network")

    def get_dns_servers(self) -> Optional[List[str]]:
        """Get DNS servers from global config"""
        config = self.load_global_config()
        dns_servers = config.get("dns_servers")

        if dns_servers is None:
            return None

        if not dns_servers:
            # Empty list means "use Docker defaults"
            return []

        return self._validate_dns_servers(dns_servers)

    def _validate_dns_servers(self, dns_servers: List[str]) -> List[str]:
        """Validate DNS servers list, filtering out invalid IP addresses"""
        if not isinstance(dns_servers, list):
            raise ValueError("DNS servers must be a list")

        valid_servers = []

        for server in dns_servers:
            try:
                # Validate IP address format
                ipaddress.ip_address(server)
                valid_servers.append(server)
            except ValueError:
                print(f"Warning: Invalid DNS server address '{server}' - skipping")

        return valid_servers

    def _default_global_config(self):
        return {
            "port_range": {"min": 8000, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://localhost:{port}",
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "default_image": "tylercollison2089/vscode-claude:latest",
            "docker_network": None,  # Default no network
            "dns_servers": None  # Default no custom DNS servers
        }

    def _save_config(self, config):
        """Save configuration to global config file"""
        config_file = self.config_dir / "global-config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

    def run_setup_wizard(self):
        """Run the interactive setup wizard."""
        from .wizard.setup_wizard import SetupWizard
        from .wizard.field_handlers import (
            PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler
        )

        wizard = SetupWizard(self)

        # Register field handlers
        wizard.register_field_handler("port_range", PortRangeFieldHandler())
        wizard.register_field_handler(
            "default_image",
            StringFieldHandler(
                "default_image",
                "Default Docker image for new instances",
                "tylercollison2089/vscode-claude:latest"
            )
        )
        wizard.register_field_handler(
            "include_docker_sock",
            BooleanFieldHandler(
                "include_docker_sock",
                "Mount Docker socket for Docker-in-Docker support",
                True
            )
        )

        return wizard.run()