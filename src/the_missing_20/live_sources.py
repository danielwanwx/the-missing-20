"""Server-side adapters for live public supply-chain context.

The live-source layer is deliberately separate from the experiment ledger.  NWS,
NOAA, and (optionally) AIS observations are context for a route-risk view; they
are never enterprise facts and can never create an incident, grant an action, or
change the synthetic ERP twin.

The default adapters use only the Python standard library.  Tests inject a small
transport function, so deterministic test runs never need a network connection.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import import_module
from threading import Event, RLock, Thread
from types import TracebackType
from typing import Protocol, cast
from urllib.request import Request, urlopen

LIVE_SOURCE_SCHEMA_VERSION = "missing20-live-sources/v1"
DEFAULT_USER_AGENT = "TheMissing20/0.1 (live supply-chain context)"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?area=CA"
NOAA_WATER_LEVEL_URL = (
    "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    "?date=latest&station=9410660&product=water_level&datum=MLLW"
    "&time_zone=gmt&units=metric&application=TheMissing20&format=json"
)
AISSTREAM_BBOX: tuple[tuple[float, float], tuple[float, float]] = (
    (33.68, -118.35),
    (33.82, -118.12),
)
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
AISSTREAM_FIRST_WINDOW_SECONDS = 3.0
AISSTREAM_MAX_MESSAGES = 32

# The NWS endpoint is intentionally broad (all active California alerts). Only
# these area descriptions belong to the Port of Los Angeles -> Inland Empire
# route context. The complete California count remains available separately,
# but it must not influence route risk.
NWS_ROUTE_AREA_TERMS: tuple[str, ...] = (
    "los angeles",
    "orange",
    "san bernardino",
    "riverside",
    "inland empire",
)


class LiveSourceStatus(StrEnum):
    """Transport/data status shown by the live context strip."""

    CONNECTED = "CONNECTED"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    OPTIONAL_NOT_CONFIGURED = "OPTIONAL_NOT_CONFIGURED"


class LiveSourceAdapter(Protocol):
    """Minimal adapter boundary, kept easy to replace with a real stream."""

    source_id: str
    provider: str
    source_type: str
    poll_interval_seconds: float

    def fetch(self, now: datetime) -> LiveSourceSnapshot:
        """Fetch and normalize one observation."""


class HTTPTransport(Protocol):
    def __call__(self, request: Request, timeout: float) -> bytes:
        """Fetch bytes for a request."""


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS URLs
        return cast(bytes, response.read())


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _freshness(now: datetime, observed_at: datetime | None) -> int | None:
    if observed_at is None:
        return None
    return max(0, int((now - observed_at).total_seconds()))


def _is_route_area(area: str) -> bool:
    normalized = area.casefold()
    return any(term in normalized for term in NWS_ROUTE_AREA_TERMS)


def _status_for_freshness(
    *, freshness_seconds: int | None, max_age_seconds: int, connected: bool = True
) -> LiveSourceStatus:
    if not connected:
        return LiveSourceStatus.DEGRADED
    if freshness_seconds is not None and freshness_seconds > max_age_seconds:
        return LiveSourceStatus.STALE
    return LiveSourceStatus.CONNECTED


@dataclass(frozen=True, slots=True)
class LiveSourceSnapshot:
    """Normalized, serializable state from one public source."""

    provider: str
    source_id: str
    source_type: str
    location: str
    status: LiveSourceStatus
    observed_at: datetime | None
    received_at: datetime
    freshness_seconds: int | None
    metrics: Mapping[str, object]
    alerts: tuple[Mapping[str, object], ...]
    provenance_url: str
    new_observation: bool = False
    sequence: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return an API-safe representation without secrets."""

        return {
            "schema_version": LIVE_SOURCE_SCHEMA_VERSION,
            "provider": self.provider,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "location": self.location,
            "status": self.status.value,
            "observed_at": _iso(self.observed_at),
            "received_at": _iso(self.received_at),
            "freshness_seconds": self.freshness_seconds,
            "metrics": dict(self.metrics),
            "alerts": [dict(item) for item in self.alerts],
            "provenance_url": self.provenance_url,
            "new_observation": self.new_observation,
            "sequence": self.sequence,
            "error": self.error,
            "external_context_only": True,
        }


