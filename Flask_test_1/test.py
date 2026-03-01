from flask import Flask, render_template, request, abort, url_for
import requests
from functools import lru_cache
from math import ceil

app = Flask(__name__)

API_BASE = "https://www.dnd5eapi.co"
API_V1 = f"{API_BASE}/api/2014"

# ---------- Helpers ----------
def api_get(path: str):
    """GET JSON from dnd5eapi with basic error handling."""
    url = f"{API_BASE}{path}" if path.startswith("/api/") else f"{API_V1}/{path.lstrip('/')}"
    r = requests.get(url, timeout=15)
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

    base_list = get_monsters_list()

    # 1) filtro veloce per nome (non richiede dettagli)
    candidates = []
    for m in base_list:
        if q and q not in m["name"].lower():
            continue
        candidates.append(m)

    # 2) se richiedi filtri che necessitano dettagli, li carichiamo server-side
    need_details = bool(f_type or f_size or f_cr)
    detailed = []

    if need_details:
        target_cr = parse_cr(f_cr) if f_cr else None
        for m in candidates:
            d = get_monster_detail(m["index"])
            if not d:
                continue
            if f_type and (d.get("type", "").lower() != f_type):
                continue
            if f_size and (d.get("size", "") != f_size):
                continue
            if target_cr is not None:
                d_cr = parse_cr(str(d.get("challenge_rating", "")))
                if d_cr is None or d_cr != target_cr:
                    continue
            detailed.append((m, d))
    else:
        # senza filtri "pesanti" mostriamo solo base list
        detailed = [(m, None) for m in candidates]

    total = len(detailed)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_items = detailed[start:end]

    # Opzioni filtri (per select): per tenerle semplici senza scaricare TUTTI i dettagli,
    # usiamo liste "manuali" standard D&D. In alternativa si possono derivare con un preload.
    type_options = [
        "aberration", "beast", "celestial", "construct", "dragon", "elemental",
        "fey", "fiend", "giant", "humanoid", "monstrosity", "ooze", "plant", "undead"
    ]
    size_options = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]
    cr_options = ["0","1/8","1/4","1/2","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25","26","27","28","29","30"]

    return render_template(
        "mostri.html",
        items=page_items,  # list of (base, detail_or_none)
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
    # filtri da querystring
    q = request.args.get("q", "", type=str).strip().lower()
    category = request.args.get("category", "", type=str).strip()
    cost = request.args.get("cost", "", type=str).strip()      # low/medium/high
    weight = request.args.get("weight", "", type=str).strip()  # light/heavy
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    base_list = get_equipment_list()

    # Nota: per categoria/costo/peso servono dettagli, quindi:
    need_details = bool(category or cost or weight)

    # 1) filtro veloce per nome sulla lista base
    candidates = []
    for it in base_list:
        if q and q not in it["name"].lower():
            continue
        candidates.append(it)

    # 2) se servono dettagli, li carichiamo per filtrare
    filtered = []
    category_options = set()

    if need_details:
        # carichiamo dettagli almeno per:
        # - filtrare per category/cost/weight
        # - costruire elenco categorie (come faceva JS)
        for it in candidates:
            d = get_equipment_detail(it["index"])
            if not d:
                continue

            cat_name = (d.get("equipment_category") or {}).get("name")
            if cat_name:
                category_options.add(cat_name)

            if category and cat_name != category:
                continue

            if cost:
                if cost_bucket(d.get("cost")) != cost:
                    continue

            if weight:
                if weight_bucket(d.get("weight")) != weight:
                    continue

            filtered.append((it, d))
    else:
        # Se non servissero dettagli, potresti fare:
        filtered = [(it, None) for it in candidates]

    category_options = sorted(category_options)

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    return render_template(
        "oggetti.html",
        items=page_items,  # list of (base, detail)
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

@app.route("/incantesimi")
def incantesimi():
    # querystring
    q = request.args.get("q", "", type=str).strip().lower()
    level = request.args.get("level", "", type=str).strip()   # "0".."9"
    school = request.args.get("school", "", type=str).strip() # es. "Evocation"
    ritual = request.args.get("ritual", "", type=str).strip() # "yes"/"no"/""
    conc = request.args.get("concentration", "", type=str).strip() # "yes"/"no"/""
    comp = request.args.get("comp", "", type=str).strip().upper()  # V/S/M oppure ""

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    base_list = get_spells_list()

    # filtro veloce per nome
    candidates = []
    for s in base_list:
        if q and q not in s["name"].lower():
            continue
        candidates.append(s)

    need_details = bool(level or school or ritual or conc or comp)

    # Opzioni filtri (lista “manuale” per non fare preload pesante)
    level_options = ["0","1","2","3","4","5","6","7","8","9"]
    school_options = ["Abjuration","Conjuration","Divination","Enchantment","Evocation","Illusion","Necromancy","Transmutation"]
    comp_options = ["V","S","M"]

    if not need_details:
        # ✅ veloce: pagini prima, poi dettagli solo per la pagina
        total = len(candidates)
        total_pages = max(1, ceil(total / per_page))
        page = max(1, min(page, total_pages))

        start = (page - 1) * per_page
        end = start + per_page
        page_candidates = candidates[start:end]

        items = []
        for s in page_candidates:
            d = get_spell_detail(s["index"])  # opzionale, per mostrare level/school in card
            items.append((s, d))

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

    # ✅ filtri pesanti: serve dettaglio per filtrare
    filtered = []
    for s in candidates:
        d = get_spell_detail(s["index"])
        if not d:
            continue

        # level
        if level != "" and str(d.get("level")) != level:
            continue

        # school
        sch = (d.get("school") or {}).get("name")
        if school and sch != school:
            continue

        # ritual
        if ritual == "yes" and not d.get("ritual"):
            continue
        if ritual == "no" and d.get("ritual"):
            continue

        # concentration
        if conc == "yes" and not d.get("concentration"):
            continue
        if conc == "no" and d.get("concentration"):
            continue

        # components
        if comp:
            comps = normalize_components(d.get("components"))
            if comp not in comps:
                continue

        filtered.append((s, d))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    return render_template(
        "incantesimi.html",
        items=page_items,
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

@app.route("/new_5e")
def new_5e():
    return render_template("new_5e.html")

if __name__ == "__main__":
    app.run(debug=True)