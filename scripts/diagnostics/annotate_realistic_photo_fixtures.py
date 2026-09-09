"""Freeze visually reviewed development truths BEFORE the model sees the images.

These sources are not fresh arrivals. They test outer-unit counting, required
retakes, and refusal to invent SKU/lot, never warehouse receipt authority.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "artifacts/fixtures/realistic-receiving-v1"


def main():
    source = json.loads((DIRECTORY / "manifest.json").read_text())
    entries = {}
    for product in source["products"]:
        for image in product["images"]:
            entries[image["file"]] = {
                **image,
                "source_url": product["source_url"],
                "license": product["image_license"],
                "attribution": product["attribution"],
            }
    for image in source["warehouse_photos"]:
        entries[image["file"]] = image
    cases = []
    specs = [
        (
            "real-jar",
            "3017620422003-image_packaging_url.jpg",
            "clear",
            1,
            "One closed Nutella jar on a tabletop, label visible. "
            "Brand and nominal contents are not ERP SKU, lot or purchase price.",
        ),
        (
            "real-water",
            "3274080005003-image_packaging_url.jpg",
            "clear",
            1,
            "One Cristaline bottle with a complete silhouette. Public API product_name is "
            "'isabelle', conflicting with photographed brand; no automatic ERP mapping.",
        ),
        (
            "three-tubs",
            "webvan-tubs.png",
            "clear",
            3,
            "Three closed delivery containers touching vertically, not their unseen contents. "
            "Asset tag 3760 is not a proven ERP item or lot.",
        ),
        (
            "mixed-parcels",
            "mixed-parcels.jpg",
            "occluded",
            None,
            "Mixed parcels behind rails and other parcels; exact total cannot be established. "
            "Request separated batch views; container ID is not SKU.",
        ),
        (
            "label-closeup",
            "5449000000996-image_packaging_url.jpg",
            "cropped",
            None,
            "Cropped recycling pictogram on a can. A drawing of a can is not a second physical "
            "can; the goods outline is missing.",
        ),
    ]
    for key, filename, visibility, count, note in specs:
        image = entries[filename]
        truth = {
            "visibility": visibility,
            "statuses": ["COUNT_CANDIDATE"] if count is not None else ["NEEDS_PHOTO"],
            "countable": count is not None,
            "visible_count": count,
            "item_codes": [""],
            "supplier_lots": [""],
            "label_declared_quantity": None,
        }
        if count is None:
            truth["reshoot_required"] = True
        else:
            truth["receiving_unit"] = "piece"
        cases.append(
            {
                "id": key,
                "file": filename,
                "sha256": image["sha256"],
                "source_url": image["source_url"],
                "license": image["license"],
                "attribution": image["attribution"],
                "truth": truth,
                "annotation": note,
            }
        )
    output = DIRECTORY / "photo-eval-manifest.json"
    output.write_text(
        json.dumps(
            {
                "version": 1,
                "scope": "Inspected public development images; not unseen warehouse accuracy",
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
