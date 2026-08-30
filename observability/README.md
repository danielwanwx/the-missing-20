# Optional observability profile

The native dashboard is the required zero-dependency demo. This profile adds a
Prometheus scrape and Grafana view for judges who want to inspect the same local
source metrics outside the product.

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/decision_workspace_server.py
docker compose -f observability/docker-compose.yml up
```

Open [Grafana](http://127.0.0.1:3000/d/missing20-live/missing-20-live-operations)
after the containers are healthy. Prometheus scrapes the local experiment's
`/metrics` endpoint; it does not contact AWS or any external provider.

The profile is optional and fail-soft. If Docker or Grafana is unavailable, the
native Dashboard and Agent Workspace continue to work unchanged.
