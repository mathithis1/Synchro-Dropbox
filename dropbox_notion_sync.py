#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║         DROPBOX → NOTION  —  Synchronisation                    ║
║                                                                  ║
║  Scanne  /2 - Résidences  et maintient dans Notion :            ║
║                                                                  ║
║  📄 Fichiers  — 1 ligne par fichier                             ║
║                   Propriétés : Nom (titre)                       ║
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

DROPBOX_TOKEN         = "sl.u.AGcylVKRBg2WAXZla_MYs37HmePM2-w3oxKhgV7ZV78eDkIwNYpwnVsMqDozLCishZHPjL2aqj2tg8EHHv-h6e_2G_MmEm8yFQLVfqa5Vc0Ov7KMB53zUChYHDcfwhKnwXp3d4Z2UTMSM9ENIv6yABfHpRb17dN34anQpK4Hyik8nmyDSr3uz9O68kjgj0eR_j-yLm__aea46OENmTRIvq9PFuVuZqOaL5H_qJ8WZEBK2BKE3W2pPIb9zZqoHJgicesihREhRS-UmMqaDj9maM_M0uLAjZ752jT0sfw6iHIQeTwh_CsDr1sz2eo07MpDzOK3-x9FYcCJkD-oDVaCXDTGI2r-9pwRuGRKCqdAHzgrzHBX__YFMWDxIA3mUrTJECvXPJy5E_R4fYAwuyuyDQ2gywi4OwhtZCtrTcUPTiywTViRjYK4ch2s8XYp8AfazTg5jQMPqxuLbpDWbqnRWNk0GTWzwpwr6G6LOD3RkKKT3eoGmkhWIFBlmiuShSrJ5VOiqiDxB-amzEtTD9Sqo9X30KoB5Q2qqMLHrUx_4mAj_aFDlRkdR8JHVNxQSRP1yX8zcqfOmVExChzgYNI8kVpPa8u49KnT-y_0TueqTvgnurzJF-riVpOgeMa6ASqT2nxLuIM3iewyJl_8MazjrRmh9EywuFb7naPqOVeoWdh0cOe25QNm94YlS0CBTnwRViA-nwDy99as1uBvrLr6nD0knGVkI1akWn34mIDqWo4QoCFmh7ld0n75gc_jQHDbfhL8Ef6gjhEQ7XKN-8xWE7_tuRlQ_0TEzB-xZZsGN-Lsf5P96opQCxUWhzjpKDCTJmSiRIy0K2bSNmKmAoKQlnAYUBHeak15N1Jolk84SJcacJum_fIQBtH4sR3qH0diRRAwWog6a-8vpD1Nv8E2FgbuhyYp6BNHNzASM7ok65r3HlwrB9Fix5ik9qkrl1AmlZNyO4I5Rst1MLYaKpx9eK-wQD2OYqj6pZW8y7V0oQVSqLY3uGRfjboXSc3PT95TTunr0eatO01bNPre0h3GLQQqurwAidLVi-tQZIg7aQGxPvEXsuFvlPvVH0lLqQMsUon9MnGSTMLT2L9qSqhA_n2TiJ8gSQ9vBIAJaTW7KgwiX0gGWDDlsyRFeAVwPhBxXOUSlXZzQ5qyM7BTjv_pXZeXUY0t7h6QoblC4Kan-xDRrErrxAJP4MHx9Bd0PZa6wGLPRSfZPOJjAONq2pzWD-gEJkIlMSMmQsvUqmfzglqw5Bv1e0KYG2Bxn7MeAljsNrEOI2AF_otDPBptETZS712YNxVir61co-TMlQ3yacmxjmdehonwY7XkKupnSkiBkws"

NOTION_TOKEN          = "ntn_G35911385941khauFZooRBkVfxLMl4ukoGVHvYNOAot6SS"
NOTION_PARENT_PAGE_ID = "3410d60c6d2281b89661edf0a2ff415b"

DROPBOX_ROOT_PATH     = "/1 - Travail par projet/18 - Synchro Drop/ARBO TEST"

# Nom du sous-dossier "Data Room" à l'intérieur de DROPBOX_ROOT_PATH
DATA_ROOM_NAME        = "2. Data Room Corporate"

