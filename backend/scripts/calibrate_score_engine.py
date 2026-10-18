import json, random, sys, os, math, statistics
sys.path.insert(0, "/var/www/aidermy/backend")
os.chdir("/var/www/aidermy/backend")
from dotenv import load_dotenv, dotenv_values
load_dotenv(".env")
import psycopg
from collections import defaultdict
from app.calibration_profiles import CALIBRATION_PROFILES
from app.calibration_service import run_score_engine, audit
import app.scoring_engine as SE

c = psycopg.connect(dotenv_values(".env")["SUPABASE_DATABASE_URL"])
cur = c.cursor()
cur.execute("""
SELECT cr.product_id, cr.profile_id, cr.reference, p.name, p.ingredients, p.catalog_category
FROM calibration_references cr JOIN products p ON p.id = cr.product_id
WHERE p.catalog_category IS NOT NULL AND p.catalog_category <> 'Уход за губами'
  AND p.ingredients IS NOT NULL AND btrim(p.ingredients) <> ''
""")
rows = cur.fetchall(); c.close()
profiles = {p["id"]: p for p in CALIBRATION_PROFILES}
cases, ref_map = [], {}
for pid, prof_id, ref_json, name, ingredients, cat in rows:
    pr = profiles.get(prof_id)
    if not pr: continue
    cases.append({"product": {"id": pid, "name": (name or "").replace(chr(10)," ").strip(), "category": cat or "", "ingredients": ingredients or ""}, "profile": pr})
    ref_map[f"{pid}:{prof_id}"] = json.loads(ref_json)
print(f"face cases (excl lips): {len(cases)}", flush=True)

by_prod = defaultdict(list)
for c in cases: by_prod[c["product"]["id"]].append(c)
prods = list(by_prod.keys())
random.seed(20261018); random.shuffle(prods)
n = len(prods); nt, nv = int(n*0.6), int(n*0.2)
train_p = set(prods[:nt]); val_p = set(prods[nt:nt+nv]); test_p = set(prods[nt+nv:])
train = [c for c in cases if c["product"]["id"] in train_p]
val = [c for c in cases if c["product"]["id"] in val_p]
test = [c for c in cases if c["product"]["id"] in test_p]
print(f"split: train={len(train)} val={len(val)} test={len(test)}", flush=True)

def run(cases, scale, decay, sat):
    o_s, o_d = SE.PROFILE_CONFLICT_SCALE, SE.PROFILE_CONFLICT_DECAY
    SE.PROFILE_CONFLICT_SCALE = scale; SE.PROFILE_CONFLICT_DECAY = decay
    try:
        return run_score_engine(cases, config_override={"saturation_scale": sat})
    finally:
        SE.PROFILE_CONFLICT_SCALE = o_s; SE.PROFILE_CONFLICT_DECAY = o_d

def full_metrics(results):
    a = audit(results, ref_map)
    deltas = []
    seg_cat = defaultdict(list); seg_prof = defaultdict(list); seg_branch = defaultdict(list)
    for r in results:
        key = f'{r["product"]["id"]}:{r["profile"]["id"]}'
        ref = ref_map.get(key)
        if ref is None: continue
        est = ref.get("estimate")
        if est is None: continue
        d = r["score"] - est
        deltas.append(d)
        seg_cat[r["product"].get("category") or "?"].append(d)
        seg_prof[r["profile"]["structured"].get("skin_type","?")].append(d)
        ps = r.get("phase1_status") or ""
        branch = "blocked" if ps == "blocked" else ("insufficient" if ps == "insufficient_data" else "passed")
        seg_branch[branch].append(d)
    a["rmse"] = round(math.sqrt(sum(d*d for d in deltas)/len(deltas)), 2) if deltas else None
    a["by_category"] = {k: round(statistics.mean(v),2) for k,v in sorted(seg_cat.items(), key=lambda kv:-len(kv[1]))[:9]}
    a["by_profile"] = {k: round(statistics.mean(v),2) for k,v in sorted(seg_prof.items(), key=lambda kv:-len(kv[1]))[:8]}
    a["by_branch"] = {k: (round(statistics.mean(v),2), len(v)) for k,v in seg_branch.items()}
    return a

configs = [
    ("baseline_sat1.5", 1.5, 2.0, 1.5),
    ("candidate_sat1.2", 1.5, 2.0, 1.2),
]
for phase, data in [("TRAIN", train), ("VAL", val), ("TEST", test)]:
    print(f"\n=== {phase} ===", flush=True)
    for name, s, d, sat in configs:
        print(name, full_metrics(run(data, s, d, sat)), flush=True)
print("DONE", flush=True)
