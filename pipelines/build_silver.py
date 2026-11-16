# -*- coding: utf-8 -*-
"""Standardise les entités Bronze vers Silver et journalise les rejets S."""
import argparse
import os
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text


BATCH_DEFAULT = "L-2026-10-14"
DB_URL_DEFAULT = "mysql+pymysql://root:root@mariadb:3306"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "pipelines" / "s4_quality_schema.sql"
REPORTS = ROOT / "reports"
VALID_TYPES = {"prospect", "souscripteur", "assure"}
VALID_DURATIONS = {"12", "24", "36", "60"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FR_PHONE_RE = re.compile(r"^0[1-9]\d{8}$")


def present(value):
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def display(value):
    if not present(value):
        return None
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).upper()


def key(value):
    if not present(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        value.encode("ascii", "ignore").decode("ascii").lower(),
    ).strip()


def parse_date(value, cif=False):
    if not present(value):
        return None
    parsed = pd.to_datetime(
        str(value).strip(),
        format="%d/%m/%Y" if cif else None,
        errors="coerce",
    )
    return None if pd.isna(parsed) else parsed.date()


def parse_decimal(value):
    if not present(value):
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def normalise_country(value, code_map, name_map):
    if not present(value):
        return None
    cleaned = str(value).strip()
    if len(cleaned) == 2 and cleaned.upper() in code_map:
        return cleaned.upper()
    return name_map.get(key(cleaned))


def normalise_postal(value, country):
    if not present(value):
        return None, False
    cleaned = re.sub(r"\s+", "", str(value).strip()).upper()
    if country == "FR" and cleaned.isdigit() and len(cleaned) < 5:
        return cleaned.zfill(5), True
    return cleaned, False


def normalise_phone(value, country):
    if not present(value):
        return None
    source = str(value).strip()
    digits = re.sub(r"\D", "", source)
    if country == "FR":
        if source.startswith("+33") and len(digits) == 11:
            digits = "0" + digits[2:]
        elif source.startswith("0033") and len(digits) == 12:
            digits = "0" + digits[4:]
        elif len(digits) == 9:
            digits = "0" + digits
    return digits or None


def age_at(birth, reference):
    if not birth or not reference:
        return None
    return reference.year - birth.year - (
        (reference.month, reference.day) < (birth.month, birth.day)
    )


def add_rejection(rows, batch_id, entity, system, bronze_row_id, rule_id, reason):
    rows.append({
        "batch_id": batch_id,
        "entite": entity,
        "source_systeme": system,
        "bronze_row_id": int(bronze_row_id),
        "rule_id": rule_id,
        "porte": "S",
        "motif": reason,
    })


def insert_many(connection, statement, rows):
    for offset in range(0, len(rows), 1000):
        connection.execute(text(statement), rows[offset:offset + 1000])


def prune_rows(connection, table, batch_id, source_system, valid_ids):
    sql = text(
        f"DELETE FROM silver.`{table}` "
        "WHERE _batch_id = :batch_id AND source_systeme = :source_system "
        "AND bronze_row_id NOT IN :valid_ids"
    ).bindparams(bindparam("valid_ids", expanding=True))
    connection.execute(sql, {
        "batch_id": batch_id,
        "source_system": source_system,
        "valid_ids": valid_ids or [-1],
    })


