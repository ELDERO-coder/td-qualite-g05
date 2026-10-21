# -*- coding: utf-8 -*-
"""Évalue des seuils de rapprochement sur les paires étiquetées, sans afficher de PII."""
import argparse
import os
import re
import unicodedata

import pandas as pd
from rapidfuzz.fuzz import ratio
from sqlalchemy import create_engine, text


def normalize(value):
    value = "" if pd.isna(value) else str(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def similarity(left, right):
    left, right = normalize(left), normalize(right)
    if not left or not right:
        return None
    return ratio(left, right) / 100.0


def source_rows(engine):
    crm = pd.read_sql(text("""
        SELECT client_id AS source_id,
               COALESCE(NULLIF(raison_sociale,''), NULLIF(nom,''), '') AS name,
               COALESCE(prenom,'') AS first_name,
               COALESCE(DATE_FORMAT(date_naissance,'%Y-%m-%d'),'') AS birth_date,
               COALESCE(cp,'') AS postal_code
        FROM crm.client
    """), engine).set_index("source_id")
    cif = pd.read_sql(text("""
        SELECT column0 AS source_id, COALESCE(column1,'') AS name,
               COALESCE(column2,'') AS first_name,
               COALESCE(STR_TO_DATE(column3,'%d/%m/%Y'),'') AS birth_date,
               COALESCE(column5,'') AS postal_code
        FROM cif.clients
    """), engine).set_index("source_id")
    return {"crm": crm, "cif": cif}


def row_for(sources, system, source_id):
    frame = sources[system.lower()]
    key = str(source_id)
    if key not in frame.index:
        return None
    row = frame.loc[key]
    return row.iloc[0] if isinstance(row, pd.DataFrame) else row


def score_pair(left, right):
    weights = (("name", 0.55), ("first_name", 0.15), ("birth_date", 0.20), ("postal_code", 0.10))
    scores = [(similarity(left[field], right[field]), weight) for field, weight in weights]
    available = [(score, weight) for score, weight in scores if score is not None]
    if not available:
        return 0.0
    return sum(score * weight for score, weight in available) / sum(weight for _, weight in available)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="data/referentiels/paires_etiquetees.csv")
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"))
    args = parser.parse_args()
    pairs = pd.read_csv(args.pairs, dtype=str, keep_default_na=False)
    sources = source_rows(create_engine(args.url))
    y_true, scores, system_pairs = [], [], []
    for pair in pairs.itertuples(index=False):
        left = row_for(sources, pair.gauche_systeme, pair.gauche_id)
        right = row_for(sources, pair.droite_systeme, pair.droite_id)
        if left is None or right is None:
            raise ValueError("Une paire étiquetée référence une source inconnue.")
        y_true.append(pair.meme_personne in {"1", "true", "True"})
        scores.append(score_pair(left, right))
        system_pairs.append(f"{pair.gauche_systeme}->{pair.droite_systeme}")

    print(f"Paires évaluées : {len(pairs)}; positives : {sum(y_true)}; négatives : {len(y_true)-sum(y_true)}")
    print("Seuil précision rappel F1 faux_positifs faux_negatifs")
    for threshold in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.98, 1.00):
        predicted = [score >= threshold for score in scores]
        tp = sum(actual and pred for actual, pred in zip(y_true, predicted))
        fp = sum((not actual) and pred for actual, pred in zip(y_true, predicted))
        fn = sum(actual and (not pred) for actual, pred in zip(y_true, predicted))
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(f"{threshold:.2f} {precision:.3f} {recall:.3f} {f1:.3f} {fp} {fn}")
    print("\nSous-ensembles par systèmes, seuil=0.85")
    print("systems paires precision rappel faux_positifs faux_negatifs")
    for systems in sorted(set(system_pairs)):
        indices = [index for index, value in enumerate(system_pairs) if value == systems]
        truths = [y_true[index] for index in indices]
        predicted = [scores[index] >= 0.85 for index in indices]
        tp = sum(actual and pred for actual, pred in zip(truths, predicted))
        fp = sum((not actual) and pred for actual, pred in zip(truths, predicted))
        fn = sum(actual and (not pred) for actual, pred in zip(truths, predicted))
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        print(f"{systems} {len(indices)} {precision:.3f} {recall:.3f} {fp} {fn}")


if __name__ == "__main__":
    main()
