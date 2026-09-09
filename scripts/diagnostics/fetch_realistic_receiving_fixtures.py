"""Fetch a small, attributed public development corpus; never create ERP stock.

Original image bytes are retained. Public product data is reference material,
not a supplier price, purchase order, unit conversion, or proof of delivery.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/fixtures/realistic-receiving-v1"
REVISION = "33dfdefcb35576612841e614d44ba9edc9aee2b5"
RAW = f"https://raw.githubusercontent.com/zxing/zxing/{REVISION}"
HOSTS = {
    "raw.githubusercontent.com",
    "world.openfoodfacts.org",
    "images.openfoodfacts.org",
    "upload.wikimedia.org",
}


def fetch(url: str) -> bytes:
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in HOSTS:
        raise ValueError("Unapproved public fixture host")
    request = Request(url, headers={"User-Agent": "Missing20-Development-Evaluation/1.0"})
    with urlopen(request, timeout=30) as response:
        if urlparse(response.url).hostname not in HOSTS:
            raise ValueError("Unexpected fixture redirect")
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("Fixture exceeds 5 MB")
    return raw


def asset(url: str, name: str) -> dict:
    raw = fetch(url)
    (OUT / name).write_bytes(raw)
    return {"file": name, "url": url, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "at": datetime.now(UTC).isoformat(),
        "purpose": "Public development fixtures, not actual received goods or an unseen benchmark",
        "barcodes": [],
        "products": [],
        "errors": [],
    }
    license_url = f"{RAW}/LICENSE"
    manifest["zxing_license"] = asset(license_url, "ZXING-LICENSE.txt")
    for directory, format_name in [
        ("ean13-1", "ean_13"),
        ("upca-1", "upc_a"),
        ("code128-1", "code_128"),
        ("qrcode-1", "qr_code"),
    ]:
        for number in range(1, 5):
            key = f"{directory}-{number}"
            try:
                base = f"{RAW}/core/src/test/resources/blackbox/{directory}/{number}"
                truth = fetch(base + ".txt").decode().rstrip("\r\n")
                entry = asset(base + ".png", key + ".png")
                entry.update(
                    {
                        "id": key,
                        "expected_code": truth,
                        "format": format_name,
                        "truth_url": base + ".txt",
                        "attribution": "ZXing contributors; upstream blackbox fixture",
                        "license_url": license_url,
                        "quantity_proven": False,
                    }
                )
                manifest["barcodes"].append(entry)
            except Exception as exc:
                manifest["errors"].append({"id": key, "error": str(exc)})
    for code in ["3017620422003", "3274080005003", "5449000000996"]:
        try:
            url = f"https://world.openfoodfacts.org/api/v2/product/{code}?fields=code,product_name,brands,quantity,image_front_url,image_packaging_url"
            raw = fetch(url)
            response = json.loads(raw)
            if response.get("status") != 1 or response.get("code") != code:
                raise ValueError("Exact public product missing")
            product = response["product"]
            (OUT / f"product-{code}.json").write_bytes(raw)
            entry = {
                "code": code,
                "product": product,
                "source_url": url,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "attribution": "Open Food Facts contributors",
                "data_license": "ODbL 1.0",
                "image_license": "CC BY-SA 3.0",
                "license_url": "https://world.openfoodfacts.org/terms-of-use",
                "price_source": None,
                "erp_mapping_verified": False,
                "images": [],
            }
            for field in ["image_front_url", "image_packaging_url"]:
                if product.get(field):
                    entry["images"].append(asset(product[field], f"{code}-{field}.jpg"))
            manifest["products"].append(entry)
        except Exception as exc:
            manifest["errors"].append({"id": code, "error": str(exc)})
    manifest["warehouse_photos"] = []
    for filename, url, source, author in [
        (
            "mixed-parcels.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/6/66/Air_shipment_of_mixed_parcels.jpg",
            "https://commons.wikimedia.org/wiki/File:Air_shipment_of_mixed_parcels.jpg",
            "R L Sheehan; upstream crop by Belbury",
        ),
        (
            "webvan-tubs.png",
            "https://upload.wikimedia.org/wikipedia/commons/e/e3/Webvan_tubs.png",
            "https://commons.wikimedia.org/wiki/File:Webvan_tubs.png",
            "Binksternet",
        ),
    ]:
        try:
            entry = asset(url, filename)
            entry.update(
                {
                    "source_url": source,
                    "license": "Public domain",
                    "license_verification": "Source-page author release reviewed on 2026-09-09",
                    "license_review": (
                        "docs/research/2026-09-09-realistic-physical-fixture-sources.md"
                    ),
                    "attribution": author,
                    "count_truth": "Requires visual annotation; source is not proof of delivery",
                }
            )
            manifest["warehouse_photos"].append(entry)
        except Exception as exc:
            manifest["errors"].append({"id": filename, "error": str(exc)})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "barcodes": len(manifest["barcodes"]),
                "products": len(manifest["products"]),
                "errors": manifest["errors"],
                "manifest": str(OUT / "manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
