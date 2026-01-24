from __future__ import annotations

from pathlib import Path

from scripts.deploy.env_schema import write_dotenv_values


def test_write_dotenv_values_replaces_existing(tmp_path: Path) -> None:
    path = tmp_path / ".env.deploy"
    path.write_text(
        "\n".join(
            [
                "# header",
                "AZURE_SUBSCRIPTION_ID=old",
                "OTHER_KEY=keep",
                "",
            ]
        )
    )

    write_dotenv_values(path=path, updates={"AZURE_SUBSCRIPTION_ID": "new"}, create=False)
    text = path.read_text()

    assert "AZURE_SUBSCRIPTION_ID=new\n" in text
    assert "OTHER_KEY=keep\n" in text
    assert "AZURE_SUBSCRIPTION_ID=old" not in text


def test_write_dotenv_values_appends_missing_sorted(tmp_path: Path) -> None:
    path = tmp_path / ".env.deploy"
    path.write_text("# header\n")

    write_dotenv_values(
        path=path,
        updates={
            "AZURE_TENANT_ID": "tid",
            "AZURE_CLIENT_ID": "cid",
        },
        create=False,
    )
    lines = [l for l in path.read_text().splitlines() if l and not l.startswith("#")]
    assert lines[-2:] == ["AZURE_CLIENT_ID=cid", "AZURE_TENANT_ID=tid"]


def test_write_dotenv_values_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.env"
    assert not path.exists()

    write_dotenv_values(path=path, updates={"AZURE_SUBSCRIPTION_ID": "sid"}, create=True)
    assert path.exists()
    assert "AZURE_SUBSCRIPTION_ID=sid\n" in path.read_text()
