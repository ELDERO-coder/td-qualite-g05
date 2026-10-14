# -*- coding: utf-8 -*-
"""aq.py : boîte à outils commune aux scripts Python du TD (S1 à S5).
Connexion à MariaDB, paramètres du lot, écriture des mesures dans dq.dq_history, empreinte du gold.
Dans un notebook (dossier notebooks/) :   import sys; sys.path.append("../pipelines");  from aq import *
En terminal (dossier de travail du conteneur) :   python pipelines/S1_bronze_profilage.py
Variables d'environnement facultatives : DQ_DB_URL (compte root), DQ_READER_URL (compte en lecture seule), BATCH_ID."""
import os, sys, re, json, shutil, subprocess, hashlib
import pandas as pd
from sqlalchemy import create_engine, text

URL    = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306")        # l'hôte est mariadb, pas localhost ; le pilote est pymysql
READER = os.environ.get("DQ_READER_URL", URL.replace("root:root", "reader:reader"))  # compte en lecture seule sur cif et crm
BATCH          = os.environ.get("BATCH_ID", "L-2026-10-01")   # identifiant du lot
DATE_REF       = "2026-10-01"                                  # date de référence du lot (fiche CD-001)
COTISATION_MIN = "2026-07-01"                                  # date de référence moins trois mois (fiche CD-001)
GOLD_TABLES    = ["client_unique", "contrat_certifie", "sinistre_certifie"]
RACINE = "/home/jovyan/work" if os.path.isdir("/home/jovyan/work/soda") else "."      # dossier du dépôt (celui qui contient soda/, reports/, data/)
SODA = f"{RACINE}/soda"
SODA_BIN = shutil.which("soda") or os.path.join(os.path.dirname(sys.executable), "soda")
CODES_RETOUR = {0: "conforme", 1: "avertissement", 2: "échec", 3: "erreur d'exécution"}

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 60)

def eng(base=""):
    """Moteur SQLAlchemy sur le compte root. base='' : toutes les tables sont alors qualifiées (bronze.crm_client)."""
    return create_engine(f"{URL}/{base}", pool_pre_ping=True)

def reader(base):
    """Moteur sur le compte reader : lecture seule, uniquement cif et crm (les sources ne se modifient jamais)."""
    return create_engine(f"{READER}/{base}")

def lire(requete, moteur=None, **params):
    """Résultat d'une requête SQL en DataFrame. coerce_float=False : un DECIMAL reste 184.10 et ne devient pas 184.1."""
    moteur = moteur or eng()
    with moteur.connect() as c:
        return pd.read_sql(text(requete), c, params=params, coerce_float=False)

def executer(requete, moteur=None, **params):
    """Exécute une instruction (INSERT, DELETE, DDL) dans sa propre transaction."""
    moteur = moteur or eng()
    with moteur.begin() as c:
        return c.execute(text(requete), params)

def mesurer(couche, rule_id, table, testees, echecs):
    """Écrit une mesure dans dq.dq_history (couche : BRONZE, SILVER, GOLD, CRM). Rejouer remplace la mesure du lot pour (couche, règle, table)."""
    with eng().begin() as c:
        c.execute(text("DELETE FROM dq.dq_history WHERE batch_id=:b AND couche=:c AND rule_id=:r AND table_cible=:t"),
                  {"b": BATCH, "c": couche, "r": rule_id, "t": table})
        c.execute(text("INSERT INTO dq.dq_history (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs) VALUES (:b,:c,:r,:t,:n,:f)"),
                  {"b": BATCH, "c": couche, "r": rule_id, "t": table, "n": int(testees), "f": int(echecs)})
    return {"rule_id": rule_id, "couche": couche, "table": table, "testees": int(testees), "echecs": int(echecs),
            "conformite_pct": round(100 * (testees - echecs) / testees, 3) if testees else None}

def mesures(couche=None):
    """Dernière mesure de chaque règle du lot, avec sa sévérité et son seuil (dq.v_derniere_mesure joint à dq.regle)."""
    q = """SELECT m.couche, m.rule_id, r.severite, m.table_cible, m.nb_testees, m.nb_echecs, m.taux_conformite, r.seuil_min
           FROM dq.v_derniere_mesure m JOIN dq.regle r USING (rule_id) WHERE m.batch_id = :b""" + (" AND m.couche = :c" if couche else "") + " ORDER BY m.rule_id, m.table_cible"
    return lire(q, b=BATCH, **({"c": couche} if couche else {}))

def empreinte_gold():
    """SHA-256 des trois tables gold : colonnes techniques (_...) exclues, lignes triées, donc indépendant de l'ordre physique."""
    h = hashlib.sha256()
    for t in GOLD_TABLES:
        df = lire(f"SELECT * FROM gold.{t}")
        df = df[[c for c in df.columns if not c.startswith("_")]].astype(str)
        df = df.sort_values(list(df.columns)).reset_index(drop=True)
        h.update(t.encode()); h.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    return h.hexdigest()

def ecrire(df, schema, table, moteur=None):
    """Ajoute un DataFrame à une table existante ; NaN et NaT deviennent NULL."""
    df = df.astype(object).where(df.notna(), None)
    with (moteur or eng()).begin() as c:
        df.to_sql(table, c, schema=schema, if_exists="append", index=False, chunksize=10_000)
    return len(df)

def soda_scan(source, fichier):
    """Équivalent de : soda scan -d <source> -c soda/configuration.yml <fichier>   (S3 détaille cette fonction)
    Renvoie (code retour, contrôles) ; le code retour vaut 0 si tout passe, 1 s'il y a un avertissement, 2 s'il y a un échec, 3 en cas d'erreur."""
    os.makedirs(f"{SODA}/reports", exist_ok=True)
    sortie = f"{SODA}/reports/{source}_{os.path.basename(fichier).replace('.yml', '')}.json"
    if os.path.exists(sortie):
        os.remove(sortie)
    p = subprocess.run([SODA_BIN, "scan", "-d", source, "-c", f"{SODA}/configuration.yml", "-srf", sortie, fichier], capture_output=True, text=True)
    if not os.path.exists(sortie):
        raise RuntimeError(f"Scan en erreur (code {p.returncode}) :\n{p.stdout[-1500:]}\n{p.stderr[-800:]}")
    controles = []
    for c in json.load(open(sortie, encoding="utf-8"))["checks"]:
        v = (c.get("diagnostics") or {}).get("value")
        regle = re.search(r"RQ-\d{3}", c["name"])
        controles.append({"fichier": os.path.basename(fichier), "couche": source, "rule_id": regle.group(0) if regle else None, "controle": c["name"],
                          "resultat": c["outcome"], "valeur": int(v) if isinstance(v, float) and v.is_integer() else v})
    return p.returncode, controles