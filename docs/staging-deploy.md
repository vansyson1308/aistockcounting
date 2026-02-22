# Staging Deployment (Ubuntu 22.04+)

## 1) Install Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## 2) Prepare server directory
```bash
sudo mkdir -p /opt/vj-inventory
sudo chown -R $USER:$USER /opt/vj-inventory
cd /opt/vj-inventory
git clone <your-repo-url> current
cd current
cp .env.staging.example .env
# edit .env values
```

## 3) Deploy
```bash
cd /opt/vj-inventory/current
chmod +x ops/deploy_staging.sh ops/smoke_test.sh
./ops/deploy_staging.sh
```

## 4) Verify
- Open `http://<server-ip-or-domain>/`
- API health: `http://<server-ip-or-domain>/api/health`

## Rollback
```bash
cd /opt/vj-inventory/current
./ops/deploy_staging.sh rollback
```
The script restores the previous compose/env snapshot and restarts services.

## HTTPS note
This setup is HTTP-only by default. Put Cloudflare/LB/reverse proxy with TLS in front for production-lite HTTPS.
