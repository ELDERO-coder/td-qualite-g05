# -*- coding: utf-8 -*-
"""Garde de publication : refuse sans certificat GO valide et Gold inchangé."""
import argparse
import json
import os

from sqlalchemy import create_engine, text

from certify_s5 import gold_fingerprint

DEFAULT_BATCH = "L-2026-10-14"
DEFAULT_URL = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306/crm")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--certificate-id", default="")
    args = parser.parse_args()
    engine = create_engine(args.url)
    with engine.connect() as connection:
        if args.certificate_id:
            cert = connection.execute(text("""
                SELECT certificat_id, batch_id, empreinte_gold, decision
                FROM dq.certificat_qualite
                WHERE certificat_id=:cert AND batch_id=:batch
            """), {"cert": args.certificate_id, "batch": args.batch_id}).mappings().first()
        else:
            cert = connection.execute(text("""
                SELECT certificat_id, batch_id, empreinte_gold, decision
                FROM dq.certificat_qualite WHERE batch_id=:batch
                ORDER BY emis_le DESC LIMIT 1
            """), {"batch": args.batch_id}).mappings().first()
        if cert is None:
            print(json.dumps({"publication": "REFUSÉE", "raison": "Aucun certificat pour le lot."}, ensure_ascii=False))
            raise SystemExit(2)
        if cert["decision"] != "GO":
            print(json.dumps({"publication": "REFUSÉE", "raison": "Le certificat n'est pas GO.",
                              "certificate_id": cert["certificat_id"]}, ensure_ascii=False))
            raise SystemExit(2)
        actual = gold_fingerprint(connection, args.batch_id)
        if actual != cert["empreinte_gold"]:
            print(json.dumps({"publication": "REFUSÉE", "raison": "Gold a changé depuis le certificat.",
                              "certificate_id": cert["certificat_id"]}, ensure_ascii=False))
            raise SystemExit(2)
        target_tables = connection.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='crm_cible'
        """)).scalars().all()
        required = {"client", "contrat", "sinistre"}
        missing = sorted(required - set(target_tables))
        if missing:
            print(json.dumps({"publication": "REFUSÉE", "raison": "Schéma cible incomplet.",
                              "tables_manquantes": missing}, ensure_ascii=False))
            raise SystemExit(2)

    # The loader is intentionally disabled until certified Gold tables and target contracts are implemented.
    print(json.dumps({"publication": "REFUSÉE", "raison": "Le chargeur transactionnel RQ-025 n'est pas encore implémenté.",
                      "certificate_id": cert["certificat_id"]}, ensure_ascii=False))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
