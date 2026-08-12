import csv
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

import requests

BATCH_SIZE = 1000

API_URL = "https://woolp.omni.manh.com/inventory/api/inventory/itemLocationSegment/bulkImport"
ORGANIZATION = "FL-INC-NA"
ENV_FILE = ".env"

DRY_RUN = False
SAVE_PAYLOADS = True
SAVE_RESPONSES = True
STOP_ON_ERROR = False
REQUEST_TIMEOUT_SECONDS = 120
SLEEP_BETWEEN_BATCHES_SECONDS = 0.25

OUTPUT_FOLDER = "bulk_import_output"

ITEM_ID_COL = "ITEM_ID"
LOCATION_ID_COL = "LOCATION_ID"
SEGMENT_COL = "AUTHORIZED_SEGMENTS"


def load_env_file(env_path: str) -> None:
    path = Path(env_path)

    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)

            key = key.strip()
            value = value.strip().strip('"').strip("'")

            os.environ.setdefault(key, value)


def clean_value(value):
    if value is None:
        return ""

    return str(value).strip()


def determine_target_location(source_location):
    source_location = clean_value(source_location)

    if source_location == "83":
        return "86"

    if source_location == "86":
        return "83"

    return None


def split_authorized_segments(segment_value):
    """
    Converts AUTHORIZED_SEGMENTS into one or more segment values.

    Example:
        "Foot Locker,Champs" -> ["Foot Locker", "Champs"]
        "Foot Locker" -> ["Foot Locker"]

    Duplicates are removed while preserving the original order.
    """
    raw_value = clean_value(segment_value)

    if not raw_value:
        return []

    segments = []
    seen_segments = set()

    for segment in raw_value.split(","):
        cleaned_segment = clean_value(segment)

        if not cleaned_segment:
            continue

        dedupe_key = cleaned_segment.casefold()

        if dedupe_key in seen_segments:
            continue

        seen_segments.add(dedupe_key)
        segments.append(cleaned_segment)

    return segments


def make_import_record(item_id, target_location, segment):
    return {
        "ItemId": item_id,
        "ItemLocationSegmentDetail": [
            {
                "Segment": segment
            }
        ],
        "LocationId": target_location
    }


def expand_rows_to_import_records(rows):
    """
    Builds one API import record per item/location/authorized segment.

    If a CSV row has multiple authorized segments, this intentionally creates
    multiple API records for the same item and target location, one per segment.
    """
    import_records = []
    skipped_rows = []
    multi_segment_rows = 0

    for row_number, row in enumerate(rows, start=2):
        item_id = clean_value(row.get(ITEM_ID_COL))
        source_location = clean_value(row.get(LOCATION_ID_COL))
        target_location = determine_target_location(source_location)
        segments = split_authorized_segments(row.get(SEGMENT_COL))

        if not target_location:
            skipped_rows.append({
                "row_number": row_number,
                "item_id": item_id,
                "location_id": source_location,
                "reason": "Unsupported LOCATION_ID"
            })
            continue

        if not item_id:
            skipped_rows.append({
                "row_number": row_number,
                "item_id": item_id,
                "location_id": source_location,
                "reason": "Missing ITEM_ID"
            })
            continue

        if not segments:
            skipped_rows.append({
                "row_number": row_number,
                "item_id": item_id,
                "location_id": source_location,
                "reason": "Missing AUTHORIZED_SEGMENTS"
            })
            continue

        if len(segments) > 1:
            multi_segment_rows += 1

        for segment in segments:
            import_records.append(
                make_import_record(
                    item_id=item_id,
                    target_location=target_location,
                    segment=segment
                )
            )

    return import_records, skipped_rows, multi_segment_rows


def build_payload(import_records):
    return {
        "Data": import_records
    }, len(import_records)


