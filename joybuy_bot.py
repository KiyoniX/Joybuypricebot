"""Surveille le prix de produits Joybuy (France) et prévient sur Discord via webhook.

`produits.json` est la wishlist exportée : une liste de {"nom", "lien"}, avec un champ
`prix_max` facultatif (en euros) par produit. Pour chaque produit, le bot lit la page produit publique. Il y trouve le prix et la
disponibilité, déjà présents dans les données structurées (JSON-LD schema.org) de la page.
Il poste une alerte quand :
- le prix passe sous le seuil `prix_max` du produit (ou baisse encore une fois sous le seuil) ;
- le prix atteint son plus bas depuis le début du suivi ;
- le prix baisse d'au moins BAISSE_MIN_PCT % depuis le dernier passage ;
- le produit revient en stock.

Usage :
    python joybuy_bot.py --dry-run   # affiche ce qui serait posté, sans rien poster ni enregistrer
    python joybuy_bot.py             # poste sur le(s) webhook(s) et met à jour etat.json

Variables d'environnement :
    DISCORD_WEBHOOK_URL  requise (hors --dry-run) : un ou plusieurs webhooks (séparés par des espaces ou des lignes)
    JOYBUY_ETAT          optionnelle : chemin de l'historique des prix (défaut : etat.json à côté du script)
    BAISSE_MIN_PCT       optionnelle : baisse minimale (en %) qui déclenche une alerte (défaut 5)

Le prix lu est le prix affiché sur la page : il ne tient pas compte des coupons à activer.
Le bot ne visite que les pages des produits suivis, avec une pause aléatoire entre deux pages.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import evenements

PARIS = ZoneInfo("Europe/Paris")

PRODUITS_FILE = Path(__file__).with_name("produits.json")
# Sur le mini PC, l'historique vit hors du dépôt (JOYBUY_ETAT), pour qu'un `git pull` n'y touche jamais.
ETAT_FILE = Path(os.environ.get("JOYBUY_ETAT") or Path(__file__).with_name("etat.json"))
# Navigateur courant : avec un User-Agent de bot, le site répond plus souvent par un CAPTCHA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"}
PAUSE_MIN, PAUSE_MAX = 2, 5  # secondes entre deux pages produit
MAX_POINTS = 500  # points d'historique gardés par produit (seulement quand le prix ou le stock change)
DEFAULT_BAISSE_MIN_PCT = 5.0

COULEURS = {
    "seuil": 0x2ECC71,
    "plus_bas": 0xF1C40F,
    "baisse": 0x3498DB,
    "stock": 0x9B59B6,
}
TITRES = {
    "seuil": "🎯 Sous ton prix cible",
    "plus_bas": "📉 Plus bas prix depuis le début du suivi",
    "baisse": "🔻 Baisse de prix",
    "stock": "📦 De retour en stock",
}

LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
ID_RE = re.compile(r"/dp/[^/]+/(\d+)")


def product_id(url: str) -> str:
    match = ID_RE.search(url)
    if not match:
        raise ValueError(f"Lien Joybuy non reconnu (attendu …/dp/<nom>/<id>) : {url}")
    return match.group(1)


def iter_ld_nodes(node):
    """Parcourt un bloc JSON-LD (objet, liste ou @graph) et renvoie chaque objet."""
    if isinstance(node, list):
        for item in node:
            yield from iter_ld_nodes(item)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from iter_ld_nodes(node["@graph"])


class Bloque(RuntimeError):
    """Joybuy répond par un CAPTCHA : on arrête le passage au lieu d'insister."""


def parse_product(html: str) -> dict:
    """Extrait nom, prix, disponibilité et image du JSON-LD `Product` de la page."""
    for bloc in LD_JSON_RE.findall(html):
        try:
            data = json.loads(bloc)
        except json.JSONDecodeError:
            continue
        for node in iter_ld_nodes(data):
            if node.get("@type") != "Product":
                continue
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            prix = offers.get("price") or offers.get("lowPrice")
            if prix is None:
                continue
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            return {
                "nom": node.get("name"),
                "prix": round(float(prix), 2),
                "devise": offers.get("priceCurrency", "EUR"),
                "en_stock": "InStock" in str(offers.get("availability", "")),
                "image": image,
            }
    if "captcha" in html.lower():
        raise Bloque("page CAPTCHA reçue (trop de requêtes, ou IP filtrée)")
    raise RuntimeError("données produit (JSON-LD) introuvables : la structure du site a peut-être changé")


