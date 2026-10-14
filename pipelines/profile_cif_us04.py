# -*- coding: utf-8 -*-
"""Profilage YData-Profiling et mesures reproductibles pour US-04."""
import os
import re

import pandas as pd
from ydata_profiling import ProfileReport


DATA_PATH = os.environ.get(
    "US04_CIF_CSV", "/home/jovyan/work/data/sources/cif/clients.csv"
)
REPORT_PATH = os.environ.get(
    "US04_PROFILE_HTML", "/home/jovyan/work/reports/us04_cif_profiling.html"
)
METRICS_PATH = os.environ.get(
    "US04_METRICS_CSV", "/home/jovyan/work/reports/us04_cif_metrics.csv"
)
PATTERNS = {
    "column0": r"K\d{6}",
    "column3": r"\d{2}/\d{2}/\d{4}",
    "column5": r"\d{5}",
    "column7": r"[A-Z]{2}",
    "column8": r"\d{10}",
    "column9": r"[^\s@]+@[^\s@]+\.[^\s@]+",
}


def main():
    frame = pd.read_csv(
        DATA_PATH,
        dtype="string",
        keep_default_na=False,
        na_values=[r"\N"],
        encoding="utf-8",
    )
    expected_columns = [f"column{index}" for index in range(10)]
    if list(frame.columns) != expected_columns:
        raise ValueError(f"Colonnes CIF inattendues: {list(frame.columns)}")

    metrics = []
    for column in expected_columns:
        values = frame[column]
        null_mask = values.isna()
        blank_mask = values.notna() & values.str.fullmatch(r"\s*", na=False)
        populated = values[~null_mask & ~blank_mask]
        lengths = populated.str.len()
        pattern = PATTERNS.get(column)
        motif_matches = (
            int(populated.str.fullmatch(pattern, na=False).sum())
            if pattern
            else None
        )
        valid_dates = None
        if column == "column3":
            parsed = pd.to_datetime(
                populated, format="%d/%m/%Y", errors="coerce"
            )
            valid_dates = int(parsed.notna().sum())

        metrics.append({
            "column": column,
            "rows": len(values),
            "nulls": int(null_mask.sum()),
            "blanks": int(blank_mask.sum()),
            "nonempty": len(populated),
            "distinct_nonempty": int(populated.nunique()),
            "length_min": int(lengths.min()) if len(lengths) else None,
            "length_median": float(lengths.median()) if len(lengths) else None,
            "length_max": int(lengths.max()) if len(lengths) else None,
            "motif": pattern,
            "motif_matches": motif_matches,
            "valid_dates": valid_dates,
        })

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    ProfileReport(frame, title="CIF profile - US-04", minimal=True).to_file(REPORT_PATH)
    pd.DataFrame(metrics).to_csv(METRICS_PATH, index=False)
    print(f"rows={len(frame)} columns={len(frame.columns)}")
    print(f"profile={REPORT_PATH}")
    print(f"metrics={METRICS_PATH}")
    print(pd.DataFrame(metrics).to_string(index=False))


if __name__ == "__main__":
    main()
