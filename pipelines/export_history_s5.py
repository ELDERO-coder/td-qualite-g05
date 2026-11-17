# -*- coding: utf-8 -*-
"""Exporte l'historique qualité agrégé pour le lot et trace les courbes disponibles."""
import argparse
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text

DEFAULT_BATCH = "L-2026-10-14"
DEFAULT_URL = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306/crm")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    engine = create_engine(args.url)
    history = pd.read_sql(text("""
        SELECT batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs,
               taux_conformite, mesure_le
        FROM dq.v_derniere_mesure
        WHERE batch_id=:batch
        ORDER BY rule_id, couche, table_cible
    """), engine, params={"batch": args.batch_id})
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "s5_history.csv"
    image_path = output_dir / "s5_history.png"
    history.to_csv(csv_path, index=False, encoding="utf-8")

    if history.empty:
        print(f"Aucune mesure pour {args.batch_id}; CSV vide exporté.")
        raise SystemExit(1)
    chart_data = history.groupby(["rule_id", "couche"], as_index=False).taux_conformite.mean()
    pivot = chart_data.pivot(index="rule_id", columns="couche", values="taux_conformite")
    ax = pivot.plot(kind="bar", figsize=(13, 6), ylim=(0, 100), width=0.8)
    ax.set_ylabel("Conformité (%)")
    ax.set_xlabel("Règle qualité")
    ax.set_title(f"Mesures qualité par couche · {args.batch_id}")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="Couche")
    plt.tight_layout()
    plt.savefig(image_path, dpi=160)
    plt.close()
    print(f"Mesures : {len(history)}; couches : {', '.join(sorted(history.couche.unique()))}")
    print(f"CSV agrégé : {csv_path}; courbe : {image_path}")
    if not {"BRONZE", "SILVER", "GOLD"}.issubset(set(history.couche)):
        print("Attention : historique incomplet; la courbe ne compare que les couches mesurées.")


if __name__ == "__main__":
    main()