def fetch_product(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_product(resp.text)


def detect_alerts(produit: dict, releve: dict, suivi: dict, baisse_min_pct: float) -> list:
    """Compare le relevé du jour à l'historique et renvoie la liste des types d'alerte."""
    alertes = []
    prix, dernier = releve["prix"], suivi.get("dernier")
    prix_max = produit.get("prix_max")

    # Seuil : on prévient au passage sous le seuil, puis à chaque nouvelle baisse sous le seuil.
    if prix_max is not None and releve["en_stock"] and prix <= prix_max:
        deja = suivi.get("seuil_alerte")
        if deja is None or prix < deja:
            alertes.append("seuil")
            suivi["seuil_alerte"] = prix
    elif prix_max is not None and prix > prix_max:
        suivi.pop("seuil_alerte", None)  # repassé au-dessus : on pourra re-prévenir

    if dernier is None:
        return alertes  # premier relevé : pas d'historique pour comparer

    if releve["en_stock"] and not dernier["en_stock"]:
        alertes.append("stock")

    plus_bas = suivi.get("plus_bas")
    if releve["en_stock"] and plus_bas is not None and prix < plus_bas and "seuil" not in alertes:
        alertes.append("plus_bas")
    elif (
        releve["en_stock"]
        and dernier["prix"] > 0
        and (dernier["prix"] - prix) / dernier["prix"] * 100 >= baisse_min_pct
        and "seuil" not in alertes
    ):
        alertes.append("baisse")
    return alertes


def update_history(suivi: dict, releve: dict, now: str):
    dernier = suivi.get("dernier")
    if dernier is None or dernier["prix"] != releve["prix"] or dernier["en_stock"] != releve["en_stock"]:
        historique = suivi.setdefault("historique", [])
        historique.append({"date": now, "prix": releve["prix"], "en_stock": releve["en_stock"]})
        del historique[:-MAX_POINTS]
    if releve["en_stock"]:
        suivi["plus_bas"] = min(suivi.get("plus_bas", releve["prix"]), releve["prix"])
    # Pas de date ici : etat.json ne change (et n'est commité) que si un prix ou un stock change.
    suivi["dernier"] = {"prix": releve["prix"], "en_stock": releve["en_stock"]}
    suivi["nom"] = releve["nom"]


# Nombre d'unités dans le nom : « 12 x 50 cl », « 24x25cl », « x6 », « Pack de 9 », « sachet de 15 »…
UNITES_RES = [
    re.compile(r"(\d+)\s*[x×]\s*\d", re.I),
    re.compile(r"[x×]\s*(\d+)(?!\d)", re.I),
    re.compile(r"(?:pack|lot|sachet|plateau|bo[iî]te) de (\d+)", re.I),
    re.compile(r"(\d+) (?:barres|canettes|rouleaux|bouteilles)", re.I),
]


def nombre_unites(nom):
    """Devine le nombre d'unités d'un lot à partir de son nom (None si introuvable)."""
    for regex in UNITES_RES:
        match = regex.search(nom or "")
        if match and 1 < int(match.group(1)) <= 200:
            return int(match.group(1))
    return None


def fmt_prix(valeur, devise="EUR") -> str:
    symbole = "€" if devise == "EUR" else f" {devise}"
    return f"{valeur:.2f}".replace(".", ",") + symbole


PRIORITE = ["seuil", "stock", "plus_bas", "baisse"]


def prix_il_y_a(suivi: dict, jours: int, maintenant: datetime):
    """Prix affiché il y a `jours` jours, d'après l'historique. Renvoie (prix, jours réels) ou None.

    Si le suivi est plus récent que ça, renvoie le premier prix connu et son âge réel. Ça sert à repérer
    les fausses promos : un prix gonflé juste avant un événement, puis « baissé ».
    """
    historique = suivi.get("historique") or []
    if not historique:
        return None
    limite = maintenant - timedelta(days=jours)
    avant = [p for p in historique if datetime.fromisoformat(p["date"]) <= limite]
    point = avant[-1] if avant else historique[0]
    age = (maintenant - datetime.fromisoformat(point["date"])).days
    return (point["prix"], min(age, jours)) if age >= 1 else None


def footer_calendrier() -> str:
    ligne = evenements.ligne_calendrier(datetime.now(PARIS).date())
    return (ligne + "\n" if ligne else "") + "Prix affiché sur Joybuy, hors coupons. Vérifie sur le site avant d'acheter."


def build_embed(alertes: list, produit: dict, releve: dict, suivi: dict, ancien) -> dict:
    alertes = sorted(alertes, key=PRIORITE.index)
    type_alerte = alertes[0]
    devise = releve["devise"]
    champs = [{"name": "Prix", "value": f"**{fmt_prix(releve['prix'], devise)}**", "inline": True}]
    unites = nombre_unites(produit.get("nom") or releve["nom"])
    if unites:
        champs.append({"name": "À l'unité", "value": f"{fmt_prix(releve['prix'] / unites, devise)} (×{unites})", "inline": True})
    if ancien is not None and ancien != releve["prix"]:
        champs.append({"name": "Avant", "value": f"~~{fmt_prix(ancien, devise)}~~", "inline": True})
    if produit.get("prix_max") is not None:
        champs.append({"name": "Ton seuil", "value": fmt_prix(produit["prix_max"], devise), "inline": True})
    if suivi.get("plus_bas") is not None:
        champs.append({"name": "Plus bas suivi", "value": fmt_prix(suivi["plus_bas"], devise), "inline": True})
    reference = prix_il_y_a(suivi, 30, datetime.now(timezone.utc))
    if reference:
        prix_ref, age = reference
        valeur = fmt_prix(prix_ref, devise)
        if releve["prix"] >= prix_ref:
            valeur += " ⚠️ pas moins cher"  # fausse promo probable
        champs.append({"name": f"Il y a {age} j", "value": valeur, "inline": True})
    champs.append({"name": "Stock", "value": "✅ En stock" if releve["en_stock"] else "❌ Rupture", "inline": True})
    embed = {
        "author": {"name": " · ".join(TITRES[a] for a in alertes)},
        "title": (produit.get("nom") or releve["nom"] or "Produit Joybuy")[:256],
        "url": produit["url"],
        "color": COULEURS[type_alerte],
        "fields": champs,
        "footer": {"text": footer_calendrier()},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if releve.get("image"):
        embed["thumbnail"] = {"url": releve["image"]}
    return embed


def build_rappel(ev: dict, etape: str, produits: list, etat: dict) -> dict:
    """Message d'annonce d'un événement (J-7, J-1 ou le jour même)."""
    debut, fin = evenements.fmt_date(ev["debut"]), evenements.fmt_date(ev["fin"])
    periode = f"le {debut}" if ev["debut"] == ev["fin"] else f"du {debut} au {fin}"
    if etape == "debut":
        titre = f"{ev['emoji']} {ev['nom']} : c'est parti !"
        texte = f"L'événement a lieu {periode}. Le bot signale chaque baisse ; regarde le champ « Il y a 30 j » pour repérer les fausses promos."
    else:
        titre = f"{ev['emoji']} {ev['nom']} {'demain' if etape == 'J-1' else 'dans une semaine'}"
        avec_seuil = sum(1 for p in produits if p.get("prix_max") is not None)
        texte = (f"L'événement a lieu {periode}.\n"
                 f"{avec_seuil} produit(s) sur {len(produits)} ont un prix cible (`prix_max`). "
                 "C'est le moment d'en fixer dans `produits.json` pour être prévenu au bon prix.\n"
                 "Le bot garde les prix d'avant l'événement : il saura dire si une promo est réelle.")
    # Les plus fortes baisses sur 7 jours, pour voir ce qui a déjà bougé.
    maintenant, baisses = datetime.now(timezone.utc), []
    for p in produits:
        try:
            suivi = etat.get(product_id(p["url"])) or {}
        except ValueError:
            continue
        ref, dernier = prix_il_y_a(suivi, 7, maintenant), suivi.get("dernier")
        if ref and dernier and dernier["prix"] < ref[0]:
            ref30 = prix_il_y_a(suivi, 30, maintenant)
            fausse = bool(ref30 and dernier["prix"] >= ref30[0])  # gonflé puis « baissé »
            baisses.append(((ref[0] - dernier["prix"]) / ref[0] * 100, p, ref[0], dernier["prix"], fausse))
    champs = []
    if baisses:
        lignes = [f"**-{pct:.0f} %** [{(p.get('nom') or 'Produit')[:60]}]({p['url']}) : "
                  f"~~{fmt_prix(avant)}~~ → {fmt_prix(apres)}" + (" ⚠️ pas moins cher qu'il y a 30 j" if fausse else "")
                  for pct, p, avant, apres, fausse in sorted(baisses, key=lambda b: b[0], reverse=True)[:5]]
        champs.append({"name": "Plus fortes baisses sur 7 jours", "value": "\n".join(lignes)[:1024]})
    return {
        "title": titre,
        "description": texte,
        "color": 0x111111 if "black" in ev["id"] else 0xE67E22,
        "fields": champs,
        "footer": {"text": footer_calendrier()},
        "timestamp": maintenant.isoformat(),
    }


def post_everywhere(webhooks, embed: dict):
    payload = {"username": "Joybuy Bot", "embeds": [embed]}
    for i, webhook in enumerate(webhooks, 1):
        try:
            resp = requests.post(webhook, json=payload, timeout=30)
            if resp.status_code == 429:  # limite de Discord : on attend puis on réessaie une fois
                time.sleep(float(resp.json().get("retry_after", 2)))
                resp = requests.post(webhook, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"⚠️ Webhook n°{i} en erreur : {exc}", file=sys.stderr)


def parse_webhooks(var: str) -> list:
    # Un ou plusieurs webhooks, séparés par des retours à la ligne, des espaces ou des virgules.
    return [w for w in re.split(r"[\s,]+", os.environ.get(var, "")) if w]


def load_json(path: Path, defaut):
    if not path.exists():
        return defaut
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    # La console Windows n'est pas en UTF-8 par défaut : sans ça, un nom comme « Tarczyński » plante.
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="n'envoie rien et n'enregistre rien")
    args = parser.parse_args()

    webhooks = parse_webhooks("DISCORD_WEBHOOK_URL")
    if not args.dry_run and not webhooks:
        sys.exit("❌ DISCORD_WEBHOOK_URL n'est pas défini.")
    baisse_min_pct = float(os.environ.get("BAISSE_MIN_PCT") or DEFAULT_BAISSE_MIN_PCT)

    produits = load_json(PRODUITS_FILE, [])
    for produit in produits:
        produit.setdefault("url", produit.get("lien"))
    if not produits:
        sys.exit("❌ produits.json est vide : ajoute au moins un produit.")
    etat = load_json(ETAT_FILE, {})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    echecs, bloque = 0, False

    for n, produit in enumerate(produits):
        if n:
            time.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
        try:
            pid = product_id(produit["url"])
            releve = fetch_product(produit["url"])
        except Bloque as exc:
            # Insister aggraverait le blocage : on garde ce qui a été lu et on réessaiera au prochain passage.
            print(f"⛔ {exc} : arrêt du passage après {n} produit(s).", file=sys.stderr)
            bloque = True
            break
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            echecs += 1
            print(f"⚠️ {produit.get('nom') or produit['url']} : {exc}", file=sys.stderr)
            continue

        suivi = etat.setdefault(pid, {})
        ancien = (suivi.get("dernier") or {}).get("prix")
        alertes = detect_alerts(produit, releve, suivi, baisse_min_pct)
        update_history(suivi, releve, now)

        etat_txt = "en stock" if releve["en_stock"] else "rupture"
        print(f"• {releve['nom'][:60]} : {fmt_prix(releve['prix'], releve['devise'])} ({etat_txt})"
              + (f" → alertes : {', '.join(alertes)}" if alertes else ""))
        if alertes:  # un seul message par produit, même si plusieurs alertes tombent ensemble
            embed = build_embed(alertes, produit, releve, suivi, ancien)
            if args.dry_run:
                print(f"  [dry-run] posterait : {embed['author']['name']}")
            else:
                post_everywhere(webhooks, embed)

    # Annonce des grands événements de remises (J-7, J-1, jour J), une seule fois chacune.
    deja = etat.setdefault("_rappels", [])
    rappel = evenements.rappel_a_poster(datetime.now(PARIS).date(), deja)
    print(f"📅 {evenements.ligne_calendrier(datetime.now(PARIS).date())}")
    if rappel:
        ev, etape, cles = rappel
        embed = build_rappel(ev, etape, produits, etat)
        if args.dry_run:
            print(f"  [dry-run] posterait l'annonce : {embed['title']}")
        else:
            post_everywhere(webhooks, embed)
        deja.extend(c for c in cles if c not in deja)
        del deja[:-50]

    if not args.dry_run:
        save_json(ETAT_FILE, etat)
    if bloque:
        sys.exit("❌ Bloqué par un CAPTCHA de Joybuy (le workflow passe en rouge pour te prévenir).")
    if echecs == len(produits):
        sys.exit("❌ Aucun produit n'a pu être lu.")


if __name__ == "__main__":
    main()