@dataclass(frozen=True, slots=True)
class LiveSourceEvent:
    """One registry poll result, including repeated observations."""

    sequence: int
    source_id: str
    observed_at: datetime | None
    received_at: datetime
    new_observation: bool
    snapshot: LiveSourceSnapshot

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": LIVE_SOURCE_SCHEMA_VERSION,
            "sequence": self.sequence,
            "source_id": self.source_id,
            "observed_at": _iso(self.observed_at),
            "received_at": _iso(self.received_at),
            "new_observation": self.new_observation,
            "snapshot": self.snapshot.as_dict(),
            "external_context_only": True,
        }


class _HTTPAdapter:
    """Common request and timestamp behavior for public HTTP adapters."""

    def __init__(
        self,
        *,
        transport: HTTPTransport = _default_transport,
        timeout_seconds: float = 8.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_age_seconds: int = 900,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not user_agent.strip() or "@" in user_agent:
            raise ValueError("user_agent must be non-empty and must not contain an email")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent.strip()
        self._max_age_seconds = max_age_seconds

    def _get_json(self, url: str, *, accept: str) -> Mapping[str, object]:
        request = Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": self._user_agent,
            },
        )
        payload = json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("public source returned a non-object JSON payload")
        return payload

    def _snapshot_status(
        self, now: datetime, observed_at: datetime | None
    ) -> tuple[LiveSourceStatus, int | None]:
        freshness = _freshness(now, observed_at)
        return _status_for_freshness(
            freshness_seconds=freshness,
            max_age_seconds=self._max_age_seconds,
        ), freshness


class NWSAlertsAdapter(_HTTPAdapter):
    """National Weather Service active California alerts adapter."""

    source_id = "nws-ca-alerts"
    provider = "National Weather Service"
    source_type = "weather_alerts"
    poll_interval_seconds = 60.0
    location = "California / Los Angeles route context"

    def __init__(
        self,
        *,
        url: str = NWS_ALERTS_URL,
        transport: HTTPTransport = _default_transport,
        timeout_seconds: float = 8.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_age_seconds: int = 900,
    ) -> None:
        super().__init__(
            transport=transport,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_age_seconds=max_age_seconds,
        )
        # Keep the common constructor option for callers, but do not use it to
        # classify an active-feed response: NWS controls active/expired state.
        self.url = url
        self.provenance_url = url

    def fetch(self, now: datetime) -> LiveSourceSnapshot:
        payload = self._get_json(self.url, accept="application/geo+json, application/json")
        raw_features = payload.get("features", [])
        if not isinstance(raw_features, Sequence) or isinstance(raw_features, (str, bytes)):
            raise ValueError("NWS alerts payload has no feature list")
        alerts: list[Mapping[str, object]] = []
        timestamps: list[datetime] = []
        route_high_severity = 0
        california_high_severity = 0
        california_alert_count = 0
        for feature in raw_features:
            if not isinstance(feature, Mapping):
                continue
            properties = feature.get("properties")
            if not isinstance(properties, Mapping):
                continue
            california_alert_count += 1
            updated = _parse_timestamp(properties.get("updated"))
            sent = _parse_timestamp(properties.get("sent"))
            observed = updated or sent
            if observed is not None:
                timestamps.append(observed)
            severity = str(properties.get("severity") or "Unknown")
            area = str(properties.get("areaDesc") or "California")
            route_relevant = _is_route_area(area)
            if severity.lower() in {"severe", "extreme"}:
                california_high_severity += 1
                if route_relevant:
                    route_high_severity += 1
            if route_relevant:
                alerts.append(
                    {
                        "id": str(feature.get("id") or properties.get("id") or "unknown"),
                        "event": str(properties.get("event") or "Alert"),
                        "severity": severity,
                        "urgency": str(properties.get("urgency") or "Unknown"),
                        "certainty": str(properties.get("certainty") or "Unknown"),
                        "area": area,
                        "updated_at": _iso(updated),
                        "expires_at": _iso(_parse_timestamp(properties.get("expires"))),
                        "route_relevant": True,
                    }
                )
        observed_at = max(timestamps) if timestamps else None
        # A successful active-feed response is connected even when the newest
        # alert was issued a while ago. Alert age is event metadata, not feed
        # availability; expiry/active state is supplied by this endpoint.
        freshness = _freshness(now, observed_at)
        return LiveSourceSnapshot(
            provider=self.provider,
            source_id=self.source_id,
            source_type=self.source_type,
            location=self.location,
            status=LiveSourceStatus.CONNECTED,
            observed_at=observed_at,
            received_at=now,
            freshness_seconds=freshness,
            metrics={
                "active_alerts": len(alerts),
                "route_alerts": len(alerts),
                "high_severity_alerts": route_high_severity,
                "route_high_severity_alerts": route_high_severity,
                "california_active_alerts": california_alert_count,
                "california_high_severity_alerts": california_high_severity,
                "latest_alert_age_seconds": freshness,
            },
            alerts=tuple(alerts[:20]),
            provenance_url=self.provenance_url,
        )


