from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import cast
from urllib.request import Request

import pytest

import the_missing_20.live_sources as live_sources
from the_missing_20.live_sources import (
    AISStreamAdapter,
    HTTPTransport,
    LiveSourcePoller,
    LiveSourceRegistry,
    LiveSourceSnapshot,
    LiveSourceStatus,
    NOAAWaterLevelAdapter,
    NWSAlertsAdapter,
    correlate_route_risk,
)

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)


def _transport(payload: object, seen: list[Request] | None = None) -> HTTPTransport:
    body = json.dumps(payload).encode("utf-8")

    def fetch(request: Request, _timeout: float) -> bytes:
        if seen is not None:
            seen.append(request)
        return body

    return cast(HTTPTransport, fetch)


def test_nws_normalizes_alerts_and_uses_a_non_sensitive_user_agent() -> None:
    requests: list[Request] = []
    payload = {
        "features": [
            {
                "id": "https://api.weather.gov/alerts/123",
                "properties": {
                    "event": "Extreme Heat Warning",
                    "severity": "Extreme",
                    "urgency": "Expected",
                    "certainty": "Likely",
                    "areaDesc": "Los Angeles County",
                    "updated": "2026-08-29T07:59:00+00:00",
                    "expires": "2026-08-30T04:00:00+00:00",
                },
            }
        ]
    }
    snapshot = NWSAlertsAdapter(
        transport=_transport(payload, requests), max_age_seconds=1
    ).fetch(NOW)

    assert snapshot.status is LiveSourceStatus.CONNECTED
    assert snapshot.metrics == {
        "active_alerts": 1,
        "route_alerts": 1,
        "high_severity_alerts": 1,
        "route_high_severity_alerts": 1,
        "california_active_alerts": 1,
        "california_high_severity_alerts": 1,
        "latest_alert_age_seconds": 60,
    }
    assert snapshot.alerts[0]["event"] == "Extreme Heat Warning"
    assert snapshot.freshness_seconds == 60
    assert requests[0].headers["User-agent"] == "TheMissing20/0.1 (live supply-chain context)"
    assert "@" not in requests[0].headers["User-agent"]
    assert "external_context_only" in snapshot.as_dict()


def test_noaa_normalizes_station_and_observation_units() -> None:
    payload = {"metadata": {"id": "9410660"}, "data": [{"t": "2026-08-29 07:54", "v": "1.672"}]}
    snapshot = NOAAWaterLevelAdapter(transport=_transport(payload)).fetch(NOW)

    assert snapshot.status is LiveSourceStatus.CONNECTED
    assert snapshot.source_id == "noaa-coops-9410660"
    assert snapshot.metrics["station_id"] == "9410660"
    assert snapshot.metrics["water_level_m"] == 1.672
    assert snapshot.metrics["unit"] == "m"
    assert snapshot.freshness_seconds == 360


def test_registry_marks_repeated_observations_without_creating_a_new_data_pulse() -> None:
    payload = {"data": [{"t": "2026-08-29 07:54", "v": "1.672"}]}
    registry = LiveSourceRegistry(
        [NOAAWaterLevelAdapter(transport=_transport(payload))],
        clock=lambda: NOW,
    )

    first = registry.poll_once(force=True, now=NOW)
    second = registry.poll_once(force=True, now=NOW + timedelta(seconds=30))

    assert first[0].new_observation is True
    assert second[0].new_observation is False
    assert second[0].sequence == first[0].sequence + 1
    events_payload = registry.events_since(1, poll=False)
    events = cast(list[dict[str, object]], events_payload["events"])
    assert events[0]["new_observation"] is False


def test_registry_preserves_last_known_value_and_exposes_timeout_as_degraded() -> None:
    calls = 0

    def fetch(_request: Request, _timeout: float) -> bytes:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise TimeoutError("source timeout")
        return json.dumps({"data": [{"t": "2026-08-29 07:59", "v": "1.20"}]}).encode()

    registry = LiveSourceRegistry(
        [NOAAWaterLevelAdapter(transport=cast(HTTPTransport, fetch))],
        clock=lambda: NOW,
    )
    first = registry.poll_once(force=True, now=NOW)[0]
    degraded = registry.poll_once(force=True, now=NOW + timedelta(seconds=60))[0]

    assert first.snapshot.status is LiveSourceStatus.CONNECTED
    assert degraded.snapshot.status is LiveSourceStatus.DEGRADED
    assert degraded.snapshot.metrics["water_level_m"] == 1.2
    assert degraded.snapshot.observed_at == first.snapshot.observed_at
    assert degraded.snapshot.error == "TimeoutError"
    assert degraded.new_observation is False


