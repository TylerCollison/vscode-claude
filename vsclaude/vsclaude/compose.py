def generate(instance_name, port, environment_vars):
    environment = {
        "IDE_ADDRESS": f"http://localhost:{port}",
        "PASSWORD": "password",  # Default, can be overridden
        "CCR_PROFILE": "default"  # Default, can be overridden
    }
    environment.update(environment_vars)

    compose_config = {
        "services": {
            "vscode-claude": {
                "image": "tylercollison2089/vscode-claude:latest",
                "container_name": f"vsclaude-{instance_name}",
                "ports": [f"{port}:8443"],
                "environment": [f"{k}={v}" for k, v in environment.items()],
                "volumes": [
                    "/var/run/docker.sock:/var/run/docker.sock",
                    f"{instance_name}-config:/config",
                    f"{instance_name}-workspace:/workspace"
                ],
                "restart": "unless-stopped"
            }
        },
        "volumes": {
            f"{instance_name}-config": {},
            f"{instance_name}-workspace": {}
        }
    }

    return compose_config