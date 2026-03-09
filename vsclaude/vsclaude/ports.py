import socket
import docker.errors

class PortManager:
    def __init__(self, min_port=8000, max_port=9000):
        self.min_port = min_port
        self.max_port = max_port
        self.docker_client = docker.from_env()

    def find_available_port(self):
        for port in range(self.min_port, self.max_port + 1):
            if self._is_port_available(port):
                return port
        raise RuntimeError(f"No available ports in range {self.min_port}-{self.max_port}")

    def _is_port_available(self, port):
        # Check if port is used by Docker containers
        try:
            containers = self.docker_client.containers.list(all=True)
            for container in containers:
                container_ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
                for container_port, host_bindings in container_ports.items():
                    if host_bindings:
                        for binding in host_bindings:
                            if binding.get('HostPort') == str(port):
                                return False
        except Exception:
            # If Docker connection fails, fall back to socket binding
            pass

        # Fallback: check if port is available via socket binding
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return True
            except OSError:
                return False