def test_stale_observation_is_visible_and_contributes_to_watch_risk() -> None:
    payload = {"data": [{"t": "2026-08-28 00:00", "v": "1.20"}]}
    registry = LiveSourceRegistry(
        [NOAAWaterLevelAdapter(transport=_transport(payload), max_age_seconds=60)],
        clock=lambda: NOW,
    )
    event = registry.poll_once(force=True, now=NOW)[0]
    result = registry.current(poll=False)

    assert event.snapshot.status is LiveSourceStatus.STALE
    risk = cast(dict[str, object], result["risk"])
    reasons = cast(list[str], risk["reasons"])
    assert risk["level"] == "WATCH"
    assert "stale" in reasons[0]


def test_optional_ais_has_no_key_and_never_fakes_vessel_data() -> None:
    adapter = AISStreamAdapter(environ={})
    snapshot = adapter.fetch(NOW)

    assert snapshot.status is LiveSourceStatus.OPTIONAL_NOT_CONFIGURED
    assert snapshot.metrics["vessel_count"] == 0
    assert snapshot.observed_at is None
    assert snapshot.error == "optional AIS key is not configured"


def test_ais_key_without_optional_runtime_degrades_and_does_not_expose_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise live_sources.AISStreamUnavailable("optional runtime unavailable")

    monkeypatch.setattr(live_sources, "_default_aisstream_fetcher", unavailable)
    snapshot = AISStreamAdapter(environ={"AISSTREAM_API_KEY": "secret"}).fetch(NOW)
    payload = snapshot.as_dict()

    assert snapshot.status is LiveSourceStatus.DEGRADED
    assert "secret" not in json.dumps(payload)
    assert snapshot.error == "AISStreamUnavailable"


def test_ais_default_fetcher_is_activated_when_key_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def default_fetcher(
        api_key: str,
        bbox: tuple[tuple[float, float], tuple[float, float]],
        timeout: float,
    ) -> dict[str, object]:
        seen.update({"api_key": api_key, "bbox": bbox, "timeout": timeout})
        return {"observed_at": "2026-08-29T07:59:30+00:00", "vessel_count": 4}

    monkeypatch.setattr(live_sources, "_default_aisstream_fetcher", default_fetcher)
    snapshot = AISStreamAdapter(environ={"AISSTREAM_API_KEY": "server-only"}).fetch(NOW)

    assert snapshot.status is LiveSourceStatus.CONNECTED
    assert snapshot.metrics["vessel_count"] == 4
    assert seen["api_key"] == "server-only"
    assert "server-only" not in json.dumps(snapshot.as_dict())


def test_ais_server_side_fetcher_normalizes_vessel_observations() -> None:
    seen: dict[str, object] = {}

    def fetcher(
        api_key: str,
        bbox: tuple[tuple[float, float], tuple[float, float]],
        timeout: float,
    ) -> dict[str, object]:
        seen.update({"api_key": api_key, "bbox": bbox, "timeout": timeout})
        return {"observed_at": "2026-08-29T07:59:30+00:00", "vessel_count": 12}

    snapshot = AISStreamAdapter(
        environ={"AISSTREAM_API_KEY": "server-only"},
        fetcher=fetcher,
    ).fetch(NOW)

    assert snapshot.status is LiveSourceStatus.CONNECTED
    assert snapshot.metrics["vessel_count"] == 12
    assert seen["api_key"] == "server-only"
    assert "server-only" not in json.dumps(snapshot.as_dict())


def test_ais_subscription_is_server_side_and_port_scoped() -> None:
    bbox = ((33.1, -118.4), (33.9, -118.0))
    subscription = live_sources._build_ais_subscription("secret", bbox)

    assert subscription == {
        "APIKey": "secret",
        "BoundingBoxes": [[[33.1, -118.4], [33.9, -118.0]]],
        "FilterMessageTypes": ["PositionReport"],
    }


def test_ais_protocol_normalizes_and_deduplicates_position_reports() -> None:
    messages = [
        {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": "123", "time_utc": "2026-08-29T07:59:00Z"},
            "Message": {"PositionReport": {"UserID": 123}},
        },
        {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": "123", "time_utc": "2026-08-29T07:59:30Z"},
            "Message": {"PositionReport": {"UserID": 123}},
        },
        {
            "MessageType": "PositionReport",
            "MetaData": {"time_utc": "2026-08-29T07:58:30Z"},
            "Message": {"PositionReport": {"UserID": 456}},
        },
    ]

    normalized = live_sources._normalize_ais_messages(messages)

    assert normalized == {
        "vessel_count": 2,
        "observed_at": "2026-08-29T07:59:30+00:00",
        "messages_seen": 3,
    }