def post_payload(payload, batch_num, total_batches, access_token):
    headers = {
        "Organization": ORGANIZATION,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    print(f"Batch {batch_num}/{total_batches}: HTTP {response.status_code}")

    return response


def process_csv(csv_path, access_token):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_prefix = csv_path.stem

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    required_columns = {
        ITEM_ID_COL,
        LOCATION_ID_COL,
        SEGMENT_COL
    }

    missing_columns = required_columns - set(reader.fieldnames or [])

    if missing_columns:
        raise ValueError(
            f"{csv_path.name} missing columns: {sorted(missing_columns)}"
        )

    source_locations = {
        clean_value(x.get(LOCATION_ID_COL))
        for x in rows
    }
    source_locations.discard("")

    if len(source_locations) != 1:
        raise ValueError(
            f"{csv_path.name} contains multiple LOCATION_ID values: {source_locations}"
        )

    source_location = next(iter(source_locations))
    target_location = determine_target_location(source_location)

    if not target_location:
        print(
            f"Skipping {csv_path.name} because LOCATION_ID={source_location} is not supported."
        )
        return None

    import_records, skipped_rows, multi_segment_rows = expand_rows_to_import_records(rows)

    if not import_records:
        print(f"Skipping {csv_path.name} because no valid import records were created.")
        return None

    output_path = (
        Path(OUTPUT_FOLDER)
        / f"{batch_prefix}_location_{source_location}_to_{target_location}_{timestamp}"
    )
    output_path.mkdir(parents=True, exist_ok=True)

    csv_rows_found = len(rows)
    total_records = len(import_records)
    total_batches = math.ceil(total_records / BATCH_SIZE)

    print("\n=====================================================")
    print(f"Processing File: {csv_path.name}")
    print(f"Source Location: {source_location}")
    print(f"Target Location: {target_location}")
    print(f"CSV Rows Found: {csv_rows_found}")
    print(f"Rows With Multiple Authorized Segments: {multi_segment_rows}")
    print(f"Import Records Created: {total_records}")
    print(f"Rows Skipped: {len(skipped_rows)}")
    print(f"Batches Needed: {total_batches}")
    print("=====================================================")

    if skipped_rows:
        skipped_rows_file = output_path / "skipped_rows.json"
        with skipped_rows_file.open("w", encoding="utf-8") as f:
            json.dump(skipped_rows, f, indent=2)

    summary = []

    total_success = 0
    total_failed = 0

    for batch_index in range(total_batches):
        start = batch_index * BATCH_SIZE
        end = start + BATCH_SIZE

        batch_records = import_records[start:end]
        batch_num = batch_index + 1

        payload, record_count = build_payload(batch_records)

        payload_file = (
            output_path
            / f"{batch_prefix}_to_{target_location}_batch_{batch_num}.json"
        )

        response_file = (
            output_path
            / f"{batch_prefix}_to_{target_location}_batch_{batch_num}_response.txt"
        )

        if SAVE_PAYLOADS:
            with payload_file.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

        if DRY_RUN:
            summary.append({
                "batch": batch_num,
                "records": record_count,
                "status": "DRY_RUN"
            })

            continue

        try:
            response = post_payload(
                payload,
                batch_num,
                total_batches,
                access_token
            )

            if SAVE_RESPONSES:
                with response_file.open("w", encoding="utf-8") as f:
                    f.write(response.text)

            success = 200 <= response.status_code < 300

            if success:
                total_success += record_count
            else:
                total_failed += record_count

            summary.append({
                "batch": batch_num,
                "records": record_count,
                "status": response.status_code,
                "success": success
            })

            if not success:
                print(response.text[:1000])

                if STOP_ON_ERROR:
                    break

        except Exception as e:
            total_failed += record_count

            summary.append({
                "batch": batch_num,
                "records": record_count,
                "status": "EXCEPTION",
                "error": str(e)
            })

            print(f"Batch {batch_num}: {e}")

            if STOP_ON_ERROR:
                break

        time.sleep(SLEEP_BETWEEN_BATCHES_SECONDS)

    summary_file = output_path / "run_summary.json"

    with summary_file.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    text_summary = output_path / "processing_summary.txt"

    with text_summary.open("w", encoding="utf-8") as f:
        f.write("=========================================\n")
        f.write("Item Location Segment Bulk Import Summary\n")
        f.write("=========================================\n\n")
        f.write(f"CSV File: {csv_path.name}\n")
        f.write(f"Source Location: {source_location}\n")
        f.write(f"Target Location: {target_location}\n")
        f.write(f"CSV Rows Found: {csv_rows_found}\n")
        f.write(f"Rows With Multiple Authorized Segments: {multi_segment_rows}\n")
        f.write(f"Import Records Created: {total_records}\n")
        f.write(f"Rows Skipped: {len(skipped_rows)}\n")
        f.write(f"Records Successful: {total_success}\n")
        f.write(f"Records Failed: {total_failed}\n")
        f.write(f"Batches Processed: {total_batches}\n")

    return {
        "file": csv_path.name,
        "source_location": source_location,
        "target_location": target_location,
        "csv_rows": csv_rows_found,
        "multi_segment_rows": multi_segment_rows,
        "records": total_records,
        "skipped_rows": len(skipped_rows),
        "successful": total_success,
        "failed": total_failed
    }


def main():
    load_env_file(ENV_FILE)

    access_token = os.environ.get("ACCESS_TOKEN", "").strip()

    if not access_token and not DRY_RUN:
        raise RuntimeError(
            "ACCESS_TOKEN was not found. Add ACCESS_TOKEN=your_token_here to .env"
        )

    csv_files = sorted(Path(".").glob("*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            "No CSV files found in current folder."
        )

    print(f"Found {len(csv_files)} CSV file(s).")

    master_summary = []

    for csv_file in csv_files:
        try:
            result = process_csv(
                csv_file,
                access_token
            )

            if result:
                master_summary.append(result)

        except Exception as e:
            print(f"Failed processing {csv_file.name}: {e}")

    master_summary_file = (
        Path(OUTPUT_FOLDER)
        / f"master_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )

    Path(OUTPUT_FOLDER).mkdir(
        parents=True,
        exist_ok=True
    )

    with master_summary_file.open(
        "w",
        encoding="utf-8"
    ) as f:
        f.write("=====================================\n")
        f.write("MASTER PROCESSING SUMMARY\n")
        f.write("=====================================\n\n")

        for row in master_summary:
            f.write(f"File: {row['file']}\n")
            f.write(
                f"Location: {row['source_location']} -> {row['target_location']}\n"
            )
            f.write(f"CSV Rows: {row['csv_rows']}\n")
            f.write(f"Rows With Multiple Authorized Segments: {row['multi_segment_rows']}\n")
            f.write(f"Import Records Created: {row['records']}\n")
            f.write(f"Rows Skipped: {row['skipped_rows']}\n")
            f.write(f"Successful: {row['successful']}\n")
            f.write(f"Failed: {row['failed']}\n")
            f.write("\n")

    print("\n=====================================================")
    print("ALL CSV FILES PROCESSED")
    print(f"Master Summary: {master_summary_file}")
    print("=====================================================")


if __name__ == "__main__":
    main()
