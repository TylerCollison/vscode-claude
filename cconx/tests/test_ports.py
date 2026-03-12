def test_find_available_port():
    """Test finding available port in range"""
    from cconx.ports import PortManager
    manager = PortManager(min_port=8000, max_port=8005)
    port = manager.find_available_port()
    assert port >= 8000
    assert port <= 8005