class NOAAWaterLevelAdapter(_HTTPAdapter):
    """NOAA CO-OPS latest water-level observation for station 9410660."""

    source_id = "noaa-coops-9410660"
    provider = "NOAA CO-OPS"
    source_type = "water_level"
    poll_interval_seconds = 60.0
    location = "Port of Los Angeles / station 9410660"

    def __init__(
        self,
        *,
        url: str = NOAA_WATER_LEVEL_URL,
        transport: HTTPTransport = _default_transport,
        timeout_seconds: float = 8.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_age_seconds: int = 900,
    ) -> None:
        super().__init__(
            transport=transport,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_age_seconds=max_age_seconds,
        )
        self.url = url
        self.provenance_url = url

    def fetch(self, now: datetime) -> LiveSourceSnapshot:
        payload = self._get_json(self.url, accept="application/json")
        raw_rows = payload.get("data", [])
        if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
            raise ValueError("NOAA payload has no data list")
        rows = [row for row in raw_rows if isinstance(row, Mapping)]
        if not rows:
            error = str(payload.get("error") or "NOAA returned no observations")
            raise ValueError(error)
        row = rows[-1]
        observed_at = _parse_timestamp(row.get("t"))
        water_level = row.get("v")
        try:
            water_level_m = float(str(water_level))
        except (TypeError, ValueError) as exc:
            raise ValueError("NOAA water level is not numeric") from exc
        status, freshness = self._snapshot_status(now, observed_at)
        return LiveSourceSnapshot(
            provider=self.provider,
            source_id=self.source_id,
            source_type=self.source_type,
            location=self.location,
            status=status,
            observed_at=observed_at,
            received_at=now,
            freshness_seconds=freshness,
            metrics={
                "station_id": "9410660",
                "water_level_m": water_level_m,
                "unit": "m",
                "datum": "MLLW",
            },
            alerts=(),
            provenance_url=self.provenance_url,
        )


AISStreamFetcher = Callable[
    [str, tuple[tuple[float, float], tuple[float, float]], float], Mapping[str, object]
]


class AISStreamUnavailable(RuntimeError):
    """A safe, non-secret reason for an unavailable optional AIS source."""


class _AISWebSocket(Protocol):
    def __enter__(self) -> _AISWebSocket:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        ...

    def send(self, message: str) -> None:
        ...

    def recv(self, timeout: float | None = None) -> str | bytes:
        ...


