"""Narrow demo receipt notifications. No QA, invoice, stock or payment writes."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from the_missing_20.adapters.saas_evidence import SaaSEvidenceConfig


class ReceivingAPI:
    def __init__(
        self, config: SaaSEvidenceConfig, transport: Callable[[Request, float], bytes] | None = None
    ) -> None:
        self.config = config
        self.transport = transport or self._transport

    @staticmethod
    def _transport(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed provider hosts
            return bytes(response.read())

    def request(self, provider: str, path: str, *, payload: Any = None) -> Any:
        config = self.config
        providers = {
            "celigo": ("https://api.integrator.io/v1", config.celigo_api_token),
            "slack": ("https://slack.com/api", config.slack_bot_token),
            "airtable": ("https://api.airtable.com/v0", config.airtable_token),
        }
        if provider == "jira":
            providers["jira"] = (
                "https://api.atlassian.com/ex/jira/" + str(UUID(config.jira_cloud_id)),
                config.jira_api_token,
            )
        origin, token = providers[provider]
        if not token or not path.startswith("/"):
            raise ValueError("Receiving destination credential/path is missing")
        request = Request(
            origin + path,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps(payload).encode() if payload is not None else None,
            method="POST" if payload is not None else "GET",
        )
        response = self.transport(request, 20)
        return json.loads(response.decode()) if response else None


class CeligoSlackReceipt:
    def __init__(self, api: ReceivingAPI, import_id: str, connection_id: str) -> None:
        self.api, self.import_id, self.connection_id = api, import_id, connection_id
        self.route = f"celigo-slack:{import_id}:{api.config.slack_channel_id}"

    @staticmethod
    def text(event: dict[str, Any], key: str) -> str:
        return (
            f"[M20 DEMO · RECEIVED] {event['case_id']} / {event['arrival_id']}\n"
            f"ERPNext verified {event['quantity']:g} {event['uom']} of {event['item_code']} "
            f"on {event['receipt']} (PO {event['purchase_order']}).\n"
            f"Stock ledger: {', '.join(event['stock_ledger_ids'])}. "
            f"Verified at {event['verified_at']}.\n"
            "Partial receipt only; no claim of complete delivery, billing, QA release or payment.\n"
            f"{event['erp_url']}\nEvent: {key}"
        )

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        auth = self.api.request("slack", "/auth.test")
        if not isinstance(auth, dict) or auth.get("ok") is not True or not auth.get("user_id"):
            raise ValueError("Slack identity could not be verified")
        cursor, matches = "", []
        for _ in range(5):
            query = urlencode(
                {"channel": self.api.config.slack_channel_id, "limit": 100, "cursor": cursor}
            )
            page = self.api.request("slack", "/conversations.history?" + query)
            if (
                not isinstance(page, dict)
                or page.get("ok") is not True
                or not isinstance(page.get("messages"), list)
            ):
                raise ValueError("Slack history read is unavailable")
            for row in page["messages"]:
                if not isinstance(row, dict) or not isinstance(row.get("text"), str):
                    raise ValueError("Slack history contains a malformed message")
                if key in row.get("text", ""):
                    # Slack canonicalizes raw URLs as <url>. Normalize only the
                    # exact authorized ERP URL, never arbitrary modified content.
                    text = row["text"].replace(f"<{event['erp_url']}>", event["erp_url"])
                    if (
                        text != self.text(event, key)
                        or row.get("user") != auth["user_id"]
                        or not isinstance(row.get("ts"), str)
                    ):
                        raise ValueError("Slack event content/author does not match")
                    matches.append(row)
            metadata = page.get("response_metadata") or {}
            if not isinstance(metadata, dict):
                raise ValueError("Slack pagination metadata is malformed")
            cursor = metadata.get("next_cursor", "")
            if not cursor and not page.get("has_more"):
                break
            if not cursor:
                raise ValueError("Slack history pagination is incomplete")
        else:
            raise ValueError("Slack history exceeds safe reconciliation window")
        if len(matches) > 1:
            raise ValueError("Multiple Slack records match one receipt event")
        if not matches:
            return None
        ts = matches[0]["ts"]
        link = self.api.request(
            "slack",
            "/chat.getPermalink?"
            + urlencode({"channel": self.api.config.slack_channel_id, "message_ts": ts}),
        )
        if (
            not isinstance(link, dict)
            or link.get("ok") is not True
            or not isinstance(link.get("permalink"), str)
        ):
            raise ValueError("Slack message link could not be verified")
        return {
            "provider": "Slack via Celigo",
            "record_id": ts,
            "url": link["permalink"],
            "celigo_import_id": self.import_id,
        }

    def send(self, event: dict[str, Any], key: str) -> None:
        definition = self.api.request("celigo", f"/imports/{self.import_id}")
        if not isinstance(definition, dict) or not isinstance(definition.get("http"), dict):
            raise ValueError("Celigo receiving definition is malformed")
        http = definition.get("http", {})
        if (
            definition.get("_connectionId") != self.connection_id
            or definition.get("externalId") != "m20-verified-receiving-slack-v1"
            or http.get("relativeURI") != ["chat.postMessage"]
            or http.get("method") != ["POST"]
            or http.get("body")
            or definition.get("mockResponse")
            or definition.get("hooks")
            or definition.get("mapping")
            or definition.get("mappings")
            or definition.get("maxAttempts") != 1
        ):
            raise ValueError("Celigo receiving destination definition changed")
        result = self.api.request(
            "celigo",
            f"/imports/{self.import_id}/invoke",
            payload={
                "data": [
                    {
                        "channel": self.api.config.slack_channel_id,
                        "text": self.text(event, key),
                        "unfurl_links": False,
                        "unfurl_media": False,
                    }
                ]
            },
        )
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], dict)
            or result[0].get("statusCode") != 200
            or result[0].get("errors")
            or result[0].get("ignored")
        ):
            raise ValueError("Celigo did not confirm the notification")


class AirtableReceipt:
    def __init__(self, api: ReceivingAPI, table_id: str) -> None:
        self.api, self.table_id = api, table_id
        self.route = f"airtable-receiving:{api.config.airtable_base_id}:{table_id}"

    @staticmethod
    def fields(event: dict[str, Any], key: str) -> dict[str, Any]:
        return {
            "Event ID": key,
            "Case ID": event["case_id"],
            "Arrival": event["arrival_id"],
            "Purchase Order": event["purchase_order"],
            "Purchase Receipt": event["receipt"],
            "Item": event["item_code"],
            "Quantity": event["quantity"],
            "Unit": event["uom"],
            "Stock Ledger IDs": ", ".join(event["stock_ledger_ids"]),
            "ERP Link": event["erp_url"],
            "Verified At": event["verified_at"],
            "Status": "RECEIVED",
            "Origin": "ERPNext ledger reread · demo goods",
        }

    def _path(self) -> str:
        return (
            f"/{quote(self.api.config.airtable_base_id, safe='')}/{quote(self.table_id, safe='')}"
        )

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        query = urlencode({"filterByFormula": f"{{Event ID}}='{key}'", "maxRecords": 2})
        result = self.api.request("airtable", self._path() + "?" + query)
        if not isinstance(result, dict):
            raise ValueError("Airtable response is malformed")
        records = result.get("records")
        if not isinstance(records, list) or len(records) > 1 or result.get("offset"):
            raise ValueError("Airtable receipt identity is ambiguous")
        if not records:
            return None
        row = records[0]
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("fields"), dict)
            or not row.get("id")
        ):
            raise ValueError("Airtable record is malformed")
        if any(row.get("fields", {}).get(k) != v for k, v in self.fields(event, key).items()):
            raise ValueError("Airtable receipt content differs from the stock evidence")
        return {
            "provider": "Airtable",
            "record_id": row["id"],
            "url": f"https://airtable.com/{self.api.config.airtable_base_id}/{self.table_id}/{row['id']}",
        }

    def send(self, event: dict[str, Any], key: str) -> None:
        self.api.request("airtable", self._path(), payload={"fields": self.fields(event, key)})