def prune_entity(connection, table, batch_id, valid_ids):
    sql = text(
        f"DELETE FROM silver.`{table}` "
        "WHERE _batch_id = :batch_id AND bronze_row_id NOT IN :valid_ids"
    ).bindparams(bindparam("valid_ids", expanding=True))
    connection.execute(sql, {
        "batch_id": batch_id,
        "valid_ids": valid_ids or [-1],
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", DB_URL_DEFAULT))
    args = parser.parse_args()
    engine = create_engine(args.url)

    client_rows = []
    contract_rows = []
    claim_rows = []
    rejects = []
    transformations = []
    client_source_ids = {"crm": set(), "cif": set()}
    crm_people = {}
    warning_counters = {}

    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT statut FROM dq.lot_ingestion WHERE batch_id = :batch_id"),
            {"batch_id": args.batch_id},
        ).scalar()
        if status != "TERMINE":
            raise RuntimeError(f"Le lot {args.batch_id} n'existe pas ou n'est pas terminé")

        countries = pd.read_sql_query(
            text("SELECT code_pays, nom_pays FROM silver.ref_pays"), connection
        )
        code_map = {str(row.code_pays).strip().upper() for row in countries.itertuples()}
        country_names = {
            key(row.nom_pays): str(row.code_pays).strip().upper()
            for row in countries.itertuples()
        }
        postal_frame = pd.read_sql_query(
            text("SELECT code_postal, commune FROM silver.ref_postal"), connection
        )
        postal_pairs = {
            (str(row.code_postal).strip(), key(row.commune))
            for row in postal_frame.itertuples()
        }
        ban_frame = pd.read_sql_query(text("""
            SELECT id_ban, numero, voie, code_postal, commune FROM silver.ref_ban
        """), connection)
        ban_keys = {}
        for row in ban_frame.itertuples():
            address_key = key(f"{row.numero} {row.voie}")
            cp = str(row.code_postal).strip()
            ban_keys[(address_key, cp, key(row.commune))] = str(row.id_ban).strip()
        contract_types = set(connection.execute(
            text("SELECT code_type FROM crm.type_contrat")
        ).scalars())

        crm = pd.read_sql_query(text("""
            SELECT * FROM bronze.crm_client WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        for row in crm.to_dict("records"):
            system = "crm"
            row_id = int(row["bronze_row_id"])
            source_id = str(row["client_id"]) if present(row["client_id"]) else None
            country = normalise_country(row["pays"], code_map, country_names)
            country_invalid = country is None
            raw_type = key(row["type_personne"])
            person_type = raw_type if raw_type in VALID_TYPES else None
            type_invalid = person_type is None
            blocked = False
            if country_invalid:
                add_rejection(
                    rejects, args.batch_id, "client", system, row_id,
                    "RQ-007", "pays absent ou non reconnu dans le référentiel",
                )
                blocked = True
            if type_invalid:
                add_rejection(
                    rejects, args.batch_id, "client", system, row_id,
                    "RQ-009", "type_personne absent ou hors domaine",
                )
                blocked = True
            if blocked:
                continue

            cp, restored = normalise_postal(row["cp"], country)
            phone = normalise_phone(row["telephone"], country)
            email = str(row["email"]).strip().lower() if present(row["email"]) else None
            identity = display(
                row["raison_sociale"]
                if present(row["raison_sociale"])
                else row["nom"]
            )
            first_name = display(row["prenom"])
            city = display(row["ville"])
            address = display(row["adresse"])
            birth = parse_date(row["date_naissance"])
            warnings = []
            if person_type == "souscripteur" and not phone:
                warnings.append("RQ-003")
            if country == "FR" and phone and not FR_PHONE_RE.fullmatch(phone):
                warnings.append("RQ-004")
            if country == "FR" and (not cp or not re.fullmatch(r"\d{5}", cp)):
                warnings.append("RQ-005")
            if country == "FR" and (
                not cp or not city or (cp, key(city)) not in postal_pairs
            ):
                warnings.append("RQ-006")
            if email and not EMAIL_RE.fullmatch(email):
                warnings.append("RQ-008")
            for rule_id in warnings:
                warning_counters[rule_id] = warning_counters.get(rule_id, 0) + 1
            if restored:
                transformations.append({
                    "traitement": "Restauration du zéro initial du code postal",
                    "table": "crm_client",
                    "bronze_row_id": row_id,
                })
            client_rows.append({
                "bronze_row_id": row_id,
                "source_systeme": system,
                "source_id": source_id,
                "type_personne": person_type,
                "identite_normalisee": identity,
                "prenom_normalise": first_name,
                "date_naissance": birth,
                "adresse_normalisee": address,
                "cp": cp,
                "ville_normalisee": city,
                "pays_iso": country,
                "telephone_normalise": phone,
                "email_normalise": email,
                "statut_qualite": "A_SURVEILLER" if warnings else "VALIDE",
                "_batch_id": args.batch_id,
            })
            if source_id:
                client_source_ids[system].add(source_id)
                crm_people[source_id] = {
                    "type_personne": person_type,
                    "raison_sociale": present(row["raison_sociale"]),
                    "date_naissance": birth,
                }

        cif = pd.read_sql_query(text("""
            SELECT * FROM bronze.cif_clients WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        for row in cif.to_dict("records"):
            system = "cif"
            row_id = int(row["bronze_row_id"])
            source_id = str(row["column0"]) if present(row["column0"]) else None
            country = normalise_country(row["column7"], code_map, country_names)
            if country is None:
                add_rejection(
                    rejects, args.batch_id, "client", system, row_id,
                    "RQ-007", "pays absent ou non reconnu dans le référentiel",
                )
                continue

            cp, restored = normalise_postal(row["column5"], country)
            phone = normalise_phone(row["column8"], country)
            email = str(row["column9"]).strip().lower() if present(row["column9"]) else None
            identity = display(row["column1"])
            first_name = display(row["column2"])
            city = display(row["column6"])
            address = display(row["column4"])
            birth = parse_date(row["column3"], cif=True)
            warnings = []
            if country == "FR" and phone and not FR_PHONE_RE.fullmatch(phone):
                warnings.append("RQ-004")
            if country == "FR" and (not cp or not re.fullmatch(r"\d{5}", cp)):
                warnings.append("RQ-005")
            if country == "FR" and (
                not cp or not city or (cp, key(city)) not in postal_pairs
            ):
                warnings.append("RQ-006")
            if email and not EMAIL_RE.fullmatch(email):
                warnings.append("RQ-008")
            for rule_id in warnings:
                warning_counters[rule_id] = warning_counters.get(rule_id, 0) + 1
            if restored:
                transformations.append({
                    "traitement": "Restauration du zéro initial du code postal",
                    "table": "cif_clients",
                    "bronze_row_id": row_id,
                })
            client_rows.append({
                "bronze_row_id": row_id,
                "source_systeme": system,
                "source_id": source_id,
                "type_personne": None,
                "identite_normalisee": identity,
                "prenom_normalise": first_name,
                "date_naissance": birth,
                "adresse_normalisee": address,
                "cp": cp,
                "ville_normalisee": city,
                "pays_iso": country,
                "telephone_normalise": phone,
                "email_normalise": email,
                "statut_qualite": "A_SURVEILLER" if warnings else "VALIDE",
                "_batch_id": args.batch_id,
            })
            if source_id:
                client_source_ids[system].add(source_id)

        contracts = pd.read_sql_query(text("""
            SELECT * FROM bronze.crm_contrat WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        for row in contracts.to_dict("records"):
            row_id = int(row["bronze_row_id"])
            contract_id = str(row["contrat_id"]) if present(row["contrat_id"]) else None
            subscriber = str(row["souscripteur_id"]) if present(row["souscripteur_id"]) else None
            assured_raw = str(row["assure_id"]).strip() if present(row["assure_id"]) else None
            assured = None if assured_raw == "0" else assured_raw
            start = parse_date(row["date_debut"])
            end = parse_date(row["date_fin"])
            duration = str(row["duree_garantie_mois"]).strip() if present(
                row["duree_garantie_mois"]
            ) else None
            failed = []
            if not start or not end or end <= start:
                failed.append(("RQ-001", "date de fin absente ou non postérieure au début"))
            if duration not in VALID_DURATIONS:
                failed.append(("RQ-010", "durée de garantie absente ou hors domaine"))
            for rule_id, reason in failed:
                add_rejection(
                    rejects, args.batch_id, "contrat", "crm", row_id, rule_id, reason
                )
            if failed:
                continue

            warning = (
                not subscriber
                or subscriber not in client_source_ids["crm"]
                or not row["code_type"]
                or row["code_type"] not in contract_types
                or (assured and assured not in client_source_ids["crm"])
            )
            if subscriber:
                subscriber_client = crm_people.get(subscriber)
                birth = subscriber_client["date_naissance"] if subscriber_client else None
                if (
                    subscriber_client
                    and subscriber_client["type_personne"] == "souscripteur"
                    and not subscriber_client["raison_sociale"]
                    and age_at(birth, start) is not None
                    and age_at(birth, start) < 18
                ):
                    warning = True
            contract_rows.append({
                "bronze_row_id": row_id,
                "contrat_id": contract_id,
                "souscripteur_id": subscriber,
                "assure_id": assured,
                "code_type": row["code_type"] if present(row["code_type"]) else None,
                "date_debut": start,
                "date_fin": end,
                "duree_garantie_mois": int(duration),
                "prime_annuelle": parse_decimal(row["prime_annuelle"]),
                "date_derniere_cotisation": parse_date(
                    row["date_derniere_cotisation"]
                ),
                "statut_qualite": "A_SURVEILLER" if warning or assured_raw == "0"
                else "VALIDE",
                "_batch_id": args.batch_id,
            })

        claims = pd.read_sql_query(text("""
            SELECT * FROM bronze.crm_sinistre WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        contract_dates = {
            str(row["contrat_id"]): (
                parse_date(row["date_debut"]), parse_date(row["date_fin"])
            )
            for row in contracts.to_dict("records")
            if present(row["contrat_id"])
        }
        for row in claims.to_dict("records"):
            row_id = int(row["bronze_row_id"])
            claim_id = str(row["sinistre_id"]) if present(row["sinistre_id"]) else None
            contract_id = str(row["contrat_id"]) if present(row["contrat_id"]) else None
            address = display(row["adresse_sinistre"])
            cp, _ = normalise_postal(row["cp_sinistre"], "FR")
            city = display(row["ville_sinistre"])
            ban_id = ban_keys.get((key(address), cp or "", key(city)))
            if not ban_id:
                add_rejection(
                    rejects, args.batch_id, "sinistre", "crm", row_id,
                    "RQ-014", "adresse non rapprochée du référentiel BAN",
                )
                continue
            occurrence = parse_date(row["date_survenance"])
            period = contract_dates.get(contract_id)
            outside_warranty = bool(
                not occurrence or not period or not period[0] or not period[1]
                or occurrence < period[0] or occurrence > period[1]
            )
            claim_rows.append({
                "bronze_row_id": row_id,
                "sinistre_id": claim_id,
                "contrat_id": contract_id,
                "date_survenance": occurrence,
                "date_declaration": parse_date(row["date_declaration"]),
                "type_sinistre": row["type_sinistre"],
                "montant_estime": parse_decimal(row["montant_estime"]),
                "adresse_sinistre": address,
                "cp_sinistre": cp,
                "ville_sinistre": city,
                "canal_saisie": row["canal_saisie"],
                "id_ban": ban_id,
                "statut_qualite": "A_SURVEILLER" if outside_warranty else "VALIDE",
                "_batch_id": args.batch_id,
            })

    client_columns = (
        "bronze_row_id, source_systeme, source_id, type_personne, "
        "identite_normalisee, prenom_normalise, date_naissance, adresse_normalisee, "
        "cp, ville_normalisee, pays_iso, telephone_normalise, email_normalise, "
        "statut_qualite, _batch_id"
    )
    client_update = ", ".join(
        f"{column}=VALUES({column})"
        for column in client_columns.replace(" ", "").split(",")
        if column not in {"bronze_row_id", "source_systeme"}
    )
    client_insert = (
        f"INSERT INTO silver.client ({client_columns}) VALUES "
        "(:bronze_row_id, :source_systeme, :source_id, :type_personne, "
        ":identite_normalisee, :prenom_normalise, :date_naissance, :adresse_normalisee, "
        ":cp, :ville_normalisee, :pays_iso, :telephone_normalise, :email_normalise, "
        ":statut_qualite, :_batch_id) "
        f"ON DUPLICATE KEY UPDATE {client_update}"
    )
    contract_insert = """
        INSERT INTO silver.contrat
            (bronze_row_id, contrat_id, souscripteur_id, assure_id, code_type,
             date_debut, date_fin, duree_garantie_mois, prime_annuelle,
             date_derniere_cotisation, statut_qualite, _batch_id)
        VALUES
            (:bronze_row_id, :contrat_id, :souscripteur_id, :assure_id, :code_type,
             :date_debut, :date_fin, :duree_garantie_mois, :prime_annuelle,
             :date_derniere_cotisation, :statut_qualite, :_batch_id)
        ON DUPLICATE KEY UPDATE
            contrat_id=VALUES(contrat_id), souscripteur_id=VALUES(souscripteur_id),
            assure_id=VALUES(assure_id), code_type=VALUES(code_type),
            date_debut=VALUES(date_debut), date_fin=VALUES(date_fin),
            duree_garantie_mois=VALUES(duree_garantie_mois),
            prime_annuelle=VALUES(prime_annuelle),
            date_derniere_cotisation=VALUES(date_derniere_cotisation),
            statut_qualite=VALUES(statut_qualite), _batch_id=VALUES(_batch_id)
    """
    claim_insert = """
        INSERT INTO silver.sinistre
            (bronze_row_id, sinistre_id, contrat_id, date_survenance,
             date_declaration, type_sinistre, montant_estime, adresse_sinistre,
             cp_sinistre, ville_sinistre, canal_saisie, id_ban, statut_qualite,
             _batch_id)
        VALUES
            (:bronze_row_id, :sinistre_id, :contrat_id, :date_survenance,
             :date_declaration, :type_sinistre, :montant_estime, :adresse_sinistre,
             :cp_sinistre, :ville_sinistre, :canal_saisie, :id_ban,
             :statut_qualite, :_batch_id)
        ON DUPLICATE KEY UPDATE
            sinistre_id=VALUES(sinistre_id), contrat_id=VALUES(contrat_id),
            date_survenance=VALUES(date_survenance),
            date_declaration=VALUES(date_declaration), type_sinistre=VALUES(type_sinistre),
            montant_estime=VALUES(montant_estime),
            adresse_sinistre=VALUES(adresse_sinistre), cp_sinistre=VALUES(cp_sinistre),
            ville_sinistre=VALUES(ville_sinistre), canal_saisie=VALUES(canal_saisie),
            id_ban=VALUES(id_ban), statut_qualite=VALUES(statut_qualite),
            _batch_id=VALUES(_batch_id)
    """
    rejection_insert = """
        INSERT INTO dq.rejets
            (batch_id, entite, source_systeme, bronze_row_id, rule_id, porte, motif)
        VALUES
            (:batch_id, :entite, :source_systeme, :bronze_row_id, :rule_id, :porte, :motif)
    """

    with engine.begin() as connection:
        for statement in SCHEMA_FILE.read_text(encoding="utf-8").split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.execute(
            text("DELETE FROM dq.rejets WHERE batch_id = :batch_id"),
            {"batch_id": args.batch_id},
        )
        prune_rows(
            connection, "client", args.batch_id, "crm",
            [row["bronze_row_id"] for row in client_rows if row["source_systeme"] == "crm"],
        )
        prune_rows(
            connection, "client", args.batch_id, "cif",
            [row["bronze_row_id"] for row in client_rows if row["source_systeme"] == "cif"],
        )
        prune_entity(
            connection, "contrat", args.batch_id,
            [row["bronze_row_id"] for row in contract_rows],
        )
        prune_entity(
            connection, "sinistre", args.batch_id,
            [row["bronze_row_id"] for row in claim_rows],
        )
        insert_many(connection, client_insert, client_rows)
        insert_many(connection, contract_insert, contract_rows)
        insert_many(connection, claim_insert, claim_rows)
        insert_many(connection, rejection_insert, rejects)

        reconciliation = []
        for source_table, silver_table, entity, system in (
            ("crm_client", "client", "client", "crm"),
            ("cif_clients", "client", "client", "cif"),
            ("crm_contrat", "contrat", "contrat", "crm"),
            ("crm_sinistre", "sinistre", "sinistre", "crm"),
        ):
            bronze_count = int(connection.execute(text(
                f"SELECT COUNT(*) FROM bronze.{source_table} WHERE _batch_id=:batch_id"
            ), {"batch_id": args.batch_id}).scalar())
            silver_query = (
                "SELECT COUNT(*) FROM silver.client "
                "WHERE _batch_id=:batch_id AND source_systeme=:system"
                if silver_table == "client"
                else f"SELECT COUNT(*) FROM silver.{silver_table} WHERE _batch_id=:batch_id"
            )
            silver_count = int(connection.execute(text(silver_query), {
                "batch_id": args.batch_id, "system": system
            } if silver_table == "client" else {"batch_id": args.batch_id}).scalar())
            rejected_count = int(connection.execute(text("""
                SELECT COUNT(DISTINCT bronze_row_id)
                FROM dq.rejets
                WHERE batch_id=:batch_id AND entite=:entity AND source_systeme=:system
            """), {
                "batch_id": args.batch_id, "entity": entity, "system": system
            }).scalar())
            difference = bronze_count - silver_count - rejected_count
            reconciliation.append({
                "table": source_table,
                "lignes_bronze": bronze_count,
                "lignes_silver": silver_count,
                "lignes_rejetees": rejected_count,
                "ecart": difference,
            })
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES
                    (:batch_id, 'SILVER', 'RQ-024', :table_cible, :tested, :failures)
            """), {
                "batch_id": args.batch_id,
                "table_cible": f"silver.{silver_table}",
                "tested": bronze_count,
                "failures": abs(difference),
            })
        for table_name in ("client", "contrat", "sinistre"):
            count = int(connection.execute(text(
                f"SELECT COUNT(*) FROM silver.{table_name} WHERE _batch_id=:batch_id"
            ), {"batch_id": args.batch_id}).scalar())
            missing = int(connection.execute(text(
                f"SELECT COUNT(*) FROM silver.{table_name} "
                "WHERE _batch_id=:batch_id AND bronze_row_id IS NULL"
            ), {"batch_id": args.batch_id}).scalar())
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES
                    (:batch_id, 'SILVER', 'RQ-023', :table_cible, :tested, :failures)
            """), {
                "batch_id": args.batch_id,
                "table_cible": f"silver.{table_name}",
                "tested": count,
                "failures": missing,
            })

    REPORTS.mkdir(exist_ok=True)
    pd.DataFrame(reconciliation).to_csv(
        REPORTS / "us23_bronze_vs_silver.csv", index=False
    )
    rejection_summary = (
        pd.DataFrame(rejects).groupby(
            ["entite", "source_systeme", "rule_id"], as_index=False
        ).size().rename(columns={"size": "lignes_rejetees"})
        if rejects else pd.DataFrame(
            columns=["entite", "source_systeme", "rule_id", "lignes_rejetees"]
        )
    )
    rejection_summary.to_csv(REPORTS / "us22_quarantaine.csv", index=False)
    transformation_summary = (
        pd.DataFrame(transformations).groupby(
            ["traitement", "table"], as_index=False
        ).size().rename(columns={"size": "lignes_modifiees"})
        if transformations else pd.DataFrame(
            columns=["traitement", "table", "lignes_modifiees"]
        )
    )
    transformation_summary.to_csv(
        REPORTS / "us21_standardisation.csv", index=False
    )
    print("US-21 transformations:", pd.DataFrame(transformations).groupby(
        ["traitement", "table"]
    ).size().to_dict())
    print("US-22 rejets par règle:", pd.DataFrame(rejects).groupby(
        ["entite", "rule_id"]
    ).size().to_dict())
    print("US-23", pd.DataFrame(reconciliation).to_string(index=False))
    print("Avertissements conservés en Silver:", warning_counters)
    if any(row["ecart"] != 0 for row in reconciliation):
        raise SystemExit("RQ-024 non conforme : l'invariant silver + rejets = bronze est rompu")
    engine.dispose()


if __name__ == "__main__":
    main()
