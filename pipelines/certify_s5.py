# -*- coding: utf-8 -*-
"""Émet un certificat uniquement après couverture complète des règles bloquantes."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, text

DEFAULT_BATCH = "L-2026-10-14"
DEFAULT_URL = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306/crm")
LAYER_BY_GATE = {"B": "BRONZE", "S": "SILVER", "G": "GOLD", "C": "CRM"}


def canonical(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def gold_fingerprint(connection, batch_id):
    digest = hashlib.sha256()
    for query, params in (
        ("SELECT * FROM gold.client_unique WHERE _batch_id=:batch ORDER BY cli_id", {"batch": batch_id}),
        ("SELECT x.* FROM gold.xref_identifiants x JOIN gold.client_unique g ON g.cli_id=x.cli_id "
         "WHERE g._batch_id=:batch ORDER BY x.source_systeme,x.source_id", {"batch": batch_id}),
    ):
        result = connection.execute(text(query), params)
        for row in result:
            payload = json.dumps([canonical(item) for item in row], ensure_ascii=False,
                                 separators=(",", ":"), default=str)
            digest.update(payload.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--signataire", default="")
    parser.add_argument("--commentaire", default="")
    args = parser.parse_args()
    engine = create_engine(args.url)

    with engine.begin() as connection:
        rules = connection.execute(text("""
            SELECT rule_id, porte, severite FROM dq.regle
            WHERE severite='BLOQUANTE' ORDER BY rule_id
        """)).mappings().all()
        latest = connection.execute(text("""
            SELECT h.rule_id, h.couche, h.nb_testees, h.nb_echecs
            FROM dq.dq_history h
            JOIN (
                SELECT rule_id, couche, table_cible, MAX(id) AS max_id
                FROM dq.dq_history WHERE batch_id=:batch
                GROUP BY rule_id, couche, table_cible
            ) m ON m.max_id=h.id
            WHERE h.batch_id=:batch
        """), {"batch": args.batch_id}).mappings().all()
        latest_by_rule_layer = {}
        for row in latest:
            key = (row["rule_id"], row["couche"])
            summary = latest_by_rule_layer.setdefault(key, {"tested": 0, "failures": 0})
            summary["tested"] += int(row["nb_testees"])
            summary["failures"] += int(row["nb_echecs"])

        coverage = []
        passed_rules = 0
        for rule in rules:
            expected_layer = LAYER_BY_GATE[rule["porte"]]
            metric = latest_by_rule_layer.get((rule["rule_id"], expected_layer))
            measured = bool(metric and metric["tested"] > 0)
            passed = bool(measured and metric["failures"] == 0)
            if passed:
                passed_rules += 1
            coverage.append({
                "rule_id": rule["rule_id"], "expected_layer": expected_layer,
                "measured": measured,
                "tested": metric["tested"] if metric else 0,
                "failures": metric["failures"] if metric else None,
                "passed": passed,
            })

        fingerprint = gold_fingerprint(connection, args.batch_id)
        blocking_count = len(rules)
        decision = "GO" if blocking_count and passed_rules == blocking_count and args.signataire.strip() else "NO_GO"
        certificate_id = "CERT-" + args.batch_id.replace("-", "") + "-" + datetime.now(timezone.utc).strftime("%H%M%S")
        connection.execute(text("""
            INSERT INTO dq.certificat_qualite
                (certificat_id, batch_id, nb_bloquantes_testees, nb_bloquantes_ok,
                 empreinte_gold, decision, signataire, commentaire)
            VALUES (:cert, :batch, :tested, :passed, :fingerprint, :decision, :signer, :comment)
        """), {
            "cert": certificate_id, "batch": args.batch_id,
            "tested": sum(item["measured"] for item in coverage),
            "passed": passed_rules, "fingerprint": fingerprint,
            "decision": decision, "signer": args.signataire.strip() or None,
            "comment": args.commentaire.strip() or "Généré par pipelines/certify_s5.py",
        })

    print(json.dumps({
        "certificate_id": certificate_id, "batch_id": args.batch_id,
        "decision": decision, "blocking_rules": blocking_count,
        "blocking_rules_measured_in_required_layer": sum(item["measured"] for item in coverage),
        "blocking_rules_passed": passed_rules, "gold_sha256": fingerprint,
        "signatory_present": bool(args.signataire.strip()), "coverage": coverage,
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if decision == "GO" else 2)


if __name__ == "__main__":
    main()
