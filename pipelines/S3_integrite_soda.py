# %% Paramètres, connexion et lancement d'un scan Soda
import sys, os, re, json, shutil, subprocess, warnings
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from aq import *
import yaml
warnings.filterwarnings("ignore")

RACINE = "/home/jovyan/work" if os.path.isdir("/home/jovyan/work/soda") else "."
SODA = f"{RACINE}/soda"
os.makedirs(f"{SODA}/checks/bronze", exist_ok=True)
os.makedirs(f"{SODA}/reports", exist_ok=True)
SODA_BIN = shutil.which("soda") or os.path.join(os.path.dirname(sys.executable), "soda")
REGLES = lire("SELECT rule_id, severite, seuil_min FROM dq.regle").set_index("rule_id")
CODES_RETOUR = {0: "conforme", 1: "avertissement", 2: "échec", 3: "erreur d'exécution"}

def nombre(v):
    """Entier quand la valeur est entière (5989.0 devient 5989), sinon la valeur telle quelle."""
    return int(v) if isinstance(v, float) and v.is_integer() else v

def scan(source, fichier):
    """Équivalent de : soda scan -d <source> -c soda/configuration.yml <fichier>
    Renvoie (code retour, contrôles). Le code retour vaut 0 si tout passe, 1 s'il y a un avertissement, 2 s'il y a un échec, 3 en cas d'erreur."""
    sortie = f"{SODA}/reports/{source}_{os.path.basename(fichier).replace('.yml', '')}.json"
    if os.path.exists(sortie):
        os.remove(sortie)
    p = subprocess.run([SODA_BIN, "scan", "-d", source, "-c", f"{SODA}/configuration.yml", "-srf", sortie, fichier], capture_output=True, text=True)
    if not os.path.exists(sortie):
        raise RuntimeError(f"Scan en erreur (code {p.returncode}) :\n{p.stdout[-1500:]}\n{p.stderr[-800:]}")
    controles = []
    for c in json.load(open(sortie, encoding="utf-8"))["checks"]:
        regle = re.search(r"RQ-\d{3}", c["name"])
        controles.append({"fichier": os.path.basename(fichier), "couche": source, "rule_id": regle.group(0) if regle else None,
                          "controle": c["name"], "resultat": c["outcome"], "valeur": nombre((c.get("diagnostics") or {}).get("value"))})
    return p.returncode, controles


    # %% US-12 — Une source de données par couche, un fichier de checks par table
# La configuration déclare une source de données par base (crm, bronze, silver, gold) : les mêmes fichiers de checks se lancent sur chaque couche.
print("Sources de données déclarées :", [k.replace("data_source ", "") for k in yaml.safe_load(open(f"{SODA}/configuration.yml", encoding="utf-8"))])

# Les fichiers soda/checks/*.yml ciblent la source crm (tables client, contrat, sinistre). Dans bronze, les tables s'appellent crm_client, crm_contrat,
# crm_sinistre : le fichier de bronze se génère à partir de celui de crm en changeant le nom de table, comme le dit la fiche S3.
TABLES_BRONZE = {"client": "crm_client", "contrat": "crm_contrat", "sinistre": "crm_sinistre", "type_contrat": "crm_type_contrat"}

def vers_bronze(texte):
    for source, cible in TABLES_BRONZE.items():
        texte = re.sub(rf"(checks for |filter |FROM |JOIN |exists in |must exist in ){source}\b", rf"\1{cible}", texte)
    return texte.replace("[12, 24, 36, 60]", "['12', '24', '36', '60']")

for nom in ["client", "contrat", "sinistre"]:
    texte = open(f"{SODA}/checks/{nom}_checks.yml", encoding="utf-8").read()
    open(f"{SODA}/checks/bronze/{nom}_checks.yml", "w", encoding="utf-8").write(vers_bronze(texte))

# Contrôles ajoutés pour bronze : RQ-016 (statut) et la relation sinistre vers contrat. Un contrôle qui ne mesure qu'un avertissement le déclare avec `warn`.
open(f"{SODA}/checks/bronze/integrite_checks.yml", "w", encoding="utf-8").write("""# RQ-016 : un souscripteur a au moins un contrat (règle d'avertissement dans dq.regle, seuil 98 %)
checks for crm_client:
  - failed rows:
      name: RQ-016 souscripteur sans contrat
      fail query: |
        SELECT k.client_id FROM crm_client k
        WHERE k.type_personne = 'souscripteur'
          AND NOT EXISTS (SELECT 1 FROM crm_contrat c WHERE c.souscripteur_id = k.client_id)
      warn: when > 0

# Relation sinistre vers contrat : aucune clé étrangère n'est déclarée dans la base
checks for crm_sinistre:
  - values in (contrat_id) must exist in crm_contrat (contrat_id):
      name: Relation sinistre vers contrat
""")

CONTROLES, CODES = [], {}
for nom in ["client_checks", "contrat_checks", "sinistre_checks", "integrite_checks"]:
    CODES[nom], c = scan("bronze", f"{SODA}/checks/bronze/{nom}.yml")
    CONTROLES += c

