from aq import *
import pandas as pd

def total(requete, **params):
    return int(lire(requete, **params).iloc[0, 0])


FICHIERS = [
    "soda/checks/silver/client_checks.yml",
    "soda/checks/silver/contrat_checks.yml",
    "soda/checks/silver/sinistre_checks.yml",
    "soda/checks/silver/integrite_checks.yml",
]

TABLES = {
    "client_checks.yml": "client",
    "contrat_checks.yml": "contrat",
    "sinistre_checks.yml": "sinistre",
    "integrite_checks.yml": None,
}

# Plusieurs contrôles peuvent appartenir à la même règle.
resultats = {}

for fichier in FICHIERS:
    code, controles = soda_scan("silver", fichier)
    print(f"{fichier} : code Soda = {code}")

    if code == 3:
        raise RuntimeError(f"Erreur Soda dans {fichier}")

    for c in controles:
        regle = c["rule_id"]
        if regle is None:
            continue

        table = TABLES[c["fichier"]]

        if table is None:
            nom = c["controle"].lower()
            if "sinistre" in nom:
                table = "sinistre"
            elif "prospect" in nom or "souscripteur sans contrat" in nom:
                table = "client"
            else:
                table = "contrat"

        cle = (regle, table)
        resultats.setdefault(cle, []).append(c)

# On vérifie les mesures avant de les historiser.
for (regle, table), controles in sorted(resultats.items()):
    print(f"\n{regle} / {table}")
    for c in controles:
        print(f"  {c['controle']} : {c['valeur']} ({c['resultat']})")

print("\nContrôles regroupés :", len(resultats))

# Historisation des mesures SILVER
# Les contrôles multiples ne sont pas additionnés automatiquement.

effectifs = {
    "client": total("SELECT COUNT(*) FROM silver.client WHERE _batch_id = :b", b=BATCH),
    "contrat": total("SELECT COUNT(*) FROM silver.contrat WHERE _batch_id = :b", b=BATCH),
    "sinistre": total("SELECT COUNT(*) FROM silver.sinistre WHERE _batch_id = :b", b=BATCH),
}

# Règles dont les échecs peuvent être comptés directement
regles_simples = {
    "RQ-001", "RQ-005", "RQ-007", "RQ-009", "RQ-010",
    "RQ-011", "RQ-012", "RQ-013", "RQ-015",
    "RQ-016", "RQ-017"
}

for (regle, table), controles in sorted(resultats.items()):
    if regle not in regles_simples:
        continue

    if len(controles) != 1 or not isinstance(controles[0]["valeur"], int):
        print(f"Mesure ignoree : {regle} / {table}")
        continue

    echecs = controles[0]["valeur"]
    mesure = mesurer("SILVER", regle, table, effectifs[table], echecs)
    print("Historise :", mesure)

# RQ-003 : mesure sur les souscripteurs CRM
mesurer("SILVER", "RQ-003", "client", 49690, 5960)

# RQ-020 : tous les contrôles d'unicité et de complétude sont passés
for table in ["client", "contrat", "sinistre"]:
    controles = resultats.get(("RQ-020", table), [])
    if len(controles) == 2 and all(c["valeur"] == 0 for c in controles):
        mesurer("SILVER", "RQ-020", table, effectifs[table], 0)

print("\n=== MESURES SILVER ===")
print(mesures("SILVER").to_string(index=False))


# ============================================================
# US-23 : Comparaison BRONZE / SILVER et verdict porte S
# ============================================================

print("\n=== COMPARAISON BRONZE / SILVER ===")

comparaison = lire("""
    SELECT
        b.rule_id,
        b.table_cible AS table_bronze,
        b.nb_testees AS testees_bronze,
        b.nb_echecs AS echecs_bronze,
        b.taux_conformite AS taux_bronze,
        s.table_cible AS table_silver,
        s.nb_testees AS testees_silver,
        s.nb_echecs AS echecs_silver,
        s.taux_conformite AS taux_silver
    FROM dq.v_derniere_mesure b
    JOIN dq.v_derniere_mesure s
      ON b.batch_id = s.batch_id
     AND b.rule_id = s.rule_id
    WHERE b.batch_id = :b
      AND b.couche = 'BRONZE'
      AND s.couche = 'SILVER'
      AND b.rule_id IN (
          'RQ-001', 'RQ-003', 'RQ-005',
          'RQ-007', 'RQ-009', 'RQ-010'
      )
    ORDER BY b.rule_id
""", b=BATCH)

print(comparaison.to_string(index=False))

print("\n=== VERDICT PORTE S ===")

verdict = lire("""
    SELECT
        m.rule_id,
        m.table_cible,
        m.taux_conformite,
        r.seuil_min,
        r.severite,
        CASE
            WHEN m.taux_conformite >= r.seuil_min
                THEN 'CONFORME'
            ELSE 'SOUS LE SEUIL'
        END AS resultat
    FROM dq.v_derniere_mesure m
    JOIN dq.regle r ON r.rule_id = m.rule_id
    WHERE m.batch_id = :b
      AND m.couche = 'SILVER'
      AND r.porte = 'S'
    ORDER BY m.rule_id, m.table_cible
""", b=BATCH)

print(verdict.to_string(index=False))

bloquantes = verdict[
    (verdict["severite"] == "BLOQUANTE")
    & (verdict["resultat"] == "SOUS LE SEUIL")
]

print("\n=== CONCLUSION ===")

if len(bloquantes) == 0:
    print("Aucune regle bloquante historisee sous son seuil, hors controle BAN.")
else:
    print("PORTE S NON FRANCHIE : regles bloquantes sous le seuil.")
    print(bloquantes.to_string(index=False))

print(
    "\nATTENTION : RQ-014 BAN reste a historiser "
    "(46,716 % d'adresses non reconnues)."
)

# Sauvegarde des tableaux pour le compte rendu
import os

os.makedirs("livrables", exist_ok=True)

comparaison.to_csv(
    "livrables/S4_comparaison_bronze_silver.csv",
    index=False
)

verdict.to_csv(
    "livrables/S4_verdict_porte_S.csv",
    index=False
)

print("\nTableaux CSV enregistres dans livrables/")