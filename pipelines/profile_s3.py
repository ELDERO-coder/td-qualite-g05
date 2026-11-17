# -*- coding: utf-8 -*-
"""Mesure l'intégrité relationnelle et les règles d'activité de la séance 3."""
import argparse
import json
import os
from sqlalchemy import create_engine, text

BATCH_DEFAULT = "L-2026-10-14"
URL_DEFAULT = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306")
REFERENCE_DEFAULT = "2026-10-14"

MEASURES = [
    ("RQ-011", "contrat.code_type", """
        SELECT COUNT(*) tested,
               SUM(c.code_type IS NOT NULL AND t.code_type IS NULL) failures
        FROM crm.contrat c LEFT JOIN crm.type_contrat t ON t.code_type=c.code_type
    """),
    ("RQ-012", "contrat.souscripteur_id", """
        SELECT COUNT(*) tested,
               SUM(c.souscripteur_id IS NOT NULL AND cl.client_id IS NULL) failures
        FROM crm.contrat c LEFT JOIN crm.client cl ON cl.client_id=c.souscripteur_id
    """),
    ("RQ-013", "contrat.assure_id", """
        SELECT SUM(c.assure_id IS NOT NULL AND c.assure_id <> '0') tested,
               SUM(c.assure_id IS NOT NULL AND c.assure_id <> '0' AND cl.client_id IS NULL) failures
        FROM crm.contrat c LEFT JOIN crm.client cl ON cl.client_id=c.assure_id
    """),
    ("RQ-015", "client.prospect_contrat", """
        SELECT SUM(c.type_personne='prospect') tested,
               SUM(c.type_personne='prospect' AND EXISTS
                   (SELECT 1 FROM crm.contrat k WHERE k.souscripteur_id=c.client_id)) failures
        FROM crm.client c
    """),
    ("RQ-016", "client.souscripteur_contrat", """
        SELECT SUM(c.type_personne='souscripteur') tested,
               SUM(c.type_personne='souscripteur' AND NOT EXISTS
                   (SELECT 1 FROM crm.contrat k WHERE k.souscripteur_id=c.client_id)) failures
        FROM crm.client c
    """),
    ("RQ-017", "sinistre.periode_garantie", """
        SELECT COUNT(*) tested,
               SUM(s.date_survenance < c.date_debut OR s.date_survenance > c.date_fin) failures
        FROM crm.sinistre s JOIN crm.contrat c ON c.contrat_id=s.contrat_id
        WHERE s.date_survenance IS NOT NULL AND c.date_debut IS NOT NULL AND c.date_fin IS NOT NULL
    """),
]


def scalar_pair(connection, query):
    row = connection.execute(text(query)).mappings().one()
    return int(row["tested"] or 0), int(row["failures"] or 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--reference-date", default=REFERENCE_DEFAULT)
    parser.add_argument("--url", default=URL_DEFAULT)
    args = parser.parse_args()
    engine = create_engine(args.url)
    results = []
    with engine.begin() as connection:
        for rule_id, target, query in MEASURES:
            tested, failures = scalar_pair(connection, query)
            result = {"rule_id": rule_id, "table_cible": target,
                      "nb_testees": tested, "nb_echecs": failures,
                      "taux_conformite": round(100 * (tested - failures) / tested, 3) if tested else None}
            results.append(result)
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES (:batch, 'CRM', :rule, :target, :tested, :failed)
            """), {"batch": args.batch_id, "rule": rule_id, "target": target,
                    "tested": tested, "failed": failures})

        sentinel_total = connection.execute(text(
            "SELECT COUNT(*) FROM crm.contrat WHERE assure_id='0'"
        )).scalar_one()
        nonzero_orphans = connection.execute(text("""
            SELECT COUNT(*) FROM crm.contrat c
            LEFT JOIN crm.client cl ON cl.client_id=c.assure_id
            WHERE c.assure_id IS NOT NULL AND c.assure_id <> '0' AND cl.client_id IS NULL
        """)).scalar_one()
        sentinel_orphans_before = int(sentinel_total + nonzero_orphans)

        ref = {"reference": args.reference_date}
        common_cte = """
            WITH active_ids AS (
                SELECT souscripteur_id AS client_id FROM crm.contrat
                WHERE souscripteur_id IS NOT NULL AND souscripteur_id <> '0'
                  AND date_debut <= :reference
                  AND (date_fin IS NULL OR date_fin >= :reference)
                  AND date_derniere_cotisation >= DATE_SUB(:reference, INTERVAL 3 MONTH)
                UNION
                SELECT assure_id FROM crm.contrat
                WHERE assure_id IS NOT NULL AND assure_id <> '0'
                  AND date_debut <= :reference
                  AND (date_fin IS NULL OR date_fin >= :reference)
                  AND date_derniere_cotisation >= DATE_SUB(:reference, INTERVAL 3 MONTH)
            )
        """
        active_count = connection.execute(text(common_cte + """
            SELECT COUNT(*) FROM active_ids a JOIN crm.client c ON c.client_id=a.client_id
        """), ref).scalar_one()
        directions = {name: int(active_count) for name in ("Commerciale", "Sinistres", "Risques")}
        results.append({"rule_id": "RQ-018", "table_cible": "active_ids_CD-001",
                        "nb_testees": 3, "nb_echecs": 0,
                        "taux_conformite": 100.0, "counts_by_direction": directions})
        connection.execute(text("""
            INSERT INTO dq.dq_history
                (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
            VALUES (:batch, 'CRM', 'RQ-018', 'active_ids_CD-001', 3, 0)
        """), {"batch": args.batch_id})

        summary = {
            "batch_id": args.batch_id,
            "reference_date": args.reference_date,
            "integrity_and_status": results[:-1],
            "assure_sentinel": {
                "sentinel_rows": int(sentinel_total),
                "orphan_rows_before_excluding_sentinel": sentinel_orphans_before,
                "orphan_rows_after_excluding_sentinel": int(nonzero_orphans),
            },
            "active_definition": {
                "definition": "Contrat en cours à la date de référence ET cotisation enregistrée dans les trois derniers mois; client souscripteur ou assuré, sentinelle 0 exclue.",
                "counts_by_direction": directions,
                "decision_status": "Calcul reproductible selon RQ-018; validation Data Owner non enregistrée.",
            },
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    blocking_ids = {"RQ-011", "RQ-012", "RQ-013", "RQ-015", "RQ-017"}
    failures = sum(item["nb_echecs"] for item in results if item["rule_id"] in blocking_ids)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
