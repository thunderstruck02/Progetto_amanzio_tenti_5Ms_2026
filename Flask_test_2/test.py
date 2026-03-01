from flask import Flask, render_template, request, abort, url_for
import requests
from functools import lru_cache
from math import ceil
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_BASE = "https://www.dnd5eapi.co"
API_V1 = f"{API_BASE}/api/2014"
SPELL_INDEX_FILE = "indexes/spells_index.json"
MONSTER_INDEX_FILE = "indexes/monsters_index.json"
EQUIP_INDEX_FILE = "indexes/equipment_index.json"

session = requests.Session()

# ---------- Helpers ----------
def api_get(path: str):
    """GET JSON from dnd5eapi with basic error handling."""
    url = f"{API_BASE}{path}" if path.startswith("/api/") else f"{API_V1}/{path.lstrip('/')}"
    r = session.get(url, timeout=15)
    if not r.ok:
        return None
    return r.json()

# --- EQUIPMENT (cache and helpers) ---

@lru_cache(maxsize=64)
def get_equipment_list():
    """Lista base equip: [{index, name, url}, ...]"""
    data = api_get("/api/2014/equipment")
    if not data or "results" not in data:
        return []
    return data["results"]

@lru_cache(maxsize=4096)
def get_equipment_detail(index: str):
    return api_get(f"/api/2014/equipment/{index}")

def build_equipment_index():
    """Indice leggero per filtri oggetti: category/cost/weight + name."""
    base_list = get_equipment_list()
    indices = [it["index"] for it in base_list]

    index_data = {}
    workers = 12

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_equipment_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue

            cat_name = (d.get("equipment_category") or {}).get("name") or ""

            index_data[idx] = {
                "index": idx,
                "name": d.get("name", ""),
                "category": cat_name,
                "cost_bucket": cost_bucket(d.get("cost")),     # low/medium/high/None
                "weight_bucket": weight_bucket(d.get("weight")) # light/heavy/None
            }

    with open(EQUIP_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)

    return index_data