DB_FICHIERS           = "📄 Fichiers"
DB_DOSSIERS           = "📁 Dossiers"
RELATION_PROP         = "Fichiers liés"    # colonne relation dans Dossiers (→ Fichiers)
BACK_RELATION_PROP    = "Dossier"          # colonne miroir auto-créée dans Fichiers (→ Dossiers)

# Propriétés texte (à convertir en relations plus tard)
POLE_PROP             = "Pôle"
SOCIETE_PROP          = "Société"

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
    """Crée la base 📄 Fichiers : Nom (titre) + Lien Dropbox (url)."""
    r, _ = _http(
        "https://api.notion.com/v1/databases", "POST", _NTN,
        {
            "parent": {"type": "page_id", "page_id": parent_id},
            "title":  [{"type": "text", "text": {"content": DB_FICHIERS}}],
            "properties": {
                "Nom":           {"title": {}},
                "Lien Dropbox":  {"url":   {}},
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


def ntn_ensure_fichiers_properties(fic_id):
    """Ajoute 'Lien Dropbox' (url) à la base Fichiers si elle en est dépourvue."""
    r, _ = _http(f"https://api.notion.com/v1/databases/{fic_id}", "GET", _NTN)
    if not r:
        return
    if "Lien Dropbox" not in r.get("properties", {}):
        print(f"  ➕ Ajout propriété « Lien Dropbox » sur {DB_FICHIERS}")
        _http(f"https://api.notion.com/v1/databases/{fic_id}", "PATCH", _NTN,
              {"properties": {"Lien Dropbox": {"url": {}}}})
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
    Retourne { nom -> page_id } pour toutes les lignes de 📄 Fichiers.
    (Le nom seul suffit comme clé — Fichiers n'a pas de champ Dossier.)
    """
    rows = {}
    for page in _ntn_query_all(fic_id):
        nom = ""
        for pval in page.get("properties", {}).values():
            if pval.get("type") == "title":
                nom = "".join(x.get("plain_text", "")
                              for x in pval.get("title", [])).strip()
        if nom:
            rows[nom] = page["id"]
    return rows


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

def ntn_add_fichier(fic_id, nom, dropbox_url=None):
    """Crée une ligne dans 📄 Fichiers. Retourne le page_id ou None."""
    props = {
        "Nom": {"title": [{"type": "text", "text": {"content": nom}}]},
    }
    if dropbox_url:
        props["Lien Dropbox"] = {"url": dropbox_url}
    r, _ = _http(
        "https://api.notion.com/v1/pages", "POST", _NTN,
        {"parent": {"database_id": fic_id}, "properties": props},
    )
    return r.get("id") if r else None


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
    existing_fic = ntn_get_fichiers_rows(fic_id)   # { nom -> page_id }
    existing_dos = ntn_get_dossiers_rows(dos_id)   # { nom -> {page_id, linked_ids} }
    print(f"   → {len(existing_fic)} fichier(s) déjà en base")
    print(f"   → {len(existing_dos)} dossier(s) déjà en base")
    time.sleep(API_DELAY)

    # ── 5. PASSE 1 : alimenter 📄 Fichiers ────────────────────────
    print(f"\n📄  PASSE 1 — « {DB_FICHIERS} »...")
    folder_to_file_ids = {}   # { folder_path -> [page_id, ...] }

    for dos in dossiers_found:
        dos_path = dos["path"]
        folder_to_file_ids[dos_path] = []
        children = dbx_list(dos_path)

        for e in children:
            if e.get(".tag") != "file":
                continue
            item_name = os.path.splitext(e["name"])[0]
            item_path = e["path_lower"]

            if item_name in existing_fic:
                folder_to_file_ids[dos_path].append(existing_fic[item_name])
                print(f"   ↩  [{dos['name']}] {item_name}")
            else:
                link = dbx_get_shared_link(item_path)
                time.sleep(API_DELAY)
                pid  = ntn_add_fichier(fic_id, item_name, link)
                time.sleep(API_DELAY)
                if pid:
                    existing_fic[item_name] = pid
                    folder_to_file_ids[dos_path].append(pid)
                    print(f"   ➕ [{dos['name']}] {item_name}")

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