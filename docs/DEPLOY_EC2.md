# Running on AWS EC2

The dashboard is served on the instance's public address. Nothing in the UI is
tied to `localhost`: the browser calls `/api` on whatever origin served the
page, and the web server forwards it to the API inside the machine.

## What is exposed

| Port | Service | Bound to | Open in the security group? |
|---|---|---|---|
| `WEB_PORT` (default 5173) | Web UI, and `/api` through it | all interfaces | **Yes**, this one only |
| 8000 | API directly, `/docs` | loopback | No |
| 8545 | Hardhat node | loopback | **Never** |

The Hardhat node has unlocked accounts, so anyone who can reach port 8545 can
write to the registry as admin. It is bound to loopback for that reason.

## Read this before opening the port

**This is a demo with mock authentication.** Anyone who can load the page can
act as any user, approve payments (mock ones), switch AI off, tamper with
receipts and reset the data. That is by design for a walkthrough and is not
safe for an open audience.

- Restrict the security group's inbound rule to **your own IP address** (or
  your interviewer's), not `0.0.0.0/0`.
- Traffic is plain HTTP. For anything longer-lived, put it behind a load
  balancer or reverse proxy with TLS and real authentication.
- No real money, credentials or personal data are involved, so the exposure is
  limited to people playing with your demo. It is still your instance.

## Steps

Assumed instance: Ubuntu 22.04 or 24.04, `t3.small` or larger (the image build
compiles the contract and bundles the UI; 2 GB of memory is comfortable).
The port bindings and non-loopback access were verified on a local Linux host;
these steps have not been run on an EC2 instance from this repository's CI.

```bash
# 1. Docker
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER" && newgrp docker

# 2. The project
git clone <this repository> trustchain-ai && cd trustchain-ai

# 3. Start. Use WEB_PORT=80 to serve on the default HTTP port.
WEB_PORT=80 docker compose up --build -d

# 4. The address to open
scripts/public-url.sh 80
```

`scripts/public-url.sh` reads the public hostname from EC2 instance metadata
and prints, for example, `http://ec2-203-0-113-10.compute-1.amazonaws.com`.

Then in the EC2 console: **Security group → Inbound rules → Add rule**: Custom
TCP (or HTTP), port 80 (or your `WEB_PORT`), source *My IP*.

Check from the instance that everything is healthy:

```bash
docker compose ps
python3 scripts/smoke.py          # runs every demo story against the API
```

Stop and remove everything, including the chain's state:

```bash
docker compose down -v
```

## Without Docker

`make install && make demo` also works on the instance. The script detects the
public hostname, tells the Vite dev server to accept it, and prints the public
URL. This runs a development server; prefer Docker for anything you leave up.

## Reaching the API docs

`/docs` is on port 8000, which is not published. Use an SSH tunnel:

```bash
ssh -L 8000:localhost:8000 ubuntu@<public address>
# then open http://localhost:8000/docs on your own machine
```

## Notes

- The public IP changes when the instance is stopped and started, unless you
  attach an Elastic IP.
- All state is ephemeral: the chain and the database start empty on every
  `docker compose up`.
