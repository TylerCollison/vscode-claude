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