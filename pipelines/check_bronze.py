# -*- coding: utf-8 -*-
"""Réconcilie un lot source/bronze et historise RQ-021 et RQ-022."""
import argparse
import os

from sqlalchemy import create_engine, text

from load_bronze import TABLES, hash_ligne, texte_source


def mesurer(source, bronze, table, batch_id, chunk_size, inject_mismatch=False):
    source_schema, source_table, bronze_table, source_system, primary_key, columns = table
    column_sql = ", ".join(f"`{column}`" for column in columns)
    source_query = text(
        f"SELECT {column_sql} FROM `{source_schema}`.`{source_table}` "
        f"ORDER BY `{primary_key}`"
    )
    bronze_query = text(
        f"SELECT {column_sql}, _batch_id, _source_system, _ingested_at, _row_hash "
        f"FROM `bronze`.`{bronze_table}` WHERE _batch_id = :batch_id "
        f"ORDER BY `{primary_key}`"
    )

    source_result = source.execute(source_query)
    source_count = 0
    source_checksum = 0
    while rows := source_result.fetchmany(chunk_size):
        for row in rows:
            values = [texte_source(value) for value in row]
            source_checksum += int(hash_ligne(values), 16)
            source_count += 1
    source_result.close()

    bronze_result = bronze.execute(bronze_query, {"batch_id": batch_id})
    bronze_count = 0
    bronze_checksum = 0
    metadata_errors = 0
    mismatch_injected = False
    while rows := bronze_result.fetchmany(chunk_size):
        for row in rows:
            values = [texte_source(value) for value in row[:len(columns)]]
            batch_value, system_value, ingested_at, stored_hash = row[len(columns):]
            if inject_mismatch and not mismatch_injected:
                values[0] = f"{values[0]}__TEST_ECART"
                mismatch_injected = True
            calculated_hash = hash_ligne(values)
            bronze_checksum += int(calculated_hash, 16)
            metadata_errors += int(
                batch_value != batch_id
                or system_value != source_system
                or ingested_at is None
                or stored_hash is None
                or stored_hash.lower() != calculated_hash
            )
            bronze_count += 1
    bronze_result.close()

    return {
        "table": f"bronze.{bronze_table}",
        "source_count": source_count,
        "bronze_count": bronze_count,
        "count_diff": bronze_count - source_count,
        "source_checksum": source_checksum,
        "bronze_checksum": bronze_checksum,
        "checksum_diff": bronze_checksum - source_checksum,
        "metadata_errors": metadata_errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--url",
        default=os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"),
    )
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument(
        "--inject-mismatch",
        action="store_true",
        help="simule un écart sur une copie en mémoire, sans modifier Bronze ni dq.dq_history",
    )
    args = parser.parse_args()
    if args.chunk_size < 1:
        parser.error("--chunk-size doit etre superieur a zero")

    engine = create_engine(args.url)
    measurements = []
    with (
        engine.connect().execution_options(stream_results=True) as source,
        engine.connect().execution_options(stream_results=True) as bronze,
    ):
        lot = source.execute(
            text("SELECT statut FROM dq.lot_ingestion WHERE batch_id = :batch_id"),
            {"batch_id": args.batch_id},
        ).scalar()
        if lot != "TERMINE":
            raise RuntimeError(f"Le lot {args.batch_id} n'existe pas ou n'est pas TERMINE")

        for table in TABLES:
            measurements.append(mesurer(
                source, bronze, table, args.batch_id, args.chunk_size,
                inject_mismatch=args.inject_mismatch and not measurements,
            ))

    if args.inject_mismatch:
        detected = any(
            result["checksum_diff"] != 0 and result["metadata_errors"] > 0
            for result in measurements
        )
        if not detected:
            raise SystemExit("ECHEC : l'écart simulé n'a pas été détecté")
        print("TEST ECART SUR COPIE : RQ-021 et RQ-022 détectent l'altération ; aucune donnée ni mesure modifiée")
        engine.dispose()
        return

    failed = False
    with engine.begin() as connection:
        for result in measurements:
            count_failed = result["count_diff"] != 0
            checksum_failed = result["checksum_diff"] != 0
            rq021_failures = int(count_failed) + int(checksum_failed)
            rq022_failures = result["metadata_errors"]
            failed = failed or rq021_failures > 0 or rq022_failures > 0

            for rule_id, tested, failures in (
                ("RQ-021", 2, rq021_failures),
                ("RQ-022", result["bronze_count"], rq022_failures),
            ):
                connection.execute(text(
                    "INSERT INTO dq.dq_history "
                    "(batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs) "
                    "VALUES (:batch_id, 'BRONZE', :rule_id, :table_cible, :nb_testees, :nb_echecs)"
                ), {
                    "batch_id": args.batch_id,
                    "rule_id": rule_id,
                    "table_cible": result["table"],
                    "nb_testees": tested,
                    "nb_echecs": failures,
                })

    for result in measurements:
        print(
            f"{result['table']}: source={result['source_count']} "
            f"bronze={result['bronze_count']} ecart_comptage={result['count_diff']} "
            f"somme_hash_source={result['source_checksum']} "
            f"somme_hash_bronze={result['bronze_checksum']} "
            f"ecart_hash={result['checksum_diff']} "
            f"erreurs_metadonnees={result['metadata_errors']}"
        )
    print(f"Porte B {'ECHEC' if failed else 'CONFORME'} pour {args.batch_id}")
    engine.dispose()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()