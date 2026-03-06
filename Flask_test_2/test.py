# DND Player's helping wand, di Tenti Filippo e Amanzio Riccardo
#   una pagina web con informazioni basilari su DND 5E,
#   tipologie di equipaggiamento, nemici e incantesimi disponibili, con un lanciadadi incluso

# Importare tutte le librerie necessarie
# Flask per il backend della pagina web
from flask import Flask, render_template, request, abort, url_for, redirect
# Requests per compiere richieste all'API
import requests
# lru_cache per salvare i dati della sessione in cache ed evitare tempi di attesi ripetuti
from functools import lru_cache
# ceil per arrotondare per eccesso (usato nel calcolo delle pagine)
from math import ceil
# os per creare directory e i JSON file necessari allo storing dei dati
import os
import json
import re
# ThreadPoolExecutor serve per eseguire operazioni in concorrenza (parallelismo)
from concurrent.futures import ThreadPoolExecutor, as_completed
# Datetime per ottenere informazioni sulla data di oggi e altro
from datetime import datetime

# Inizializzazione della pagina flask
app = Flask(__name__)

# Definizione dell'API DND 5E
API_BASE = "https://www.dnd5eapi.co"
API_V1 = f"{API_BASE}/api/2014"

# Directory per i file JSON salvati
DATA_DIR = "data"
# --- File di index utilizzati per velocizzare l'uso dei filtri
SPELL_INDEX_FILE = os.path.join(DATA_DIR,"/indexes/spells_index.json")
MONSTER_INDEX_FILE =  os.path.join(DATA_DIR,"/indexes/monsters_index.json")
EQUIP_INDEX_FILE =  os.path.join(DATA_DIR,"/indexes/equipment_index.json")
# --- File JSON per memorizzare le informazioni prese dalle request
MONSTERS_FULL = os.path.join(DATA_DIR, "monsters_full.json")
EQUIPMENT_FULL = os.path.join(DATA_DIR, "equipment_full.json")
SPELLS_FULL = os.path.join(DATA_DIR, "spells_full.json")

# Se la directory non esiste, la crea (permette di condividere il file, etc.)
os.makedirs(DATA_DIR, exist_ok=True)
CHAR_DIR = os.path.join(DATA_DIR, "characters")
os.makedirs(CHAR_DIR, exist_ok=True)
# inizializzazione della sessione (velocizza le request e permette di conservarle)
session = requests.Session()

# -- permette la creazione sicura dei file json
def atomic_write_json(path: str, obj):
    """Scrive JSON in modo 'sicuro' (evita file rotti se interrompi la scrittura)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)

# lru_cache è un DECORATORE (modifica una funzione senza alterarne il codice interno)
# serve a memorizzare le informazioni sulla cache del browser (massimo 8 salvataggi)
# load_json_dict carica il JSON dictionary selezionato e lo salva nella RAM (caching)
@lru_cache(maxsize=8)
def load_json_dict(path: str) -> dict:
    """Carica JSON (dict) e lo cachea in RAM."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        #load trasforma il json in un oggetto python
        return json.load(f)

# siccome la cache salva l'ultimo dato memorizzato, se il JSON cambia è necessario ripulirla
def reload_json(path: str):
    """Invalida cache per ricaricare file aggiornato."""
    load_json_dict.cache_clear()

# ---------- Helpers ----------
# api_get è la funzione che costruire l'url per eseguire la request all'API, per poi creare la sessione (r)
# session è preferito in quanto riutilizza la connessione HTTP piuttosto che realizzarne una nuova
def api_get(path: str):
    """GET JSON from dnd5eapi with basic error handling."""
    url = f"{API_BASE}{path}" if path.startswith("/api/") else f"{API_V1}/{path.lstrip('/')}"
    r = session.get(url, timeout=15)
    if not r.ok:
        return None
    return r.json()

# --- EQUIPMENT (cache and helpers) ---

# funzione per ottenere la lista dell'equipaggiamento (da mettere sulla pagina)
@lru_cache(maxsize=64)
def get_equipment_list():
    """Lista base equip: [{index, name, url}, ...]"""
    data = api_get("/api/2014/equipment")
    if not data or "results" not in data:
        return []
    return data["results"]

# funzione più pesante, prende tutti i dati degli eventuali oggetti
# per questo motivo richiede più spazio sulla cache
@lru_cache(maxsize=4096)
def get_equipment_detail(index: str):
    return api_get(f"/api/2014/equipment/{index}")

