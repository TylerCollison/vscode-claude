"""Field handler classes for configuration wizard."""

from abc import ABC, abstractmethod
from typing import Any


class FieldHandler(ABC):
    """Abstract base class for field handlers."""

    def __init__(self, field_name: str):
        self.field_name = field_name

    @abstractmethod
    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        pass

    @abstractmethod
    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        pass

    @abstractmethod
    def format(self, input_value: Any) -> Any:
        """Format input to appropriate data type."""
        pass

    @abstractmethod
    def get_default(self) -> Any:
        """Provide sensible default value."""
        pass

    @abstractmethod
    def get_explanation(self) -> str:
        """Provide field explanation for user."""
        pass


class StringFieldHandler(FieldHandler):
    """Handler for string fields."""

    def __init__(self, field_name: str, explanation: str, default_value: str = ""):
        super().__init__(field_name)
        self.explanation = explanation
        self.default_value = default_value

    def prompt(self, current_value: Any) -> Any:
        print(f"Description: {self.explanation}")
        default_str = current_value if current_value else self.default_value
        return input(f"Enter value (default: {default_str}): ") or default_str

    def validate(self, input_value: Any) -> bool:
        return isinstance(input_value, str)

    def format(self, input_value: Any) -> Any:
        return str(input_value)

    def get_default(self) -> Any:
        return self.default_value

    def get_explanation(self) -> str:
        return self.explanation


class BooleanFieldHandler(FieldHandler):
    """Handler for boolean fields."""

    def __init__(self, field_name: str, explanation: str, default_value: bool = True):
        super().__init__(field_name)
        self.explanation = explanation
        self.default_value = default_value

    def prompt(self, current_value: Any) -> Any:
        print(f"Description: {self.explanation}")
        default_bool = current_value if current_value is not None else self.default_value
        default_str = "yes" if default_bool else "no"
        response = input(f"Enable? (yes/no, default: {default_str}): ").lower().strip()

        if not response:
            return default_bool

        return response in ["yes", "y", "true", "1"]

    def validate(self, input_value: Any) -> bool:
        return isinstance(input_value, bool)

    def format(self, input_value: Any) -> Any:
        return bool(input_value)

    def get_default(self) -> Any:
        return self.default_value

    def get_explanation(self) -> str:
        return self.explanation


class PortRangeFieldHandler(FieldHandler):
    """Handler for port range configuration."""

    def __init__(self, field_name: str = "port_range"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        default_min = current_value.get("min", 8000) if current_value else 8000
        default_max = current_value.get("max", 9000) if current_value else 9000

        print("Configure port range for instance allocation:")
        min_port = input(f"Minimum port (default: {default_min}): ") or default_min
        max_port = input(f"Maximum port (default: {default_max}): ") or default_max

        return {"min": min_port, "max": max_port}

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, dict):
            return False

        try:
            min_port = int(input_value.get("min", 0))
            max_port = int(input_value.get("max", 0))

            return (1 <= min_port <= 65535 and
                    1 <= max_port <= 65535 and
                    min_port < max_port)
        except (ValueError, TypeError):
            return False

    def format(self, input_value: Any) -> Any:
        return {
            "min": int(input_value["min"]),
            "max": int(input_value["max"])
        }

    def get_default(self) -> Any:
        return {"min": 8000, "max": 9000}

    def get_explanation(self) -> str:
        return "Defines the port range for automatically assigning ports to new instances"


