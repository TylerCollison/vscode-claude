"""Tests for cconx setup wizard."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_field_handler_abc():
    """Test FieldHandler abstract base class."""
    from cconx.wizard.field_handlers import FieldHandler

    # Should raise TypeError when instantiated directly
    try:
        FieldHandler("test")
        assert False, "Should not be able to instantiate ABC"
    except TypeError:
        pass


def test_setup_wizard_creation():
    """Test SetupWizard class creation."""
    from unittest.mock import MagicMock
    from cconx.wizard.setup_wizard import SetupWizard

    mock_config_manager = MagicMock()
    wizard = SetupWizard(mock_config_manager)

    assert wizard.config_manager == mock_config_manager
    assert isinstance(wizard.field_handlers, dict)
    assert len(wizard.field_handlers) == 0


def test_setup_wizard_run_method():
    """Test SetupWizard run method with mock handlers."""
    from unittest.mock import MagicMock, patch
    from cconx.wizard.setup_wizard import SetupWizard
    from cconx.wizard.field_handlers import StringFieldHandler

    mock_config_manager = MagicMock()
    mock_config_manager.load_global_config.return_value = {}

    wizard = SetupWizard(mock_config_manager)
    handler = StringFieldHandler("test_field", "Test explanation", "default")
    wizard.register_field_handler("test_field", handler)

    with patch('builtins.input', return_value="test_value"):
        with patch('builtins.print'):
            result = wizard.run()

    assert "test_field" in result
    assert result["test_field"] == "test_value"


def test_setup_wizard_preserves_existing_config():
    """Test that wizard preserves existing configuration values."""
    from unittest.mock import MagicMock, patch
    from cconx.wizard.setup_wizard import SetupWizard
    from cconx.wizard.field_handlers import StringFieldHandler

    mock_config_manager = MagicMock()
    mock_config_manager.load_global_config.return_value = {"existing_field": "existing_value"}

    wizard = SetupWizard(mock_config_manager)
    handler = StringFieldHandler("test_field", "Test explanation", "default")
    wizard.register_field_handler("test_field", handler)

    with patch('builtins.input', return_value=""):
        with patch('builtins.print'):
            result = wizard.run()

    assert "existing_field" in result
    assert result["existing_field"] == "existing_value"
    assert "test_field" in result




def test_string_field_handler():
    """Test StringFieldHandler functionality."""
    from cconx.wizard.field_handlers import StringFieldHandler

    handler = StringFieldHandler("test_field", "Test explanation", "default_value")

    assert handler.field_name == "test_field"
    assert handler.get_explanation() == "Test explanation"
    assert handler.get_default() == "default_value"
    assert handler.validate("test") == True
    assert handler.validate(123) == False
    assert handler.format("test") == "test"


def test_boolean_field_handler():
    """Test BooleanFieldHandler functionality."""
    from cconx.wizard.field_handlers import BooleanFieldHandler

    handler = BooleanFieldHandler("test_field", "Test explanation", True)

    assert handler.field_name == "test_field"
    assert handler.get_explanation() == "Test explanation"
    assert handler.get_default() == True
    assert handler.validate(True) == True
    assert handler.validate("string") == False
    assert handler.format(True) == True


def test_port_range_field_handler():
    """Test PortRangeFieldHandler functionality."""
    from cconx.wizard.field_handlers import PortRangeFieldHandler

    handler = PortRangeFieldHandler()

    assert handler.field_name == "port_range"
    assert "port range" in handler.get_explanation().lower()

    # Test validation
    assert handler.validate({"min": "8000", "max": "9000"}) == True
    assert handler.validate({"min": "9000", "max": "8000"}) == False  # min > max
    assert handler.validate({"min": "0", "max": "9000"}) == False     # min too low
    assert handler.validate({"min": "8000", "max": "70000"}) == False # max too high

    # Test formatting
    formatted = handler.format({"min": "8000", "max": "9000"})
    assert formatted == {"min": 8000, "max": 9000}


def test_setup_command_integration():
    """Test setup command integration with CLI."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    from unittest.mock import MagicMock, patch

    # Test the ConfigManager.run_setup_wizard method directly
    with patch('cconx.wizard.setup_wizard.SetupWizard') as mock_wizard_class:
        mock_wizard = MagicMock()
        mock_wizard_class.return_value = mock_wizard
        mock_wizard.run.return_value = {"test": "config"}

        from cconx.config import ConfigManager
        config_manager = ConfigManager()

        result = config_manager.run_setup_wizard()

        # Verify wizard was created and run
        mock_wizard_class.assert_called_once_with(config_manager)
        mock_wizard.run.assert_called_once()
        assert result == {"test": "config"}


if __name__ == "__main__":
    # Run all test functions
    test_field_handler_abc()
    test_setup_wizard_creation()
    test_setup_wizard_run_method()
    test_setup_wizard_preserves_existing_config()
    test_string_field_handler()
    test_boolean_field_handler()
    test_port_range_field_handler()
    test_setup_command_integration()
    print("All tests passed!")