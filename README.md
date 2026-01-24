# Protected Azure Container

A world-class protected container setup featuring:
- **VS Code in browser** via [code-server](https://github.com/coder/code-server)
- **TLS termination** with automatic Let's Encrypt certificates via Caddy
- **Azure Key Vault** integration for secrets management
- **Azure Managed Identity** for secure authentication
- **GitHub Actions** CI/CD with OIDC authentication

## Quick Start (Local Development)

```bash
# Copy example environment files
cp env.example .env
cp env.deploy.example .env.deploy

# Generate a Basic Auth password hash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'

# Add the hash to .env
echo 'BASIC_AUTH_USER=admin' >> .env
echo 'BASIC_AUTH_HASH=<paste-hash-here>' >> .env

# Start the containers
docker compose up --build
```

Open `https://localhost` (accept the self-signed cert warning for local dev).

## Architecture

Two containers in a container group:

| Container | Purpose | Ports |
|-----------|---------|-------|
| `protected-azure-container` | code-server (VS Code) | 8080 (internal) |
| `tls-proxy` (Caddy) | TLS termination + Basic Auth | 80, 443 |

```
Internet → Caddy (443) → [Basic Auth] → code-server (8080)
```

## Documentation

- [Azure Container Deployment](docs/AZURE_CONTAINER.md) - Deploy to Azure Container Instances
- [code-server Setup](docs/CODE_SERVER.md) - Configuration and customization

## Pre-installed Extensions

- **Roo Code** (`rooveterinaryinc.roo-cline`) - AI coding assistant
- **GitHub Pull Requests** (`GitHub.vscode-pull-request-github`) - PR management

## Environment Variables

This repo uses a strict, schema-driven set of env keys.

- Runtime config lives in `.env` (and is uploaded to Key Vault as a single secret).
- Deploy-time config lives in `.env.deploy`.
- Deployment reads `.env` first, then `.env.deploy` on top (deploy-time overrides).

See env.example and env.deploy.example for the canonical keys.

## License

MIT License - see [LICENSE](LICENSE)
