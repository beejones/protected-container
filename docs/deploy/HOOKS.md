# Deployment Customization Hooks

This repository allows downstream consumers (forks or layered repositories) to customize the deployment process without modifying the core `scripts/deploy/azure_deploy_container.py` script. This makes it easier to pull upstream updates while maintaining custom behavior.

## Overview

Hooks are Python callback methods that run at specific points in the deployment lifecycle. You can implement these hooks to:

- Override default configuration (e.g., container images, resources).
- Enforce custom validation rules.
- Modify the generated Azure Container Instances (ACI) YAML.
- Run pre-flight or post-deploy tasks.

The same hook mechanism is available for `scripts/deploy/ubuntu_deploy.py`.

## Configuration

### Loader Precedence
The hook loader follows this order of precedence for configuration:
1. **CLI Argument**: `--hooks-module <path>`
2. **Environment Variable**: `DEPLOY_HOOKS_MODULE=<path>`
3. **Default**: `scripts/deploy/deploy_customizations.py` (relative to repo root)

> [!IMPORTANT]
> - If an explicit module or path is provided and it cannot be loaded, the deployment will **hard fail**.
> - If the default file `scripts/deploy/deploy_customizations.py` exists but fails to import (e.g., due to syntax errors), the deployment will **hard fail**.
> - Hooks are only skipped (no-op) if the default file is missing and no module was specified.

### Soft Fail Precedence
By default, hook failures abort the deployment. You can enable "soft-fail" mode (log error and continue):
1. **CLI Argument**: `--hooks-soft-fail`
2. **Environment Variable**: `DEPLOY_HOOKS_SOFT_FAIL=true`
3. **Default**: `false`

> [!NOTE]
> When `soft-fail` is enabled, it also covers **loading failures**. If a hook module exists but fails to import, the loader will log a warning and return a dummy hooks object (no-op) instead of raising an error.

### Ubuntu deploy flags

`ubuntu_deploy.py` supports the same hook controls:

- `--hooks-module <path-or-module>`
- `--hooks-soft-fail`

and reads the same environment variables:

- `DEPLOY_HOOKS_MODULE`
- `DEPLOY_HOOKS_SOFT_FAIL`

## Ubuntu Upstream Container Contract

Hooks for Ubuntu deployments should customize the application stack, not the shared platform control plane. The deploy script owns the central Caddy proxy, the external `caddy` Docker network, and the `portainer` admin container. Portainer is expected to be reachable through Caddy at `https://portainer.<base-domain>` on HTTPS port `443`; hooks should not assume direct host access to Portainer on `9000` or `9443`.

Downstream repos that vendor this toolkit as a submodule should run their repo-local deploy wrapper from the downstream repo's virtual environment. The wrapper should call the upstream entrypoint with `repo_root_override` pointing at the downstream repo root. Helper scripts that need Python receive the active Python executable from the deploy engine, so downstream repos should not create or depend on a separate `.venv` inside the toolkit submodule.

Downstream containers do not need to package toolkit proxy helper files. The shared proxy refresh preserves existing Caddy routes from the toolkit side, including temporary upstream checkouts that include the proxy shell script and template but omit standalone helper modules.

Hooks that patch the shared proxy after deployment may rerun `docker compose up -d caddy` in the remote proxy directory. The toolkit refresh writes a proxy-local `.env` for those follow-up Compose commands, so hooks do not need to re-export Caddy Basic Auth or ACME variables.

For web-facing upstream containers, hook customizations must preserve the shared ingress contract:

- Attach the web service to the external `caddy` network.
- Use a unique `container_name` or stack/container naming scheme so Caddy can resolve the upstream target deterministically.
- Keep the public route behind the central Caddy `basic_auth` block unless the deploy docs explicitly define a different edge-auth policy.
- Do not publish public host ports for normal web traffic; expose only the internal container port that Caddy will reverse proxy to.

### Portainer Auth For Ubuntu Hooks

Portainer uses its own API authentication behind the Caddy TLS route. This is separate from the Caddy Basic Auth guard used for application routes.

If a hook or deploy flow needs Portainer API operations, create an access token in the Portainer UI and store the token value in `.env.deploy.secrets`:

```env
PORTAINER_ACCESS_TOKEN=<portainer-api-token>
```

The deploy helpers send this value as Portainer's `X-API-Key` header over `https://portainer.<base-domain>`. Store only the token value, not a `Bearer ...` prefix, and never log it from hook code.

Webhook-only deployments may also use a stack webhook token:

```env
PORTAINER_WEBHOOK_TOKEN=<token-tail-only>
```

Prefer `PORTAINER_ACCESS_TOKEN` when hooks or staging/swap flows need to resolve endpoints, find stacks, create or repair webhooks, stop staging containers, or verify Portainer before triggering the stack. `PORTAINER_WEBHOOK_TOKEN` is enough only when the correct stack webhook already exists and no Portainer API lookup is needed.

## Implementing Hooks

Create a Python module that exports a `get_hooks()` function returning an object (class instance or simple object) that implements any of the methods defined in the protocol. You only need to implement the hooks you care about.

