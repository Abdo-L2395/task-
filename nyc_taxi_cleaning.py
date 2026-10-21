
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import pandas as pd

CHUNK_SIZE = 100_000
JAN_START = pd.Timestamp("2021-01-01")
FEB_START = pd.Timestamp("2021-02-01")

def profile_data(path: str, chunksize: int = CHUNK_SIZE):
    """Profile the full file incrementally without loading it all into memory."""
    total_rows = 0
    null_counts = None
    dtype_seen = {}
    minimums, maximums = {}, {}
    issue_counts = {
        "pickup_outside_jan_2021": 0,
        "dropoff_outside_jan_2021": 0,
        "pickup_datetime_invalid": 0,
        "dropoff_datetime_invalid": 0,
        "negative_fare": 0,
        "zero_fare": 0,
        "negative_distance": 0,
        "zero_distance": 0,
        "passenger_count_zero": 0,
    }
    # Hashes are retained to detect exact duplicates even across chunk boundaries.
    hash_chunks = []

    for chunk in pd.read_csv(path, compression="infer", chunksize=chunksize, low_memory=False):
        total_rows += len(chunk)
        if null_counts is None:
            null_counts = chunk.isna().sum()
            for col in chunk.columns:
                dtype_seen[col] = {str(chunk[col].dtype)}
            for col in chunk.columns:
                series = chunk[col].dropna()
                minimums[col] = series.min() if not series.empty else None
                maximums[col] = series.max() if not series.empty else None
        else:
            null_counts = null_counts.add(chunk.isna().sum(), fill_value=0)
            for col in chunk.columns:
                dtype_seen[col].add(str(chunk[col].dtype))
            for col in chunk.columns:
                series = chunk[col].dropna()
                if not series.empty:
                    lo, hi = series.min(), series.max()
                    if minimums[col] is None or lo < minimums[col]:
                        minimums[col] = lo
                    if maximums[col] is None or hi > maximums[col]:
                        maximums[col] = hi

        pickup = pd.to_datetime(chunk["tpep_pickup_datetime"], errors="coerce")
        dropoff = pd.to_datetime(chunk["tpep_dropoff_datetime"], errors="coerce")
        issue_counts["pickup_datetime_invalid"] += int(pickup.isna().sum())
        issue_counts["dropoff_datetime_invalid"] += int(dropoff.isna().sum())
        issue_counts["pickup_outside_jan_2021"] += int(
            ((pickup < JAN_START) | (pickup >= FEB_START)).sum()
        )
        issue_counts["dropoff_outside_jan_2021"] += int(
            ((dropoff < JAN_START) | (dropoff >= FEB_START)).sum()
        )
        issue_counts["negative_fare"] += int((chunk["fare_amount"] < 0).sum())
        issue_counts["zero_fare"] += int((chunk["fare_amount"] == 0).sum())
        issue_counts["negative_distance"] += int((chunk["trip_distance"] < 0).sum())
        issue_counts["zero_distance"] += int((chunk["trip_distance"] == 0).sum())
        issue_counts["passenger_count_zero"] += int((chunk["passenger_count"] == 0).sum())

        hash_chunks.append(pd.util.hash_pandas_object(chunk, index=False).to_numpy())

    all_hashes = pd.concat(
        [pd.Series(values, dtype="uint64") for values in hash_chunks],
        ignore_index=True
    ).to_numpy()
    issue_counts["exact_duplicate_rows"] = int(len(all_hashes) - len(pd.unique(all_hashes)))
    dtypes = {
        col: "/".join(sorted(types))
        for col, types in dtype_seen.items()
    }
    profile = pd.DataFrame({
        "dtype": pd.Series(dtypes),
        "null_count": null_counts.astype(int),
        "null_pct": (null_counts / total_rows * 100).round(3),
        "min": pd.Series(minimums),
        "max": pd.Series(maximums),
    })
    return profile, issue_counts, total_rows

def clean(df: pd.DataFrame):
    cleaned = df.copy()
    before = len(cleaned)
    removed = {}

    pickup = pd.to_datetime(cleaned["tpep_pickup_datetime"], errors="coerce")
    bad = pickup.isna() | (pickup < JAN_START) | (pickup >= FEB_START)
    removed["pickup_outside_jan_or_invalid"] = int(bad.sum())
    cleaned = cleaned.loc[~bad].copy()

    dropoff = pd.to_datetime(cleaned["tpep_dropoff_datetime"], errors="coerce")
    bad = dropoff.isna() | (dropoff < JAN_START) | (dropoff >= FEB_START)
    removed["dropoff_outside_jan_or_invalid"] = int(bad.sum())
    cleaned = cleaned.loc[~bad].copy()

    bad = cleaned["fare_amount"] < 0
    removed["negative_fare"] = int(bad.sum())
    cleaned = cleaned.loc[~bad].copy()

    before_duplicates = len(cleaned)
    cleaned = cleaned.drop_duplicates().copy()
    removed["exact_duplicates"] = before_duplicates - len(cleaned)

    # These are flagged, not removed. Their counts are reported separately.
    removed["zero_fare_flagged_not_removed"] = 0
    removed["nonpositive_distance_flagged_not_removed"] = 0
    removed["zero_passengers_flagged_not_removed"] = 0
    assert len(cleaned) <= before
    return cleaned, removed

def clean_in_chunks(path: str, chunksize: int = CHUNK_SIZE):
    totals = {}
    rows_before = rows_after = 0
    for chunk in pd.read_csv(path, compression="infer", chunksize=chunksize, low_memory=False):
        rows_before += len(chunk)
        cleaned_chunk, removed = clean(chunk)
        rows_after += len(cleaned_chunk)
        for rule, count in removed.items():
            totals[rule] = totals.get(rule, 0) + count
        # Release each chunk before reading the next one.
        del cleaned_chunk, chunk
    print(f"Rows before cleaning: {rows_before:,}")
    print(f"Rows after cleaning:  {rows_after:,}")
    print(f"Rows removed:         {rows_before - rows_after:,}")
    print("Rows removed per rule:")
    print(pd.Series(totals, name="rows_removed").to_frame())
    return rows_before, rows_after, totals

def main():
    parser = argparse.ArgumentParser(description="Profile and clean NYC Yellow Taxi January 2021 data.")
    parser.add_argument("--input", required=True, help="Path to yellow_tripdata_2021-01.csv.gz")
    args = parser.parse_args()
    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    profile, issues, total = profile_data(str(path))
    print("\n=== FIRST 100 ROWS ===")
    print(pd.read_csv(path, compression="infer", nrows=100).head())
    print("\n=== DTYPES (first 100 rows) ===")
    print(pd.read_csv(path, compression="infer", nrows=100).dtypes)
    print("\n=== FULL DATA PROFILE ===")
    print(profile.to_string())
    print("\n=== PROBLEM COUNTS ===")
    print(pd.Series(issues, name="count").to_frame().to_string())
    print(f"\nTotal rows profiled: {total:,}")

    
    rows_before, rows_after, removed = clean_in_chunks(str(path))
    print("\nCleaning summary:")
    print(f"Rows before: {rows_before:,}; rows after: {rows_after:,}; rows removed: {rows_before - rows_after:,}")

if __name__ == "__main__":
    main()
