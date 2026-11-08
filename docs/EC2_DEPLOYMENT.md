# Ubuntu EC2 deployment

The production stack runs the existing Next.js UI, FastAPI, PostgreSQL 17/pgvector, Redis and a Celery document worker. Host Caddy provides HTTPS. `compose.production.yml` uses independent named volumes and leaves the existing local `compose.yml`, `.env`, database and UI intact.

## 1. Create the EC2 host

Use Ubuntu 24.04 LTS **x86_64**. Start with 2 vCPUs, 8 GiB RAM and 30–40 GiB encrypted gp3 EBS as an initial capacity estimate, then measure your workload. Building and loading the local embedding/reranking models need memory and disk. Local Docker tests cover amd64, not Graviton/ARM. Allocate an Elastic IP and point your domain's A record to it. Publish an AAAA record only with working IPv6 routing.

Configure inbound rules as follows, following the [AWS security group reference](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html):

| Port | Source | Purpose |
|---|---|---|
| TCP 22 | Your administrator IP `/32` | SSH |
| TCP 80 | `0.0.0.0/0` | Certificate validation and HTTPS redirects |
| TCP 443 | `0.0.0.0/0` | HTTPS application |

Add IPv6 rules for 80/443 only if needed. Do **not** open 5432, 6379, 8100, 3000 or 3080. Database, Redis and backend have no published ports; frontend publishes only `127.0.0.1:3080`. The data network is internal to Docker. Allow outbound DNS/HTTPS for image, package and model downloads and AI provider APIs.

## 2. Install Docker on a fresh Ubuntu instance

```bash
ssh -i /path/to/key.pem ubuntu@YOUR_EC2_IP
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
exit
```

