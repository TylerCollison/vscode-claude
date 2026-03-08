import socket

class PortManager:
    def __init__(self, min_port=8000, max_port=9000):
        self.min_port = min_port
        self.max_port = max_port

    def find_available_port(self):
        for port in range(self.min_port, self.max_port + 1):
            if self._is_port_available(port):
                return port
        raise RuntimeError(f"No available ports in range {self.min_port}-{self.max_port}")

    def _is_port_available(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return True
            except OSError:
                return False