# funzione per costruire un indice per filtrare gli oggetti
# fondamentale per ridurre i tempi di caricamento del filtering
#   la funzione è stata realizzata prima della creazione dei data JSON, quindi potrebbe risultare ora superflua
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

# carica l'indice dell'equipaggiamento (per eventuali filtri)
@lru_cache(maxsize=1)
def load_equipment_index():
    if not os.path.exists(EQUIP_INDEX_FILE):
        return {}
    with open(EQUIP_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# FUNZIONE ADMIN PER RICOSTRUIRE L'INDICE MANUALMENTE
@app.route("/admin/rebuild_equipment_index")
def rebuild_equipment_index():
    data = build_equipment_index()
    load_equipment_index.cache_clear()
    return f"Equipment index rebuilt: {len(data)} items"

# divisione degli oggetti in base al costo
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

# divisione degli oggetti in base al peso
def weight_bucket(weight):
    """Ritorna 'light'/'heavy' o None."""
    if weight is None:
        return None
    if weight < 5:
        return "light"
    if weight > 20:
        return "heavy"
    return None

# Costruire il file JSON per gli oggetti/equipaggiamento
def build_equipment_full():
    base = get_equipment_list()
    indices = [it["index"] for it in base]

    out = {}
    workers = 10

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_equipment_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue
            if d.get("image"):
                d["image_full"] = API_BASE + d["image"]
            out[idx] = d

    atomic_write_json(EQUIPMENT_FULL, out)
    return len(out)

# FUNZIONE ADMIN PER COSTRUIRE IL FILE EQUIPAGGIAMENTO
@app.route("/admin/build_equipment_json")
def admin_build_equipment_json():
    n = build_equipment_full()
    reload_json(EQUIPMENT_FULL)
    return f"OK - equipment_full.json built: {n}"

# --- MONSTERS (cache and helpers) ---

# prende i dettagli sui mostri (salvati in cache)
@lru_cache(maxsize=2048)
def get_monster_detail(index: str):
    return api_get(f"/api/2014/monsters/{index}")

# prende la lista sui mostri (uguale al processo degli oggetti)
@lru_cache(maxsize=64)
def get_monsters_list():
    """Returns base list: [{index,name,url}, ...]"""
    data = api_get("/api/2014/monsters")
    if not data or "results" not in data:
        return []
    return data["results"]

# costruzione dell'indice mostri
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

# caricare l'indice dei mostri
@lru_cache(maxsize=1)
def load_monster_index():
    """Carica indice da file. Se non esiste, ritorna {} (build manuale)."""
    if not os.path.exists(MONSTER_INDEX_FILE):
        return {}
    with open(MONSTER_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# FUNZIONE ADMIN PER RICOSTRUIRE L'INDICE MOSTRI
@app.route("/admin/rebuild_monsters_index")
def rebuild_monsters_index():
    data = build_monster_index()
    load_monster_index.cache_clear()
    return f"Monster index rebuilt: {len(data)} monsters"

# funzione basilare per il calcolo del bonus derivato dal punteggio totale delle abilità
def ability_mod(score: int) -> int:
    return (score - 10) // 2

# parse_cr è usata per analizzare i cr e renderli leggibili al codice (rimuovendo eventuali / e altro)
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

# -- Costruzione del file JSON per i mostri
def build_monsters_full():
    base = get_monsters_list()
    indices = [m["index"] for m in base]

    out = {}  # index -> full monster json
    workers = 10

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_monster_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue
            if d.get("image"):
                d["image_full"] = API_BASE + d["image"]
            out[idx] = d

    atomic_write_json(MONSTERS_FULL, out)
    return len(out)

# FUNZIONE MANUALE PER COSTRUIRE IL FILE JSON PER I MOSTRI
@app.route("/admin/build_monsters_json")
def admin_build_monsters_json():
    n = build_monsters_full()
    reload_json(MONSTERS_FULL)
    return f"OK - monsters_full.json built: {n}"

# -------- SPELLS (cache and helpers) --------

# creare la lista di incantesimi
@lru_cache(maxsize=64)
def get_spells_list():
    """Lista base spells: [{index,name,url}, ...]"""
    data = api_get("/api/2014/spells")
    if not data or "results" not in data:
        return []
    return data["results"]

# ottenere i dettagli sugli incantesimi
@lru_cache(maxsize=4096)
def get_spell_detail(index: str):
    return api_get(f"/api/2014/spells/{index}")

# ....SPELL_INDEX (per facilitare la ricerca)....
def build_spell_index():
    """Crea (o ricrea) un indice locale dei campi necessari ai filtri."""
    base_list = get_spells_list()
    indices = [s["index"] for s in base_list]

    index_data = {}

    # Parallelismo per velocizzare il primo build
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

# carica l'indice degli incantesimi
@lru_cache(maxsize=1)
def load_spell_index():
    """Carica indice da file. Se non esiste, lo crea."""
    if not os.path.exists(SPELL_INDEX_FILE):
        return {}
    with open(SPELL_INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# FUNZIONE ADMIN PER RICOSTRUIRE L'INDICE INCANTESIMI
@app.route("/admin/rebuild_spells_index")
def rebuild_spells_index():
    # ricrea indice e invalida cache del loader
    data = build_spell_index()
    load_spell_index.cache_clear()
    return f"Spell index rebuilt: {len(data)} spells"


# normalize è usato per trasformare la lista di componenti per incantesimi
# in un SET di elementi unici e non ordinati
def normalize_components(components):
    """components è una lista tipo ['V','S','M']"""
    if not components:
        return set()
    return set([str(c).upper().strip() for c in components])

# -- Costuire il file JSON per gli incantesimi
def build_spells_full():
    base = get_spells_list()
    indices = [s["index"] for s in base]

    out = {}
    workers = 10

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_spell_detail, idx): idx for idx in indices}
        for fut in as_completed(futs):
            idx = futs[fut]
            d = fut.result()
            if not d:
                continue
            out[idx] = d

    atomic_write_json(SPELLS_FULL, out)
    return len(out)

# FUNZIONE ADMIN PER COSTRUIRE IL JSON INCANTESIMI
@app.route("/admin/build_spells_json")
def admin_build_spells_json():
    n = build_spells_full()
    reload_json(SPELLS_FULL)
    return f"OK - spells_full.json built: {n}"


# -- COMANDO GENERALE PER COSTRUIRE TUTTI I JSON
@app.route("/admin/build_all_json")
def admin_build_all_json():
    started = datetime.now()

    n_mon = build_monsters_full()
    reload_json(MONSTERS_FULL)

    n_eq = build_equipment_full()
    reload_json(EQUIPMENT_FULL)

    n_sp = build_spells_full()
    reload_json(SPELLS_FULL)

    ended = datetime.now()
    delta = (ended - started).total_seconds()

    return (
        "OK - build_all_json completed\n"
        f"monsters: {n_mon}\n"
        f"equipment: {n_eq}\n"
        f"spells: {n_sp}\n"
        f"time_sec: {delta:.2f}\n"
    )

# -- HELPER PER LA SCHEDA PERSONAGGIO
def slugify(name: str) -> str:
    """Crea un id file-safe partendo dal nome."""
    name = (name or "").strip().lower()
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-z0-9\-]", "", name)
    return name or "senza-nome"

