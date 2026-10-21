# -*- coding: utf-8 -*-
"""Construit Silver et un Gold conservateur avec conservation du lignage Bronze."""
import argparse
import re
import unicodedata
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text

DEFAULT_BATCH = "L-2026-10-14"
DEFAULT_URL = "mysql+pymysql://root:root@mariadb:3306/crm"


def clean(value):
    if pd.isna(value):
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def normalized(value):
    value = clean(value)
    if not value:
        return None
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.casefold()


def parsed_date(value, cif=False):
    value = clean(value)
    if not value:
        return None
    formats = ("%d/%m/%Y", "%d/%m/%y") if cif else ("%Y-%m-%d",)
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def normalize_phone(value):
    value = clean(value)
    if not value:
        return None
    compact = re.sub(r"[\s().-]", "", value)
    if compact.startswith("+33"):
        compact = "0" + compact[3:]
    elif compact.startswith("0033"):
        compact = "0" + compact[4:]
    return compact[:20]


def map_person(value):
    key = normalized(value)
    return {
        "prospect": "prospect", "prosp": "prospect", "prosp.": "prospect",
        "souscripteur": "souscripteur", "assure": "assure", "client": None,
    }.get(key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--reference-date", default="2026-10-14")
    args = parser.parse_args()
    engine = create_engine(args.url)
    params = {"batch": args.batch_id, "reference": args.reference_date}
    crm = pd.read_sql(text("""
        SELECT bronze_row_id, client_id, type_personne, nom, prenom, raison_sociale,
               date_naissance, adresse, cp, ville, pays, telephone, email
        FROM bronze.crm_client WHERE _batch_id=:batch ORDER BY bronze_row_id
    """), engine, params=params)
    cif = pd.read_sql(text("""
        SELECT bronze_row_id, column0, column1, column2, column3, column4,
               column5, column6, column7, column8, column9
        FROM bronze.cif_clients WHERE _batch_id=:batch ORDER BY bronze_row_id
    """), engine, params=params)
    with engine.connect() as connection:
        country_rows = connection.execute(text("SELECT code_pays, nom_pays FROM silver.ref_pays")).all()
        postal_rows = connection.execute(text("SELECT code_postal, commune FROM silver.ref_postal")).all()
        active_ids = {row[0] for row in connection.execute(text("""
            SELECT souscripteur_id FROM crm.contrat
            WHERE date_debut<=:reference AND (date_fin IS NULL OR date_fin>=:reference)
              AND date_derniere_cotisation>=DATE_SUB(:reference, INTERVAL 3 MONTH)
            UNION SELECT assure_id FROM crm.contrat
            WHERE date_debut<=:reference AND (date_fin IS NULL OR date_fin>=:reference)
              AND date_derniere_cotisation>=DATE_SUB(:reference, INTERVAL 3 MONTH)
        """), params)}

    country_by_name = {normalized(name): code for code, name in country_rows}
    country_codes = {code for code, _ in country_rows}
    valid_postal_pairs = {(str(code).strip(), normalized(city)) for code, city in postal_rows}
    silver_records = []

    def add_record(system, bronze_id, source_id, person_type, identity, first_name,
                   birth_date, address, postal, city, country, phone, email):
        identity = clean(identity)
        first_name = clean(first_name)
        postal = clean(postal)
        city = clean(city)
        country = clean(country)
        if postal and postal.isdigit() and len(postal) == 4 and city:
            candidate = postal.zfill(5)
            if (candidate, normalized(city)) in valid_postal_pairs:
                postal = candidate
        country_key = normalized(country)
        country_iso = country if country in country_codes else country_by_name.get(country_key)
        birth = parsed_date(birth_date, cif=(system == "cif"))
        valid = bool(identity and person_type and (not country or country_iso))
        silver_records.append({
            "bronze_row_id": int(bronze_id), "source_systeme": system,
            "source_id": str(source_id), "type_personne": person_type,
            "identite_normalisee": normalized(identity),
            "prenom_normalise": normalized(first_name), "date_naissance": birth,
            "adresse_normalisee": clean(address), "cp": postal,
            "ville_normalisee": normalized(city), "pays_iso": country_iso,
            "telephone_normalise": normalize_phone(phone),
            "email_normalise": clean(email).casefold() if clean(email) else None,
            "statut_qualite": "VALIDE" if valid else "A_SURVEILLER",
            "_batch_id": args.batch_id,
        })

    for row in crm.itertuples(index=False):
        identity = row.raison_sociale if clean(row.raison_sociale) else row.nom
        add_record("crm", row.bronze_row_id, row.client_id, map_person(row.type_personne),
                   identity, row.prenom, row.date_naissance, row.adresse, row.cp,
                   row.ville, row.pays, row.telephone, row.email)
    for row in cif.itertuples(index=False):
        add_record("cif", row.bronze_row_id, row.column0, None, row.column1,
                   row.column2, row.column3, row.column4, row.column5,
                   row.column6, row.column7, row.column8, row.column9)

    silver_frame = pd.DataFrame(silver_records)
    with engine.begin() as connection:
        connection.execute(text("USE gold"))
        connection.execute(text("""
            DELETE x FROM gold.xref_identifiants x
            JOIN gold.client_unique g ON g.cli_id=x.cli_id
            WHERE g._batch_id=:batch
        """), {"batch": args.batch_id})
        connection.execute(text("DELETE FROM gold.client_unique WHERE _batch_id=:batch"),
                           {"batch": args.batch_id})
        connection.execute(text("DELETE FROM silver.client WHERE _batch_id=:batch"),
                           {"batch": args.batch_id})
        silver_frame.to_sql("client", connection, schema="silver", if_exists="append",
                            index=False, method="multi", chunksize=1000)

    silver = pd.read_sql(text("""
        SELECT silver_row_id, bronze_row_id, source_systeme, source_id, type_personne,
               identite_normalisee, prenom_normalise, date_naissance, cp,
               ville_normalisee, pays_iso, telephone_normalise, email_normalise
        FROM silver.client WHERE _batch_id=:batch ORDER BY source_systeme, source_id
    """), engine, params={"batch": args.batch_id})
    # Only a unique one-to-one, exact cross-system identity key is merged.
    key_columns = ["identite_normalisee", "prenom_normalise", "date_naissance", "cp"]
    crm_candidates = silver.loc[silver.source_systeme.eq("crm")].dropna(subset=key_columns)
    cif_candidates = silver.loc[silver.source_systeme.eq("cif")].dropna(subset=key_columns)
    crm_unique = crm_candidates.loc[~crm_candidates.duplicated(subset=key_columns, keep=False)]
    cif_unique = cif_candidates.loc[~cif_candidates.duplicated(subset=key_columns, keep=False)]
    matches = crm_unique.reset_index(names="crm_index").merge(
        cif_unique.reset_index(names="cif_index"),
        on=key_columns, how="inner", validate="one_to_one", suffixes=("_crm", "_cif"))
    matched_pairs = list(zip(matches.crm_index.astype(int), matches.cif_index.astype(int)))
    pair_group = {}
    for group_number, (crm_index, cif_index) in enumerate(matched_pairs):
        pair_group[crm_index] = group_number
        pair_group[cif_index] = group_number
    next_group = len(matched_pairs)
    group_ids = []
    for index in silver.index:
        if index in pair_group:
            group_ids.append(pair_group[index])
        else:
            group_ids.append(next_group)
            next_group += 1
    silver["_group_id"] = group_ids
    silver["_source_priority"] = silver.source_systeme.map({"crm": 0, "cif": 1})
    ordered = silver.sort_values(["_group_id", "_source_priority"])
    gold_frame = ordered.groupby("_group_id", sort=True).agg(
        nom_reference=("identite_normalisee", "first"),
        date_naissance=("date_naissance", "first"), cp=("cp", "first"),
        ville=("ville_normalisee", "first"), pays_iso=("pays_iso", "first"),
        telephone=("telephone_normalise", "first"), email=("email_normalise", "first"),
        nb_identifiants_source=("source_id", "size"),
    ).reset_index(drop=True)
    gold_frame["cli_id"] = [f"CLI-{index:06d}" for index in range(1, len(gold_frame) + 1)]
    gold_frame["nom_reference"] = gold_frame.nom_reference.fillna("IDENTITE_INCONNUE")
    active_mask = ordered.source_id.isin(active_ids).groupby(ordered._group_id).any()
    person_types = ordered.groupby("_group_id").type_personne.agg(
        lambda values: set(values.dropna()))
    gold_frame["statut_client"] = [
        "ACTIF" if active_mask.loc[group_id] else
        "ASSURE" if "assure" in person_types.loc[group_id] else
        "PROSPECT" if "prospect" in person_types.loc[group_id] else "INACTIF"
        for group_id in range(len(gold_frame))
    ]
    gold_frame["_batch_id"] = args.batch_id
    cli_by_group = {group_id: f"CLI-{group_id + 1:06d}" for group_id in range(len(gold_frame))}
    xref_frame = ordered[["source_systeme", "source_id", "bronze_row_id", "silver_row_id", "_group_id"]].copy()
    xref_frame["cli_id"] = xref_frame._group_id.map(cli_by_group)
    xref_frame = xref_frame[["cli_id", "source_systeme", "source_id", "bronze_row_id", "silver_row_id"]]
    with engine.begin() as connection:
        gold_frame.to_sql("client_unique", connection, schema="gold", if_exists="append",
                          index=False, method="multi", chunksize=200)
        xref_frame.to_sql("xref_identifiants", connection, schema="gold", if_exists="append",
                          index=False, method="multi", chunksize=500)

    print(f"Silver client: {len(silver_frame)} lignes ({len(crm)} CRM + {len(cif)} CIF); "
          f"surveillance={int((silver_frame.statut_qualite=='A_SURVEILLER').sum())}; rejets=0")
    print(f"Gold client_unique: {len(gold_frame)}; xref: {len(xref_frame)}; "
            f"fusion exacte CRM-CIF: {len(matched_pairs)} paires")
    print("Conservation Silver: bronze CRM clients + CIF clients = Silver + rejets; "
          "les anomalies sont conservées avec statut A_SURVEILLER.")
    print("Attention: les CIF sans type_personne connu sont provisoirement INACTIF dans Gold; "
          "cette interprétation doit être validée par le Data Owner avant publication.")


if __name__ == "__main__":
    main()