def _build_ais_subscription(
    api_key: str, bbox: tuple[tuple[float, float], tuple[float, float]]
) -> dict[str, object]:
    """Build the server-only AISStream subscription payload."""

    return {
        "APIKey": api_key,
        "BoundingBoxes": [[list(bbox[0]), list(bbox[1])]],
        "FilterMessageTypes": ["PositionReport"],
    }


def _load_ais_connect() -> Callable[..., _AISWebSocket]:
    """Load the optional maintained ``websockets`` sync client lazily."""

    try:
        module = import_module("websockets.sync.client")
    except ImportError as exc:
        raise AISStreamUnavailable("optional websockets dependency is unavailable") from exc
    connect = getattr(module, "connect", None)
    if not callable(connect):
        raise AISStreamUnavailable("optional websockets client has no sync connector")
    return cast(Callable[..., _AISWebSocket], connect)


def _ais_mmsi(message: Mapping[str, object]) -> str | None:
    metadata = message.get("MetaData")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    nested_message = message.get("Message")
    nested_map = nested_message if isinstance(nested_message, Mapping) else {}
    position = nested_map.get("PositionReport")
    position_map = position if isinstance(position, Mapping) else {}
    for candidate in (
        metadata_map.get("MMSI"),
        position_map.get("UserID"),
        message.get("MMSI"),
    ):
        if isinstance(candidate, bool) or not isinstance(candidate, (int, str)):
            continue
        value = str(candidate).strip()
        if value:
            return value
    return None


def _ais_timestamp(message: Mapping[str, object]) -> datetime | None:
    metadata = message.get("MetaData")
    if isinstance(metadata, Mapping):
        for key in ("time_utc", "timestamp", "observed_at"):
            parsed = _parse_timestamp(metadata.get(key))
            if parsed is not None:
                return parsed
    for key in ("time_utc", "timestamp", "observed_at"):
        parsed = _parse_timestamp(message.get(key))
        if parsed is not None:
            return parsed
    return None


