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
        print(f"Description: {self.get_explanation()}")
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