Reconnect, then run `docker version` and `docker compose version`. These steps follow [Docker's Ubuntu documentation](https://docs.docker.com/engine/install/ubuntu/). Use the current Compose plugin, not Python `docker-compose` 1.x. Give Docker group membership only to trusted operators; it grants host administrative capability.

## 3. Upload the source

On your laptop, substitute your key and EC2 IP:

```bash
rsync -az -e 'ssh -i /path/to/key.pem' \
  --exclude='.git' --exclude='.env' --exclude='.env.*' --exclude='.secrets' \
  --exclude='.runtime' --exclude='node_modules' --exclude='.next' \
  --exclude='__pycache__' --exclude='.pytest_cache' --exclude='deployment-backups' \
  /home/jony/Documents/chat/ ubuntu@YOUR_EC2_IP:~/school-insight/
```

Include the supplied SQL and PDF. Do not copy laptop PostgreSQL data directories into the new volume. This procedure starts with the supplied sample data; it preserves your laptop installation but does not migrate later school edits, chat history or app passwords from it.

## 4. Configure secrets

On EC2, replace the domain/email with real values:

```bash
cd ~/school-insight
python3 scripts/configure_deployment.py \
  --domain school.YOUR_DOMAIN.com \
  --email YOUR_CERTIFICATE_CONTACT_EMAIL
```

The generator creates random database passwords in `.secrets/`, plus `.env.production` with non-secret settings. It refuses to overwrite existing configuration. The original `.env` is untouched. Keep the host secret directory private (`0700`); individual mounted secret files are readable by non-root containers. File-backed Compose secrets are not an encrypted vault. Keep them on encrypted EBS and retain a separately encrypted recovery copy. An EC2 instance role can provision files from AWS Secrets Manager later; no AWS access keys are required in the application.

Enter a provider key privately, without putting it in shell history. For example:

```bash
chmod u+w .secrets/gemini_api_key
nano .secrets/gemini_api_key
chmod 0444 .secrets/gemini_api_key
nano .env.production
```

Set `AI_PROVIDER=gemini`, `GEMINI_MODEL` and `GEMINI_MODELS` to exact model IDs available to your account. Alternatively use the OpenAI or Groq key file and corresponding model settings. Unused key files remain empty. Keys never belong in Docker build arguments, the frontend, Git or screenshots. Restart backend/worker after changing keys.

For public HTTPS confirm:

```dotenv
PRODUCT_WEB_ORIGINS=https://school.YOUR_DOMAIN.com
COOKIE_SECURE=true
WEB_PORT=3080
```

Origin matching is exact, with no trailing slash. Do not disable Secure cookies for public deployment.

## 5. Build and start

```bash
cd ~/school-insight
bash scripts/production.sh config --quiet
bash scripts/production.sh build backend frontend
bash scripts/production.sh up -d --wait --wait-timeout 300
bash scripts/production.sh run --rm ingest
bash scripts/production.sh ps -a
```

Bootstrap should exit successfully (code 0); the other five services should be healthy. The first manual ingestion downloads CPU model weights and can take several minutes. Models and uploaded PDFs persist in the runtime volume. `run --rm ingest` safely skips an already indexed manual. Failed ingestion still permits SQL reporting but is not a successful full deployment.

The frontend sends same-origin `/api/*` requests and proxies internally to `http://backend:8100`. This rewrite is compiled during the standalone build; changing the non-secret `API_INTERNAL_URL` build argument requires rebuilding the frontend. Browser clients never need an internal backend hostname or API keys.

API health checks test PostgreSQL/Redis, and the worker check pings its own Celery identity. Long-running services use `unless-stopped` restart policies and start after healthy dependencies. Docker restarts failed processes, but a running unhealthy process is not automatically restarted solely for being unhealthy; monitor health and investigate alerts.

```bash
bash scripts/production.sh logs --tail=100 bootstrap backend worker frontend
curl --fail http://127.0.0.1:3080/api/health
```

View initial app credentials **privately**:

```bash
bash scripts/production.sh exec -T backend cat .runtime/demo-accounts.json
```

EC2 gets new app passwords; the source's placeholder hashes stay unchanged. Change initial passwords in Account settings. Never publish credential output.

## 6. HTTPS using host Caddy

Point DNS to the instance and allow inbound 80/443 first. Install Caddy using its [official Ubuntu instructions](https://caddyserver.com/docs/install#debian-ubuntu-raspbian):

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https gpg curl
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
```

Edit `deploy/Caddyfile.ec2`: replace `school.example.com` and `admin@example.com` with your actual domain/contact. If `WEB_PORT` changed, update the proxy port too. On a new host:

```bash
nano deploy/Caddyfile.ec2
sudo caddy validate --config "$PWD/deploy/Caddyfile.ec2" --adapter caddyfile
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-school-insight
sudo install -m 0644 deploy/Caddyfile.ec2 /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

On a shared host, merge the site block instead of replacing existing sites. Caddy obtains/renews public certificates, redirects HTTP and streams chat without buffering (`flush_interval -1`). Keep Caddy's certificate state during maintenance.

Open **https://school.YOUR_DOMAIN.com/chat**. Test login, student count (Admin: 4), attendance, and a manual question with page citations. Confirm HTTPS and Secure/HttpOnly cookies. Test wrong passwords and student access restrictions. Public HTTPS needs your real domain, DNS and EC2 host and is not claimed by local Docker verification.

## 7. Persistence and preservation

Volumes are `school-insight-production_postgres_data`, `school-insight-production_redis_data` and `school-insight-production_app_runtime`, separate from the local `chat_*` volumes. Do not attach the new stack to an existing cluster volume or change the Compose project name after initialization without deliberately migrating volumes.

The supplied SQL contains `DROP SCHEMA school CASCADE`. It is **not** installed as an automatic PostgreSQL init script. Bootstrap checks the target database first and imports all 29 tables, four views and sample rows only when `school` is absent. Later runs with matching runtime state apply additive migrations only. If school data exists but runtime state is missing, bootstrap stops rather than resetting data. Do not bypass the guard or run the source SQL manually against valuable records.

```bash
bash scripts/production.sh down
bash scripts/production.sh up -d --wait --wait-timeout 300
```

These commands retain volumes. Never use `down -v`, `docker volume prune` or EBS deletion as an update procedure.

## 8. Backups, restore checks and updates

Run on the EC2 host:

```bash
bash deploy/backup.sh
```

This saves a PostgreSQL custom-format dump, runtime archive and checksums under `deployment-backups/`. The archive contains private connection settings, credentials, PDFs and model caches. Copy it to encrypted off-instance storage, for example S3 through an EC2 instance role. Schedule the host script through a systemd timer or cron with an absolute checkout path. It does not mount the Docker socket or give database administrator credentials to app containers.

The database/runtime pair is not atomic; pause writes/uploads during backup when an exact pair is required. Do not run legacy `scripts/backup_product.py` or Celery beat in this stack: those helpers target the previous laptop installation. This production stack runs a document worker, with backups operated on the host.

Verify a dump in a separate database in the same cluster (replace TIMESTAMP):

```bash
bash scripts/production.sh exec -T postgres createdb -U postgres school_restore_check
bash scripts/production.sh exec -T postgres pg_restore -U postgres --exit-on-error -d school_restore_check < deployment-backups/TIMESTAMP/database.dump
bash scripts/production.sh exec -T postgres psql -U postgres -d school_restore_check -c 'SELECT count(*) FROM school.students;'
```

This uses the cluster's existing restricted roles. Leave the live app pointed at `school_ai`. For whole-host disaster recovery, preserve matching `.secrets/`, `.env.production`, runtime archive and database dump together, and recreate restricted roles before restoring into a fresh cluster. Restoring over production requires a separate reviewed recovery procedure. To migrate later laptop edits/history, take its verified database/runtime backup and plan that restore instead of running the sample bootstrap over restored data.

For updates, back up first, upload new source, retain the same secrets/volumes and run:

```bash
bash scripts/production.sh build backend frontend
bash scripts/production.sh up -d --wait --wait-timeout 300
```

Bootstrap applies additive migrations before the API starts. Do not regenerate secrets for updates. Changing a PostgreSQL password file alone does not change passwords stored in an existing cluster; role/password rotation needs an explicit migration.

## 9. Local Docker verification

On a checkout without existing deployment secrets, use `python3 scripts/configure_deployment.py --local-http` instead of the public-domain command, then the same build/start/ingest steps. Open `http://localhost:3080`. This local-only configuration sets the exact HTTP origin and disables Secure cookies. Do not upload this local config for public deployment; generate the HTTPS config on EC2.

```bash
python3 scripts/test_deployment.py
```

The script tests the actual production containers, frontend proxy, logins, SQL permissions and persisted state. `--live` additionally checks configured AI provider answers and manual citations. See `docs/deployment-verification.json` for recorded local results and their scope. Public AWS provisioning and real-domain certificate issuance remain EC2 deployment steps.
