# pipelines/01_ingest_bronze.py  (testé sur MariaDB 10.11 et 11.2 ; à relire avant la séance)
import os
import pandas as pd
from sqlalchemy import create_engine, text

src_crm = create_engine("mysql+pymysql://reader:reader@mariadb:3306/crm")  # lecture seule
src_cif = create_engine("mysql+pymysql://reader:reader@mariadb:3306/cif")
dst = create_engine("mysql+pymysql://root:root@mariadb:3306/bronze")
BATCH = os.environ.get("BATCH_ID", "L-2026-10-01")

def ingest(src, table, target, source_system):
    # types texte : bronze n'échoue pas. coerce_float=False garde les DECIMAL tels quels (184.10 et non 184.1)
    df = pd.read_sql(f"SELECT * FROM {table}", src, coerce_float=False).astype("string")
    df = df.astype(object).where(df.notna(), None)
    # empreinte de ligne calculée AVANT d'ajouter les métadonnées
    h = pd.util.hash_pandas_object(df.fillna("\\N").astype(str), index=False)
    df["_row_hash"] = [f"{v:016x}" for v in h]
    df["_batch_id"] = BATCH
    df["_source_system"] = source_system
    with dst.begin() as c:                                    # relance d'un même lot : on remplace ce lot seulement
        c.execute(text(f"DELETE FROM {target} WHERE _batch_id = :b"), {"b": BATCH})
        df.to_sql(target, c, if_exists="append", index=False, chunksize=10_000)

for t in ["client", "contrat", "type_contrat", "sinistre"]:
    ingest(src_crm, t, f"crm_{t}", "crm")
for t, target in [("clients", "cif_clients"), ("compte", "cif_compte"), ("pays", "cif_pays")]:
    ingest(src_cif, t, target, "cif")