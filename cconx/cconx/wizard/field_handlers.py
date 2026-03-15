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