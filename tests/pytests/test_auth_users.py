from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.deploy.auth_users import (
    AuthUsersError,
    AuthentikGroup,
    AuthentikUser,
    UserSpec,
    add_user,
    build_parser,
    config_from_env_or_args,
    remove_user,
    sync_users,
    user_spec_from_email,
    user_specs_from_file,
)


@dataclass
class FakeAuthentikClient:
    users: list[AuthentikUser] = field(default_factory=list)
    groups: list[AuthentikGroup] = field(default_factory=list)
    group_members: dict[str, set[int]] = field(default_factory=dict)
    operations: list[str] = field(default_factory=list)

    def list_group_users(self, *, group_name: str) -> list[AuthentikUser]:
        group = self.find_group(group_name=group_name)
        if group is None:
            return []
        member_pks = self.group_members.get(group.pk, set())
        return [user for user in self.users if user.pk in member_pks]

    def ensure_group(self, *, group_name: str) -> AuthentikGroup:
        existing_group = self.find_group(group_name=group_name)
        if existing_group is not None:
            return existing_group
        group = AuthentikGroup(pk=f"group-{len(self.groups) + 1}", name=group_name)
        self.groups.append(group)
        self.group_members[group.pk] = set()
        self.operations.append(f"create-group:{group_name}")
        return group

    def ensure_user(self, *, user_spec: UserSpec) -> AuthentikUser:
        existing_user = self.find_user(email=user_spec.email)
        if existing_user is not None:
            return existing_user
        user = AuthentikUser(pk=len(self.users) + 1, username=user_spec.username, email=user_spec.email, name=user_spec.name)
        self.users.append(user)
        self.operations.append(f"create-user:{user.email}")
        return user

    def add_user_to_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool:
        self.group_members.setdefault(group.pk, set()).add(user.pk)
        self.operations.append(f"add-user:{user.email}:{group.name}")
        return True

    def remove_user_from_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool:
        self.group_members.setdefault(group.pk, set()).discard(user.pk)
        self.operations.append(f"remove-user:{user.email}:{group.name}")
        return True

    def find_user(self, *, email: str) -> AuthentikUser | None:
        normalized_email = email.strip().lower()
        return next((user for user in self.users if user.email == normalized_email), None)

    def find_group(self, *, group_name: str) -> AuthentikGroup | None:
        return next((group for group in self.groups if group.name == group_name), None)

    def deactivate_user(self, *, user: AuthentikUser) -> bool:
        self.operations.append(f"deactivate-user:{user.email}")
        return True


def test_user_spec_from_email_normalizes_defaults() -> None:
    spec = user_spec_from_email(email="User@Example.COM")

    assert spec.email == "user@example.com"
    assert spec.username == "user@example.com"
    assert spec.name == "user@example.com"


def test_user_spec_from_email_rejects_invalid_email() -> None:
    with pytest.raises(AuthUsersError):
        user_spec_from_email(email="not-an-email")


def test_add_user_dry_run_does_not_call_client() -> None:
    client = FakeAuthentikClient()
    result = add_user(
        client=client,
        user_spec=user_spec_from_email(email="user@example.com"),
        group_name="approved-users",
        dry_run=True,
    )

    assert result.changed is False
    assert result.target == "user@example.com"
    assert client.operations == []


def test_add_user_creates_group_user_and_membership() -> None:
    client = FakeAuthentikClient()
    result = add_user(
        client=client,
        user_spec=user_spec_from_email(email="user@example.com", name="Example User"),
        group_name="approved-users",
        dry_run=False,
    )

    assert result.changed is True
    assert client.operations == [
        "create-group:approved-users",
        "create-user:user@example.com",
        "add-user:user@example.com:approved-users",
    ]
    assert [user.email for user in client.list_group_users(group_name="approved-users")] == ["user@example.com"]


def test_add_user_is_idempotent_when_user_is_already_in_group() -> None:
    client = FakeAuthentikClient()
    user_spec = user_spec_from_email(email="user@example.com")
    first_result = add_user(client=client, user_spec=user_spec, group_name="approved-users", dry_run=False)
    client.operations.clear()

    second_result = add_user(client=client, user_spec=user_spec, group_name="approved-users", dry_run=False)

    assert first_result.changed is True
    assert second_result.changed is False
    assert second_result.detail == "already in group approved-users"
    assert client.operations == []


def test_remove_user_removes_group_membership_and_deactivates() -> None:
    client = FakeAuthentikClient()
    user_spec = user_spec_from_email(email="user@example.com")
    add_user(client=client, user_spec=user_spec, group_name="approved-users", dry_run=False)
    client.operations.clear()

    result = remove_user(
        client=client,
        email="user@example.com",
        group_name="approved-users",
        deactivate=True,
        dry_run=False,
    )

    assert result.changed is True
    assert client.list_group_users(group_name="approved-users") == []
    assert client.operations == [
        "remove-user:user@example.com:approved-users",
        "deactivate-user:user@example.com",
    ]


def test_user_specs_from_file_skips_comments_and_reads_optional_fields(tmp_path: Path) -> None:
    user_file = tmp_path / "users.csv"
    user_file.write_text(
        "# approved users\n"
        "one@example.com\n"
        "two@example.com,two,Two User\n",
        encoding="utf-8",
    )

    specs = user_specs_from_file(user_file)

    assert [(spec.email, spec.username, spec.name) for spec in specs] == [
        ("one@example.com", "one@example.com", "one@example.com"),
        ("two@example.com", "two", "Two User"),
    ]


def test_sync_users_uses_add_contract_for_each_user() -> None:
    client = FakeAuthentikClient()
    user_specs = [user_spec_from_email(email="one@example.com"), user_spec_from_email(email="two@example.com")]

    results = sync_users(client=client, user_specs=user_specs, group_name="approved-users", dry_run=False)

    assert [result.target for result in results] == ["one@example.com", "two@example.com"]
    assert [user.email for user in client.list_group_users(group_name="approved-users")] == ["one@example.com", "two@example.com"]


def test_config_from_args_allows_dry_run_without_token() -> None:
    args = build_parser().parse_args(["list", "--base-url", "auth.example.com", "--group", "approved-users", "--dry-run"])

    config = config_from_env_or_args(args)

    assert config.base_url == "https://auth.example.com"
    assert config.api_token == ""
    assert config.group_name == "approved-users"