class EnvironmentFieldHandler(FieldHandler):
    """Handler for environment variables configuration."""

    def __init__(self, field_name: str = "environment"):
        super().__init__(field_name)
        self.special_variables = {
            # API Keys & Authentication
            "NIM_API_KEY": "NVIDIA NIM API key",
            "GOOGLE_API_KEY": "Google AI Studio API key",
            "MISTRAL_API_KEY": "Mistral AI API key",
            "OPENROUTER_API_KEY": "OpenRouter API key",

            # Container Configuration
            "PUID": "User ID for container processes",
            "PGID": "Group ID for container processes",
            "TZ": "Timezone configuration (ex. Etc/UTC)",
            "PROXY_DOMAIN": "Reverse proxy domain for external access",
            "DEFAULT_WORKSPACE": "Default workspace directory",
            "PWA_APPNAME": "Progressive Web App name",
            "CCR_PROFILE": "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)",

            # Authentication & Access Control
            "PASSWORD": "Plaintext password for VS Code web interface",
            "SUDO_PASSWORD": "Plaintext sudo password",

            # Git Repository Setup (new)
            "GIT_REPO_URL": "Repository URL to clone on startup",
            "GIT_BRANCH_NAME": "Branch name",

            # Knowledge Repository Integration (new)
            "KNOWLEDGE_REPOS": "Git repos with markdown files to load into CLAUDE.md",

            # Claude Code Configuration
            "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)",
            "CLAUDE_MARKETPLACES": "Comma-separated list of plugin marketplaces",
            "CLAUDE_PLUGINS": "Comma-separated list of plugins to install",

            # Claude Threads Configuration (new)
            "ENABLE_THREADS": "Enable Claude Threads server",
            "MM_ADDRESS": "Mattermost server URL",
            "MM_TOKEN": "Mattermost bot authentication token",
            "MM_TEAM": "Mattermost team name",
            "MM_BOT_NAME": "Bot display name",
            "THREADS_CHROME": "Chrome executable path",
            "THREADS_WORKTREE_MODE": "Git worktree mode",
            "THREADS_SKIP_PERMISSIONS": "Skip permission prompts"
        }

    def prompt(self, current_value: Any) -> Any:
        env_vars = current_value.copy() if current_value else {}

        print("\n=== CONFIGURE ENVIRONMENT VARIABLES ===")
        print("The following special variables are commonly configured:")

        for var_name, description in self.special_variables.items():
            current_val = env_vars.get(var_name, "")
            print(f"\n{var_name}: {description}")
            if current_val:
                print(f"Current value: {current_val}")

            new_value = input(f"Enter value for {var_name} (leave empty to keep current): ")
            if new_value.strip():
                env_vars[var_name] = new_value.strip()
            elif var_name not in env_vars and new_value == "":
                # Skip if no current value and user enters empty
                continue

        # Allow adding arbitrary variables
        print("\n=== ADDITIONAL VARIABLES ===")
        print("You can add any additional environment variables.")
        print("Enter variables as KEY=VALUE pairs, one per line.")
        print("Enter an empty line when finished.\n")

        while True:
            user_input = input("Enter KEY=VALUE (or empty to finish): ").strip()
            if not user_input:
                break

            if "=" in user_input:
                key, value = user_input.split("=", 1)
                env_vars[key.strip()] = value.strip()
            else:
                print("Invalid format. Use KEY=VALUE format.")

        return env_vars

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, dict):
            return False

        # Basic validation - all keys should be strings
        return all(isinstance(key, str) for key in input_value.keys())

    def format(self, input_value: Any) -> Any:
        return dict(input_value)

    def get_default(self) -> Any:
        return {}

    def get_explanation(self) -> str:
        return "Environment variables passed to Docker containers"


class VolumesFieldHandler(FieldHandler):
    """Handler for volume paths configuration."""

    def __init__(self, field_name: str = "enabled_volumes"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        volumes = current_value.copy() if current_value else []

        print("\n=== CONFIGURE VOLUME PATHS ===")
        print("Configure volume paths to mount in containers.")
        print("Paths must start with '/' and be absolute paths.")
        print("Enter one path per line. Enter empty line when finished.\n")

        if volumes:
            print("Current volumes:")
            for vol in volumes:
                print(f"  - {vol}")
            print()

        new_volumes = []

        while True:
            user_input = input("Enter volume path (or empty to finish): ").strip()
            if not user_input:
                break

            if user_input.startswith("/"):
                new_volumes.append(user_input)
                print(f"Added: {user_input}")
            else:
                print("Invalid path. Path must start with '/'.")

        # FIXED: Merge new volumes with existing volumes
        if new_volumes:
            return volumes + new_volumes
        else:
            return volumes

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, list):
            return False

        return all(isinstance(path, str) and path.startswith("/") for path in input_value)

    def format(self, input_value: Any) -> Any:
        return list(input_value)

    def get_default(self) -> Any:
        return []

    def get_explanation(self) -> str:
        return "List of volume paths to mount in Docker containers"