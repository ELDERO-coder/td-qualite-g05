# -*- coding: utf-8 -*-
"""Execute les attentes Great Expectations S2 sur Bronze et historise les résultats."""
import argparse
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
from great_expectations.dataset import PandasDataset
from sqlalchemy import create_engine, text

DEFAULT_BATCH = "L-2026-10-14"
DEFAULT_URL = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306")


def get_frame(engine, query, params):
    return pd.read_sql(text(query), engine, params=params)


def completed_age(birth_date, reference_date):
    if pd.isna(birth_date) or pd.isna(reference_date):
        return None
    years = reference_date.year - birth_date.year
    before_birthday = (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day)
    return years - int(before_birthday)


def add_expectation(rows, rule_id, table_name, expectation_name, dataset, method_name,
                    method_args, failed_rows, failed_count, exported):
    result = getattr(dataset, method_name)(**method_args, result_format="COMPLETE", meta={"rule_id": rule_id})
    result_dict = result.to_json_dict() if hasattr(result, "to_json_dict") else result
    if not result_dict.get("success", False) and failed_count == 0:
        raise RuntimeError(f"{rule_id}: Great Expectations a échoué sans lignes détaillées.")
    tested = int(result_dict.get("result", {}).get("element_count", len(failed_rows)))
    failure_count = int(failed_count)
    rows.append({
        "rule_id": rule_id,
        "table_cible": table_name,
        "expectation": expectation_name,
        "nb_testees": tested,
        "nb_echecs": failure_count,
        "taux_conformite": round(100 * (tested - failure_count) / tested, 3) if tested else 100.0,
        "success": failure_count == 0,
    })
    if not failed_rows.empty:
        for row_id in failed_rows["row_id"].tolist():
            exported.append({"rule_id": rule_id, "table": table_name,
                             "expectation": expectation_name, "row_id": int(row_id)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--failures", default="reports/s2_failures.json")
    parser.add_argument("--sample-failures", default="reports/s2_failures_sample.json")
    args = parser.parse_args()
    engine = create_engine(args.url)
    batch = {"batch": args.batch_id}
    results = []
    exported = []

    clients = get_frame(engine, """
        SELECT bronze_row_id AS row_id, client_id, type_personne, nom, raison_sociale,
               date_naissance, pays, cp, telephone, email
        FROM bronze.crm_client WHERE _batch_id=:batch
    """, batch)
    contracts = get_frame(engine, """
        SELECT bronze_row_id AS row_id, contrat_id, souscripteur_id, assure_id,
               code_type, date_debut, date_fin, duree_garantie_mois
        FROM bronze.crm_contrat WHERE _batch_id=:batch
    """, batch)

    # RQ-001: seuls les contrats ayant les deux bornes renseignées sont comparés.
    date_pairs = contracts.loc[contracts.date_debut.notna() & contracts.date_fin.notna()].copy()
    start = pd.to_datetime(date_pairs.date_debut, errors="coerce")
    end = pd.to_datetime(date_pairs.date_fin, errors="coerce")
    valid_dates = start.notna() & end.notna()
    date_pairs = date_pairs.loc[valid_dates].copy()
    start = start.loc[valid_dates]
    end = end.loc[valid_dates]
    bad_dates = date_pairs.loc[end <= start, ["row_id", "contrat_id"]].copy()
    ds = PandasDataset(date_pairs.reset_index(drop=True))
    add_expectation(results, "RQ-001", "crm_contrat", "expect_column_pair_values_A_to_be_greater_than_B",
                    ds, "expect_column_pair_values_A_to_be_greater_than_B",
                    {"column_A": "date_fin", "column_B": "date_debut", "or_equal": False,
                     "parse_strings_as_datetimes": True}, bad_dates, len(bad_dates), exported)

    # RQ-002: âge révolu calculé à la date de début du contrat puis comparé à aujourd'hui.
    age_rows = get_frame(engine, """
        SELECT k.bronze_row_id AS row_id, k.contrat_id, k.date_debut,
               c.client_id, c.date_naissance
        FROM bronze.crm_contrat k
        JOIN bronze.crm_client c ON c.client_id=k.souscripteur_id AND c._batch_id=k._batch_id
        WHERE k._batch_id=:batch AND c.raison_sociale IS NULL
          AND k.date_debut IS NOT NULL AND c.date_naissance IS NOT NULL
    """, batch)
    age_rows["age_debut"] = [completed_age(pd.to_datetime(birth, errors="coerce"),
                                                pd.to_datetime(start_date, errors="coerce"))
                             for birth, start_date in zip(age_rows.date_naissance, age_rows.date_debut)]
    age_rows["age_jour"] = [completed_age(pd.to_datetime(birth, errors="coerce"), date.today())
                            for birth in age_rows.date_naissance]
    age_failures = age_rows.loc[age_rows.age_debut.lt(18), ["row_id", "contrat_id", "age_debut"]].copy()
    age_check = pd.DataFrame({"age_at_start_valid": age_rows.age_debut.ge(18)})
    ds = PandasDataset(age_check)
    add_expectation(results, "RQ-002", "crm_contrat", "age_minimum_18_a_date_debut",
                    ds, "expect_column_values_to_be_in_set",
                    {"column": "age_at_start_valid", "value_set": [True]},
                    age_failures, len(age_failures), exported)
    age_changed_since_start = int((age_rows.age_debut.lt(18) & age_rows.age_jour.ge(18)).sum())

    # RQ-003: le téléphone du souscripteur n'est ni NULL, ni vide, ni blanc.
    subscribers = clients.loc[clients.type_personne.eq("souscripteur")].copy()
    subscribers["telephone_nonblank"] = (
        subscribers.telephone.notna() & subscribers.telephone.fillna("").str.strip().ne("")
    )
    phone_missing = ~subscribers.telephone_nonblank
    ds = PandasDataset(subscribers.reset_index(drop=True))
    add_expectation(results, "RQ-003", "crm_client", "telephone_souscripteur_non_nul_vide_blanc",
                    ds, "expect_column_values_to_be_in_set",
                    {"column": "telephone_nonblank", "value_set": [True]},
                    subscribers.loc[phone_missing, ["row_id", "client_id"]].copy(),
                    int(phone_missing.sum()), exported)

    # RQ-005: code postal français constitué de cinq chiffres.
    france = clients.loc[clients.pays.eq("FR")].copy()
    cp_bad = france.cp.isna() | ~france.cp.fillna("").str.fullmatch(r"[0-9]{5}")
    ds = PandasDataset(france.reset_index(drop=True))
    add_expectation(results, "RQ-005", "crm_client", "code_postal_fr_5_chiffres",
                    ds, "expect_column_values_to_match_regex", {"column": "cp", "regex": r"^[0-9]{5}$"},
                    france.loc[cp_bad, ["row_id", "client_id"]].copy(), int(cp_bad.sum()), exported)

    # RQ-009: domaine de type_personne.
    allowed_people = {"prospect", "souscripteur", "assure"}
    people_bad = clients.type_personne.isna() | ~clients.type_personne.isin(allowed_people)
    ds = PandasDataset(clients.reset_index(drop=True))
    add_expectation(results, "RQ-009", "crm_client", "type_personne_dans_domaine",
                    ds, "expect_column_values_to_be_in_set",
                    {"column": "type_personne", "value_set": sorted(allowed_people)},
                    clients.loc[people_bad, ["row_id", "client_id"]].copy(), int(people_bad.sum()), exported)

    # RQ-010: durée de garantie parmi les valeurs autorisées.
    allowed_terms = {"12", "24", "36", "60"}
    term_bad = contracts.duree_garantie_mois.isna() | ~contracts.duree_garantie_mois.isin(allowed_terms)
    ds = PandasDataset(contracts.reset_index(drop=True))
    add_expectation(results, "RQ-010", "crm_contrat", "duree_garantie_dans_domaine",
                    ds, "expect_column_values_to_be_in_set",
                    {"column": "duree_garantie_mois", "value_set": sorted(allowed_terms)},
                    contracts.loc[term_bad, ["row_id", "contrat_id"]].copy(), int(term_bad.sum()), exported)

    # RQ-020: clés des deux tables couvertes par la séance.
    for table_name, frame, key in (("crm_client", clients, "client_id"),
                                   ("crm_contrat", contracts, "contrat_id")):
        null_mask = frame[key].isna() | frame[key].fillna("").eq("")
        ds = PandasDataset(frame.reset_index(drop=True))
        add_expectation(results, "RQ-020", table_name, f"{key}_non_nul",
                        ds, "expect_column_values_to_not_be_null", {"column": key},
                        frame.loc[null_mask, ["row_id"]].copy(), int(null_mask.sum()), exported)
        duplicate_mask = frame[key].notna() & frame[key].duplicated(keep=False)
        ds = PandasDataset(frame.reset_index(drop=True))
        add_expectation(results, "RQ-020", table_name, f"{key}_unique",
                        ds, "expect_column_values_to_be_unique", {"column": key},
                        frame.loc[duplicate_mask, ["row_id"]].copy(), int(duplicate_mask.sum()), exported)

    with engine.begin() as connection:
        for item in results:
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES (:batch, 'BRONZE', :rule, :target, :tested, :failed)
            """), {"batch": args.batch_id, "rule": item["rule_id"],
                    "target": item["table_cible"], "tested": item["nb_testees"],
                    "failed": item["nb_echecs"]})

    failure_path = Path(args.failures)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    sample_path = Path(args.sample_failures)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample = []
    for rule_id in sorted({item["rule_id"] for item in exported}):
        sample.extend([item for item in exported if item["rule_id"] == rule_id][:3])
    if len(sample) < 20:
        selected = {(item["rule_id"], item["row_id"]) for item in sample}
        remaining = [item for item in exported
                 if (item["rule_id"], item["row_id"]) not in selected]
        sample.extend(remaining[:20 - len(sample)])
    sample_path.write_text(json.dumps(sample[:20], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"batch_id": args.batch_id, "results": results,
                      "underage_at_contract_start_but_adult_today": age_changed_since_start,
                      "failure_export": str(failure_path),
                      "failure_sample": str(sample_path),
                      "failure_rows": len(exported)}, ensure_ascii=False, indent=2))
    blocking_failures = sum(item["nb_echecs"] for item in results
                            if item["rule_id"] in {"RQ-001", "RQ-002", "RQ-009", "RQ-010", "RQ-020"})
    raise SystemExit(1 if blocking_failures else 0)


if __name__ == "__main__":
    main()
