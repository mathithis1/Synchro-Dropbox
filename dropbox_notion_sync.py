#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║         DROPBOX → NOTION  —  Synchronisation                    ║
║                                                                  ║
║  Scanne  /2 - Résidences  et maintient dans Notion :            ║
║                                                                  ║
║  📄 Fichiers  — 1 ligne par fichier                             ║
║                   Propriétés : Nom (titre)                       ║
║                                Date (date — extraite du nom)     ║
║                                Pôle (relation — 1er niveau)     ║
║                                Société (relation — 2e niveau)    ║
║                                                                  ║
║  📁 Dossiers  — 1 ligne par sous-dossier                        ║
║                   Propriétés : Nom (titre)                       ║
║                                Dossier Dropbox (url)             ║
║                                Date (date)                       ║
║                                Fichiers liés (relation→Fichiers) ║
║                                                                  ║
║  Idempotent : n'ajoute que ce qui manque, ne supprime rien.     ║
╚══════════════════════════════════════════════════════════════════╝

UTILISATION : python dropbox_notion_sync.py
PRÉREQUIS   : Python 3.6+, aucun paquet externe
"""

import urllib.request
import urllib.error
import json
import os
import re
import sys
import time
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════
#  CONFIGURATION  ← seule section à modifier
# ═══════════════════════════════════════════════════════════════════

DROPBOX_TOKEN         = "sl.u.AGes6xtJ2tobZgH9WtQDRZ90BkEvUhzx-GrBPim269JdaM3zhVoX4sZJKPXsGC1Tz1JZpWgqLH_AOtWCKbaqN7xnFerQctmMntKHn96Y2IQ0MkCEOYejuBcBozhUz5cF7XPKfk_KcGh8Xku1BXGTppuyvXyuLZVZqjdXzGF9l4775kkIo6N5UwfKNOcAk5WFeyQNM9oRbvQhWsDxFSzDtWcZk7HnoaK7kID7Hel2YBcp4iFIsRmn_W28tzVuJby1n9VnISr39aJ9Th2aGUVknMnqeoPF5teJII3q6N4N48X-u2k_I495oonC8gzov17j8VR8VsFStF3eBGdTKH8JT_CIIM-3PtByQ91cKv2Pc6krWWXz7g6KKTEJl8IlVNMLgl_3whwrG2m6MnvzDczJA8iBPSX5Lnp3Q8cc2TWZZMmEvS1lDwPKvfcOxsuCweQKX4cG8u6RjBb1msZ3UetgQvuh6DuCW0tVOtGyPzecK2V7XJI8ONqbOdnQU4EHnTGOTFjgis6-rGyGO9a9C7OQG41jIMUHban1yJNIH0XKBoD3nitiYFye5N6Ov4cB9-7xkcy-CjXXkt8keuFSwQgcWsZ9FR4p23sr4CWLVw9SwNO2I5wvz3T6VKQAJEfxMYh4izKiyzladW0k_DtbyOrLoyGx-ElFRH8ARzhdlVv6mRSS0qXtrh-m1TLn2pfa2W5gLc9YLvoIzZNsOgxSkTJxJGKe9MeC2xiNl-RiYefGU8q5yaBqEKefDkoVzm32UO4AJTRptWOFQBfxBU1xy8ti0XgzdxSFxFflXOdKr6CNQnvO0rzCAG-tDRqXbYn8oX8vefu2ekqz3Yxn02A5v3FiLaJ35Iif3XCghp23VVnd_Aakz4ItN2KHzT_bSmULSaNpxT0doDkH--_i9euUIgAG0qZl8ouVBV3LrFS3IDYIjzVIwu4C5HkZf2TbnPhha3zU0tFuIfwO3z429YL0JtZojFNC-4b1e5v4YRH6_PGGOipkHeHVHGNg6KTz5qirfiB_z95LRTMBJlMJQdXKX9O2HculJtflUWvpSgbg8_-TYWvO5dF2I0VRAsLRORZzC3NBs0KWjovZTLPl7fn_GVejXSB4txTs2mgWhIsXBPGhnuK_tKl75z2WUzhDFthwG5EH1QGpZYezBCHms41QWWs1Ae358gLu7sc42xrwhadaRFruUtYhNKWQOx0S3IaaMI47b1JMszssrttzGNu5UWUiA6dOMLse2Ulcpn2pwXHRxsPalUBlZ2CWf6SN4y_qb4HcRDD54uA_ZTi4d625g402i7V7_RQZhnN4ldXjV4tBBQJ95AHDJuh-FK2EC-AVCC0EMts"

NOTION_TOKEN          = "ntn_G35911385941khauFZooRBkVfxLMl4ukoGVHvYNOAot6SS"
NOTION_PARENT_PAGE_ID = "3410d60c6d2281b89661edf0a2ff415b"

DROPBOX_ROOT_PATH     = "/1 - Travail par projet/18 - Synchro Drop/ARBO TEST"

# Nom du sous-dossier "Data Room" à l'intérieur de DROPBOX_ROOT_PATH
DATA_ROOM_NAME        = "2. Data Room Corporate"

DB_FICHIERS           = "📄 Fichiers"
DB_DOSSIERS           = "📁 Dossiers"
RELATION_PROP         = "Fichiers liés"    # colonne relation dans Dossiers (→ Fichiers)
BACK_RELATION_PROP    = "Dossier"          # colonne miroir auto-créée dans Fichiers (→ Dossiers)

POLE_PROP             = "Pôle"
SOCIETE_PROP          = "Société"

DB_SOCIETES_ID        = "3510d60c6d2281d2b5b4fd13dde67b9a"  # base Notion des sociétés

API_DELAY             = 0.35   # secondes entre appels API (évite le rate-limit)

# ═══════════════════════════════════════════════════════════════════
#  COUCHE HTTP  (stdlib uniquement)
# ═══════════════════════════════════════════════════════════════════

_DBX = {
    "Authorization": f"Bearer {DROPBOX_TOKEN}",
    "Content-Type":  "application/json",
}
_NTN = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Content-Type":   "application/json",
    "Notion-Version": "2022-06-28",
}



def _http(url, method, headers, data=None):
    """Effectue un appel HTTP JSON. Retourne (dict|None, status_code)."""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"  ⚠️  HTTP {e.code} [{method} {url.split('/')[-1]}] : {msg[:300]}")
        return None, e.code
    except Exception as e:
        print(f"  ⚠️  Erreur réseau : {e}")
        return None, 0


# ═══════════════════════════════════════════════════════════════════
#  API DROPBOX
# ═══════════════════════════════════════════════════════════════════

def dbx_list(path):
    """Liste les entrées directes d'un dossier Dropbox (non récursif)."""
    r, _ = _http(
        "https://api.dropboxapi.com/2/files/list_folder", "POST", _DBX,
        {"path": path, "recursive": False, "include_deleted": False},
    )
    if not r:
        return []
    entries = list(r.get("entries", []))
    while r.get("has_more"):
        r, _ = _http(
            "https://api.dropboxapi.com/2/files/list_folder/continue",
            "POST", _DBX, {"cursor": r["cursor"]},
        )
        if r:
            entries.extend(r.get("entries", []))
    return entries


