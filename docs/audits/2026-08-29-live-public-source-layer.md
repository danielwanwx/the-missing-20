# Phase 2 live public source layer

Status: implementation complete; deterministic checks and a public one-shot
smoke are captured below.

## Purpose

The Missing 20 now has a server-side public-context layer for the Port of Los
Angeles to inland-warehouse route. It reads official National Weather Service
alerts and NOAA CO-OPS station `9410660` observations. These observations are
advisory route context only. They do not create an enterprise incident, alter
warehouse/ERP counts, enter the Authority-B ledger, grant an action, or bypass
the existing investigation and approval gates.

The operational enterprise flow remains the repeatable synthetic digital twin.
This boundary is intentional: a free public API does not provide the private
ERP, purchase-order, warehouse, and invoice truth needed for a real enterprise
transaction.

## Data contract and endpoints

`src/the_missing_20/live_sources.py` defines the adapter boundary and normalized
`LiveSourceSnapshot`/`LiveSourceEvent` records. Each record carries:

- provider, source ID, source type, and route location
- transport/data status (`CONNECTED`, `STALE`, `DEGRADED`, or
  `OPTIONAL_NOT_CONFIGURED`)
- source observed timestamp, server received timestamp, and freshness seconds
- normalized metrics/alerts and an official provenance URL
- `new_observation`, registry sequence, and a safe error reason
- `external_context_only: true`

The local server exposes:

- `GET /api/v1/live-sources`: current cached snapshots and advisory route risk
- `GET /api/v1/live-sources/events?after=<cursor>`: bounded poll/event contract
- `GET /healthz`: declares the public source layer and synthetic authority boundary

The browser polls the current endpoint every 15 seconds. NWS and NOAA adapters
enforce a 60-second minimum source interval; the UI does not make browser-side
cross-origin calls. A source heartbeat can animate while connected, but a data
packet pulse is marked only when the source's observed timestamp changes.
For an always-open server poller, set `MISSING20_LIVE_SOURCES_AUTOSTART=1`; the
default is off so deterministic local tests never open a public connection.

Source cards have their own render cursor. The operational 1 Hz render path does
not rebuild them; a card update requires a changed live-source payload/cursor or
an initial host mount. The UI carries disclosure state across source updates
and view changes, and records the last animated source sequence/cursor so a
cached `new_observation` flag cannot replay its pulse during unrelated renders.
The browser smoke also treats official provenance links as inert evidence while
still rejecting actual off-host resource loads.

## Sources and activation

- NWS: `https://api.weather.gov/alerts/active?area=CA`; request includes a stable,
  non-personal User-Agent. The adapter keeps active alert severity, area, and
  timestamps, counts California alerts separately, and only counts alerts whose
  area description matches the Los Angeles/Orange/San Bernardino/Riverside/Inland
  Empire route corridor for route risk. A successful active-feed response stays
  `CONNECTED`; `latest_alert_age_seconds` describes the newest alert event and is
  not a transport-health timeout.
- NOAA CO-OPS: station `9410660`, latest metric water level, datum `MLLW`.
- AISStream: optional server-side adapter for a Port of Los Angeles bounding box.
  Without `AISSTREAM_API_KEY`, the API reports `OPTIONAL_NOT_CONFIGURED` and no
  vessel data is invented. To activate the default bounded WebSocket adapter,
  install the optional extra (`pip install -e '.[live]'`) and set
  `AISSTREAM_API_KEY` in the server environment before starting the server. The
  adapter subscribes to `PositionReport`, collects at most 32 messages in a
  three-second window, and deduplicates MMSIs. The browser never receives the
  key. A deployment may still inject a fetcher for deterministic tests.

The official references are [NWS web services](https://www.weather.gov/documentation/services-web-api),
[NOAA CO-OPS API](https://api.tidesandcurrents.noaa.gov/api/dev), and
[AISStream documentation](https://aisstream.io/documentation).

## Failure behavior

- Timeout/HTTP/parse failure: preserve last-known values, mark the source
  `DEGRADED`, and expose the error type. No new observation pulse is emitted.
- Old NOAA/AIS observation: mark `STALE`; route risk may become `WATCH`. An old
  NWS alert timestamp alone does not make a successful active feed stale.
- Severe NWS alert in the documented route corridor: route risk becomes `HIGH`
  with source IDs and a short reason. Severe alerts outside that corridor do not
  affect route risk.
- Missing AIS key, optional runtime, or WebSocket failure: optional/degraded
  status, never fake traffic.
- Live context failure never blocks or changes the deterministic operational
  lifecycle.

## Evidence

The deterministic source tests cover successful normalization, public User-Agent
redaction, repeated observations, stale data, timeout/error with last-known
preservation, optional AIS states, route-risk correlation, and poller shutdown.
The primary controller can run a one-shot public check with:

```bash
python3 scripts/smoke_live_sources.py --output artifacts/live-sources/smoke.json
```

The resulting artifact must contain only public observations, timestamps, source
IDs, and provenance URLs. It must not contain a key, cookie, or personal email.
The captured smoke artifact is `artifacts/live-sources/smoke.json`: it records
the public NWS and NOAA responses, route-filtered alert metrics, station
`9410660` water level, timestamps, and provenance. AIS remains optional and is
not called unless its server-side key and optional dependency are configured.
