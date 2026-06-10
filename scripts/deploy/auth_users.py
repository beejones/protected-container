#!/usr/bin/env python3
"""Provision approved users for the central Authentik edge-auth gateway."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence, TypeAlias
from urllib.parse import urljoin

import requests

sys.path.append(str(Path(__file__).parent))

from env_schema import SecretsEnum, VarsEnum


JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


class AuthUsersError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthentikConfig:
    base_url: str
    api_token: str
    group_name: str
    timeout_seconds: float = 20.0


@dataclass(frozen=True)
class UserSpec:
    email: str
    username: str
    name: str


@dataclass(frozen=True)
class AuthentikUser:
    pk: int
    username: str
    email: str
    name: str


@dataclass(frozen=True)
class AuthentikGroup:
    pk: str
    name: str


@dataclass(frozen=True)
class OperationResult:
    action: str
    target: str
    changed: bool
    detail: str


class AuthentikProvisioningClient(Protocol):
    def list_group_users(self, *, group_name: str) -> list[AuthentikUser]: ...

    def ensure_group(self, *, group_name: str) -> AuthentikGroup: ...

    def ensure_user(self, *, user_spec: UserSpec) -> AuthentikUser: ...

    def add_user_to_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool: ...

    def remove_user_from_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool: ...

    def find_user(self, *, email: str) -> AuthentikUser | None: ...

    def find_group(self, *, group_name: str) -> AuthentikGroup | None: ...

    def deactivate_user(self, *, user: AuthentikUser) -> bool: ...


class AuthentikApiClient:
    def __init__(self, *, config: AuthentikConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def list_group_users(self, *, group_name: str) -> list[AuthentikUser]:
        payload = self._api_get_mapping(
            "/api/v3/core/users/",
            params={"groups_by_name": group_name, "include_groups": "true", "page_size": "100"},
        )
        return [_user_from_mapping(item) for item in _results_from_paginated_payload(payload)]

    def ensure_group(self, *, group_name: str) -> AuthentikGroup:
        existing_group = self.find_group(group_name=group_name)
        if existing_group is not None:
            return existing_group

        payload: dict[str, JSONValue] = {
            "name": group_name,
            "is_superuser": False,
            "attributes": {},
        }
        return _group_from_mapping(self._api_post_mapping("/api/v3/core/groups/", payload=payload))

    def ensure_user(self, *, user_spec: UserSpec) -> AuthentikUser:
        existing_user = self.find_user(email=user_spec.email)
        if existing_user is not None:
            return existing_user

        payload: dict[str, JSONValue] = {
            "username": user_spec.username,
            "name": user_spec.name,
            "email": user_spec.email,
            "is_active": True,
            "path": "users/external",
            "type": "external",
            "attributes": {},
        }
        return _user_from_mapping(self._api_post_mapping("/api/v3/core/users/", payload=payload))

    def add_user_to_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool:
        self._api_post_no_content(f"/api/v3/core/groups/{group.pk}/add_user/", payload={"pk": user.pk})
        return True

    def remove_user_from_group(self, *, user: AuthentikUser, group: AuthentikGroup) -> bool:
        self._api_post_no_content(f"/api/v3/core/groups/{group.pk}/remove_user/", payload={"pk": user.pk})
        return True

    def find_user(self, *, email: str) -> AuthentikUser | None:
        payload = self._api_get_mapping(
            "/api/v3/core/users/",
            params={"email": email, "include_groups": "true", "page_size": "1"},
        )
        users = [_user_from_mapping(item) for item in _results_from_paginated_payload(payload)]
        return users[0] if users else None

    def find_group(self, *, group_name: str) -> AuthentikGroup | None:
        payload = self._api_get_mapping(
            "/api/v3/core/groups/",
            params={"name": group_name, "include_users": "true", "page_size": "1"},
        )
        groups = [_group_from_mapping(item) for item in _results_from_paginated_payload(payload)]
        return groups[0] if groups else None

    def deactivate_user(self, *, user: AuthentikUser) -> bool:
        self._api_patch_mapping(f"/api/v3/core/users/{user.pk}/", payload={"is_active": False})
        return True

    def _api_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.api_token}",
        }

    def _api_url(self, path: str) -> str:
        return urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))

    def _api_get_mapping(self, path: str, *, params: Mapping[str, str]) -> Mapping[str, JSONValue]:
        response = self.session.get(
            self._api_url(path),
            headers=self._api_headers(),
            params=params,
            timeout=self.config.timeout_seconds,
        )
        return _mapping_from_response(response)

    def _api_post_mapping(self, path: str, *, payload: Mapping[str, JSONValue]) -> Mapping[str, JSONValue]:
        response = self.session.post(
            self._api_url(path),
            headers=self._api_headers(),
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        return _mapping_from_response(response)

    def _api_patch_mapping(self, path: str, *, payload: Mapping[str, JSONValue]) -> Mapping[str, JSONValue]:
        response = self.session.patch(
            self._api_url(path),
            headers=self._api_headers(),
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        return _mapping_from_response(response)

    def _api_post_no_content(self, path: str, *, payload: Mapping[str, JSONValue]) -> None:
        response = self.session.post(
            self._api_url(path),
            headers=self._api_headers(),
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        _raise_for_status(response)


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = response.status_code
        raise AuthUsersError(f"Authentik API request failed with status {status_code}") from exc


def _mapping_from_response(response: requests.Response) -> Mapping[str, JSONValue]:
    _raise_for_status(response)
    payload: JSONValue = response.json()
    if not isinstance(payload, dict):
        raise AuthUsersError("Authentik API returned a non-object JSON response")
    return payload


def _results_from_paginated_payload(payload: Mapping[str, JSONValue]) -> list[Mapping[str, JSONValue]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise AuthUsersError("Authentik API response is missing a results list")

    results: list[Mapping[str, JSONValue]] = []
    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            raise AuthUsersError("Authentik API result item is not an object")
        results.append(raw_item)
    return results


def _required_str(payload: Mapping[str, JSONValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthUsersError(f"Authentik API response is missing string field: {key}")
    return value.strip()


def _required_int(payload: Mapping[str, JSONValue], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthUsersError(f"Authentik API response is missing integer field: {key}")
    return value


def _user_from_mapping(payload: Mapping[str, JSONValue]) -> AuthentikUser:
    return AuthentikUser(
        pk=_required_int(payload, "pk"),
        username=_required_str(payload, "username"),
        email=str(payload.get("email") or "").strip(),
        name=str(payload.get("name") or "").strip(),
    )


def _group_from_mapping(payload: Mapping[str, JSONValue]) -> AuthentikGroup:
    return AuthentikGroup(
        pk=_required_str(payload, "pk"),
        name=_required_str(payload, "name"),
    )


def user_spec_from_email(*, email: str, username: str | None = None, name: str | None = None) -> UserSpec:
    normalized_email = str(email or "").strip().lower()
    if "@" not in normalized_email:
        raise AuthUsersError("email must contain @")

    normalized_username = str(username or normalized_email).strip()
    normalized_name = str(name or normalized_email).strip()
    if not normalized_username:
        raise AuthUsersError("username must not be empty")
    if not normalized_name:
        raise AuthUsersError("name must not be empty")

    return UserSpec(email=normalized_email, username=normalized_username, name=normalized_name)


def user_specs_from_file(path: Path) -> list[UserSpec]:
    specs: list[UserSpec] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        email = parts[0]
        username = parts[1] if len(parts) > 1 and parts[1] else None
        name = parts[2] if len(parts) > 2 and parts[2] else None
        specs.append(user_spec_from_email(email=email, username=username, name=name))
    return specs


def config_from_env_or_args(args: argparse.Namespace) -> AuthentikConfig:
    raw_base_url = str(args.base_url or os.getenv(VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value) or "").strip()
    api_token = str(args.api_token or os.getenv(SecretsEnum.AUTHENTIK_API_TOKEN.value) or "").strip()
    group_name = str(args.group or os.getenv(VarsEnum.AUTH_POLICY.value) or "protected-container-users").strip()

    if not raw_base_url:
        raise AuthUsersError(f"--base-url or {VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value} is required")
    if not api_token and not bool(args.dry_run):
        raise AuthUsersError(f"--api-token or {SecretsEnum.AUTHENTIK_API_TOKEN.value} is required unless --dry-run is set")
    if not group_name:
        raise AuthUsersError("--group must not be empty")

    base_url = raw_base_url if "://" in raw_base_url else f"https://{raw_base_url}"
    return AuthentikConfig(base_url=base_url, api_token=api_token, group_name=group_name)


def add_user(
    *,
    client: AuthentikProvisioningClient,
    user_spec: UserSpec,
    group_name: str,
    dry_run: bool,
) -> OperationResult:
    if dry_run:
        return OperationResult(
            action="add",
            target=user_spec.email,
            changed=False,
            detail=f"would ensure user is active and belongs to group {group_name}",
        )

    group = client.ensure_group(group_name=group_name)
    user = client.ensure_user(user_spec=user_spec)
    current_users = client.list_group_users(group_name=group.name)
    if any(current_user.pk == user.pk for current_user in current_users):
        return OperationResult(action="add", target=user_spec.email, changed=False, detail=f"already in group {group.name}")

    changed = client.add_user_to_group(user=user, group=group)
    return OperationResult(action="add", target=user_spec.email, changed=changed, detail=f"ensured group {group.name}")


def remove_user(
    *,
    client: AuthentikProvisioningClient,
    email: str,
    group_name: str,
    deactivate: bool,
    dry_run: bool,
) -> OperationResult:
    user_spec = user_spec_from_email(email=email)
    if dry_run:
        action_detail = f"would remove user from group {group_name}"
        if deactivate:
            action_detail = f"{action_detail} and deactivate user"
        return OperationResult(action="remove", target=user_spec.email, changed=False, detail=action_detail)

    user = client.find_user(email=user_spec.email)
    group = client.find_group(group_name=group_name)
    if user is None:
        return OperationResult(action="remove", target=user_spec.email, changed=False, detail="user not found")
    if group is None:
        return OperationResult(action="remove", target=user_spec.email, changed=False, detail="group not found")
    current_users = client.list_group_users(group_name=group.name)
    if not any(current_user.pk == user.pk for current_user in current_users):
        if deactivate:
            changed = client.deactivate_user(user=user)
            return OperationResult(action="remove", target=user_spec.email, changed=changed, detail="user deactivated")
        return OperationResult(action="remove", target=user_spec.email, changed=False, detail=f"not in group {group.name}")

    changed = client.remove_user_from_group(user=user, group=group)
    if deactivate:
        changed = client.deactivate_user(user=user) or changed
    return OperationResult(action="remove", target=user_spec.email, changed=changed, detail=f"removed from group {group.name}")


def sync_users(
    *,
    client: AuthentikProvisioningClient,
    user_specs: Sequence[UserSpec],
    group_name: str,
    dry_run: bool,
) -> list[OperationResult]:
    return [add_user(client=client, user_spec=user_spec, group_name=group_name, dry_run=dry_run) for user_spec in user_specs]


def format_result(result: OperationResult) -> str:
    status = "changed" if result.changed else "ok"
    return f"{result.action}\t{status}\t{result.target}\t{result.detail}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision Authentik users/groups for central edge auth")
    parser.add_argument("action", choices=("list", "add", "remove", "sync"))
    parser.add_argument("--base-url", help=f"Authentik base URL or host; defaults to {VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value}")
    parser.add_argument("--api-token", help=f"Authentik API token; defaults to {SecretsEnum.AUTHENTIK_API_TOKEN.value}")
    parser.add_argument("--group", help=f"Approved Authentik group; defaults to {VarsEnum.AUTH_POLICY.value}")
    parser.add_argument("--email", help="User email for add/remove")
    parser.add_argument("--username", help="Username for add; defaults to email")
    parser.add_argument("--name", help="Display name for add; defaults to email")
    parser.add_argument("--user-file", type=Path, help="File of users for sync: email[,username,name] per line")
    parser.add_argument("--deactivate", action="store_true", help="Deactivate the Authentik user after removing group access")
    parser.add_argument("--dry-run", action="store_true", help="Print intended changes without calling Authentik")
    return parser


def run_with_client(*, args: argparse.Namespace, client: AuthentikProvisioningClient, config: AuthentikConfig) -> list[str]:
    if args.action == "list":
        if args.dry_run:
            return [f"list\tok\t{config.group_name}\twould list approved users"]
        return [f"list\tok\t{user.email}\t{user.username}\t{user.name}" for user in client.list_group_users(group_name=config.group_name)]

    if args.action == "add":
        if not args.email:
            raise AuthUsersError("--email is required for add")
        result = add_user(
            client=client,
            user_spec=user_spec_from_email(email=args.email, username=args.username, name=args.name),
            group_name=config.group_name,
            dry_run=bool(args.dry_run),
        )
        return [format_result(result)]

    if args.action == "remove":
        if not args.email:
            raise AuthUsersError("--email is required for remove")
        result = remove_user(
            client=client,
            email=args.email,
            group_name=config.group_name,
            deactivate=bool(args.deactivate),
            dry_run=bool(args.dry_run),
        )
        return [format_result(result)]

    if args.action == "sync":
        if args.user_file is None:
            raise AuthUsersError("--user-file is required for sync")
        results = sync_users(
            client=client,
            user_specs=user_specs_from_file(args.user_file),
            group_name=config.group_name,
            dry_run=bool(args.dry_run),
        )
        return [format_result(result) for result in results]

    raise AuthUsersError(f"Unsupported action: {args.action}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = config_from_env_or_args(args)
        client = AuthentikApiClient(config=config)
        for output_line in run_with_client(args=args, client=client, config=config):
            print(output_line)
    except AuthUsersError as exc:
        print(f"[auth-users] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())