@lru_cache(maxsize=1)
def load_equipment_index():
    if not os.path.exists(EQUIP_INDEX_FILE):
        return {}
    with open(EQUIP_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/admin/rebuild_equipment_index")
def rebuild_equipment_index():
    data = build_equipment_index()
    load_equipment_index.cache_clear()
    return f"Equipment index rebuilt: {len(data)} items"

def cost_bucket(cost):
    """Ritorna 'low'/'medium'/'high' o None."""
    if not cost or "quantity" not in cost:
        return None
    q = cost["quantity"]
    if q < 10:
        return "low"
    if q < 100:
        return "medium"
    if q > 100:
        return "high"
    return None

def weight_bucket(weight):
    """Ritorna 'light'/'heavy' o None."""
    if weight is None:
        return None
    if weight < 5:
        return "light"
    if weight > 20:
        return "heavy"
    return None

# --- MONSTERS (cache and helpers) ---

@lru_cache(maxsize=2048)
def get_monster_detail(index: str):
    return api_get(f"/api/2014/monsters/{index}")

@lru_cache(maxsize=64)
def get_monsters_list():
    """Returns base list: [{index,name,url}, ...]"""
    data = api_get("/api/2014/monsters")
    if not data or "results" not in data:
        return []
    return data["results"]

def build_monster_index():
    """Indice leggero per filtri mostri: type/size/cr + name."""
    base_list = get_monsters_list()
    indices = [m["index"] for m in base_list]

    index_data = {}
    workers = 12

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_monster_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue

            index_data[idx] = {
                "index": idx,
                "name": d.get("name", ""),
                "type": (d.get("type") or "").lower(),
                "size": d.get("size", ""),
                "cr": str(d.get("challenge_rating", "")),  # "10" / "1/4" ecc.
            }

    with open(MONSTER_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)

    return index_data


@lru_cache(maxsize=1)
def load_monster_index():
    """Carica indice da file. Se non esiste, ritorna {} (build manuale)."""
    if not os.path.exists(MONSTER_INDEX_FILE):
        return {}
    with open(MONSTER_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/admin/rebuild_monsters_index")
def rebuild_monsters_index():
    data = build_monster_index()
    load_monster_index.cache_clear()
    return f"Monster index rebuilt: {len(data)} monsters"


def ability_mod(score: int) -> int:
    return (score - 10) // 2

def parse_cr(value: str):
    """CR can be int-like ('10') or fraction ('1/4'). Return a comparable float."""
    if not value:
        return None
    value = value.strip()
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den)
        except:
            return None
    try:
        return float(value)
    except:
        return None

# -------- SPELLS (cache and helpers) --------

@lru_cache(maxsize=64)
def get_spells_list():
    """Lista base spells: [{index,name,url}, ...]"""
    data = api_get("/api/2014/spells")
    if not data or "results" not in data:
        return []
    return data["results"]

@lru_cache(maxsize=4096)
def get_spell_detail(index: str):
    return api_get(f"/api/2014/spells/{index}")

    # ....SPELL_INDEX (per facilitare la ricerca)....

def build_spell_index():
    """Crea (o ricrea) un indice locale dei campi necessari ai filtri."""
    base_list = get_spells_list()
    indices = [s["index"] for s in base_list]

    index_data = {}

    # Parallelismo per velocizzare il primo build (senza esagerare)
    workers = 12
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_spell_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue

            index_data[idx] = {
                "index": idx,
                "name": d.get("name", ""),
                "level": d.get("level"),
                "school": (d.get("school") or {}).get("name"),
                "ritual": bool(d.get("ritual")),
                "concentration": bool(d.get("concentration")),
                "components": [c.upper() for c in (d.get("components") or [])],
            }

    with open(SPELL_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)

    return index_data

@lru_cache(maxsize=1)
def load_spell_index():
    """Carica indice da file. Se non esiste, lo crea."""
    if not os.path.exists(SPELL_INDEX_FILE):
        return {}
    with open(SPELL_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/admin/rebuild_spells_index")
def rebuild_spells_index():
    # ricrea indice e invalida cache del loader
    data = build_spell_index()
    load_spell_index.cache_clear()
    return f"Spell index rebuilt: {len(data)} spells"



def normalize_components(components):
    """components è una lista tipo ['V','S','M']"""
    if not components:
        return set()
    return set([str(c).upper().strip() for c in components])

# Make helper available in templates
app.jinja_env.globals["ability_mod"] = ability_mod


# ---------- Routes ----------
@app.route("/")
def home():
    return render_template("home.html")


# ----- MONSTER ROUTES ------
@app.route("/mostri")
def mostri():
    q = request.args.get("q", "", type=str).strip().lower()
    f_type = request.args.get("type", "", type=str).strip().lower()
    f_size = request.args.get("size", "", type=str).strip()
    f_cr = request.args.get("cr", "", type=str).strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    idx = load_monster_index()
    if not idx:
        return render_template("index_missing.html",
                               title="Mostri",
                               admin_url="/admin/rebuild_monsters_index")

    monsters = list(idx.values())

    # filtri in RAM
    filtered = []
    for m in monsters:
        if q and q not in m["name"].lower():
            continue
        if f_type and m.get("type") != f_type:
            continue
        if f_size and m.get("size") != f_size:
            continue
        if f_cr and m.get("cr") != f_cr:
            continue
        filtered.append(m)

    # ordinamento: per CR poi nome (opzionale)
    filtered.sort(key=lambda x: (parse_cr(x.get("cr", "")) or 99, x.get("name", "")))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_slice = filtered[start:end]

    # dettagli completi SOLO per i mostri in pagina (se servono in card)
    items = []
    for m in page_slice:
        d = get_monster_detail(m["index"])
        items.append(({"index": m["index"], "name": m["name"], "url": f"/api/2014/monsters/{m['index']}"}, d))

    type_options = [
        "aberration", "beast", "celestial", "construct", "dragon", "elemental",
        "fey", "fiend", "giant", "humanoid", "monstrosity", "ooze", "plant", "undead"
    ]
    size_options = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]
    cr_options = ["0","1/8","1/4","1/2","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25","26","27","28","29","30"]

    return render_template(
        "mostri.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        q=q,
        f_type=f_type,
        f_size=f_size,
        f_cr=f_cr,
        type_options=type_options,
        size_options=size_options,
        cr_options=cr_options
    )
@app.route("/mostri/<index>")
def mostro(index):
    d = get_monster_detail(index)
    if not d:
        abort(404)
    # aggiungo url immagine completo se presente
    if d.get("image"):
        d["image_full"] = API_BASE + d["image"]
    return render_template("mostro.html", monster=d)

# -------- EQUIPMENT ROUTES --------

@app.route("/oggetti")
def oggetti():
    q = request.args.get("q", "", type=str).strip().lower()
    category = request.args.get("category", "", type=str).strip()
    cost = request.args.get("cost", "", type=str).strip()
    weight = request.args.get("weight", "", type=str).strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    idx = load_equipment_index()
    if not idx:
        return render_template("index_missing.html",
                               title="Oggetti",
                               admin_url="/admin/rebuild_equipment_index")

    equip = list(idx.values())

    # opzioni categoria (ora gratis)
    category_options = sorted({e.get("category","") for e in equip if e.get("category")})

    # filtri in RAM
    filtered = []
    for e in equip:
        if q and q not in e["name"].lower():
            continue
        if category and e.get("category") != category:
            continue
        if cost and e.get("cost_bucket") != cost:
            continue
        if weight and e.get("weight_bucket") != weight:
            continue
        filtered.append(e)

    filtered.sort(key=lambda x: x.get("name",""))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_slice = filtered[start:end]

    # dettagli completi SOLO per quelli in pagina
    items = []
    for e in page_slice:
        d = get_equipment_detail(e["index"])
        items.append(({"index": e["index"], "name": e["name"], "url": f"/api/2014/equipment/{e['index']}"}, d))

    return render_template(
        "oggetti.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        q=q,
        category=category,
        cost=cost,
        weight=weight,
        category_options=category_options
    )
@app.route("/oggetti/<index>")
def oggetto(index):
    d = get_equipment_detail(index)
    if not d:
        abort(404)

    if d.get("image"):
        d["image_full"] = API_BASE + d["image"]

    return render_template("oggetto.html", item=d)

# -------- SPELLS ROUTES --------
@app.route("/incantesimi")
def incantesimi():
    q = request.args.get("q", "", type=str).strip().lower()
    level = request.args.get("level", "", type=str).strip()
    school = request.args.get("school", "", type=str).strip()
    ritual = request.args.get("ritual", "", type=str).strip()  # yes/no/""
    conc = request.args.get("concentration", "", type=str).strip()  # yes/no/""
    comp = request.args.get("comp", "", type=str).strip().upper()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    # Indice locale (veloce)
    idx = load_spell_index()

    if not idx:
        return render_template("index_missing.html")
    spells = list(idx.values())  # lista di dict

    # Filtri in RAM (istantanei)
    filtered = []
    for s in spells:
        if q and q not in s["name"].lower():
            continue
        if level != "" and str(s.get("level")) != level:
            continue
        if school and s.get("school") != school:
            continue
        if ritual == "yes" and not s.get("ritual"):
            continue
        if ritual == "no" and s.get("ritual"):
            continue
        if conc == "yes" and not s.get("concentration"):
            continue
        if conc == "no" and s.get("concentration"):
            continue
        if comp and comp not in set(s.get("components") or []):
            continue
        filtered.append(s)

    # Ordina (opzionale ma utile)
    filtered.sort(key=lambda x: (x.get("level", 99), x.get("name", "")))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_slice = filtered[start:end]

    # Dettagli completi SOLO per quelli in pagina (se vuoi mostrarli in card)
    items = []
    for s in page_slice:
        d = get_spell_detail(s["index"])
        items.append(({"index": s["index"], "name": s["name"], "url": f"/api/2014/spells/{s['index']}"}, d))

    level_options = ["0","1","2","3","4","5","6","7","8","9"]
    school_options = ["Abjuration","Conjuration","Divination","Enchantment","Evocation","Illusion","Necromancy","Transmutation"]
    comp_options = ["V","S","M"]

    return render_template(
        "incantesimi.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        q=q,
        level=level,
        school=school,
        ritual=ritual,
        concentration=conc,
        comp=comp,
        level_options=level_options,
        school_options=school_options,
        comp_options=comp_options
    )
@app.route("/incantesimi/<index>")
def incantesimo(index):
    d = get_spell_detail(index)
    if not d:
        abort(404)
    return render_template("incantesimo.html", spell=d)

# -------- NEW_5E ROUTE --------

@app.route("/new_5e")
def new_5e():
    return render_template("new_5e.html")

if __name__ == "__main__":
    app.run(debug=True)