def char_path(char_id: str) -> str:
    return os.path.join(CHAR_DIR, f"{char_id}.json")

def save_character(character: dict) -> str:
    """Salva su file e ritorna char_id."""
    char_name = character.get("nome", "")
    char_id = slugify(char_name)
    character["id"] = char_id
    character["updated_at"] = datetime.now().isoformat(timespec="seconds")
    atomic_write_json(char_path(char_id), character)
    return char_id

def load_character(char_id: str) -> dict | None:
    p = char_path(char_id)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def list_characters() -> list[dict]:
    out = []
    for fn in os.listdir(CHAR_DIR):
        if not fn.endswith(".json"):
            continue
        char_id = fn[:-5]
        d = load_character(char_id)
        if d:
            out.append(d)
    # ordina per nome
    out.sort(key=lambda x: (x.get("nome","").lower(), x.get("updated_at","")))
    return out

def delete_character(char_id: str) -> bool:
    p = char_path(char_id)
    if not os.path.exists(p):
        return False
    os.remove(p)
    return True

# rende la funzione ability_mod utilizzabile nei templates
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

    data = load_json_dict(MONSTERS_FULL)
    if not data:
        return render_template("index_missing.html", title="Mostri", admin_url="/admin/build_monsters_json")

    monsters = list(data.values())

    filtered = []
    for m in monsters:
        name = (m.get("name") or "").lower()
        if q and q not in name:
            continue
        if f_type and (m.get("type","").lower() != f_type):
            continue
        if f_size and (m.get("size","") != f_size):
            continue
        if f_cr and str(m.get("challenge_rating","")) != f_cr:
            continue
        filtered.append(m)

    filtered.sort(key=lambda x: (parse_cr(str(x.get("challenge_rating",""))) or 99, x.get("name","")))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page

    page_items = [({"index": m["index"], "name": m["name"], "url": m.get("url","")}, m) for m in filtered[start:end]]

    type_options = ["aberration","beast","celestial","construct","dragon","elemental","fey","fiend","giant","humanoid","monstrosity","ooze","plant","undead"]
    size_options = ["Tiny","Small","Medium","Large","Huge","Gargantuan"]
    cr_options = ["0","1/8","1/4","1/2","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25","26","27","28","29","30"]

    return render_template(
        "mostri.html",
        items=page_items,
        total=total, page=page, total_pages=total_pages, per_page=per_page,
        q=q, f_type=f_type, f_size=f_size, f_cr=f_cr,
        type_options=type_options, size_options=size_options, cr_options=cr_options
    )