def test_ais_default_protocol_uses_bounded_window_and_decodes_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class Socket:
        def __enter__(self) -> Socket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, message: str) -> None:
            seen["subscription"] = json.loads(message)

        def recv(self, timeout: float | None = None) -> str | bytes:
            seen["timeout"] = timeout
            if "messages" not in seen:
                seen["messages"] = True
                return json.dumps(
                    {
                        "MessageType": "PositionReport",
                        "MetaData": {"MMSI": "321", "time_utc": "2026-08-29T07:59:30Z"},
                        "Message": {"PositionReport": {"UserID": 321}},
                    }
                ).encode("utf-8")
            raise TimeoutError

    def connect(*args: object, **kwargs: object) -> Socket:
        seen["connect_args"] = args
        seen["connect_kwargs"] = kwargs
        return Socket()

    monkeypatch.setattr(live_sources, "_load_ais_connect", lambda: connect)
    normalized = live_sources._default_aisstream_fetcher(
        "secret", ((33.1, -118.4), (33.9, -118.0)), 1.0
    )

    assert seen["connect_args"] == (live_sources.AISSTREAM_URL,)
    assert cast(dict[str, object], seen["connect_kwargs"])["open_timeout"] == 1.0
    assert cast(dict[str, object], seen["subscription"])["APIKey"] == "secret"
    assert normalized["vessel_count"] == 1
    assert normalized["observed_at"] == "2026-08-29T07:59:30+00:00"


def test_nws_severe_alert_outside_route_does_not_raise_route_risk() -> None:
    payload = {
        "features": [
            {
                "id": "https://api.weather.gov/alerts/san-diego",
                "properties": {
                    "event": "Severe Thunderstorm Warning",
                    "severity": "Severe",
                    "areaDesc": "San Diego County Coastal Areas",
                    "updated": "2026-08-29T07:00:00+00:00",
                },
            }
        ]
    }

    snapshot = NWSAlertsAdapter(transport=_transport(payload)).fetch(NOW)
    risk = correlate_route_risk((snapshot,))

    assert snapshot.status is LiveSourceStatus.CONNECTED
    assert snapshot.metrics["california_active_alerts"] == 1
    assert snapshot.metrics["california_high_severity_alerts"] == 1
    assert snapshot.metrics["route_alerts"] == 0
    assert snapshot.metrics["route_high_severity_alerts"] == 0
    assert snapshot.alerts == ()
    assert risk.level == "LOW"


def test_nws_severe_alert_in_inland_empire_raises_route_risk() -> None:
    payload = {
        "features": [
            {
                "id": "https://api.weather.gov/alerts/inland-empire",
                "properties": {
                    "event": "Flash Flood Warning",
                    "severity": "Severe",
                    "areaDesc": "San Bernardino and Riverside County Valleys-The Inland Empire",
                    "updated": "2026-08-29T07:00:00+00:00",
                },
            }
        ]
    }

    snapshot = NWSAlertsAdapter(transport=_transport(payload)).fetch(NOW)
    risk = correlate_route_risk((snapshot,))

    assert snapshot.metrics["route_alerts"] == 1
    assert snapshot.metrics["route_high_severity_alerts"] == 1
    assert snapshot.alerts[0]["route_relevant"] is True
    assert risk.level == "HIGH"


def test_route_risk_is_advisory_and_severe_weather_is_high() -> None:
    weather = LiveSourceSnapshot(
        provider="National Weather Service",
        source_id="nws-ca-alerts",
        source_type="weather_alerts",
        location="California",
        status=LiveSourceStatus.CONNECTED,
        observed_at=NOW,
        received_at=NOW,
        freshness_seconds=0,
        metrics={
            "active_alerts": 1,
            "route_alerts": 1,
            "high_severity_alerts": 1,
            "route_high_severity_alerts": 1,
        },
        alerts=(),
        provenance_url="https://www.weather.gov/documentation/services-web-api",
    )
    risk = correlate_route_risk((weather,))

    assert risk.level == "HIGH"
    assert risk.as_dict()["advisory_only"] is True
    assert risk.as_dict()["creates_operational_incident"] is False


def test_poller_starts_and_stops_cleanly_without_network() -> None:
    stopped = Event()

    class Adapter:
        source_id = "stub"
        provider = "stub"
        source_type = "stub"
        poll_interval_seconds = 60.0

        def fetch(self, now: datetime) -> LiveSourceSnapshot:
            stopped.set()
            return LiveSourceSnapshot(
                provider="stub",
                source_id="stub",
                source_type="stub",
                location="test",
                status=LiveSourceStatus.CONNECTED,
                observed_at=now,
                received_at=now,
                freshness_seconds=0,
                metrics={},
                alerts=(),
                provenance_url="https://example.test/source",
            )

    registry = LiveSourceRegistry([Adapter()], clock=lambda: NOW)
    poller = LiveSourcePoller(registry, interval_seconds=0.01)
    poller.start()
    try:
        assert stopped.wait(1)
    finally:
        poller.stop()
    assert poller._thread is None
