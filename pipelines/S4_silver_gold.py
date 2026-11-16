# US-21 — Imports nécessaires à la construction de SILVER
# Provenance : code du professeur (pipelines/02_build_silver.py)

from aq import *

import pandas as pd
from pyspark.sql import SparkSession, functions as F
from sqlalchemy import create_engine

spark = SparkSession.builder \
    .master("local[2]") \
    .appName("S4_silver_gold") \
    .getOrCreate()

def depuis_bronze(requete):
    df = lire(requete, b=BATCH)
    return spark.createDataFrame(df)

def total(requete, b=None):
    return int(lire(requete, b=b).iloc[0, 0])

# %% US-21 — Règles de standardisation : majuscules, sans accent, pays ISO, téléphone, code postal (PySpark)
ACC_DE = "ÀÁÂÃÄÅàáâãäåÇçÈÉÊËèéêëÌÍÎÏìíîïÑñÒÓÔÕÖòóôõöÙÚÛÜùúûüÝýÿ"
ACC_A = "AAAAAAaaaaaaCcEEEEeeeeIIIIiiiiNnOOOOOoooooUUUUuuuuYyy"
PAYS_FR = ["FR", "FRANCE", "F", "FRNACE"]

def sans_accent(c):
    return F.regexp_replace(F.translate(c, ACC_DE, ACC_A), r"[^\x00-\x7F]", "")

def vide_en_null(c):
    return F.when(c.isNotNull() & (c != ""), c)

def maj(c):
    return vide_en_null(F.trim(F.regexp_replace(F.upper(sans_accent(c)), r"\s+", " ")))

def identite(c):
    r = F.regexp_replace(maj(c), r"^(SOCIETE|SOC\.?|STE|ETS)\s+", "")
    r = F.regexp_replace(r, r"(?<![A-Z])S\.?\s*A\.?\s*R\.?\s*L\.?(?![A-Z])", "SARL")
    return F.trim(F.regexp_replace(r, r"\s+", " "))

def adresse(c):
    r = maj(c)
    for a, b in [(r"\bR\.\s*", "RUE "), (r"\bAV\.\s*", "AVENUE "), (r"\bBD\s*", "BOULEVARD "), (r"\bCH\.\s*", "CHEMIN "), (r"\bIMP\.\s*", "IMPASSE ")]:
        r = F.regexp_replace(r, a, b)
    return F.trim(F.regexp_replace(r, r"\s+", " "))

def telephone(c):
    r = vide_en_null(F.trim(c))
    return F.regexp_replace(F.regexp_replace(r, r"[ .\-()]", ""), r"^(\+33|0033)", "0")

def pays(c):
    r = vide_en_null(F.upper(F.trim(c)))
    return F.when(r.isin(PAYS_FR), "FR").otherwise(r)

def courriel(c):
    return vide_en_null(F.lower(F.trim(c)))


def client_crm(b):
    p = pays(F.col("pays"))
    cp0 = F.trim(F.col("cp"))
    zero = F.coalesce(cp0.rlike(r"^[0-9]{4}$") & (p == "FR"), F.lit(False))  # zéro initial perdu : restauré pour la France seulement
    morale = F.col("raison_sociale").isNotNull() & (F.trim(F.col("raison_sociale")) != "")
    return b.select("bronze_row_id", F.lit("crm").alias("source_system"), F.col("client_id").alias("source_id"),
        F.when(F.col("type_personne").isin("prospect", "souscripteur", "assure"), F.col("type_personne")).alias("type_personne"),
        identite(F.when(morale, F.col("raison_sociale")).otherwise(F.col("nom"))).alias("identite_normalisee"),
        maj(F.col("prenom")).alias("prenom_normalise"),
        F.to_date("date_naissance", "yyyy-MM-dd").alias("date_naissance"),
        adresse(F.col("adresse")).alias("adresse_normalisee"),
        p.alias("pays_iso"),
        F.when(zero, F.lpad(cp0, 5, "0")).otherwise(cp0).alias("cp"),
        maj(F.col("ville")).alias("ville_normalisee"),
        telephone(F.col("telephone")).alias("telephone_normalise"),
        courriel(F.col("email")).alias("email_normalise"),
        F.when(zero, "A_SURVEILLER").otherwise("VALIDE").alias("statut_qualite"))

