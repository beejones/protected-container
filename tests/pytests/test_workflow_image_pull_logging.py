from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_reports_pull_digest_changes() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "pull_with_digest_report caddy:2-alpine" in workflow
    assert "NEW_IMAGE_DOWNLOADED=" in workflow
    assert "IMAGE_DIGEST_BEFORE=" in workflow
    assert "IMAGE_DIGEST_AFTER=" in workflow


def test_deploy_workflow_reports_pull_and_mirror_digest_changes() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "NEW_IMAGE_DOWNLOADED=" in workflow
    assert "MIRROR_UPDATE_REQUIRED=" in workflow
    assert "IMAGE_DIGEST_BEFORE=" in workflow
    assert "IMAGE_DIGEST_AFTER=" in workflow