### Example `deploy_customizations.py`

```python
from pathlib import Path

from scripts.deploy.deploy_hooks import DeployContext, DeployPlan
from scripts.deploy.deploy_log import DeployLogSettings

class MyHooks:
    def pre_validate_env(self, ctx: DeployContext) -> None:
        """Called before .env files are validated. Good for injecting defaults."""
        # ctx.env is a live view of os.environ.
        # Modifying it here affects subsequent validation and deployment.
        if "MY_CUSTOM_VAR" not in ctx.env:
             print("Injecting default for MY_CUSTOM_VAR")
             ctx.env["MY_CUSTOM_VAR"] = "default-value"

    def build_deploy_plan(self, ctx: DeployContext, plan: DeployPlan) -> None:
        """Called before YAML generation. Modify the plan here."""
        # Use plan metadata to decide behavior
        if plan.deploy_mode == "full" and plan.deploy_role == "app":
             plan.app_cpu = 4.0
             plan.web_command = ["./start-custom.sh"]

    def post_render_yaml(self, ctx: DeployContext, plan: DeployPlan, yaml_text: str) -> str:
        """Called after YAML generation. Return modified YAML."""
        return yaml_text + "\n# Patched by custom hook"

    def configure_deploy_log(self, ctx: DeployContext, plan: DeployPlan, settings: DeployLogSettings) -> None:
        """Called before ubuntu_deploy.py writes the version log CSV."""
        settings.versioning_enabled = False
        settings.csv_path = Path("out/custom/version_log.csv")

def get_hooks():
    return MyHooks()
```

## Hook Reference

### `pre_validate_env(ctx)`
- **Summary**: Called before strict schema validation and before `.env` files are loaded.
- **Environment Mutability**: `ctx.env` is a mutable mapping. Changes made here are synchronized back to `os.environ` and are visible to the subsequent validation steps.

### `post_validate_env(ctx)`
- **Summary**: After environment variables are loaded and validated.
- **Use for**: Enforcing cross-field validation rules specific to your deployment.

### `build_deploy_plan(ctx, plan)`
- **Summary**: After parsing arguments and Docker Compose defaults, but before generating YAML.
- **Use for**: Overriding images, resources, ports, or command. This is the **preferred** place for most customizations.

For `ubuntu_deploy.py`, this hook is also used to customize storage-manager registration behavior through `plan.extra_metadata` keys:

- `storage_manager_api_url` (str): override resolved Storage Manager API URL.
- `storage_registrations` (list[dict]): override parsed compose-label registrations.
- `enable_default_storage_registration` (bool, default `True`): disable built-in auto-registration if your hook handles registration itself.

### `pre_render_yaml(ctx, plan)`
- **Summary**: Just before the YAML generation function is called.

### `post_render_yaml(ctx, plan, yaml_text) -> str`
- **Summary**: After YAML generation.
- **Use for**: String-based patching of result YAML.

### `pre_az_apply(ctx, plan, yaml_path)`
- **Summary**: Before `az container create` is executed.

### `post_deploy(ctx, plan, deploy_result)`
- **Summary**: After successful deployment.

For `ubuntu_deploy.py`, `deploy_result` includes:

- `storage_registration_count`
- `storage_manager_api_url`
- `default_storage_registration_enabled`

### `configure_deploy_log(ctx, plan, settings)`
- **Summary**: Before `ubuntu_deploy.py` writes `version_log.csv`.
- **Use for**: Customizing where deploy tracking is written and whether deploy logging manages version bumps.

The `settings` object is mutable:

- `settings.csv_path` (`Path`): CSV path to write. Relative paths are resolved from `ctx.repo_root`.
- `settings.versioning_enabled` (`bool`, default `True`): when `False`, deploy rows still record the current `APP_VERSION`. When enabled, repeated records for the same git ref reuse the logged version; successful merge or deploy records for a new git ref bump `APP_VERSION` from the newest successful version-log row unless `.env` is already ahead.

### `on_error(ctx, exc)`
- **Summary**: If an exception occurs during the deployment lifecycle.
- **Note**: This catch includes deployment runtime exceptions but excludes `SystemExit` (e.g. from argparse or direct validation skips).

## Data Structures

### `DeployContext`
- `repo_root`: Path to repository root.
- `env`: Mutable mapping of current environment variables.
- `args`: Parsed command-line arguments.

### `DeployPlan`
Mutable object representing the deployment configuration:
- `deploy_mode`: (e.g., "full", "web-caddy") - the requested deployment mode.
- `compose_service_name`: (e.g., "web") - the specific service being processed.
- `deploy_role`: (e.g., "app", "caddy", "other") - the role in the deployment.
- `app_port`: (int) The principal application port.
- `app_ports`: (list[int]) All ports exposed by the application container.
- `service_mode`: (str) Deployment mode (e.g., "app", "sidecar", "worker").
- `ftp_passive_range`: (str) FTP passive port range if applicable (e.g., "30000-30009").
- `web_command`: list of strings for the application entrypoint.
- `extra_metadata`: A dictionary for custom data.
