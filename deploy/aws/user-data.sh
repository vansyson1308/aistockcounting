#!/bin/bash
# TrayAgent EC2 user data (Amazon Linux 2023, arm64). Runs once, as root, at
# first boot. infra/aws/trayagent_stack.py fills in the @@...@@ placeholders
# and strips comment lines.
#
# It only bootstraps the host (Docker, the compose plugin, the Postgres
# password) and hands over to /opt/trayagent/update.sh, which fetches the
# desired state from SSM Parameter Store. Keeping user data this small means
# a config change never needs it to run again. Output: /var/log/trayagent-bootstrap.log
set -euo pipefail
exec > >(tee -a /var/log/trayagent-bootstrap.log) 2>&1

AWS_REGION="@@REGION@@"
PARAM_PREFIX="@@PARAM_PREFIX@@"
ELASTIC_IP="@@ELASTIC_IP@@"
COMPOSE_VERSION="@@COMPOSE_VERSION@@"

retry() { # retry <attempts> <command...>
  local attempts=$1 n=1
  shift
  until "$@"; do
    if ((n >= attempts)); then return 1; fi
    echo "attempt $n/$attempts failed: $*"
    sleep $((n * 5))
    n=$((n + 1))
  done
}

# The Elastic IP is associated right after launch. It replaces the temporary
# public IP (there is no NAT gateway), so wait for it before downloading
# anything, or a download could break half-way.
imds() {
  local token
  token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  curl -fsS -H "X-aws-ec2-metadata-token: $token" "http://169.254.169.254/latest/meta-data/$1"
}
for _ in $(seq 1 60); do
  [[ "$(imds public-ipv4 || true)" == "$ELASTIC_IP" ]] && break
  sleep 5
done
echo "public IPv4: $(imds public-ipv4 || echo unknown)"

# Docker from the AL2023 repositories; the compose v2 plugin from its GitHub
# release (AL2023 does not package it), checked against the published SHA-256.
retry 5 dnf install -y docker
systemctl enable --now docker
plugin_dir=/usr/local/lib/docker/cli-plugins
base_url="https://github.com/docker/compose/releases/download/$COMPOSE_VERSION"
mkdir -p "$plugin_dir"
retry 5 curl -fsSL -o /tmp/docker-compose "$base_url/docker-compose-linux-aarch64"
retry 5 curl -fsSL -o /tmp/docker-compose.sha256 "$base_url/docker-compose-linux-aarch64.sha256"
echo "$(cut -d' ' -f1 /tmp/docker-compose.sha256)  /tmp/docker-compose" | sha256sum -c -
install -m 755 /tmp/docker-compose "$plugin_dir/docker-compose"
docker compose version

install -d -m 700 /opt/trayagent
install -d -m 755 /opt/trayagent/models /opt/trayagent/pgdata
cat >/opt/trayagent/instance.env <<EOF
AWS_REGION=$AWS_REGION
PARAM_PREFIX=$PARAM_PREFIX
EOF

# The Postgres password is generated here and lives only in this root-only
# file; it is never in the CloudFormation template or in SSM.
if [[ ! -s /opt/trayagent/secrets.env ]]; then
  (umask 077 && echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >/opt/trayagent/secrets.env)
fi

retry 5 aws ssm get-parameter --region "$AWS_REGION" --name "$PARAM_PREFIX/update-sh" \
  --query Parameter.Value --output text >/opt/trayagent/update.sh
chmod 700 /opt/trayagent/update.sh

# The images may not be in ECR yet on the very first deploy; deploy.sh pushes
# them and then runs update.sh through SSM Run Command.
if ! TRAYAGENT_SELF_UPDATED=1 /opt/trayagent/update.sh; then
  echo "update.sh failed (expected on the first deploy, before the images are pushed)"
fi
echo "bootstrap done"
