def test_docker_client_initialization():
    """Test Docker client can be initialized"""
    from vsclaude.vsclaude.docker import DockerClient
    client = DockerClient()
    assert client.client is not None