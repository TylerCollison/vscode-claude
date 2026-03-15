"""Interactive setup wizard for cconx configuration."""

from typing import Dict, Any, List
from pathlib import Path
from .field_handlers import FieldHandler


class SetupWizard:
    """Interactive wizard for configuring cconx.

    This wizard guides users through setting up the global configuration
    file with interactive prompts and validation.

    Args:
        config_manager: ConfigManager instance for loading/saving configuration
    """

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.field_handlers: Dict[str, FieldHandler] = {}

    def register_field_handler(self, field_name: str, handler: FieldHandler):
        """Register a field handler for configuration.

        Args:
            field_name: Name of the configuration field
            handler: FieldHandler instance for processing this field
        """
        self.field_handlers[field_name] = handler

    def run(self) -> Dict[str, Any]:
        """Run the interactive setup wizard.

        Returns:
            Dictionary containing the new configuration
        """
        print("Welcome to the cconx setup wizard!")
        print("This wizard will help you configure your global cconx settings.\n")

        # Load current configuration
        current_config = self.config_manager.load_global_config()
        new_config = current_config.copy()

        # Process each field
        for field_name, handler in self.field_handlers.items():
            current_value = current_config.get(field_name, handler.get_default())
            new_value = self._process_field(handler, current_value)
            if new_value is not None:
                new_config[field_name] = new_value

        return new_config

    def _process_field(self, handler: FieldHandler, current_value: Any) -> Any:
        """Process a single field with user interaction."""
        print(f"\n=== {handler.field_name.upper().replace('_', ' ')} ===")
        print(f"Description: {handler.get_explanation()}")
        print(f"Current value: {current_value}")

        while True:
            try:
                user_input = handler.prompt(current_value)
                if handler.validate(user_input):
                    return handler.format(user_input)
                else:
                    print("Invalid input. Please check the format and try again.")
            except KeyboardInterrupt:
                print("\nSetup cancelled.")
                return None
            except (ValueError, TypeError) as e:
                print(f"Error: Invalid input format - {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")
                print("Please try again.")