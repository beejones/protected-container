# code-server base container
# Provides VS Code in browser with Azure Key Vault integration

FROM codercom/code-server:latest

USER root

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install Azure CLI for Key Vault access
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Create workspace directory
RUN mkdir -p /home/coder/workspace && chown -R coder:coder /home/coder/workspace

# Prepare the default log directory for the non-root code-server process.
RUN mkdir -p /app/logs && chown -R coder:coder /app

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Install VS Code extensions
USER coder
RUN code-server --install-extension rooveterinaryinc.roo-cline \
    && code-server --install-extension GitHub.vscode-pull-request-github

USER root

# Copy startup script
COPY azure_start.sh /usr/local/bin/azure_start.sh
RUN chmod +x /usr/local/bin/azure_start.sh

# Copy Ubuntu startup script (no Azure CLI/Key Vault usage)
COPY ubuntu_start.sh /usr/local/bin/ubuntu_start.sh
RUN chmod +x /usr/local/bin/ubuntu_start.sh

# Copy code-server logging wrapper (daily file rollover by date)
COPY run_code_server_with_daily_logs.sh /usr/local/bin/run_code_server_with_daily_logs.sh
RUN chmod +x /usr/local/bin/run_code_server_with_daily_logs.sh

EXPOSE 8080

# Environment defaults
ENV CODE_SERVER_PORT=8080 \
    WORKSPACE_DIR=/home/coder/workspace

# Entrypoint fetches secrets from Key Vault, then starts supervisor
ENTRYPOINT ["/usr/local/bin/azure_start.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
