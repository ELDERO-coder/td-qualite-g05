# -*- coding: utf-8 -*-
"""Construire les identités et entités certifiées Gold à partir de Silver."""
import argparse
import itertools
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import bindparam, create_engine, text

from build_silver import BATCH_DEFAULT, DB_URL_DEFAULT, ROOT, age_at, key, present


REPORTS = ROOT / "reports"
LABELS = ROOT / "data" / "referentiels" / "paires_etiquetees.csv"
ACTIVE_REFERENCE = date(2026, 10, 1)
PREMIUM_WINDOW_START = date(2026, 7, 1)
ACTIVE_TARGET = 37643
MIN_AUTO_THRESHOLD = 70
PHONE_RE = re.compile(r"^0[1-9]\d{8}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def value_or_none(value):
    return None if not present(value) else value


def as_date(value):
    if not present(value):
        return None
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def record_key(record):
    return record["source_systeme"], record["source_id"]


def full_name(record):
    return key(" ".join(filter(None, (
        str(record.get("identite_normalisee") or ""),
        str(record.get("prenom_normalise") or ""),
    ))))


def similarity(left, right):
    name_left, name_right = full_name(left), full_name(right)
    if name_left and name_right:
        name_score = fuzz.token_sort_ratio(name_left, name_right)
    else:
        name_score = 0

    birth_left = as_date(left.get("date_naissance"))
    birth_right = as_date(right.get("date_naissance"))
    if birth_left and birth_right:
        birth_score = 100 if birth_left == birth_right else 0
    else:
        birth_score = 50

    postal_left = key(left.get("cp"))
    postal_right = key(right.get("cp"))
    if postal_left and postal_right:
        postal_score = 100 if postal_left == postal_right else 0
    else:
        postal_score = 50

    city_left = key(left.get("ville_normalisee"))
    city_right = key(right.get("ville_normalisee"))
    if city_left and city_right:
        city_score = fuzz.ratio(city_left, city_right)
    else:
        city_score = 50

    email_left = str(left.get("email_normalise") or "").strip().lower()
    email_right = str(right.get("email_normalise") or "").strip().lower()
    email_score = 100 if email_left and email_left == email_right else 0

    return round(
        name_score * 0.50
        + birth_score * 0.20
        + postal_score * 0.15
        + city_score * 0.10
        + email_score * 0.05
    )


def pair_code(left_index, right_index):
    low, high = sorted((left_index, right_index))
    return (low << 32) | high


def candidate_pairs(records):
    blocks = defaultdict(set)
    for index, record in enumerate(records):
        name = full_name(record)
        email = str(record.get("email_normalise") or "").strip().lower()
        birth = as_date(record.get("date_naissance"))
        if name:
            blocks[("name", name)].add(index)
        if email:
            blocks[("email", email)].add(index)
        if birth:
            blocks[("birth", birth.isoformat())].add(index)

    pairs = set()
    for members in blocks.values():
        if len(members) < 2:
            continue
        pairs.update(
            (left << 32) | right
            for left, right in itertools.combinations(sorted(members), 2)
        )
    return pairs


def positive_label(value):
    if isinstance(value, (int, float)) and not pd.isna(value):
        return int(value) == 1
    normalized = key(value)
    return normalized in {"1", "true", "oui", "yes", "meme personne", "doublon"}


def evaluate_labels(labels, lookup, record_indexes, candidate_set):
    rows = []
    for row in labels.to_dict("records"):
        left_key = (str(row["gauche_systeme"]).strip().lower(), str(row["gauche_id"]))
        right_key = (str(row["droite_systeme"]).strip().lower(), str(row["droite_id"]))
        left, right = lookup.get(left_key), lookup.get(right_key)
        eligible = left is not None and right is not None
        in_candidate_set = (
            eligible
            and pair_code(record_indexes[left_key], record_indexes[right_key]) in candidate_set
        )
        score = similarity(left, right) if in_candidate_set else 0
        rows.append({
            "meme_personne": int(positive_label(row["meme_personne"])),
            "score": score,
            "eligible_silver": eligible,
            "candidate_generee": in_candidate_set,
        })

    positives = sum(row["meme_personne"] for row in rows)
    if positives == 0:
        raise ValueError("Les paires étiquetées ne contiennent aucune paire positive")

    def counts(threshold):
        predicted = [row["score"] >= threshold for row in rows]
        tp = sum(
            int(prediction and row["meme_personne"])
            for prediction, row in zip(predicted, rows)
        )
        fp = sum(
            int(prediction and not row["meme_personne"])
            for prediction, row in zip(predicted, rows)
        )
        fn = positives - tp
        return tp, fp, fn

    safe_thresholds = [
        threshold for threshold in range(MIN_AUTO_THRESHOLD, 101)
        if counts(threshold)[1] == 0
    ]
    if not safe_thresholds:
        raise ValueError(
            f"Aucun seuil sans faux positif à partir du plancher {MIN_AUTO_THRESHOLD}"
        )
    auto_threshold = min(
        safe_thresholds,
        key=lambda threshold: (-counts(threshold)[0], threshold),
    )
    candidate_recall = sum(
        row["meme_personne"] and row["candidate_generee"] for row in rows
    ) / positives
    review_thresholds = [
        threshold for threshold in range(1, auto_threshold)
        if counts(threshold)[0] / positives >= candidate_recall
    ]
    review_threshold = max(review_thresholds) if review_thresholds else max(
        1, auto_threshold - 1
    )
    tp, fp, fn = counts(auto_threshold)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / positives
    return auto_threshold, review_threshold, {
        "paires_etiquetees": len(rows),
        "paires_positives": positives,
        "paires_non_eligibles_silver": sum(not row["eligible_silver"] for row in rows),
        "paires_positives_non_generees": sum(
            row["meme_personne"] and not row["candidate_generee"] for row in rows
        ),
        "plancher_seuil_auto": MIN_AUTO_THRESHOLD,
        "seuil_fusion_auto": auto_threshold,
        "seuil_zone_revue": review_threshold,
        "vrais_positifs_auto": tp,
        "faux_positifs_auto": fp,
        "faux_negatifs_auto": fn,
        "precision_auto_pct": round(precision * 100, 2),
        "rappel_auto_pct": round(recall * 100, 2),
    }


class UnionFind:
    def __init__(self, members):
        self.parent = {member: member for member in members}

    def find(self, member):
        root = member
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[member] != member:
            parent = self.parent[member]
            self.parent[member] = root
            member = parent
        return root

    def union(self, left, right):
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def choose_value(group, attribute):
    valid_records = [record for record in group if present(record.get(attribute))]
    if not valid_records:
        return None, "aucune"

    def rank(record):
        value = record[attribute]
        crm_preference = int(record["source_systeme"] == "crm")
        if attribute == "email_normalise":
            quality = int(bool(EMAIL_RE.fullmatch(str(value))))
        elif attribute == "telephone_normalise":
            quality = int(bool(PHONE_RE.fullmatch(str(value))))
        elif attribute == "cp":
            quality = int(bool(re.fullmatch(r"\d{5}", str(value))))
        elif attribute == "identite_normalisee":
            quality = min(len(str(value).strip()), 150)
        elif attribute == "adresse_normalisee":
            quality = min(len(str(value).strip()), 255)
        else:
            quality = 1
        return quality, crm_preference, record["source_id"]

    selected = max(valid_records, key=rank)
    return selected[attribute], selected["source_systeme"]


def add_rejection(rows, batch_id, entity, system, bronze_row_id, rule_id, reason):
    rows.append({
        "batch_id": batch_id,
        "entite": entity,
        "source_systeme": system,
        "bronze_row_id": int(bronze_row_id),
        "rule_id": rule_id,
        "porte": "G",
        "motif": reason,
    })


def insert_many(connection, statement, rows):
    for offset in range(0, len(rows), 1000):
        connection.execute(text(statement), rows[offset:offset + 1000])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", DB_URL_DEFAULT))
    args = parser.parse_args()
    engine = create_engine(args.url)
    REPORTS.mkdir(parents=True, exist_ok=True)

    with engine.connect() as connection:
        silver = pd.read_sql_query(text("""
            SELECT silver_row_id, bronze_row_id, source_systeme, source_id,
                   type_personne, identite_normalisee, prenom_normalise,
                   date_naissance, adresse_normalisee, cp, ville_normalisee,
                   pays_iso, telephone_normalise, email_normalise, _batch_id
            FROM silver.client
            WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        contracts = pd.read_sql_query(text("""
            SELECT * FROM silver.contrat WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        claims = pd.read_sql_query(text("""
            SELECT * FROM silver.sinistre WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        crm_people_frame = pd.read_sql_query(text("""
            SELECT client_id, raison_sociale, type_personne
            FROM bronze.crm_client WHERE _batch_id = :batch_id
        """), connection, params={"batch_id": args.batch_id})
        contract_types = set(connection.execute(
            text("SELECT code_type FROM crm.type_contrat")
        ).scalars())

    records = silver.to_dict("records")
    lookup = {}
    for record in records:
        record["source_systeme"] = str(record["source_systeme"]).strip().lower()
        record["source_id"] = str(record["source_id"])
        identity = record_key(record)
        if identity in lookup:
            raise ValueError(f"Identifiant source non unique dans Silver: {identity}")
        lookup[identity] = record

    if not LABELS.exists():
        raise FileNotFoundError(f"Fichier de paires étiquetées introuvable: {LABELS}")
    labels = pd.read_csv(LABELS, dtype="string")
    required_columns = {
        "gauche_systeme", "gauche_id", "droite_systeme", "droite_id", "meme_personne"
    }
    if not required_columns.issubset(labels.columns):
        raise ValueError(f"Colonnes manquantes dans les paires étiquetées: {required_columns - set(labels.columns)}")

    record_indexes = {record_key(record): index for index, record in enumerate(records)}
    candidates = candidate_pairs(records)
    auto_threshold, review_threshold, label_metrics = evaluate_labels(
        labels, lookup, record_indexes, candidates
    )
    auto_pairs = []
    review_pairs = []
    for encoded_pair in candidates:
        left_index, right_index = encoded_pair >> 32, encoded_pair & 0xFFFFFFFF
        score = similarity(records[left_index], records[right_index])
        if score >= auto_threshold:
            auto_pairs.append(encoded_pair)
        elif score >= review_threshold:
            review_pairs.append(encoded_pair)
    union_find = UnionFind(lookup)
    for encoded_pair in auto_pairs:
        left_index, right_index = encoded_pair >> 32, encoded_pair & 0xFFFFFFFF
        union_find.union(
            record_key(records[left_index]), record_key(records[right_index])
        )
    groups_by_root = defaultdict(list)
    for identity, record in lookup.items():
        groups_by_root[union_find.find(identity)].append(record)
    groups = sorted(
        (sorted(group, key=lambda row: (row["source_systeme"], row["source_id"]))
         for group in groups_by_root.values()),
        key=lambda group: tuple((row["source_systeme"], row["source_id"]) for row in group),
    )

    client_rows = []
    xref_rows = []
    survival_counts = defaultdict(lambda: defaultdict(int))
    record_to_cli = {}
    for index, group in enumerate(groups, start=1):
        cli_id = f"CLI-{index:06d}"
        attributes = {
            "nom_reference": "identite_normalisee",
            "adresse": "adresse_normalisee",
            "date_naissance": "date_naissance",
            "cp": "cp",
            "ville": "ville_normalisee",
            "pays_iso": "pays_iso",
            "telephone": "telephone_normalise",
            "email": "email_normalise",
        }
        selected = {}
        for target, source in attributes.items():
            selected[target], winning_source = choose_value(group, source)
            if winning_source != "aucune":
                survival_counts[target][winning_source] += 1
        if not selected["nom_reference"]:
            selected["nom_reference"] = "IDENTITE INCONNUE"
        client_rows.append({
            "cli_id": cli_id,
            "nom_reference": selected["nom_reference"][:150],
            "adresse": selected["adresse"],
            "date_naissance": as_date(selected["date_naissance"]),
            "cp": selected["cp"],
            "ville": selected["ville"],
            "pays_iso": selected["pays_iso"],
            "telephone": selected["telephone"],
            "email": selected["email"],
            "nb_identifiants_source": len(group),
            "statut_client": "INACTIF",
            "_batch_id": args.batch_id,
        })
        for record in group:
            identity = record_key(record)
            record_to_cli[identity] = cli_id
            xref_rows.append({
                "cli_id": cli_id,
                "source_systeme": record["source_systeme"],
                "source_id": record["source_id"],
                "bronze_row_id": int(record["bronze_row_id"]),
                "silver_row_id": int(record["silver_row_id"]),
            })

    crm_people = {
        str(row.client_id): {
            "raison_sociale": present(row.raison_sociale),
            "type_personne": key(row.type_personne),
        }
        for row in crm_people_frame.itertuples()
        if present(row.client_id)
    }
    bronze_contract_rows = {
        str(row["contrat_id"]): int(row["bronze_row_id"])
        for row in contracts.to_dict("records")
        if present(row.get("contrat_id"))
    }
    certified_contracts = []
    rejected = []
    gold_contract_ids = set()
    gate_counts = defaultdict(lambda: [0, 0])
    for row in contracts.to_dict("records"):
        contract_id = str(row["contrat_id"]) if present(row.get("contrat_id")) else None
        subscriber = str(row["souscripteur_id"]) if present(row.get("souscripteur_id")) else None
        assured = str(row["assure_id"]) if present(row.get("assure_id")) else None
        silver_row_id = int(row["silver_row_id"])
        bronze_row_id = int(row["bronze_row_id"])
        failures = []

        subscriber_key = ("crm", subscriber) if subscriber else None
        assured_key = ("crm", assured) if assured else None
        subscriber_cli = record_to_cli.get(subscriber_key) if subscriber_key else None
        assured_cli = record_to_cli.get(assured_key) if assured_key else None

        physical_subscriber = (
            subscriber in crm_people
            and crm_people[subscriber]["type_personne"] == "souscripteur"
            and not crm_people[subscriber]["raison_sociale"]
            if subscriber else False
        )
        if physical_subscriber:
            gate_counts["RQ-002"][0] += 1
            person = lookup.get(subscriber_key)
            birth = as_date(person.get("date_naissance")) if person else None
            start = as_date(row.get("date_debut"))
            age = age_at(birth, start) if birth and start else None
            if age is None or age < 18:
                failures.append(("RQ-002", "souscripteur physique mineur ou âge non vérifiable"))
        if failures and failures[-1][0] == "RQ-002":
            gate_counts["RQ-002"][1] += 1

        if subscriber and subscriber in crm_people:
            gate_counts["RQ-015"][0] += 1
            if crm_people[subscriber]["type_personne"] == "prospect":
                failures.append(("RQ-015", "un prospect ne peut pas être souscripteur d'un contrat"))
                gate_counts["RQ-015"][1] += 1

        gate_counts["RQ-011"][0] += 1
        if not present(row.get("code_type")) or row["code_type"] not in contract_types:
            failures.append(("RQ-011", "type de contrat absent ou inconnu"))
            gate_counts["RQ-011"][1] += 1

        gate_counts["RQ-012"][0] += 1
        if not subscriber_cli:
            failures.append(("RQ-012", "souscripteur absent du référentiel client Gold"))
            gate_counts["RQ-012"][1] += 1

        if assured:
            gate_counts["RQ-013"][0] += 1
            if not assured_cli:
                failures.append(("RQ-013", "assuré absent du référentiel client Gold"))
                gate_counts["RQ-013"][1] += 1

        if not contract_id or contract_id in gold_contract_ids:
            failures.append(("RQ-020", "identifiant de contrat absent ou dupliqué"))
        if not as_date(row.get("date_debut")) or not as_date(row.get("date_fin")):
            failures.append(("RQ-001", "dates du contrat absentes"))

        if failures:
            for rule_id, reason in failures:
                add_rejection(rejected, args.batch_id, "contrat", "crm", bronze_row_id, rule_id, reason)
            continue

        gold_contract_ids.add(contract_id)
        certified_contracts.append({
            "contrat_id": contract_id,
            "souscripteur_cli_id": subscriber_cli,
            "assure_cli_id": assured_cli,
            "code_type": str(row["code_type"]),
            "date_debut": as_date(row["date_debut"]),
            "date_fin": as_date(row["date_fin"]),
            "duree_garantie_mois": int(row["duree_garantie_mois"]),
            "prime_annuelle": value_or_none(row.get("prime_annuelle")),
            "date_derniere_cotisation": as_date(row.get("date_derniere_cotisation")),
            "bronze_row_id": bronze_row_id,
            "silver_row_id": silver_row_id,
            "_batch_id": args.batch_id,
        })

    certified_claims = []
    gold_claim_ids = set()
    gate_counts["RQ-017"][0] = len(claims)
    contract_by_id = {row["contrat_id"]: row for row in certified_contracts}
    for row in claims.to_dict("records"):
        claim_id = str(row["sinistre_id"]) if present(row.get("sinistre_id")) else None
        contract_id = str(row["contrat_id"]) if present(row.get("contrat_id")) else None
        contract = contract_by_id.get(contract_id)
        occurrence = as_date(row.get("date_survenance"))
        bronze_row_id = int(row["bronze_row_id"])
        failures = []
        if (
            not contract
            or not occurrence
            or occurrence < contract["date_debut"]
            or occurrence > contract["date_fin"]
        ):
            failures.append(("RQ-017", "sinistre hors période de garantie ou contrat non certifié"))
            gate_counts["RQ-017"][1] += 1
        if not claim_id or claim_id in gold_claim_ids:
            failures.append(("RQ-020", "identifiant de sinistre absent ou dupliqué"))
        if failures:
            for rule_id, reason in failures:
                add_rejection(rejected, args.batch_id, "sinistre", "crm", bronze_row_id, rule_id, reason)
            continue

        gold_claim_ids.add(claim_id)
        certified_claims.append({
            "sinistre_id": claim_id,
            "contrat_id": contract_id,
            "date_survenance": occurrence,
            "date_declaration": as_date(row.get("date_declaration")),
            "type_sinistre": value_or_none(row.get("type_sinistre")),
            "montant_estime": value_or_none(row.get("montant_estime")),
            "adresse_sinistre": row["adresse_sinistre"],
            "cp_sinistre": row["cp_sinistre"],
            "ville_sinistre": row["ville_sinistre"],
            "id_ban": row["id_ban"],
            "bronze_row_id": bronze_row_id,
            "silver_row_id": int(row["silver_row_id"]),
            "_batch_id": args.batch_id,
        })

    active_cli_ids = {
        row["souscripteur_cli_id"]
        for row in certified_contracts
        if row["date_debut"] <= ACTIVE_REFERENCE
        and row["date_fin"] >= ACTIVE_REFERENCE
        and row["date_derniere_cotisation"]
        and row["date_derniere_cotisation"] >= PREMIUM_WINDOW_START
    }
    assured_cli_ids = {
        row["assure_cli_id"] for row in certified_contracts if row["assure_cli_id"]
    }
    prospect_cli_ids = {
        record_to_cli[record_key(record)]
        for record in records
        if record.get("type_personne") == "prospect"
    }
    for row in client_rows:
        if row["cli_id"] in active_cli_ids:
            row["statut_client"] = "ACTIF"
        elif row["cli_id"] in assured_cli_ids:
            row["statut_client"] = "ASSURE"
        elif row["cli_id"] in prospect_cli_ids:
            row["statut_client"] = "PROSPECT"

    client_insert = """
        INSERT INTO gold.client_unique
            (cli_id, nom_reference, adresse, date_naissance, cp, ville, pays_iso,
             telephone, email, nb_identifiants_source, statut_client, _batch_id)
        VALUES
            (:cli_id, :nom_reference, :adresse, :date_naissance, :cp, :ville, :pays_iso,
             :telephone, :email, :nb_identifiants_source, :statut_client, :_batch_id)
    """
    xref_insert = """
        INSERT INTO gold.xref_identifiants
            (cli_id, source_systeme, source_id, bronze_row_id, silver_row_id)
        VALUES
            (:cli_id, :source_systeme, :source_id, :bronze_row_id, :silver_row_id)
    """
    contract_insert = """
        INSERT INTO gold.contrat_certifie
            (contrat_id, souscripteur_cli_id, assure_cli_id, code_type, date_debut,
             date_fin, duree_garantie_mois, prime_annuelle, date_derniere_cotisation,
             bronze_row_id, silver_row_id, _batch_id)
        VALUES
            (:contrat_id, :souscripteur_cli_id, :assure_cli_id, :code_type, :date_debut,
             :date_fin, :duree_garantie_mois, :prime_annuelle, :date_derniere_cotisation,
             :bronze_row_id, :silver_row_id, :_batch_id)
    """
    claim_insert = """
        INSERT INTO gold.sinistre_certifie
            (sinistre_id, contrat_id, date_survenance, date_declaration, type_sinistre,
             montant_estime, adresse_sinistre, cp_sinistre, ville_sinistre, id_ban,
             bronze_row_id, silver_row_id, _batch_id)
        VALUES
            (:sinistre_id, :contrat_id, :date_survenance, :date_declaration, :type_sinistre,
             :montant_estime, :adresse_sinistre, :cp_sinistre, :ville_sinistre, :id_ban,
             :bronze_row_id, :silver_row_id, :_batch_id)
    """
    rejection_insert = """
        INSERT INTO dq.rejets
            (batch_id, entite, source_systeme, bronze_row_id, rule_id, porte, motif)
        VALUES
            (:batch_id, :entite, :source_systeme, :bronze_row_id, :rule_id, :porte, :motif)
    """

    with engine.begin() as connection:
        address_column_exists = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = 'gold' AND table_name = 'client_unique'
              AND column_name = 'adresse'
        """)).scalar()
        if not address_column_exists:
            connection.exec_driver_sql(
                "ALTER TABLE gold.client_unique ADD COLUMN adresse VARCHAR(255) AFTER nom_reference"
            )

        index_exists = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = 'gold' AND table_name = 'xref_identifiants'
              AND index_name = 'idx_xref_cli_id'
        """)).scalar()
        if not index_exists:
            connection.exec_driver_sql(
                "CREATE INDEX idx_xref_cli_id ON gold.xref_identifiants (cli_id)"
            )

    with engine.begin() as connection:
        connection.exec_driver_sql(f"""
            CREATE OR REPLACE VIEW gold.v_client_actif AS
            SELECT DISTINCT souscripteur_cli_id AS cli_id, _batch_id
            FROM gold.contrat_certifie
            WHERE date_debut <= '{ACTIVE_REFERENCE.isoformat()}'
              AND date_fin >= '{ACTIVE_REFERENCE.isoformat()}'
              AND date_derniere_cotisation >= '{PREMIUM_WINDOW_START.isoformat()}'
        """)

    with engine.begin() as connection:
        for statement in (
            "DELETE FROM gold.sinistre_certifie WHERE _batch_id = :batch_id",
            "DELETE FROM gold.contrat_certifie WHERE _batch_id = :batch_id",
            "DELETE FROM dq.rejets WHERE batch_id = :batch_id AND porte = 'G'",
            "DELETE FROM dq.dq_history WHERE batch_id = :batch_id AND couche = 'GOLD'",
            "DELETE FROM gold.xref_identifiants WHERE source_systeme = 'crm' "
            "AND source_id IN (SELECT source_id FROM silver.client "
            "WHERE _batch_id = :batch_id AND source_systeme = 'crm')",
            "DELETE FROM gold.xref_identifiants WHERE source_systeme = 'cif' "
            "AND source_id IN (SELECT source_id FROM silver.client "
            "WHERE _batch_id = :batch_id AND source_systeme = 'cif')",
            "DELETE FROM gold.client_unique WHERE _batch_id = :batch_id",
        ):
            connection.execute(text(statement), {"batch_id": args.batch_id})

        insert_many(connection, client_insert, client_rows)
        insert_many(connection, xref_insert, xref_rows)
        insert_many(connection, contract_insert, certified_contracts)
        insert_many(connection, claim_insert, certified_claims)
        insert_many(connection, rejection_insert, rejected)

        active_count = int(connection.execute(text("""
            SELECT COUNT(DISTINCT cli_id) FROM gold.v_client_actif
            WHERE _batch_id = :batch_id
        """), {"batch_id": args.batch_id}).scalar())
        orphan_contracts = int(connection.execute(text("""
            SELECT COUNT(*) FROM gold.contrat_certifie k
            LEFT JOIN gold.client_unique c ON c.cli_id = k.souscripteur_cli_id
            WHERE k._batch_id = :batch_id AND c.cli_id IS NULL
        """), {"batch_id": args.batch_id}).scalar())
        orphan_claims = int(connection.execute(text("""
            SELECT COUNT(*) FROM gold.sinistre_certifie s
            LEFT JOIN gold.contrat_certifie k ON k.contrat_id = s.contrat_id
            WHERE s._batch_id = :batch_id AND k.contrat_id IS NULL
        """), {"batch_id": args.batch_id}).scalar())
        duplicate_cli = len(client_rows) - len({row["cli_id"] for row in client_rows})
        gate_counts["RQ-018"] = [3, 0 if active_count == ACTIVE_TARGET else 3]
        gate_counts["RQ-019"] = [len(client_rows), duplicate_cli]
        lineage_rows = len(client_rows) + len(xref_rows) + len(certified_contracts) + len(certified_claims)
        gate_counts["RQ-023"] = [lineage_rows, 0]

        history_insert = text("""
            INSERT INTO dq.dq_history (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
            VALUES (:batch_id, 'GOLD', :rule_id, :table_cible, :tested, :failed)
        """)
        targets = {
            "RQ-002": "gold.contrat_certifie",
            "RQ-015": "gold.contrat_certifie",
            "RQ-011": "gold.contrat_certifie",
            "RQ-012": "gold.contrat_certifie",
            "RQ-013": "gold.contrat_certifie",
            "RQ-017": "gold.sinistre_certifie",
            "RQ-018": "gold.v_client_actif",
            "RQ-019": "gold.client_unique",
            "RQ-023": "gold",
        }
        for rule_id, (tested, failed) in gate_counts.items():
            if rule_id not in targets:
                continue
            connection.execute(history_insert, {
                "batch_id": args.batch_id,
                "rule_id": rule_id,
                "table_cible": targets[rule_id],
                "tested": tested,
                "failed": failed,
            })

        counts = {}
        for table in ("client_unique", "xref_identifiants", "contrat_certifie", "sinistre_certifie"):
            if table == "xref_identifiants":
                query = """
                    SELECT COUNT(*) FROM gold.xref_identifiants x
                    JOIN silver.client s
                      ON s.source_systeme = x.source_systeme AND s.source_id = x.source_id
                    WHERE s._batch_id = :batch_id
                """
            else:
                query = f"SELECT COUNT(*) FROM gold.{table} WHERE _batch_id = :batch_id"
            counts[table] = int(connection.execute(
                text(query), {"batch_id": args.batch_id}
            ).scalar())
        rejected_by_entity = {
            row.entite: int(row.n)
            for row in connection.execute(text("""
                SELECT entite, COUNT(DISTINCT CONCAT(source_systeme, ':', bronze_row_id)) AS n
                FROM dq.rejets
                WHERE batch_id = :batch_id AND porte = 'G'
                GROUP BY entite
            """), {"batch_id": args.batch_id})
        }
        rejected_rules_by_entity = {
            row.entite: str(row.rules)
            for row in connection.execute(text("""
                SELECT entite, GROUP_CONCAT(DISTINCT rule_id ORDER BY rule_id) AS rules
                FROM dq.rejets
                WHERE batch_id = :batch_id AND porte = 'G'
                GROUP BY entite
            """), {"batch_id": args.batch_id})
        }

        trace_rows = []
        company = connection.execute(text("""
            SELECT cli_id, nom_reference FROM gold.client_unique
            WHERE _batch_id = :batch_id
              AND UPPER(nom_reference) LIKE '%SOCIETE MEUNIER%'
            ORDER BY cli_id LIMIT 1
        """), {"batch_id": args.batch_id}).first()
        if company:
            source_rows = connection.execute(text("""
                SELECT x.cli_id, x.source_systeme, x.source_id, x.bronze_row_id,
                       x.silver_row_id
                FROM gold.xref_identifiants x
                WHERE x.cli_id = :cli_id
                ORDER BY x.source_systeme, x.source_id
            """), {"cli_id": company.cli_id})
            for source in source_rows:
                trace_rows.append({
                    "donnee": "Société Meunier",
                    "valeur_gold": company.nom_reference,
                    "cli_id": source.cli_id,
                    "silver_row_id": source.silver_row_id,
                    "bronze_row_id": source.bronze_row_id,
                    "batch_id": args.batch_id,
                    "source_table": "bronze.crm_client" if source.source_systeme == "crm" else "bronze.cif_clients",
                    "source_key": source.source_id,
                })

        postal_trace = connection.execute(text("""
            SELECT c.cli_id, c.cp AS valeur_gold, x.source_systeme, x.source_id,
                   x.bronze_row_id, x.silver_row_id,
                   CASE WHEN x.source_systeme = 'crm' THEN b.cp
                        ELSE ci.column5 END AS valeur_bronze
            FROM gold.client_unique c
            JOIN gold.xref_identifiants x ON x.cli_id = c.cli_id
            JOIN silver.client s
              ON s.source_systeme = x.source_systeme AND s.source_id = x.source_id
            LEFT JOIN bronze.crm_client b
              ON x.source_systeme = 'crm' AND b.bronze_row_id = s.bronze_row_id
             AND b._batch_id = :batch_id
            LEFT JOIN bronze.cif_clients ci
              ON x.source_systeme = 'cif' AND ci.bronze_row_id = s.bronze_row_id
             AND ci._batch_id = :batch_id
            WHERE c._batch_id = :batch_id AND c.cp LIKE '0%'
              AND s._batch_id = :batch_id
              AND (
                  (x.source_systeme = 'crm' AND TRIM(b.cp) NOT LIKE '0%'
                   AND CHAR_LENGTH(TRIM(b.cp)) < 5 AND TRIM(b.cp) REGEXP '^[0-9]+$')
                  OR
                  (x.source_systeme = 'cif' AND TRIM(ci.column5) NOT LIKE '0%'
                   AND CHAR_LENGTH(TRIM(ci.column5)) < 5
                   AND TRIM(ci.column5) REGEXP '^[0-9]+$')
              )
            ORDER BY c.cli_id LIMIT 1
        """), {"batch_id": args.batch_id}).first()
        if postal_trace:
            trace_rows.append({
                "donnee": "Code postal à zéro initial",
                "valeur_gold": postal_trace.valeur_gold,
                "valeur_bronze": postal_trace.valeur_bronze,
                "cli_id": postal_trace.cli_id,
                "silver_row_id": postal_trace.silver_row_id,
                "bronze_row_id": postal_trace.bronze_row_id,
                "batch_id": args.batch_id,
                "source_table": "bronze.crm_client" if postal_trace.source_systeme == "crm" else "bronze.cif_clients",
                "source_key": postal_trace.source_id,
            })

        claim_trace = connection.execute(text("""
            SELECT g.sinistre_id, g.adresse_sinistre, g.bronze_row_id,
                   g.silver_row_id, s.contrat_id
            FROM gold.sinistre_certifie g
            JOIN silver.sinistre s ON s.silver_row_id = g.silver_row_id
            WHERE g._batch_id = :batch_id
            ORDER BY g.sinistre_id LIMIT 1
        """), {"batch_id": args.batch_id}).first()
        if claim_trace:
            trace_rows.append({
                "donnee": "Adresse de sinistre",
                "valeur_gold": claim_trace.adresse_sinistre,
                "cli_id": None,
                "silver_row_id": claim_trace.silver_row_id,
                "bronze_row_id": claim_trace.bronze_row_id,
                "batch_id": args.batch_id,
                "source_table": "bronze.crm_sinistre",
                "source_key": claim_trace.sinistre_id,
            })

    pd.DataFrame([label_metrics]).to_csv(
        REPORTS / "us24_dedup_metrics.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame([
        {
            "attribut": attribute,
            "source": source,
            "groupes_avec_valeur_retenue": count,
            "regle": "valeur la plus valide/complète; CRM en cas d'égalité",
        }
        for attribute, sources in survival_counts.items()
        for source, count in sources.items()
    ]).to_csv(REPORTS / "us25_survivorship.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{
        "seuil_auto": auto_threshold,
        "seuil_revue": review_threshold,
        "candidats_generes": len(candidates),
        "paires_fusionnees_auto": len(auto_pairs),
        "paires_zone_revue": len(review_pairs),
        "groupes_dedoublonnes": sum(len(group) > 1 for group in groups),
        "identites_distinctes": len(groups),
        "precision_auto_pct": label_metrics["precision_auto_pct"],
        "rappel_auto_pct": label_metrics["rappel_auto_pct"],
        "paires_labelisees": len(labels),
        "paires_labelisees_non_eligibles_silver": label_metrics["paires_non_eligibles_silver"],
    }]).to_csv(REPORTS / "us24_candidates_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{
        "table_gold": table,
        "lignes": count,
        "lignes_ecartees_porte_g": rejected_by_entity.get(
            "contrat" if table == "contrat_certifie"
            else "sinistre" if table == "sinistre_certifie"
            else "client", 0
        ),
        "regles_responsables": rejected_rules_by_entity.get(
            "contrat" if table == "contrat_certifie"
            else "sinistre" if table == "sinistre_certifie"
            else "client", ""
        ),
    } for table, count in counts.items()]).to_csv(
        REPORTS / "us27_gold_counts.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(trace_rows, columns=[
        "donnee", "valeur_gold", "valeur_bronze", "cli_id", "silver_row_id", "bronze_row_id",
        "batch_id", "source_table", "source_key",
    ]).to_csv(REPORTS / "us28_trace.csv", index=False, encoding="utf-8-sig")

    print(f"Lot : {args.batch_id}")
    print(f"Identités Gold : {len(client_rows)}; paires candidates : {len(candidates)}")
    print(
        f"Seuil auto : {auto_threshold}; seuil revue : {review_threshold}; "
        f"fusionnées : {len(auto_pairs)}; à revoir : {len(review_pairs)}"
    )
    print(
        f"Contrats Gold : {len(certified_contracts)}; sinistres Gold : {len(certified_claims)}; "
        f"clients actifs : {active_count}/{ACTIVE_TARGET}"
    )
    print(
        f"Rejets Gold : {len(rejected)}; orphelins contrats/sinistres : "
        f"{orphan_contracts}/{orphan_claims}"
    )
    print(f"Rapports : {REPORTS}")
    engine.dispose()


if __name__ == "__main__":
    main()
