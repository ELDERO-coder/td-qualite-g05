# -*- coding: utf-8 -*-
"""Copie les sept tables source vers bronze avec suivi de lot et hash de ligne.

Usage depuis le conteneur Jupyter :
    python pipelines/load_bronze.py --batch-id L-2026-10-14

Relancer avec le même batch_id remplace les lignes de ce lot au lieu de les dupliquer.
"""
import argparse
import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text


TABLES = [
    ("crm", "client", "crm_client", "crm", "client_id", (
        "client_id", "type_personne", "nom", "prenom", "raison_sociale", "date_naissance",
        "adresse", "cp", "ville", "pays", "telephone", "email", "date_creation",
    )),
    ("crm", "contrat", "crm_contrat", "crm", "contrat_id", (
        "contrat_id", "souscripteur_id", "assure_id", "code_type", "date_debut", "date_fin",
        "duree_garantie_mois", "prime_annuelle", "date_derniere_cotisation",
    )),
    ("crm", "sinistre", "crm_sinistre", "crm", "sinistre_id", (
        "sinistre_id", "contrat_id", "date_survenance", "date_declaration", "type_sinistre",
        "montant_estime", "adresse_sinistre", "cp_sinistre", "ville_sinistre", "canal_saisie",
    )),
    ("crm", "type_contrat", "crm_type_contrat", "crm", "code_type", (
        "code_type", "libelle", "branche",
    )),
    ("cif", "clients", "cif_clients", "cif", "column0", (
        "column0", "column1", "column2", "column3", "column4", "column5", "column6",
        "column7", "column8", "column9",
    )),
    ("cif", "compte", "cif_compte", "cif", "column0", (
        "column0", "column1", "column2", "column3",
    )),
    ("cif", "pays", "cif_pays", "cif", "code_pays", ("code_pays", "nom_pays")),
]


def texte_source(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def hash_ligne(values):
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True, help="Identifiant du lot, par exemple L-2026-10-14")
    parser.add_argument(
        "--url",
        default=os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"),
    )
    parser.add_argument("--chunk-size", type=int, default=2000)
    args = parser.parse_args()
    if args.chunk_size < 1:
        parser.error("--chunk-size doit etre superieur a zero")

    engine = create_engine(args.url)
    with engine.connect().execution_options(stream_results=True) as source, engine.begin() as target:
        target.execute(text(
            "INSERT INTO dq.lot_ingestion (batch_id, started_at, finished_at, statut) "
            "VALUES (:batch_id, CURRENT_TIMESTAMP, NULL, 'EN_COURS') "
            "ON DUPLICATE KEY UPDATE started_at = CURRENT_TIMESTAMP, "
            "finished_at = NULL, statut = 'EN_COURS'"
        ), {"batch_id": args.batch_id})

        for source_schema, source_table, bronze_table, source_system, primary_key, columns in TABLES:
            column_sql = ", ".join(f"`{column}`" for column in columns)
            select_sql = text(
                f"SELECT {column_sql} FROM `{source_schema}`.`{source_table}` "
                f"ORDER BY `{primary_key}`"
            )
            insert_columns = columns + ("_batch_id", "_source_system", "_row_hash")
            insert_column_sql = ", ".join(f"`{column}`" for column in insert_columns)
            value_sql = ", ".join(f":v{index}" for index in range(len(columns)))
            insert_sql = text(
                f"INSERT INTO `bronze`.`{bronze_table}` ({insert_column_sql}) "
                f"VALUES ({value_sql}, :batch_id, :source_system, :row_hash)"
            )

            target.execute(
                text(f"DELETE FROM `bronze`.`{bronze_table}` WHERE _batch_id = :batch_id"),
                {"batch_id": args.batch_id},
            )
            result = source.execute(select_sql)
            loaded = 0
            while rows := result.fetchmany(args.chunk_size):
                batch = []
                for row in rows:
                    values = [texte_source(value) for value in row]
                    record = {f"v{index}": value for index, value in enumerate(values)}
                    record.update({
                        "batch_id": args.batch_id,
                        "source_system": source_system,
                        "row_hash": hash_ligne(values),
                    })
                    batch.append(record)
                target.execute(insert_sql, batch)
                loaded += len(batch)
            result.close()
            print(f"{source_schema}.{source_table} -> bronze.{bronze_table}: {loaded} lignes")

        target.execute(text(
            "UPDATE dq.lot_ingestion SET finished_at = CURRENT_TIMESTAMP, statut = 'TERMINE' "
            "WHERE batch_id = :batch_id"
        ), {"batch_id": args.batch_id})

    engine.dispose()
    print(f"Lot {args.batch_id} termine")


if __name__ == "__main__":
    main()