def client_cif(c):  # le CIF est anonyme : colonne 0 identifiant, 1 identité, 2 prénom, 3 naissance (jj/mm/aaaa), 4 adresse, 5 code postal, 6 ville, 7 pays, 8 téléphone, 9 e-mail
    p = pays(F.col("column7"))
    cp0 = F.trim(F.col("column5"))
    zero = F.coalesce(cp0.rlike(r"^[0-9]{4}$") & (p == "FR"), F.lit(False))
    return c.select("bronze_row_id", F.lit("cif").alias("source_system"), F.col("column0").alias("source_id"), F.lit(None).cast("string").alias("type_personne"),
        identite(F.col("column1")).alias("identite_normalisee"), maj(F.col("column2")).alias("prenom_normalise"),
        F.to_date("column3", "dd/MM/yyyy").alias("date_naissance"), adresse(F.col("column4")).alias("adresse_normalisee"),
        p.alias("pays_iso"), F.when(zero, F.lpad(cp0, 5, "0")).otherwise(cp0).alias("cp"), maj(F.col("column6")).alias("ville_normalisee"),
        telephone(F.col("column8")).alias("telephone_normalise"), courriel(F.col("column9")).alias("email_normalise"),
        F.when(zero, "A_SURVEILLER").otherwise("VALIDE").alias("statut_qualite"))

def contrat_silver(k):
    return k.select("bronze_row_id", "contrat_id", "souscripteur_id",
        F.when(F.col("assure_id") != "0", F.col("assure_id")).alias("assure_id"),  # la sentinelle '0' devient NULL (US-17)
        "code_type", F.to_date("date_debut", "yyyy-MM-dd").alias("date_debut"), F.to_date("date_fin", "yyyy-MM-dd").alias("date_fin"),
        F.col("duree_garantie_mois").cast("int").alias("duree_garantie_mois"), F.col("prime_annuelle").cast("decimal(10,2)").alias("prime_annuelle"),
        F.to_date("date_derniere_cotisation", "yyyy-MM-dd").alias("date_derniere_cotisation"))

def sinistre_silver(s):
    return s.select("bronze_row_id", "sinistre_id", "contrat_id",
        F.to_date("date_survenance", "yyyy-MM-dd").alias("date_survenance"), F.to_date("date_declaration", "yyyy-MM-dd").alias("date_declaration"),
        "type_sinistre", F.col("montant_estime").cast("decimal(12,2)").alias("montant_estime"),
        adresse(F.col("adresse_sinistre")).alias("adresse_normalisee"), F.col("cp_sinistre").alias("cp"),
        maj(F.col("ville_sinistre")).alias("ville_normalisee"), "canal_saisie")


# %% US-21, 22 - Bronze vers silver, pare-feu qualité et quarantaine (une fonction idempotente)
DDL_SILVER = [
"CREATE TABLE IF NOT EXISTS silver.type_contrat (code_type VARCHAR(10) PRIMARY KEY, libelle VARCHAR(80) NOT NULL, branche VARCHAR(20) NOT NULL)",
"""CREATE TABLE IF NOT EXISTS silver.contrat (
silver_row_id BIGINT AUTO_INCREMENT PRIMARY KEY, bronze_row_id BIGINT NOT NULL,
contrat_id VARCHAR(12) NOT NULL, souscripteur_id VARCHAR(12), assure_id VARCHAR(12),
code_type VARCHAR(10), date_debut DATE, date_fin DATE, duree_garantie_mois INT, prime_annuelle DECIMAL(10,2), date_derniere_cotisation DATE,
_batch_id VARCHAR(20) NOT NULL, _processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
UNIQUE KEY uq_bronze (bronze_row_id), KEY ix_contrat (contrat_id), KEY ix_souscripteur (souscripteur_id), KEY ix_assure (assure_id))""",
"""CREATE TABLE IF NOT EXISTS silver.sinistre (
silver_row_id BIGINT AUTO_INCREMENT PRIMARY KEY, bronze_row_id BIGINT NOT NULL,
sinistre_id VARCHAR(12) NOT NULL, contrat_id VARCHAR(12), date_survenance DATE, date_declaration DATE, type_sinistre VARCHAR(40),
montant_estime DECIMAL(12,2), adresse_normalisee VARCHAR(160), cp VARCHAR(10), ville_normalisee VARCHAR(80), canal_saisie VARCHAR(30),
_batch_id VARCHAR(20) NOT NULL, _processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
UNIQUE KEY uq_bronze (bronze_row_id), KEY ix_contrat (contrat_id))"""]

def rejet(df, entite, source, regle, motif):
    """Lignes écartées : leur identifiant bronze, le code de la règle bloquante et le motif. Rien ne disparaît sans trace."""
    return df.select(F.lit(BATCH).alias("batch_id"), F.lit(entite).alias("entite"), F.lit(source).alias("source_system"), "bronze_row_id",
                     F.lit(regle).alias("rule_id"), F.lit("S").alias("porte"), F.lit(motif).alias("motif"))


