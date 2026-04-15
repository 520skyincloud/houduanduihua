from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def read_xlsx_rows(path: Path) -> list[tuple[str, str, int]]:
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", NS):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iterfind(".//a:t", NS))
                )

        sheet = workbook.find("a:sheets", NS)[0]
        sheet_rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        sheet_path = "xl/" + rel_map[sheet_rid]
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[tuple[str, str, int]] = []
        for row in root.findall(".//a:sheetData/a:row", NS)[1:]:
            values: list[str] = []
            for cell in row.findall("a:c", NS):
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", NS)
                value = ""
                if cell_type == "s" and value_node is not None:
                    value = shared_strings[int(value_node.text)]
                elif cell_type == "inlineStr":
                    inline = cell.find("a:is/a:t", NS)
                    value = inline.text if inline is not None else ""
                elif value_node is not None:
                    value = value_node.text or ""
                values.append(value)

            prompt = values[0].strip() if len(values) > 0 else ""
            completion = values[1].strip() if len(values) > 1 else ""
            row_number = int(row.attrib.get("r", "0"))
            rows.append((prompt, completion, row_number))
        return rows


def normalize_answer_type(answer: str) -> str:
    if not answer:
        return "invalid"
    if answer.strip() == "转接":
        return "handoff"
    return "direct"


def build_items(rows: list[tuple[str, str, int]], hotel_id: str) -> dict[str, object]:
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"aliases": [], "source_rows": [], "answer_type": "direct"}
    )
    invalid_counter = 0
    for prompt, completion, row_number in rows:
        answer_type = normalize_answer_type(completion)
        if answer_type == "invalid":
            invalid_counter += 1
            continue

        key = completion or f"handoff-{row_number}"
        grouped[key]["aliases"].append(prompt)
        grouped[key]["source_rows"].append(row_number)
        grouped[key]["answer_type"] = answer_type

    items = []
    for standard_answer, payload in grouped.items():
        aliases = sorted({alias for alias in payload["aliases"] if alias})
        base = standard_answer or "-".join(aliases)
        faq_id = hashlib.md5(base.encode("utf-8")).hexdigest()[:12]
        items.append(
            {
                "faq_id": faq_id,
                "hotel_id": hotel_id,
                "standard_answer": standard_answer,
                "aliases": aliases,
                "answer_type": payload["answer_type"],
                "source_rows": payload["source_rows"],
            }
        )

    items.sort(key=lambda item: (item["answer_type"], item["faq_id"]))
    return {
        "hotel_id": hotel_id,
        "source_rows": len(rows),
        "invalid_rows": invalid_counter,
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--hotel-id", default="lis-south-station")
    args = parser.parse_args()

    rows = read_xlsx_rows(args.input)
    payload = build_items(rows, args.hotel_id)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(payload['items'])} FAQ items to {args.output}")


if __name__ == "__main__":
    main()