@app.route("/mostri/<index>")
def mostro(index):
    data = load_json_dict(MONSTERS_FULL)
    m = data.get(index)
    if not m:
        abort(404)
    return render_template("mostro.html", monster=m)
# -------- EQUIPMENT ROUTES --------

@app.route("/oggetti")
def oggetti():
    q = request.args.get("q", "", type=str).strip().lower()
    category = request.args.get("category", "", type=str).strip()
    cost = request.args.get("cost", "", type=str).strip()
    weight = request.args.get("weight", "", type=str).strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    data = load_json_dict(EQUIPMENT_FULL)
    if not data:
        return render_template("index_missing.html", title="Oggetti", admin_url="/admin/build_equipment_json")

    items_all = list(data.values())

    # categorie gratuite
    category_options = sorted({(d.get("equipment_category") or {}).get("name") for d in items_all if (d.get("equipment_category") or {}).get("name")})

    filtered = []
    for it in items_all:
        name = (it.get("name") or "").lower()
        if q and q not in name:
            continue

        cat = (it.get("equipment_category") or {}).get("name", "")
        if category and cat != category:
            continue

        if cost and cost_bucket(it.get("cost")) != cost:
            continue

        if weight and weight_bucket(it.get("weight")) != weight:
            continue

        filtered.append(it)

    filtered.sort(key=lambda x: x.get("name",""))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page

    page_items = [({"index": it["index"], "name": it["name"], "url": it.get("url","")}, it) for it in filtered[start:end]]

    return render_template(
        "oggetti.html",
        items=page_items,
        total=total, page=page, total_pages=total_pages, per_page=per_page,
        q=q, category=category, cost=cost, weight=weight,
        category_options=category_options
    )

@app.route("/oggetti/<index>")
def oggetto(index):
    data = load_json_dict(EQUIPMENT_FULL)
    it = data.get(index)
    if not it:
        abort(404)
    return render_template("oggetto.html", item=it)

# -------- SPELLS ROUTES --------
@app.route("/incantesimi")
def incantesimi():
    q = request.args.get("q", "", type=str).strip().lower()
    level = request.args.get("level", "", type=str).strip()
    school = request.args.get("school", "", type=str).strip()
    ritual = request.args.get("ritual", "", type=str).strip()
    conc = request.args.get("concentration", "", type=str).strip()
    comp = request.args.get("comp", "", type=str).strip().upper()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)

    data = load_json_dict(SPELLS_FULL)
    if not data:
        return render_template("index_missing.html", title="Incantesimi", admin_url="/admin/build_spells_json")

    spells = list(data.values())

    filtered = []
    for s in spells:
        name = (s.get("name") or "").lower()
        if q and q not in name:
            continue
        if level != "" and str(s.get("level")) != level:
            continue
        sch = (s.get("school") or {}).get("name")
        if school and sch != school:
            continue
        if ritual == "yes" and not s.get("ritual"):
            continue
        if ritual == "no" and s.get("ritual"):
            continue
        if conc == "yes" and not s.get("concentration"):
            continue
        if conc == "no" and s.get("concentration"):
            continue
        if comp:
            comps = set([c.upper() for c in (s.get("components") or [])])
            if comp not in comps:
                continue
        filtered.append(s)

    filtered.sort(key=lambda x: (x.get("level", 99), x.get("name","")))

    total = len(filtered)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page

    page_items = [({"index": sp["index"], "name": sp["name"], "url": sp.get("url","")}, sp) for sp in filtered[start:end]]

    level_options = ["0","1","2","3","4","5","6","7","8","9"]
    school_options = ["Abjuration","Conjuration","Divination","Enchantment","Evocation","Illusion","Necromancy","Transmutation"]
    comp_options = ["V","S","M"]

    return render_template(
        "incantesimi.html",
        items=page_items,
        total=total, page=page, total_pages=total_pages, per_page=per_page,
        q=q, level=level, school=school, ritual=ritual, concentration=conc, comp=comp,
        level_options=level_options, school_options=school_options, comp_options=comp_options
    )