CTRL = pd.DataFrame(CONTROLES, dtype=object)
CTRL["severite"] = CTRL.rule_id.map(REGLES.severite)
print(CTRL[["fichier", "rule_id", "controle", "resultat", "valeur", "severite"]].sort_values(["fichier", "rule_id"]).to_string(index=False))

# Le code retour du scan est ce qui ferme la porte dans un pipeline : il suffit qu'un seuil d'échec renvoie un code non nul.
print("\nCodes retour par fichier :", {k: f"{v} ({CODES_RETOUR[v]})" for k, v in CODES.items()})
code_porte = max(CODES.values())
bloquants = CTRL[(CTRL.resultat == "fail") & (CTRL.severite == "BLOQUANTE")].rule_id.dropna().unique().tolist()
print(f"Code retour de la porte : {code_porte} ({CODES_RETOUR[code_porte]}) ; règles bloquantes en échec : {bloquants}")
print("Avertissements :", CTRL[CTRL.resultat == "warn"].controle.tolist())
# Dans un pipeline, l'étape se termine par : sys.exit(code_porte) (une étape qui sort avec un code non nul arrête la suite)


# %% US-16 - Clés étrangères : orphelins par relation (RQ-007, 011, 012, 013)
# Un contrôle 'values in (...) must exist in ...' (reference) par relation. La base n'impose aucune de ces clés étrangères.
def valeur(rule_id=None, controle=None):
    ligne = CTRL[CTRL.rule_id == rule_id] if rule_id else CTRL[CTRL.controle == controle]
    return int(ligne.valeur.iloc[0])

def total(requete):
    return int(lire(requete, b=BATCH).iloc[0, 0])

RELATIONS = pd.DataFrame([
    ("RQ-007 : client.pays -> ref_pays",
     total("SELECT COUNT(*) FROM bronze.crm_client WHERE _batch_id = :b"), valeur("RQ-007")),
    ("RQ-011 : contrat.code_type -> type_contrat",
     total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b"), valeur("RQ-011")),
    ("RQ-012 : contrat.souscripteur_id -> client",
     total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b"), valeur("RQ-012")),
    ("RQ-013 : contrat.assure_id -> client (sentinelle 0 exclue)",
     total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b AND assure_id <> '0'"), valeur("RQ-013")),
    ("sinistre.contrat_id -> contrat",
     total("SELECT COUNT(*) FROM bronze.crm_sinistre WHERE _batch_id = :b"), valeur(controle="Relation sinistre vers contrat"))
], columns=["relation", "lignes_testees", "orphelins"])

RELATIONS["pct"] = (100 * RELATIONS.orphelins / RELATIONS.lignes_testees).round(3)
print(RELATIONS.to_string(index=False))

# À vous : une conclusion argumentée par relation (erreur de saisie, donnée supprimée, valeur conventionnelle) dans livrables/S3_integrite_soda.md.
# Les lignes elles-mêmes se lisent par anti-jointure :
orphelins_souscripteur = lire("""
SELECT c.contrat_id, c.souscripteur_id FROM bronze.crm_contrat c
LEFT JOIN bronze.crm_client k ON k.client_id = c.souscripteur_id
WHERE c._batch_id = :b AND k.client_id IS NULL LIMIT 20
""", b=BATCH)
print(orphelins_souscripteur.head(5).to_string(index=False))



# %% US-17 - Traiter la valeur sentinelle de assure_id avant le contrôle de clé (RQ-013)
# Avant traitement : le même contrôle de référence, sans le filtre qui écarte la sentinelle '0'.
open(f"{SODA}/checks/bronze/sentinelle_avant.yml", "w", encoding="utf-8").write("""checks for crm_contrat:
  - values in (assure_id) must exist in crm_client (client_id):
      name: RQ-013 avant traitement de la sentinelle
""")

_, avant = scan("bronze", f"{SODA}/checks/bronze/sentinelle_avant.yml")
contrats = total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b")
sentinelles = total("SELECT COUNT(*) FROM bronze.crm_contrat WHERE _batch_id = :b AND assure_id = '0'")
orph_avant, orph_apres = int(avant[0]["valeur"]), valeur("RQ-013")

print(pd.DataFrame([{
    "contrats": contrats,
    "valeurs_sentinelles": sentinelles,
    "orphelins_avant": orph_avant,
    "orphelins_apres": orph_apres,
    "ecart_explique_par_la_sentinelle": orph_avant - orph_apres,
    "pct_avant": round(100 * orph_avant / contrats, 1),
    "pct_apres": round(100 * orph_apres / contrats, 1)
}]).to_string(index=False))

# Après : le filtre `assure_id <> '0'` du fichier contrat_checks.yml revient à remplacer la sentinelle par NULL, donc à l'exclure du contrôle.
# Convention à documenter dans livrables/S3_integrite_soda.md : la sentinelle '0' signifie « pas d'assuré distinct » ; elle devient NULL en silver.