from pathlib import Path


def test_dockerfile_prepares_code_server_log_directory_for_coder_user():
    dockerfile = (Path(__file__).parents[2] / "docker" / "Dockerfile").read_text()

    assert "RUN mkdir -p /app/logs && chown -R coder:coder /app" in dockerfile