# -*- coding: utf-8 -*-
"""Profil YData-Profiling de crm.client et mesures des motifs US-06/US-07."""
import os
import re

import pandas as pd
from ydata_profiling import ProfileReport


DATA_ROOT = os.environ.get("ASSURCONNECT_DATA", "/home/jovyan/work/data")
CLIENT_PATH = os.path.join(DATA_ROOT, "sources/crm/client.csv")
COUNTRY_PATH = os.path.join(DATA_ROOT, "referentiels/ref_pays.csv")
REPORT_PATH = "/home/jovyan/work/reports/us06_crm_client_profiling.html"
METRICS_PATH = "/home/jovyan/work/reports/us06_crm_client_metrics.csv"
PATTERNS_PATH = "/home/jovyan/work/reports/us07_crm_motifs.csv"


def read_csv(path):
    return pd.read_csv(
        path,
        dtype="string",
        keep_default_na=False,
        na_values=[r"\N"],
        encoding="utf-8",
    )


def main():
    frame = read_csv(CLIENT_PATH)
    countries = read_csv(COUNTRY_PATH)
    if "code_pays" not in countries.columns:
        raise ValueError("La colonne code_pays est absente du référentiel pays")

    profile_rows = []
    for column in frame.columns:
        values = frame[column]
        null_mask = values.isna()
        blank_mask = values.notna() & values.str.fullmatch(r"\s*", na=False)
        populated = values[~null_mask & ~blank_mask]
        lengths = populated.str.len()
        profile_rows.append({
            "column": column,
            "rows": len(values),
            "nulls": int(null_mask.sum()),
            "blanks": int(blank_mask.sum()),
            "nonempty": len(populated),
            "distinct_nonempty": int(populated.nunique()),
            "length_min": int(lengths.min()) if len(lengths) else None,
            "length_median": float(lengths.median()) if len(lengths) else None,
            "length_max": int(lengths.max()) if len(lengths) else None,
        })

    motifs = []

    def add_motif(attribute, scope, values, pattern, reference_codes=None):
        present = values.notna() & ~values.str.fullmatch(r"\s*", na=False)
        tested_values = values[present]
        if pattern is None:
            conforms = tested_values.isin(reference_codes)
        elif reference_codes is None:
            conforms = tested_values.str.fullmatch(pattern, na=False)
        else:
            conforms = tested_values.str.fullmatch(pattern, na=False) & tested_values.isin(reference_codes)
        conforming = int(conforms.sum())
        failures = tested_values[~conforms]
        masked_example = (
            re.sub(r"\d", "X", str(failures.iloc[0]))
            if len(failures)
            else ""
        )
        motifs.append({
            "attribute": attribute,
            "scope": scope,
            "pattern": pattern or "code présent exactement dans ref_pays",
            "tested_nonempty": len(tested_values),
            "conforming": conforming,
            "nonconforming": len(tested_values) - conforming,
            "null_or_blank_in_scope": int((~present).sum()),
            "masked_nonconforming_example": masked_example,
        })

    add_motif("Code postal", "Toutes les valeurs CRM renseignées", frame["cp"], r"\d{5}")
    france_scope = frame["pays"].fillna("").str.strip().str.upper().eq("FR")
    add_motif(
        "Téléphone",
        "Clients dont pays normalisé vaut FR, téléphones renseignés",
        frame.loc[france_scope, "telephone"],
        r"0[1-9]\d{8}",
    )
    reference_codes = set(countries["code_pays"].dropna().astype(str))
    add_motif(
        "Pays - forme",
        "Toutes les valeurs CRM renseignées",
        frame["pays"],
        r"[A-Z]{2}",
    )
    add_motif(
        "Pays - référentiel",
        "Toutes les valeurs CRM renseignées, correspondance exacte",
        frame["pays"],
        None,
        reference_codes,
    )

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    pd.DataFrame(profile_rows).to_csv(METRICS_PATH, index=False)
    pd.DataFrame(motifs).to_csv(PATTERNS_PATH, index=False)
    print(f"rows={len(frame)} columns={len(frame.columns)}")
    print(f"metrics={METRICS_PATH}")
    print(f"motifs={PATTERNS_PATH}")
    print(pd.DataFrame(profile_rows).to_string(index=False))
    print(pd.DataFrame(motifs).to_string(index=False))
    ProfileReport(frame, title="CRM client profile - US-06", minimal=True).to_file(REPORT_PATH)
    print(f"profile={REPORT_PATH}")


if __name__ == "__main__":
    main()
