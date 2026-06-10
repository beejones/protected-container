import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "ubuntu_deploy_proxy.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _copy_proxy_script_fixture(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    script_dir = repo_root / "scripts" / "deploy"
    proxy_dir = repo_root / "docker" / "proxy"
    script_dir.mkdir(parents=True)
    proxy_dir.mkdir(parents=True)
    shutil.copy2(PROXY_SCRIPT, script_dir / "ubuntu_deploy_proxy.sh")
    (proxy_dir / "Caddyfile").write_text("{$PUBLIC_DOMAIN} {\n\treverse_proxy app:8080\n}\n", encoding="utf-8")
    (proxy_dir / "docker-compose.yml").write_text("services:\n  caddy:\n    image: caddy:2-alpine\n", encoding="utf-8")
    return repo_root


def test_proxy_deploy_uses_oidc_profile_and_remote_env_files(tmp_path: Path) -> None:
    repo_root = _copy_proxy_script_fixture(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh_log = tmp_path / "ssh.log"
    rsync_log = tmp_path / "rsync.log"

    _write_executable(
        fake_bin / "ssh",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$FAKE_SSH_LOG\"\n",
    )
    _write_executable(
        fake_bin / "rsync",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$FAKE_RSYNC_LOG\"\n",
    )

    (repo_root / ".env").write_text("ACME_EMAIL=ops@example.com\n", encoding="utf-8")
    (repo_root / ".env.secrets").write_text("BASIC_AUTH_HASH='$2a$14$placeholder'\n", encoding="utf-8")
    (repo_root / ".env.deploy").write_text(
        "\n".join(
            [
                "UBUNTU_SSH_HOST=deploy@example.com",
                "UBUNTU_REMOTE_DIR=/srv/protected-container",
                "PUBLIC_DOMAIN=protected.example.com",
                "EDGE_AUTH_MODE=oidc",
                "AUTHENTIK_PUBLIC_DOMAIN=auth.example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / ".env.deploy.secrets").write_text(
        "AUTHENTIK_SECRET_KEY=secret\nAUTHENTIK_POSTGRESQL__PASSWORD=postgres-secret\n",
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_SSH_LOG": str(ssh_log),
        "FAKE_RSYNC_LOG": str(rsync_log),
    }

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "deploy" / "ubuntu_deploy_proxy.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--profile oidc up -d" in ssh_log.read_text(encoding="utf-8")
    assert ".env.deploy.secrets" in rsync_log.read_text(encoding="utf-8")
    assert "../../.env.deploy.secrets" in ssh_log.read_text(encoding="utf-8")