def dbx_get_shared_link(path):
    """
    Retourne l'URL de partage Dropbox d'un fichier ou dossier —
    équivalent du "Obtenir le lien Dropbox" du clic droit.

    Stratégie :
      1. Cherche un lien existant via sharing/list_shared_links
         (ne nécessite que sharing.read)
      2. Si aucun lien, en crée un via create_shared_link_with_settings
         sans restriction de visibilité (utilise le défaut du compte)
      3. Si erreur 409 "lien déjà existant", récupère l'URL dans la réponse
    """
    # ── 1. Lien existant ? ────────────────────────────────────────
    r, _ = _http(
        "https://api.dropboxapi.com/2/sharing/list_shared_links", "POST", _DBX,
        {"path": path, "direct_only": True},
    )
    if r and r.get("links"):
        return r["links"][0].get("url")

    # ── 2. Création d'un nouveau lien (visibilité par défaut) ─────
    url  = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"
    body = json.dumps({"path": path}).encode()   # pas de "settings" → visibilité par défaut
    req  = urllib.request.Request(url, data=body, headers=_DBX, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("url")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        # ── 3. Lien déjà existant (409) ───────────────────────────
        if e.code == 409:
            try:
                err  = json.loads(raw)
                meta = (err.get("error", {})
                           .get("shared_link_already_exists", {})
                           .get("metadata", {}))
                if meta.get("url"):
                    return meta["url"]
            except Exception:
                pass
        print(f"  ⚠️  Lien Dropbox impossible pour {path!r} ({e.code}) : {raw[:200]}")
    return None


# ═══════════════════════════════════════════════════════════════════
#  UTILITAIRE : collecte récursive des dossiers Dropbox
# ═══════════════════════════════════════════════════════════════════

def _collect_dossiers(path, pole, societe, result):
    """
    Parcourt récursivement tous les sous-dossiers de `path` et les ajoute
    à `result` en conservant le Pôle et la Société d'appartenance.
    Gère donc n'importe quelle profondeur d'arborescence.
    """
    for e in dbx_list(path):
        if e.get(".tag") != "folder":
            continue
        result.append({
            "name":    e["name"],
            "path":    e["path_lower"],
            "pole":    pole,
            "societe": societe,
        })
        _collect_dossiers(e["path_lower"], pole, societe, result)


def _collect_files(path, result):
    """Collecte récursivement tous les fichiers Dropbox sous `path`."""
    for e in dbx_list(path):
        if e.get(".tag") == "file":
            result.append(e)
        elif e.get(".tag") == "folder":
            _collect_files(e["path_lower"], result)


# ═══════════════════════════════════════════════════════════════════
#  UTILITAIRE : date depuis le nom de dossier
# ═══════════════════════════════════════════════════════════════════

def parse_folder_date(name):
    """
    Extrait une date ISO depuis un nom de dossier au format "AA MM JJ …".
    Ex. "24 03 15 NOM" → "2024-03-15".  Retourne None si non reconnu.
    """
    m = re.match(r"^(\d{2})\s+(\d{2})\s+(\d{2})", name.strip())
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(2000 + yy, mm, dd).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_file_date(name):
    """
    Extrait une date ISO depuis un nom de fichier (sans extension) en testant
    plusieurs formats en début de chaîne. Retourne None si non reconnu.

    Formats supportés (en ordre de priorité) :
      YYYYMMDD        ex. "20260414_rapport"   → "2026-04-14"
      YYYY-MM-DD      ex. "2026-04-14 rapport" → "2026-04-14"
      YYYY_MM_DD      ex. "2026_04_14 rapport" → "2026-04-14"
      AA MM JJ        ex. "26 04 14 rapport"   → "2026-04-14"
    """
    s = name.strip()

    # YYYYMMDD
    m = re.match(r"^(\d{4})(\d{2})(\d{2})\b", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # YYYY-MM-DD ou YYYY_MM_DD
    m = re.match(r"^(\d{4})[-_](\d{2})[-_](\d{2})\b", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # AA MM JJ (même format que les dossiers)
    m = re.match(r"^(\d{2})\s+(\d{2})\s+(\d{2})\b", s)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(2000 + yy, mm, dd).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


# ═══════════════════════════════════════════════════════════════════
#  API NOTION — bases de données
# ═══════════════════════════════════════════════════════════════════

def ntn_search_db(name):
    """Cherche une base Notion par son titre exact. Retourne l'objet ou None."""
    r, _ = _http(
        "https://api.notion.com/v1/search", "POST", _NTN,
        {"query": name, "filter": {"value": "database", "property": "object"}, "page_size": 25},
    )
    if not r:
        return None
    for x in r.get("results", []):
        title = "".join(p.get("plain_text", "") for p in x.get("title", [])).strip()
        if title == name.strip():
            return x
    return None


def ntn_create_db_fichiers(parent_id):
    """Crée la base 📄 Fichiers avec toutes ses propriétés."""
    r, _ = _http(
        "https://api.notion.com/v1/databases", "POST", _NTN,
        {
            "parent": {"type": "page_id", "page_id": parent_id},
            "title":  [{"type": "text", "text": {"content": DB_FICHIERS}}],
            "properties": {
                "Nom":          {"title": {}},
                "Lien Dropbox": {"url":   {}},
                "Date":         {"date":  {}},
                POLE_PROP:      {"select": {}},
                SOCIETE_PROP: {
                    "relation": {
                        "database_id":     DB_SOCIETES_ID,
                        "type":            "single_property",
                        "single_property": {},
                    }
                },
            },
        },
    )
    if r and r.get("id"):
        print(f"  ✅ Base créée : {DB_FICHIERS}  (id: {r['id']})")
        return r["id"]
    return None


def ntn_create_db_dossiers(parent_id, fic_id):
    """Crée la base 📁 Dossiers avec toutes ses propriétés."""
    r, _ = _http(
        "https://api.notion.com/v1/databases", "POST", _NTN,
        {
            "parent": {"type": "page_id", "page_id": parent_id},
            "title":  [{"type": "text", "text": {"content": DB_DOSSIERS}}],
            "properties": {
                "Nom":             {"title": {}},
                "Date":            {"date":  {}},
                "Dossier Dropbox": {"url":   {}},
                RELATION_PROP: {
                    "relation": {
                        "database_id":   fic_id,
                        "type":          "dual_property",
                        "dual_property": {
                            "synced_property_name": BACK_RELATION_PROP,
                        },
                    }
                },
            },
        },
    )
    if r and r.get("id"):
        print(f"  ✅ Base créée : {DB_DOSSIERS}  (id: {r['id']})")
        return r["id"]
    return None


def ntn_ensure_dossiers_properties(dos_id, fic_id):
    """
    Si la base Dossiers existait déjà, vérifie qu'elle possède bien
    toutes les propriétés attendues et les ajoute si nécessaire.
    """
    r, _ = _http(f"https://api.notion.com/v1/databases/{dos_id}", "GET", _NTN)
    if not r:
        return
    props  = r.get("properties", {})
    to_add = {}

    rel_def = {
        "relation": {
            "database_id":   fic_id,
            "type":          "dual_property",
            "dual_property": {"synced_property_name": BACK_RELATION_PROP},
        }
    }
    if RELATION_PROP not in props:
        # Propriété absente → on la crée en dual
        to_add[RELATION_PROP] = rel_def
    elif props[RELATION_PROP].get("relation", {}).get("type") == "single_property":
        # Propriété présente mais en single → on migre vers dual
        print(f"  🔄 Migration « {RELATION_PROP} » : single_property → dual_property")
        to_add[RELATION_PROP] = rel_def

    if "Date" not in props:
        to_add["Date"] = {"date": {}}
    if "Dossier Dropbox" not in props:
        to_add["Dossier Dropbox"] = {"url": {}}

    if to_add:
        print(f"  ➕ Ajout propriété(s) manquante(s) sur {DB_DOSSIERS} : {list(to_add)}")
        _http(f"https://api.notion.com/v1/databases/{dos_id}", "PATCH", _NTN,
              {"properties": to_add})
        time.sleep(API_DELAY)


def _migrate_to_relation(fic_id, props, prop_name, db_id, to_add):
    """Helper : ajoute prop_name comme relation dans to_add, en migrant depuis rich_text si besoin."""
    rel_def = {
        "relation": {
            "database_id":     db_id,
            "type":            "single_property",
            "single_property": {},
        }
    }
    if prop_name not in props:
        to_add[prop_name] = rel_def
    elif props[prop_name].get("type") == "rich_text":
        print(f"  🔄 Migration « {prop_name} » : rich_text → relation")
        _http(f"https://api.notion.com/v1/databases/{fic_id}", "PATCH", _NTN,
              {"properties": {prop_name: {"name": prop_name + " (texte)"}}})
        time.sleep(API_DELAY)
        to_add[prop_name] = rel_def


def ntn_ensure_fichiers_properties(fic_id):
    """Ajoute les propriétés manquantes à la base Fichiers (Lien Dropbox, Date, Pôle, Société)."""
    r, _ = _http(f"https://api.notion.com/v1/databases/{fic_id}", "GET", _NTN)
    if not r:
        return
    props  = r.get("properties", {})
    to_add = {}
    if "Lien Dropbox" not in props:
        to_add["Lien Dropbox"] = {"url": {}}
    if "Date" not in props:
        to_add["Date"] = {"date": {}}

    # Pôle → select (migration depuis relation ou rich_text si besoin)
    pole_type = props.get(POLE_PROP, {}).get("type")
    if POLE_PROP not in props:
        to_add[POLE_PROP] = {"select": {}}
    elif pole_type in ("relation", "rich_text"):
        print(f"  🔄 Migration « {POLE_PROP} » : {pole_type} → select")
        _http(f"https://api.notion.com/v1/databases/{fic_id}", "PATCH", _NTN,
              {"properties": {POLE_PROP: {"name": POLE_PROP + f" ({pole_type})"}}})
        time.sleep(API_DELAY)
        to_add[POLE_PROP] = {"select": {}}

    _migrate_to_relation(fic_id, props, SOCIETE_PROP, DB_SOCIETES_ID, to_add)

    if to_add:
        print(f"  ➕ Ajout propriété(s) manquante(s) sur {DB_FICHIERS} : {list(to_add)}")
        _http(f"https://api.notion.com/v1/databases/{fic_id}", "PATCH", _NTN,
              {"properties": to_add})
        time.sleep(API_DELAY)


# ═══════════════════════════════════════════════════════════════════
#  API NOTION — lecture des lignes existantes
# ═══════════════════════════════════════════════════════════════════

def _ntn_query_all(db_id):
    """Pagine sur toutes les lignes d'une base Notion."""
    results, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r, _ = _http(f"https://api.notion.com/v1/databases/{db_id}/query",
                     "POST", _NTN, body)
        if not r:
            break
        results.extend(r.get("results", []))
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return results


def ntn_get_fichiers_rows(fic_id):
    """
    Retourne { nom -> {"page_id": str, "has_date": bool, "has_pole": bool, "has_societe": bool} }
    pour toutes les lignes de 📄 Fichiers.
    """
    rows = {}
    for page in _ntn_query_all(fic_id):
        props       = page.get("properties", {})
        nom         = ""
        has_date    = False
        has_pole    = False
        has_societe = False
        for pname, pval in props.items():
            if pval.get("type") == "title":
                nom = "".join(x.get("plain_text", "")
                              for x in pval.get("title", [])).strip()
            if pname == "Date" and pval.get("type") == "date":
                has_date = pval.get("date") is not None
            if pname == POLE_PROP and pval.get("type") == "select":
                has_pole = pval.get("select") is not None
            if pname == SOCIETE_PROP and pval.get("type") == "relation":
                has_societe = bool(pval.get("relation"))
        if nom:
            rows[nom] = {
                "page_id":    page["id"],
                "has_date":   has_date,
                "has_pole":   has_pole,
                "has_societe": has_societe,
            }
    return rows


_db_title_prop = {}  # cache : { db_id -> nom_de_la_propriété_titre }


def _title_prop(db_id):
    """Retourne le nom de la propriété titre d'une base (avec cache)."""
    if db_id not in _db_title_prop:
        r, _ = _http(f"https://api.notion.com/v1/databases/{db_id}", "GET", _NTN)
        _db_title_prop[db_id] = "Nom"
        if r:
            for pname, pval in r.get("properties", {}).items():
                if pval.get("type") == "title":
                    _db_title_prop[db_id] = pname
                    break
        time.sleep(API_DELAY)
    return _db_title_prop[db_id]


def _query_name_to_id(db_id):
    """Retourne { nom_titre -> page_id } pour n'importe quelle base Notion."""
    result = {}
    for page in _ntn_query_all(db_id):
        nom = ""
        for pval in page.get("properties", {}).values():
            if pval.get("type") == "title":
                nom = "".join(x.get("plain_text", "") for x in pval.get("title", [])).strip()
        if nom:
            result[nom] = page["id"]
    return result


def ntn_ensure_ref(db_id, name, cache):
    """Retourne le page_id de `name` dans la base de référence.
    Crée automatiquement la page si elle n'existe pas encore."""
    if name in cache:
        return cache[name]
    prop = _title_prop(db_id)
    r, _ = _http(
        "https://api.notion.com/v1/pages", "POST", _NTN,
        {
            "parent":     {"database_id": db_id},
            "properties": {prop: {"title": [{"type": "text", "text": {"content": name}}]}},
        }
    )
    time.sleep(API_DELAY)
    if r and r.get("id"):
        cache[name] = r["id"]
        print(f"   ➕ Référence créée : « {name} »")
        return r["id"]
    print(f"  ⚠️  Impossible de créer la référence : « {name} »")
    return None


def ntn_get_societes_pages():
    """Retourne { nom_de_la_société -> page_id }."""
    return _query_name_to_id(DB_SOCIETES_ID)


def ntn_get_dossiers_rows(dos_id):
    """
    Retourne { nom -> {"page_id": str, "linked_ids": set[str]} }.
    linked_ids = IDs (sans tirets) des fichiers déjà reliés.
    """
    rows = {}
    for page in _ntn_query_all(dos_id):
        props  = page.get("properties", {})
        nom    = ""
        linked = set()
        for pname, pval in props.items():
            if pval.get("type") == "title":
                nom = "".join(x.get("plain_text", "")
                              for x in pval.get("title", [])).strip()
            if pname == RELATION_PROP and pval.get("type") == "relation":
                linked = {rel["id"].replace("-", "")
                          for rel in pval.get("relation", [])}
        if nom:
            rows[nom] = {"page_id": page["id"], "linked_ids": linked}
    return rows


# ═══════════════════════════════════════════════════════════════════
#  API NOTION — création / mise à jour des lignes
# ═══════════════════════════════════════════════════════════════════

def ntn_add_fichier(fic_id, nom, dropbox_url=None, date_iso=None, pole=None, societe=None):
    """Crée une ligne dans 📄 Fichiers. Retourne le page_id ou None."""
    props = {
        "Nom": {"title": [{"type": "text", "text": {"content": nom}}]},
    }
    if dropbox_url:
        props["Lien Dropbox"] = {"url": dropbox_url}
    if date_iso:
        props["Date"] = {"date": {"start": date_iso}}
    if pole:
        props[POLE_PROP]    = {"select":   {"name": pole}}
    if societe:
        props[SOCIETE_PROP] = {"relation": [{"id": societe}]}
    r, _ = _http(
        "https://api.notion.com/v1/pages", "POST", _NTN,
        {"parent": {"database_id": fic_id}, "properties": props},
    )
    return r.get("id") if r else None


def ntn_update_fichier(page_id, date_iso=None, pole=None, societe=None):
    """Met à jour les champs manquants d'une ligne existante dans 📄 Fichiers (un seul PATCH)."""
    props = {}
    if date_iso:
        props["Date"]       = {"date":     {"start": date_iso}}
    if pole:
        props[POLE_PROP]    = {"select":   {"name": pole}}
    if societe:
        props[SOCIETE_PROP] = {"relation": [{"id": societe}]}
    if not props:
        return True
    r, _ = _http(
        f"https://api.notion.com/v1/pages/{page_id}", "PATCH", _NTN,
        {"properties": props},
    )
    return r is not None


def ntn_add_dossier(dos_id, nom, file_page_ids, date_iso=None, dropbox_url=None):
    """Crée une ligne dans 📁 Dossiers. Retourne le page_id ou None."""
    props = {
        "Nom": {"title": [{"type": "text", "text": {"content": nom}}]},
    }
    if file_page_ids:
        props[RELATION_PROP] = {"relation": [{"id": fid} for fid in file_page_ids]}
    if date_iso:
        props["Date"] = {"date": {"start": date_iso}}
    if dropbox_url:
        props["Dossier Dropbox"] = {"url": dropbox_url}
    r, _ = _http(
        "https://api.notion.com/v1/pages", "POST", _NTN,
        {"parent": {"database_id": dos_id}, "properties": props},
    )
    return r.get("id") if r else None


def ntn_update_dossier_relations(dos_page_id, all_file_ids):
    """Met à jour la relation Fichiers liés d'un dossier existant."""
    r, _ = _http(
        f"https://api.notion.com/v1/pages/{dos_page_id}", "PATCH", _NTN,
        {"properties": {
            RELATION_PROP: {"relation": [{"id": fid} for fid in all_file_ids]}
        }},
    )
    return r is not None


# ═══════════════════════════════════════════════════════════════════
#  SYNCHRONISATION PRINCIPALE
# ═══════════════════════════════════════════════════════════════════

def sync():
    print()
    print("═" * 62)
    print("  🔄  Synchronisation Dropbox → Notion")
    print(f"       Racine : {DROPBOX_ROOT_PATH}")
    print("═" * 62)

    # ── 1. Navigation jusqu'aux Dossiers ─────────────────────────
    # Arborescence : ARBO TEST / Data Room / Pôle / Société / Dossier / Fichiers
    print("\n📂  Lecture de Dropbox...")

    # Data Room
    root_entries = dbx_list(DROPBOX_ROOT_PATH)
    data_room = next(
        (e for e in root_entries
         if e.get(".tag") == "folder" and e["name"] == DATA_ROOM_NAME),
        None
    )
    if not data_room:
        print(f"  ❌  Dossier « {DATA_ROOM_NAME} » introuvable dans {DROPBOX_ROOT_PATH}")
        sys.exit(1)
    data_room_path = data_room["path_lower"]

    # Collecte récursive de tous les Dossiers avec leur Pôle et Société.
    # Structure minimale attendue : DataRoom / Pôle / Société / [dossiers…]
    # Tous les sous-dossiers à n'importe quelle profondeur sont collectés.
    dossiers_found = []
    poles = [e for e in dbx_list(data_room_path) if e.get(".tag") == "folder"]
    nb_societes = 0
    for pole_entry in poles:
        pole_name = pole_entry["name"]
        societes  = [e for e in dbx_list(pole_entry["path_lower"])
                     if e.get(".tag") == "folder"]
        nb_societes += len(societes)
        for soc_entry in societes:
            soc_name = soc_entry["name"]
            _collect_dossiers(soc_entry["path_lower"], pole_name, soc_name, dossiers_found)

    print(f"   → {len(poles)} pôle(s), {nb_societes} société(s)")
    print(f"   → {len(dossiers_found)} dossier(s) à synchroniser (récursif)")

    # ── 2. Base 📄 Fichiers ───────────────────────────────────────
    print(f"\n🗄️  Base « {DB_FICHIERS} »")
    db_fic = ntn_search_db(DB_FICHIERS)
    if db_fic:
        fic_id = db_fic["id"]
        print(f"   ↩  Déjà existante  (id: {fic_id})")
        ntn_ensure_fichiers_properties(fic_id)
    else:
        fic_id = ntn_create_db_fichiers(NOTION_PARENT_PAGE_ID)
        time.sleep(API_DELAY)
        if not fic_id:
            print("   ❌  Impossible de créer la base.")
            print("       → La page Notion est-elle partagée avec l'intégration ?")
            sys.exit(1)

    # ── 3. Base 📁 Dossiers ───────────────────────────────────────
    print(f"\n🗄️  Base « {DB_DOSSIERS} »")
    db_dos = ntn_search_db(DB_DOSSIERS)
    if db_dos:
        dos_id = db_dos["id"]
        print(f"   ↩  Déjà existante  (id: {dos_id})")
        ntn_ensure_dossiers_properties(dos_id, fic_id)
    else:
        dos_id = ntn_create_db_dossiers(NOTION_PARENT_PAGE_ID, fic_id)
        time.sleep(API_DELAY)
        if not dos_id:
            print("   ❌  Impossible de créer la base.")
            sys.exit(1)

    # ── 4. Chargement des lignes existantes ───────────────────────
    print("\n📋  Chargement des lignes existantes...")
    existing_fic   = ntn_get_fichiers_rows(fic_id)   # { nom -> {page_id, has_date, has_pole, has_societe} }
    existing_dos   = ntn_get_dossiers_rows(dos_id)   # { nom -> {page_id, linked_ids} }
    societes_pages = ntn_get_societes_pages()         # { nom_société -> page_id }
    print(f"   → {len(existing_fic)} fichier(s) déjà en base")
    print(f"   → {len(existing_dos)} dossier(s) déjà en base")
    print(f"   → {len(societes_pages)} société(s) trouvée(s)")
    time.sleep(API_DELAY)

    # ── 5. PASSE 1 : alimenter 📄 Fichiers ────────────────────────
    print(f"\n📄  PASSE 1 — « {DB_FICHIERS} »...")
    folder_to_file_ids = {}   # { folder_path -> [page_id, ...] }

    for dos in dossiers_found:
        dos_path = dos["path"]
        folder_to_file_ids[dos_path] = []
        children = []
        _collect_files(dos_path, children)
        if not children:
            continue
        print(f"   🔍 {dos['name']} : {len(children)} fichier(s)")

        for e in children:
            item_name = os.path.splitext(e["name"])[0]
            item_path = e["path_lower"]

            pole_name       = dos["pole"]
            societe_name    = dos["societe"]
            societe_page_id = ntn_ensure_ref(DB_SOCIETES_ID, societe_name, societes_pages)

            if item_name in existing_fic:
                fic_info  = existing_fic[item_name]
                page_id   = fic_info["page_id"]
                folder_to_file_ids[dos_path].append(page_id)
                # Compléter les champs manquants en un seul PATCH
                upd_date    = None if fic_info["has_date"]    else parse_file_date(item_name)
                upd_pole    = None if fic_info["has_pole"]    else pole_name
                upd_societe = None if fic_info["has_societe"] else societe_page_id
                if upd_date or upd_pole or upd_societe:
                    ok = ntn_update_fichier(page_id, upd_date, upd_pole, upd_societe)
                    time.sleep(API_DELAY)
                    if ok:
                        fic_info["has_date"]    = fic_info["has_date"]    or bool(upd_date)
                        fic_info["has_pole"]    = fic_info["has_pole"]    or bool(upd_pole)
                        fic_info["has_societe"] = fic_info["has_societe"] or bool(upd_societe)
                        parts = ([f"date→{upd_date}"]    if upd_date    else []) + \
                                ([f"pôle→{pole_name}"]   if upd_pole    else []) + \
                                ([f"sté→{societe_name}"] if upd_societe else [])
                        print(f"   📅 [{dos['name']}] {item_name}  ({', '.join(parts)})")
                    else:
                        print(f"   ↩  [{dos['name']}] {item_name}")
                else:
                    print(f"   ↩  [{dos['name']}] {item_name}")
            else:
                link      = dbx_get_shared_link(item_path)
                time.sleep(API_DELAY)
                file_date = parse_file_date(item_name)
                pid       = ntn_add_fichier(fic_id, item_name, link, file_date,
                                            pole_name, societe_page_id)
                time.sleep(API_DELAY)
                if pid:
                    existing_fic[item_name] = {
                        "page_id":     pid,
                        "has_date":    bool(file_date),
                        "has_pole":    bool(pole_name),
                        "has_societe": bool(societe_page_id),
                    }
                    folder_to_file_ids[dos_path].append(pid)
                    date_str = f" [{file_date}]" if file_date else ""
                    print(f"   ➕ [{dos['name']}] {item_name}{date_str}"
                          f"  ({pole_name} / {societe_name})")

    # ── 6. PASSE 2 : alimenter 📁 Dossiers + relations ────────────
    print(f"\n📁  PASSE 2 — « {DB_DOSSIERS} »...")
    total_new         = 0
    total_rel_updated = 0

    for dos in dossiers_found:
        folder_name = dos["name"]
        dos_path    = dos["path"]
        target_ids  = set(folder_to_file_ids.get(dos_path, []))

        # On ne crée une entrée Dossier que si le dossier contient des fichiers directs.
        if not target_ids:
            continue

        target_ids_norm = {i.replace("-", "") for i in target_ids}
        date_iso        = parse_folder_date(folder_name)
        date_str        = f" [{date_iso}]" if date_iso else ""

        dropbox_url = dbx_get_shared_link(dos_path)
        time.sleep(API_DELAY)

        if folder_name in existing_dos:
            # ── Dossier existant : compléter les relations si besoin ──
            dos_info    = existing_dos[folder_name]
            dos_page_id = dos_info["page_id"]
            already     = dos_info["linked_ids"]
            missing     = target_ids_norm - already

            if missing:
                all_ids = already | target_ids_norm
                ok = ntn_update_dossier_relations(dos_page_id, list(all_ids))
                time.sleep(API_DELAY)
                status = f"+{len(missing)} lien(s)" if ok else "❌ échec"
                print(f"   🔗 {folder_name}{date_str}  ({status})")
                if ok:
                    total_rel_updated += 1
            else:
                print(f"   ↩  {folder_name}{date_str}  (à jour)")
        else:
            # ── Nouveau dossier ───────────────────────────────────────
            pid = ntn_add_dossier(
                dos_id, folder_name, list(target_ids),
                date_iso, dropbox_url,
            )
            time.sleep(API_DELAY)
            if pid:
                existing_dos[folder_name] = {
                    "page_id": pid, "linked_ids": target_ids_norm
                }
                total_new += 1
                print(f"   ➕ {folder_name}{date_str}  ({len(target_ids)} fichier(s))")

    # ── Résumé ────────────────────────────────────────────────────
    print()
    print("═" * 62)
    print("  ✅  Synchronisation terminée")
    print(f"       {total_new} nouveau(x) dossier(s) créé(s)")
    print(f"       {total_rel_updated} dossier(s) mis à jour")
    print("═" * 62)
    print()


if __name__ == "__main__":
    sync()