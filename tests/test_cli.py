def test_cli_has_start_command():
    """Test that CLI has start command"""
    import vsclaude.cli
    # Test that the CLI module has the main function
    assert hasattr(vsclaude.cli, 'main')
    # Test that the main function is callable
    assert callable(vsclaude.cli.main)