@app.route("/incantesimi/<index>")
def incantesimo(index):
    data = load_json_dict(SPELLS_FULL)
    sp = data.get(index)
    if not sp:
        abort(404)
    return render_template("incantesimo.html", spell=sp)
# -------- NEW_5E ROUTE --------

@app.route("/new_5e")
def new_5e():
    return render_template("new_5e.html")

@app.route("/dadi")
def dadi():
    return render_template("dadi.html")

@app.route("/personaggi")
def personaggi():
    chars = list_characters()
    return render_template("personaggi.html", characters=chars)


@app.route("/personaggi/<char_id>")
def personaggio(char_id):
    d = load_character(char_id)
    if not d:
        abort(404)
    return render_template("personaggio.html", c=d)


@app.route("/personaggi/<char_id>/delete", methods=["POST"])
def personaggio_delete(char_id):
    delete_character(char_id)
    return redirect(url_for("personaggi"))


@app.route("/scheda_personaggio", methods=["GET", "POST"])
def scheda_personaggio():
    # choices per inventario (dal JSON locale)
    eq = load_json_dict(EQUIPMENT_FULL)
    if not eq:
        return render_template("index_missing.html", title="Scheda Personaggio (Oggetti)", admin_url="/admin/build_equipment_json")

    equipment_choices = sorted(
        [(v.get("index"), v.get("name")) for v in eq.values() if v.get("index") and v.get("name")],
        key=lambda x: x[1].lower()
    )

    if request.method == "GET":
        char_id = request.args.get("id", "", type=str).strip()
        c = load_character(char_id) if char_id else None
        return render_template("scheda_personaggio.html", equipment_choices=equipment_choices, c=c)

    # POST: salva
    nome = request.form.get("nome", "").strip()
    if not nome:
        abort(400, "Nome personaggio obbligatorio")

    # campi “semplici”
    classe = request.form.get("classe", "Guerriero")
    livello = int(request.form.get("livello", "1") or 1)
    hp = int(request.form.get("hp", "10") or 10)
    hit_dice = int(request.form.get("hit_dice", "1") or 1)
    descrizione = request.form.get("descrizione", "")
    storia = request.form.get("storia", "")

    # campi JSON serializzati dal JS (hidden inputs)
    stats_json = request.form.get("stats_json", "{}")
    inv_json = request.form.get("inventory_json", "[]")
    skills_json = request.form.get("skills_json", "[]")
    punti_rimanenti = int(request.form.get("punti_rimanenti", "0") or 0)

    try:
        stats = json.loads(stats_json)
        inventario = json.loads(inv_json)
        skills = json.loads(skills_json)
    except Exception:
        abort(400, "Dati JSON non validi (stats/inventario/skills)")

    character = {
        "nome": nome,
        "classe": classe,
        "livello": livello,
        "hp": hp,
        "hit_dice": hit_dice,
        "descrizione": descrizione,
        "storia": storia,
        "stats": stats,
        "punti_rimanenti": punti_rimanenti,
        "inventario": inventario,  # lista di index equipment
        "skills": skills,          # lista di dict
    }

    char_id = request.form.get("char_id", "").strip()

    character = {
        "nome": nome,
        "classe": classe,
        "livello": livello,
        "hp": hp,
        "hit_dice": hit_dice,
        "descrizione": descrizione,
        "storia": storia,
        "stats": stats,
        "punti_rimanenti": punti_rimanenti,
        "inventario": inventario,
        "skills": skills,
    }

    if char_id:
        character["id"] = char_id
        atomic_write_json(char_path(char_id), character)
    else:
        char_id = save_character(character)

    return redirect(url_for("personaggio", char_id=char_id))

if __name__ == "__main__":
    app.run(debug=True)