def construire_silver():
    for ddl in DDL_SILVER:
        executer(ddl)
    for t in ["client", "contrat", "sinistre"]:
        executer(f"DELETE FROM silver.{t} WHERE _batch_id = :b", b=BATCH)
    executer("DELETE FROM silver.type_contrat")
    executer("DELETE FROM dq.rejets WHERE batch_id = :b AND porte = 'S'", b=BATCH)
    codes_pays = lire("SELECT code_pays FROM silver.ref_pays")["code_pays"].tolist()
    types = ["prospect", "souscripteur", "assure"]
    rejets, bilan = [], {}

    # client : CRM puis CIF dans la même table, avec la source
    b = depuis_bronze("SELECT bronze_row_id, client_id, type_personne, nom, prenom, raison_sociale, date_naissance, adresse, cp, ville, pays, telephone, email FROM bronze.crm_client WHERE _batch_id = :b")
    s = client_crm(b)
    ko009 = F.col("type_personne").isNull()
    ko007 = ~F.coalesce(F.col("pays_iso").isin(*codes_pays), F.lit(False))
    rejets += [rejet(s.filter(ko009), "client", "crm", "RQ-009", "type_personne hors domaine"),
               rejet(s.filter(~ko009 & ko007), "client", "crm", "RQ-007", "pays absent du référentiel après normalisation (non deviné)")]
    valides_crm = s.filter(~(ko007 | ko009))
    c = depuis_bronze("SELECT bronze_row_id, column0, column1, column2, column3, column4, column5, column6, column7, column8, column9 FROM bronze.cif_clients WHERE _batch_id = :b")
    sc = client_cif(c)
    rejets.append(rejet(sc.filter(ko007), "client", "cif", "RQ-007", "pays absent du référentiel après normalisation (non deviné)"))
    valides = valides_crm.unionByName(sc.filter(~ko007)).withColumn("_batch_id", F.lit(BATCH))
    out = valides.toPandas()
    out = out.rename(columns={"source_system": "source_systeme"})
    ecrire(out, None, "client", moteur=eng("silver"))
    bilan["client_crm"] = (total("SELECT COUNT(*) FROM bronze.crm_client WHERE _batch_id = :b", b=BATCH), int((out.source_systeme == "crm").sum()))
    bilan["client_cif"] = (total("SELECT COUNT(*) FROM bronze.cif_clients WHERE _batch_id = :b", b=BATCH), int((out.source_systeme == "cif").sum()))

    # contrat
    k = depuis_bronze("SELECT bronze_row_id, contrat_id, souscripteur_id, assure_id, code_type, date_debut, date_fin, duree_garantie_mois, prime_annuelle, date_derniere_cotisation FROM bronze.crm_contrat WHERE _batch_id = :b")
    d = contrat_silver(k)
    ko1 = F.coalesce(F.col("date_fin") <= F.col("date_debut"), F.lit(False))
    ko10 = ~F.coalesce(F.col("duree_garantie_mois").isin(12, 24, 36, 60), F.lit(False))
    rejets += [rejet(d.filter(ko1), "contrat", "crm", "RQ-001", "date_fin <= date_debut"),
               rejet(d.filter(~ko1 & ko10), "contrat", "crm", "RQ-010", "durée de garantie hors 12, 24, 36, 60")]
    out = d.filter(~(ko1 | ko10)).withColumn("_batch_id", F.lit(BATCH)).toPandas()
    ecrire(out, None, "contrat", moteur=eng("silver"))
    bilan["contrat"] = (total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b", b=BATCH), len(out))

    # sinistre (aucune règle bloquante de la porte S n'y est appliquée : toutes les lignes passent)
    sn = depuis_bronze("SELECT bronze_row_id, sinistre_id, contrat_id, date_survenance, date_declaration, type_sinistre, montant_estime, adresse_sinistre, cp_sinistre, ville_sinistre, canal_saisie FROM bronze.crm_sinistre WHERE _batch_id = :b")
    out = sinistre_silver(sn).withColumn("_batch_id", F.lit(BATCH)).toPandas()
    ecrire(out, None, "sinistre", moteur=eng("silver"))
    bilan["sinistre"] = (total("SELECT COUNT(*) FROM bronze.crm_sinistre WHERE _batch_id = :b", b=BATCH), len(out))

    tc = lire("SELECT code_type, libelle, branche FROM bronze.crm_type_contrat WHERE _batch_id = :b", b=BATCH)
    ecrire(tc, None, "type_contrat", moteur=eng("silver"))

    rej = rejets[0]
    for r in rejets[1:]:
        rej = rej.unionByName(r)
    rejets_pd = rej.toPandas()
    rejets_pd = rejets_pd.rename(columns={"source_system": "source_systeme"})
    ecrire(rejets_pd, None, "rejets", moteur=eng("dq"))
    return bilan


if __name__ == "__main__":
    bilan = construire_silver()
    print("\n=== BILAN BRONZE → SILVER ===")
    for entite, (bronze, silver) in bilan.items():
        print(f"{entite} : BRONZE={bronze}, SILVER={silver}, écart={bronze - silver}")
    spark.stop()