def _normalize_ais_messages(messages: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Return bounded, deduplicated AIS facts without retaining raw messages."""

    mmsis: set[str] = set()
    timestamps: list[datetime] = []
    for message in messages:
        mmsi = _ais_mmsi(message)
        if mmsi is not None:
            mmsis.add(mmsi)
        timestamp = _ais_timestamp(message)
        if timestamp is not None:
            timestamps.append(timestamp)
    latest = max(timestamps) if timestamps else None
    return {
        "vessel_count": len(mmsis),
        "observed_at": _iso(latest),
        "messages_seen": len(messages),
    }


def _default_aisstream_fetcher(
    api_key: str,
    bbox: tuple[tuple[float, float], tuple[float, float]],
    timeout: float,
) -> Mapping[str, object]:
    """Collect one bounded AISStream window through a server-side WebSocket."""

    connect = _load_ais_connect()
    messages: list[Mapping[str, object]] = []
    try:
        with connect(
            AISSTREAM_URL,
            open_timeout=timeout,
            close_timeout=min(timeout, 3.0),
            max_size=1_048_576,
            max_queue=AISSTREAM_MAX_MESSAGES,
        ) as websocket:
            websocket.send(
                json.dumps(_build_ais_subscription(api_key, bbox), separators=(",", ":"))
            )
            deadline = time.monotonic() + min(AISSTREAM_FIRST_WINDOW_SECONDS, timeout)
            while len(messages) < AISSTREAM_MAX_MESSAGES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = websocket.recv(timeout=remaining)
                except TimeoutError:
                    break
                except Exception as exc:
                    if messages:
                        break
                    raise AISStreamUnavailable("AISStream message receive failed") from exc
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    decoded = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(decoded, Mapping):
                    messages.append(decoded)
    except AISStreamUnavailable:
        raise
    except TimeoutError as exc:
        raise AISStreamUnavailable("AISStream connection timed out") from exc
    except Exception as exc:
        raise AISStreamUnavailable("AISStream connection failed") from exc
    return _normalize_ais_messages(messages)


class AISStreamAdapter:
    """Optional server-side AISStream boundary.

    The repository does not force a WebSocket dependency on every local demo.
    When a key is absent this is explicitly ``OPTIONAL_NOT_CONFIGURED``. When a
    deployment supplies ``AISSTREAM_API_KEY`` and installs the optional ``live``
    dependency, the default server-side WebSocket fetcher is used. A deployment
    can still inject a fetcher for tests. A browser never sees the key.
    """

    source_id = "aisstream-port-los-angeles"
    provider = "AISStream"
    source_type = "vessel_positions"
    poll_interval_seconds = 15.0
    location = "Port of Los Angeles bounding box"
    provenance_url = "https://aisstream.io/documentation"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        environ: Mapping[str, str] | None = None,
        fetcher: AISStreamFetcher | None = None,
        timeout_seconds: float = 8.0,
        bbox: tuple[tuple[float, float], tuple[float, float]] = AISSTREAM_BBOX,
    ) -> None:
        values = os.environ if environ is None else environ
        self._api_key = (api_key or values.get("AISSTREAM_API_KEY") or "").strip() or None
        self._fetcher = fetcher or _default_aisstream_fetcher
        self._timeout_seconds = timeout_seconds
        self.bbox = bbox
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def fetch(self, now: datetime) -> LiveSourceSnapshot:
        if self._api_key is None:
            return LiveSourceSnapshot(
                provider=self.provider,
                source_id=self.source_id,
                source_type=self.source_type,
                location=self.location,
                status=LiveSourceStatus.OPTIONAL_NOT_CONFIGURED,
                observed_at=None,
                received_at=now,
                freshness_seconds=None,
                metrics={"vessel_count": 0, "bbox": self.bbox},
                alerts=(),
                provenance_url=self.provenance_url,
                error="optional AIS key is not configured",
            )
        try:
            payload = self._fetcher(self._api_key, self.bbox, self._timeout_seconds)
        except Exception as exc:  # optional source boundary; never expose a secret
            return LiveSourceSnapshot(
                provider=self.provider,
                source_id=self.source_id,
                source_type=self.source_type,
                location=self.location,
                status=LiveSourceStatus.DEGRADED,
                observed_at=None,
                received_at=now,
                freshness_seconds=None,
                metrics={"vessel_count": 0, "bbox": self.bbox},
                alerts=(),
                provenance_url=self.provenance_url,
                error=type(exc).__name__,
            )
        observed_at = _parse_timestamp(payload.get("observed_at"))
        count = payload.get("vessel_count", payload.get("count", 0))
        try:
            vessel_count = max(0, int(str(count)))
        except (TypeError, ValueError) as exc:
            raise ValueError("AISStream vessel count is not an integer") from exc
        freshness = _freshness(now, observed_at)
        status = _status_for_freshness(
            freshness_seconds=freshness,
            max_age_seconds=120,
        )
        error = None if observed_at is not None else "AIS source returned no observation timestamp"
        if observed_at is None:
            status = LiveSourceStatus.DEGRADED
        return LiveSourceSnapshot(
            provider=self.provider,
            source_id=self.source_id,
            source_type=self.source_type,
            location=self.location,
            status=status,
            observed_at=observed_at,
            received_at=now,
            freshness_seconds=freshness,
            metrics={"vessel_count": vessel_count, "bbox": self.bbox},
            alerts=(),
            provenance_url=self.provenance_url,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class RouteRisk:
    """Advisory risk only; it is not an operational incident."""

    level: str
    label: str
    reasons: tuple[str, ...]
    source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "label": self.label,
            "reasons": list(self.reasons),
            "source_ids": list(self.source_ids),
            "advisory_only": True,
            "creates_operational_incident": False,
        }


def correlate_route_risk(snapshots: Sequence[LiveSourceSnapshot]) -> RouteRisk:
    """Map public context to a bounded, advisory route-risk label."""

    reasons: list[str] = []
    source_ids: list[str] = []
    severe_alerts = 0
    for snapshot in snapshots:
        if snapshot.source_id == "nws-ca-alerts":
            raw_severe_alerts = snapshot.metrics.get("route_high_severity_alerts", 0)
            severe_alerts = (
                int(raw_severe_alerts)
                if isinstance(raw_severe_alerts, (int, float, str))
                else 0
            )
            if severe_alerts:
                reasons.append(f"{severe_alerts} severe weather alert(s) in route area")
                source_ids.append(snapshot.source_id)
        if snapshot.status in {LiveSourceStatus.DEGRADED, LiveSourceStatus.STALE}:
            reasons.append(f"{snapshot.provider} data is {snapshot.status.value.lower()}")
            source_ids.append(snapshot.source_id)
    if severe_alerts:
        return RouteRisk(
            "HIGH",
            "Route risk elevated",
            tuple(reasons),
            tuple(dict.fromkeys(source_ids)),
        )
    if reasons:
        return RouteRisk(
            "WATCH",
            "Route context needs attention",
            tuple(reasons),
            tuple(dict.fromkeys(source_ids)),
        )
    return RouteRisk("LOW", "No external route risk detected", (), ())


class LiveSourceRegistry:
    """Thread-safe source cache and bounded poll/event contract."""

    def __init__(
        self,
        adapters: Sequence[LiveSourceAdapter] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.adapters = tuple(adapters or default_adapters())
        if not self.adapters:
            raise ValueError("at least one live source adapter is required")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._snapshots: dict[str, LiveSourceSnapshot] = {}
        self._last_poll: dict[str, datetime] = {}
        self._events: list[LiveSourceEvent] = []
        self._sequence = 0

    def poll_once(
        self, *, force: bool = False, now: datetime | None = None
    ) -> tuple[LiveSourceEvent, ...]:
        captured_at = now or self._clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("live source clock must return an aware datetime")
        emitted: list[LiveSourceEvent] = []
        with self._lock:
            for adapter in self.adapters:
                previous_poll = self._last_poll.get(adapter.source_id)
                if (
                    not force
                    and previous_poll is not None
                    and (captured_at - previous_poll).total_seconds()
                    < adapter.poll_interval_seconds
                ):
                    continue
                self._last_poll[adapter.source_id] = captured_at
                prior = self._snapshots.get(adapter.source_id)
                try:
                    snapshot = adapter.fetch(captured_at)
                except Exception as exc:  # source boundary; never fake new data
                    snapshot = self._degraded_snapshot(adapter, captured_at, prior, exc)
                is_new = self._is_new_observation(prior, snapshot)
                self._sequence += 1
                snapshot = LiveSourceSnapshot(
                    provider=snapshot.provider,
                    source_id=snapshot.source_id,
                    source_type=snapshot.source_type,
                    location=snapshot.location,
                    status=snapshot.status,
                    observed_at=snapshot.observed_at,
                    received_at=snapshot.received_at,
                    freshness_seconds=snapshot.freshness_seconds,
                    metrics=snapshot.metrics,
                    alerts=snapshot.alerts,
                    provenance_url=snapshot.provenance_url,
                    new_observation=is_new,
                    sequence=self._sequence,
                    error=snapshot.error,
                )
                self._snapshots[adapter.source_id] = snapshot
                event = LiveSourceEvent(
                    sequence=self._sequence,
                    source_id=adapter.source_id,
                    observed_at=snapshot.observed_at,
                    received_at=captured_at,
                    new_observation=is_new,
                    snapshot=snapshot,
                )
                self._events.append(event)
                emitted.append(event)
            return tuple(emitted)

    @staticmethod
    def _is_new_observation(
        prior: LiveSourceSnapshot | None, current: LiveSourceSnapshot
    ) -> bool:
        if prior is None:
            return current.observed_at is not None or current.status is LiveSourceStatus.CONNECTED
        if current.observed_at is None:
            return False
        return current.observed_at != prior.observed_at

    @staticmethod
    def _degraded_snapshot(
        adapter: LiveSourceAdapter,
        now: datetime,
        prior: LiveSourceSnapshot | None,
        error: Exception,
    ) -> LiveSourceSnapshot:
        location = getattr(adapter, "location", adapter.source_id)
        provenance_url = getattr(adapter, "provenance_url", "")
        if not isinstance(location, str):
            location = adapter.source_id
        if not isinstance(provenance_url, str):
            provenance_url = ""
        return LiveSourceSnapshot(
            provider=adapter.provider,
            source_id=adapter.source_id,
            source_type=adapter.source_type,
            location=prior.location if prior is not None else location,
            status=LiveSourceStatus.DEGRADED,
            observed_at=prior.observed_at if prior is not None else None,
            received_at=now,
            freshness_seconds=_freshness(now, prior.observed_at if prior else None),
            metrics=prior.metrics if prior is not None else {},
            alerts=prior.alerts if prior is not None else (),
            provenance_url=prior.provenance_url if prior is not None else provenance_url,
            error=type(error).__name__,
        )

    def current(self, *, poll: bool = True) -> dict[str, object]:
        if poll:
            self.poll_once()
        with self._lock:
            snapshots = tuple(self._snapshots.values())
            latest_received = max(
                (item.received_at for item in snapshots),
                default=self._clock(),
            )
            return {
                "schema_version": LIVE_SOURCE_SCHEMA_VERSION,
                "scope": {
                    "route": "Port of Los Angeles to inland warehouse",
                    "external_context_only": True,
                    "operational_authority": "synthetic_enterprise_twin",
                },
                "polled_at": _iso(latest_received),
                "sequence": self._sequence,
                "sources": [item.as_dict() for item in snapshots],
                "risk": correlate_route_risk(snapshots).as_dict(),
                "event_cursor": self._sequence,
            }

    def events_since(self, after: int = 0, *, poll: bool = True) -> dict[str, object]:
        if after < 0:
            raise ValueError("live-source cursor cannot be negative")
        if poll:
            self.poll_once()
        with self._lock:
            events = tuple(item for item in self._events if item.sequence > after)
            return {
                "schema_version": LIVE_SOURCE_SCHEMA_VERSION,
                "after": after,
                "cursor": self._sequence,
                "events": [item.as_dict() for item in events[-100:]],
                "external_context_only": True,
            }

    def close(self) -> None:
        """Compatibility hook for a future stream adapter."""


class LiveSourcePoller:
    """Optional server-owned background poller for always-open dashboards."""

    def __init__(self, registry: LiveSourceRegistry, *, interval_seconds: float = 15.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.registry = registry
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self.registry.poll_once(force=True)
        self._thread = Thread(target=self._run, name="missing20-live-sources", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.registry.poll_once()
            except Exception:
                # Individual source failures are represented by registry snapshots;
                # this guard prevents an unexpected adapter bug from killing the server.
                continue

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        self.registry.close()


def default_adapters() -> tuple[LiveSourceAdapter, ...]:
    return (
        NWSAlertsAdapter(),
        NOAAWaterLevelAdapter(),
        AISStreamAdapter(),
    )


__all__ = [
    "AISStreamAdapter",
    "AISSTREAM_BBOX",
    "AISSTREAM_URL",
    "DEFAULT_USER_AGENT",
    "LiveSourceAdapter",
    "LiveSourceEvent",
    "LiveSourcePoller",
    "LiveSourceRegistry",
    "LiveSourceSnapshot",
    "LiveSourceStatus",
    "HTTPTransport",
    "NWSAlertsAdapter",
    "NWS_ROUTE_AREA_TERMS",
    "NOAAWaterLevelAdapter",
    "NOAA_WATER_LEVEL_URL",
    "NWS_ALERTS_URL",
    "RouteRisk",
    "correlate_route_risk",
    "default_adapters",
]
