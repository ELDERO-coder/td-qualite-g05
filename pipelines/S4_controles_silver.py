from aq import *
import pandas as pd


def compter(requete, **params):
    return int(lire(requete, **params).iloc[0, 0])


def controle_rq023():
    print("\n=== RQ-023 : TRACABILITE SILVER -> BRONZE ===")

    controles = {
        "client": """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(
                       NOT EXISTS (
                           SELECT 1 FROM bronze.crm_client b
                           WHERE s.source_systeme = 'crm'
                             AND b.bronze_row_id = s.bronze_row_id
                             AND b._batch_id = s._batch_id
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM bronze.cif_clients b
                           WHERE s.source_systeme = 'cif'
                             AND b.bronze_row_id = s.bronze_row_id
                             AND b._batch_id = s._batch_id
                       )
                   ), 0) AS echecs
            FROM silver.client s
            WHERE s._batch_id = :b
        """,
        "contrat": """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(NOT EXISTS (
                       SELECT 1 FROM bronze.crm_contrat b
                       WHERE b.bronze_row_id = s.bronze_row_id
                         AND b._batch_id = s._batch_id
                   )), 0) AS echecs
            FROM silver.contrat s
            WHERE s._batch_id = :b
        """,
        "sinistre": """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(NOT EXISTS (
                       SELECT 1 FROM bronze.crm_sinistre b
                       WHERE b.bronze_row_id = s.bronze_row_id
                         AND b._batch_id = s._batch_id
                   )), 0) AS echecs
            FROM silver.sinistre s
            WHERE s._batch_id = :b
        """
    }

    for table, requete in controles.items():
        r = lire(requete, b=BATCH).iloc[0]
        print(f"{table} : total={r['total']}, sans_origine={r['echecs']}")


def controle_rq024():
    print("\n=== RQ-024 : CONSERVATION DES LIGNES ===")

    sources = [
        ("client_crm", "bronze.crm_client", "silver.client", "client", "crm"),
        ("client_cif", "bronze.cif_clients", "silver.client", "client", "cif"),
        ("contrat", "bronze.crm_contrat", "silver.contrat", "contrat", "crm"),
        ("sinistre", "bronze.crm_sinistre", "silver.sinistre", "sinistre", "crm")
    ]

    lignes = []

    for nom, bronze_table, silver_table, entite, source in sources:
        bronze = compter(
            f"SELECT COUNT(*) FROM {bronze_table} WHERE _batch_id = :b",
            b=BATCH
        )

        filtre = " AND source_systeme = :s" if entite == "client" else ""
        params = {"b": BATCH, "s": source} if filtre else {"b": BATCH}

        silver = compter(
            f"SELECT COUNT(*) FROM {silver_table} WHERE _batch_id = :b{filtre}",
            **params
        )

        rejets = compter("""
            SELECT COUNT(DISTINCT bronze_row_id)
            FROM dq.rejets
            WHERE batch_id = :b
              AND porte = 'S'
              AND entite = :e
              AND source_systeme = :s
        """, b=BATCH, e=entite, s=source)

        lignes.append((nom, bronze, silver, rejets))

    df = pd.DataFrame(
        lignes, columns=["table", "bronze", "silver", "rejets"]
    )
    df["ecart"] = df["bronze"] - df["silver"] - df["rejets"]

    print(df.to_string(index=False))
    print("RQ-024 :", "OK" if (df["ecart"] == 0).all() else "ECHEC")


def controle_ban():
    print("\n=== RQ-014 : RAPPROCHEMENT BAN ===")

    print(lire("""
        SELECT
            COUNT(*) AS total_sinistres,
            SUM(
                NOT EXISTS (
                    SELECT 1
                    FROM silver.ref_ban b
                    WHERE UPPER(TRIM(CONCAT(b.numero, ' ', b.voie)))
                          = UPPER(TRIM(s.adresse_normalisee))
                      AND b.code_postal = s.cp
                      AND UPPER(TRIM(b.commune))
                          = UPPER(TRIM(s.ville_normalisee))
                )
            ) AS adresses_non_reconnues
        FROM silver.sinistre s
        WHERE s._batch_id = :b
    """, b=BATCH).to_string(index=False))


if __name__ == "__main__":
    controle_rq023()
    controle_rq024()
    controle_ban()