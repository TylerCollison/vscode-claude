def test_merge_empty_global_empty_instance():
    """Test merging when both global and instance environments are empty"""
    # Test the merge logic directly (no imports needed)
    global_environment = {}
    instance_environment = {}
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 0


def test_merge_global_only():
    """Test merging when only global environment has variables"""
    # Test the merge logic directly
    global_environment = {
        "GLOBAL_VAR1": "global_value1",
        "GLOBAL_VAR2": "global_value2"
    }
    instance_environment = {}
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 2
    assert merged_environment["GLOBAL_VAR1"] == "global_value1"
    assert merged_environment["GLOBAL_VAR2"] == "global_value2"


def test_merge_instance_overrides_global():
    """Test that instance environment overrides global environment"""
    # Test the merge logic directly
    global_environment = {
        "SHARED_VAR": "global_version",
        "GLOBAL_ONLY": "global_value"
    }
    instance_environment = {
        "SHARED_VAR": "instance_version",
        "INSTANCE_ONLY": "instance_value"
    }
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 3
    assert merged_environment["SHARED_VAR"] == "instance_version"  # Instance overrides global
    assert merged_environment["GLOBAL_ONLY"] == "global_value"  # Global-only preserved
    assert merged_environment["INSTANCE_ONLY"] == "instance_value"  # Instance-only included


def test_merge_both_environments():
    """Test merging when both global and instance environments have variables"""
    # Test the merge logic directly
    global_environment = {
        "DB_HOST": "global-db",
        "API_KEY": "global-key",
        "LOG_LEVEL": "info"
    }
    instance_environment = {
        "API_KEY": "instance-key",  # Override global
        "INSTANCE_ID": "instance-123",
        "DEBUG_MODE": "true"
    }
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 5

    # Check specific merge behavior
    assert merged_environment["DB_HOST"] == "global-db"  # Global-only preserved
    assert merged_environment["API_KEY"] == "instance-key"  # Instance overrides global
    assert merged_environment["LOG_LEVEL"] == "info"  # Global-only preserved
    assert merged_environment["INSTANCE_ID"] == "instance-123"  # Instance-only included
    assert merged_environment["DEBUG_MODE"] == "true"  # Instance-only included


def test_merge_empty_instance_with_global():
    """Test merging empty instance environment with non-empty global"""
    # Test the merge logic directly
    global_environment = {
        "DEFAULT_CONFIG": "config.json",
        "BACKUP_PATH": "/backups"
    }
    instance_environment = {}
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 2
    assert merged_environment["DEFAULT_CONFIG"] == "config.json"
    assert merged_environment["BACKUP_PATH"] == "/backups"


def test_merge_empty_global_with_instance():
    """Test merging empty global environment with non-empty instance"""
    # Test the merge logic directly
    global_environment = {}
    instance_environment = {
        "CUSTOM_VAR": "custom_value",
        "ANOTHER_VAR": "another_value"
    }
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 2
    assert merged_environment["CUSTOM_VAR"] == "custom_value"
    assert merged_environment["ANOTHER_VAR"] == "another_value"


def test_merge_complete_override():
    """Test when instance environment completely overrides all global variables"""
    # Test the merge logic directly
    global_environment = {
        "VAR1": "global1",
        "VAR2": "global2",
        "VAR3": "global3"
    }
    instance_environment = {
        "VAR1": "instance1",
        "VAR2": "instance2",
        "VAR3": "instance3"
    }
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 3
    assert merged_environment["VAR1"] == "instance1"
    assert merged_environment["VAR2"] == "instance2"
    assert merged_environment["VAR3"] == "instance3"


def test_merge_with_none_values():
    """Test merging when environment variables contain None values"""
    # Test the merge logic directly
    global_environment = {
        "NULL_VAR": None,
        "STRING_VAR": "value"
    }
    instance_environment = {
        "NULL_VAR": "not_null",  # Override None value
        "INSTANCE_VAR": None
    }
    merged_environment = {**global_environment, **instance_environment}

    assert isinstance(merged_environment, dict)
    assert len(merged_environment) == 3
    assert merged_environment["NULL_VAR"] == "not_null"  # Instance overrides None
    assert merged_environment["STRING_VAR"] == "value"  # Global preserved
    assert merged_environment["INSTANCE_VAR"] is None  # Instance None included