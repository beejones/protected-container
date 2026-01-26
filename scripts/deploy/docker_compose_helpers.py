import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def load_docker_compose_config(cwd: Path) -> Dict[str, Any]:
    """
    Runs `docker compose config --format json` in the specified directory
    and returns the parsed JSON configuration.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to load docker-compose config: {e.stderr}"
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse docker-compose config output: {e}") from e


def get_service_config(compose_config: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Retrieve the configuration for a specific service."""
    services = compose_config.get("services", {})
    if service_name not in services:
        raise ValueError(f"Service '{service_name}' not found in docker-compose config.")
    return services[service_name]


def get_env_var(service_config: Dict[str, Any], env_name: str) -> Optional[str]:
    """Get an environment variable value from a service config."""
    environment = service_config.get("environment", {})
    # Environment can be a dict or a list in docker-compose
    if isinstance(environment, dict):
        return environment.get(env_name)
    elif isinstance(environment, list):
        for item in environment:
            if item.startswith(f"{env_name}="):
                return item.split("=", 1)[1]
    return None


def get_image(service_config: Dict[str, Any]) -> str:
    """Get the image name for a service."""
    return service_config.get("image", "")

def get_ports(service_config: Dict[str, Any]) -> list:
    """Get the exposed ports for a service."""
    # Ports structure in the JSON output from `docker compose config` is a list of dicts
    # e.g., [{'mode': 'ingress', 'target': 80, 'published': '80', 'protocol': 'tcp'}]
    ports = service_config.get("ports", [])
    return ports
