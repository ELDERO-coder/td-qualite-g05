# -*- coding: utf-8 -*-
"""Mesures reproductibles du profil S1 et des définitions exploratoires de client actif."""
import os

from sqlalchemy import create_engine, text

REFERENCE_DATE = "2026-10-14"
engine = create_engine(os.environ.get(
    "DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"))


def fetch_one(sql, params=None):
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).mappings().one()


def print_table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(str(value) for value in row) + " |")


print(f"Référence : {REFERENCE_DATE}")
print("\nInventaire des sources")
inventory = []
for schema, table in (("crm", "client"), ("crm", "contrat"),
                     ("crm", "sinistre"), ("crm", "type_contrat"),
                     ("cif", "clients"), ("cif", "compte"), ("cif", "pays")):
    count = fetch_one(f"SELECT COUNT(*) AS n FROM `{schema}`.`{table}`")["n"]
    inventory.append((f"{schema}.{table}", count))
print_table(("Table", "Lignes"), inventory)

print("\nProfil de crm.client")
profile = fetch_one("""
SELECT COUNT(*) AS total,
       SUM(client_id IS NULL) AS id_null,
       COUNT(DISTINCT client_id) AS id_distinct,
       SUM(email IS NULL) AS email_null,
       SUM(email = '') AS email_empty,
       SUM(cp REGEXP '^[0-9]{5}$') AS cp_valid,
       SUM(cp IS NULL) AS cp_null,
       SUM(telephone REGEXP '^[+]?[0-9 ()-]{8,20}$') AS phone_valid,
       SUM(telephone IS NULL) AS phone_null,
       SUM(date_naissance > :reference) AS dob_future,
       SUM(pays REGEXP '^[A-Z]{2}$') AS country_valid,
       SUM(pays IS NULL) AS country_null
FROM crm.client
""", {"reference": REFERENCE_DATE})
print_table(("Mesure", "Résultat"), [
    ("Lignes", profile["total"]),
    ("client_id NULL / distincts", f"{profile['id_null']} / {profile['id_distinct']}"),
    ("email NULL / vide", f"{profile['email_null']} / {profile['email_empty']}"),
    ("CP conforme ^[0-9]{5}$ / NULL", f"{profile['cp_valid']} / {profile['cp_null']}"),
    ("Téléphone conforme ^[+]?[0-9 ()-]{8,20}$ / NULL", f"{profile['phone_valid']} / {profile['phone_null']}"),
    ("Date de naissance future", profile["dob_future"]),
    ("Pays conforme ^[A-Z]{2}$ / NULL", f"{profile['country_valid']} / {profile['country_null']}"),
])

print("\nProfil CIF")
cif = fetch_one("""
SELECT COUNT(*) AS total, COUNT(DISTINCT column0) AS id_distinct,
       SUM(column3 IS NOT NULL) AS birthdate_present,
       COUNT(DISTINCT column3) AS birthdate_distinct,
       COUNT(DISTINCT column4) AS address_distinct,
       COUNT(DISTINCT column5) AS postal_distinct,
       COUNT(DISTINCT column6) AS city_distinct,
       COUNT(DISTINCT column7) AS country_distinct,
       COUNT(DISTINCT column8) AS phone_distinct,
       COUNT(DISTINCT column9) AS email_distinct
FROM cif.clients
""")
accounts = fetch_one("""
SELECT COUNT(*) AS total, SUM(column3='O') AS open_count,
       SUM(column3='F') AS closed_count, COUNT(DISTINCT column1) AS linked_clients
FROM cif.compte
""")
print_table(("Observation", "Résultat"), [
    ("cif.clients : lignes / id distincts column0", f"{cif['total']} / {cif['id_distinct']}"),
    ("column3 : dates renseignées / valeurs distinctes", f"{cif['birthdate_present']} / {cif['birthdate_distinct']}"),
    ("column4/5/6 : adresses / CP / villes distincts", f"{cif['address_distinct']} / {cif['postal_distinct']} / {cif['city_distinct']}"),
    ("column7/8/9 : pays / téléphones / emails distincts", f"{cif['country_distinct']} / {cif['phone_distinct']} / {cif['email_distinct']}"),
    ("cif.compte : lignes / ouverts O / fermés F / clients liés", f"{accounts['total']} / {accounts['open_count']} / {accounts['closed_count']} / {accounts['linked_clients']}"),
])

active = fetch_one("""
WITH commercial AS (
    SELECT souscripteur_id AS id FROM crm.contrat
    WHERE souscripteur_id IS NOT NULL AND
          (date_debut >= DATE_SUB(:reference, INTERVAL 12 MONTH) OR
           (date_debut <= :reference AND (date_fin IS NULL OR date_fin >= :reference)))
    UNION
    SELECT assure_id FROM crm.contrat
    WHERE assure_id IS NOT NULL AND
          (date_debut >= DATE_SUB(:reference, INTERVAL 12 MONTH) OR
           (date_debut <= :reference AND (date_fin IS NULL OR date_fin >= :reference)))
), claims_proxy AS (
    SELECT DISTINCT k.assure_id AS id FROM crm.sinistre s
    JOIN crm.contrat k ON k.contrat_id=s.contrat_id
    WHERE k.assure_id IS NOT NULL
), risks AS (
    SELECT souscripteur_id AS id FROM crm.contrat
    WHERE souscripteur_id IS NOT NULL AND date_debut <= :reference
      AND (date_fin IS NULL OR date_fin >= :reference)
      AND date_derniere_cotisation >= DATE_SUB(:reference, INTERVAL 3 MONTH)
    UNION
    SELECT assure_id FROM crm.contrat
    WHERE assure_id IS NOT NULL AND date_debut <= :reference
      AND (date_fin IS NULL OR date_fin >= :reference)
      AND date_derniere_cotisation >= DATE_SUB(:reference, INTERVAL 3 MONTH)
)
SELECT (SELECT COUNT(*) FROM commercial x JOIN crm.client c ON c.client_id=x.id) AS commercial_count,
       (SELECT COUNT(*) FROM claims_proxy x JOIN crm.client c ON c.client_id=x.id) AS claims_count,
       (SELECT COUNT(*) FROM risks x JOIN crm.client c ON c.client_id=x.id) AS risks_count
""", {"reference": REFERENCE_DATE})
print("\nDéfinitions exploratoires de client actif")
print_table(("Vue", "Définition opérationnelle", "Clients"), [
    ("Commerciale", "Contrat en cours ou commencé dans les 12 derniers mois; souscripteur ou assuré", active["commercial_count"]),
    ("Sinistres", "Au moins un sinistre lié à un contrat dont le client est assuré; statut en cours non disponible", active["claims_count"]),
    ("Risques / proxy CD-001", "Contrat en cours et dernière cotisation dans les 3 mois; souscripteur ou assuré", active["risks_count"]),
])
