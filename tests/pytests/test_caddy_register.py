from __future__ import annotations

import subprocess

from scripts.deploy import caddy_register


def test_domain_present_matches_site_block() -> None:
    text = """
example.com {
    reverse_proxy app:8080
}
"""
    assert caddy_register._domain_present(text, "example.com") is True


def test_domain_present_ignores_commented_site_block() -> None:
    text = """
# example.com {
#     reverse_proxy app:8080
# }
"""
    assert caddy_register._domain_present(text, "example.com") is False


def test_site_block_template_formats_expected_fields() -> None:
    block = caddy_register.SITE_BLOCK_TEMPLATE.format(
        domain="example.com",
        service="my-service",
        port="8080",
    )
    assert "example.com {" in block
    assert "reverse_proxy my-service:8080" in block
    assert "encode gzip" in block


def test_site_block_template_includes_basic_auth_placeholders() -> None:
    block = caddy_register.SITE_BLOCK_TEMPLATE.format(
        domain="example.com",
        service="my-service",
        port="8080",
    )

    assert "basic_auth /* {" in block
    assert "{$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}" in block


def test_ensure_caddy_registration_skips_when_already_present(monkeypatch) -> None:
    calls: list[str] = []
    protected_block = """
example.com {
    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }
    reverse_proxy app:8080
}
"""

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=protected_block, stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)

    out = caddy_register.ensure_caddy_registration(
        ssh_host="user@host",
        domain="example.com",
        service="app",
        port="8080",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is False
    assert len(calls) == 1


def test_ensure_caddy_registration_appends_and_restarts(monkeypatch) -> None:
    state = {"caddyfile": ""}
    append_calls: list[str] = []

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=state["caddyfile"], stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    def fake_subprocess_run(full: list[str], input: str | None = None, text: bool = True, capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        assert text is True
        assert capture_output is True
        assert check is True
        command_text = full[-1]
        append_calls.append(command_text)
        if input is not None and command_text.startswith("tee -a "):
            state["caddyfile"] += input
        return subprocess.CompletedProcess(args=full, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)
    monkeypatch.setattr(caddy_register.subprocess, "run", fake_subprocess_run)

    out = caddy_register.ensure_caddy_registration(
        ssh_host="user@host",
        domain="example.com",
        service="my-service",
        port="8080",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is True
    assert "example.com {" in state["caddyfile"]
    assert "basic_auth /* {" in state["caddyfile"]
    assert "{$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}" in state["caddyfile"]
    assert "reverse_proxy my-service:8080" in state["caddyfile"]
    assert append_calls == ["tee -a /opt/proxy/Caddyfile > /dev/null"]


def test_ensure_caddy_registration_repairs_existing_unprotected_route(monkeypatch) -> None:
    state = {
        "caddyfile": """
example.com {
    reverse_proxy my-service:8080
}
"""
    }

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=state["caddyfile"], stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    def fake_subprocess_run(
        full: list[str],
        input: str | None = None,
        text: bool = True,
        capture_output: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        assert text is True
        assert capture_output is True
        assert check is True
        command_text = full[-1]
        if input is not None:
            if command_text.startswith("tee -a "):
                state["caddyfile"] += input
            else:
                state["caddyfile"] = input
        return subprocess.CompletedProcess(args=full, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)
    monkeypatch.setattr(caddy_register.subprocess, "run", fake_subprocess_run)

    out = caddy_register.ensure_caddy_registration(
        ssh_host="user@host",
        domain="example.com",
        service="my-service",
        port="8080",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is True
    assert state["caddyfile"].count("example.com {") == 1
    assert "basic_auth /* {" in state["caddyfile"]
    assert "{$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}" in state["caddyfile"]
    assert "reverse_proxy my-service:8080" in state["caddyfile"]


def test_ensure_caddy_registration_raises_runtime_error_on_validate_failure(monkeypatch) -> None:
    state = {"caddyfile": ""}

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=state["caddyfile"], stderr="")
        if "caddy validate" in cmd:
            return subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr="invalid caddyfile")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    def fake_subprocess_run(full: list[str], input: str | None = None, text: bool = True, capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        if input:
            state["caddyfile"] += input
        return subprocess.CompletedProcess(args=full, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)
    monkeypatch.setattr(caddy_register.subprocess, "run", fake_subprocess_run)

    try:
        caddy_register.ensure_caddy_registration(
            ssh_host="user@host",
            domain="example.com",
            service="my-service",
            port="8080",
            caddyfile_path="/opt/proxy/Caddyfile",
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        text = str(exc)
        assert "validation failed" in text
        assert "docker logs central-proxy" in text


def test_ensure_caddy_registration_skips_when_public_domain_placeholder_matches(monkeypatch) -> None:
    calls: list[str] = []
    caddyfile_text = """
{$PUBLIC_DOMAIN} {
    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }
    reverse_proxy protected-container:8080
}
"""

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=caddyfile_text, stderr="")
        if "docker inspect" in cmd:
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="example.com\n", stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)

    out = caddy_register.ensure_caddy_registration(
        ssh_host="user@host",
        domain="example.com",
        service="protected-container",
        port="8080",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is False
    assert any("docker inspect" in cmd for cmd in calls)


def test_ensure_caddy_registration_repairs_public_domain_placeholder_with_stale_upstream(monkeypatch) -> None:
    state = {
        "caddyfile": """
{$PUBLIC_DOMAIN} {
    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }
    reverse_proxy protected-container:8080
}
"""
    }

    def fake_ssh_run(host: str, cmd: str, **_: str | bool | None) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=state["caddyfile"], stderr="")
        if "docker inspect" in cmd:
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="example.com\n", stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    def fake_subprocess_run(
        full: list[str],
        input: str | None = None,
        text: bool = True,
        capture_output: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        assert text is True
        assert capture_output is True
        assert check is True
        if input is not None:
            state["caddyfile"] = input
        return subprocess.CompletedProcess(args=full, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)
    monkeypatch.setattr(caddy_register.subprocess, "run", fake_subprocess_run)

    out = caddy_register.ensure_caddy_registration(
        ssh_host="user@host",
        domain="example.com",
        service="stock-dashboard",
        port="3000",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is True
    assert "{$PUBLIC_DOMAIN} {" in state["caddyfile"]
    assert "basic_auth /* {" in state["caddyfile"]
    assert "reverse_proxy stock-dashboard:3000" in state["caddyfile"]
    assert "reverse_proxy protected-container:8080" not in state["caddyfile"]


def test_is_domain_registered_returns_false_for_unprotected_site_block(monkeypatch) -> None:
    caddyfile_text = """
example.com {
    reverse_proxy my-service:8080
}
"""

    def fake_ssh_run(host: str, cmd: str, **_: object) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=caddyfile_text, stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)

    out = caddy_register.is_domain_registered(
        ssh_host="user@host",
        domain="example.com",
        service="my-service",
        port="8080",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is False


def test_is_domain_registered_returns_false_for_public_domain_placeholder_with_stale_upstream(monkeypatch) -> None:
    caddyfile_text = """
{$PUBLIC_DOMAIN} {
    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }
    reverse_proxy protected-container:8080
}
"""

    def fake_ssh_run(host: str, cmd: str, **_: str | bool | None) -> subprocess.CompletedProcess:
        if cmd.startswith("cat "):
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=caddyfile_text, stderr="")
        if "docker inspect" in cmd:
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="example.com\n", stderr="")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(caddy_register, "_ssh_run", fake_ssh_run)

    out = caddy_register.is_domain_registered(
        ssh_host="user@host",
        domain="example.com",
        service="stock-dashboard",
        port="3000",
        caddyfile_path="/opt/proxy/Caddyfile",
    )

    assert out is False
