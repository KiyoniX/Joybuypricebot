"""Calendrier des grands événements de remises (France), calculé à partir de leurs règles.

Les dates sont calculées, donc rien à mettre à jour d'une année sur l'autre :
- Soldes d'hiver : deuxième mercredi de janvier, ou le premier mercredi si le deuxième tombe après le 12 ; 4 semaines.
- Soldes d'été : dernier mercredi de juin, ou l'avant-dernier s'il tombe après le 28 ; 4 semaines.
  (Arrêté du 27 mai 2019. Quelques départements de l'Est et d'outre-mer ont d'autres dates.)
- Black Friday : le lendemain du 4e jeudi de novembre (Thanksgiving), jusqu'au Cyber Monday.
- 11.11 (Singles' Day) et 618 : les grandes fêtes de JD.com, la maison mère de Joybuy. Joybuy n'y participe
  pas forcément en Europe : à confirmer la première année.

Pour les événements sans règle fixe (French Days, campagnes propres à Joybuy…), ajoute-les à la main
dans `evenements.json` : [{"nom": "French Days", "debut": "2027-04-28", "fin": "2027-05-04"}].
"""

import json
from datetime import date, timedelta
from pathlib import Path

MANUELS_FILE = Path(__file__).with_name("evenements.json")
MERCREDI, JEUDI = 2, 3


def _mercredis(annee: int, mois: int) -> list:
    jour = date(annee, mois, 1)
    jour += timedelta(days=(MERCREDI - jour.weekday()) % 7)
    liste = []
    while jour.month == mois:
        liste.append(jour)
        jour += timedelta(days=7)
    return liste


def soldes_hiver(annee: int) -> date:
    premier, deuxieme = _mercredis(annee, 1)[:2]
    return premier if deuxieme.day > 12 else deuxieme


def soldes_ete(annee: int) -> date:
    mercredis = _mercredis(annee, 6)
    return mercredis[-2] if mercredis[-1].day > 28 else mercredis[-1]


def black_friday(annee: int) -> date:
    jour = date(annee, 11, 1)
    jour += timedelta(days=(JEUDI - jour.weekday()) % 7)  # 1er jeudi
    return jour + timedelta(days=21 + 1)  # 4e jeudi + 1 jour


def evenements_annee(annee: int) -> list:
    hiver, ete, bf = soldes_hiver(annee), soldes_ete(annee), black_friday(annee)
    return [
        {"id": f"soldes-hiver-{annee}", "nom": "Soldes d'hiver", "emoji": "❄️",
         "debut": hiver, "fin": hiver + timedelta(days=27)},
        {"id": f"618-{annee}", "nom": "618 (fête de JD.com)", "emoji": "🧧",
         "debut": date(annee, 6, 18), "fin": date(annee, 6, 18)},
        {"id": f"soldes-ete-{annee}", "nom": "Soldes d'été", "emoji": "☀️",
         "debut": ete, "fin": ete + timedelta(days=27)},
        {"id": f"11-11-{annee}", "nom": "11.11 (Singles' Day)", "emoji": "🛒",
         "debut": date(annee, 11, 11), "fin": date(annee, 11, 11)},
        {"id": f"black-friday-{annee}", "nom": "Black Friday → Cyber Monday", "emoji": "🖤",
         "debut": bf, "fin": bf + timedelta(days=3)},
    ]


def evenements_manuels() -> list:
    if not MANUELS_FILE.exists():
        return []
    liste = []
    for ev in json.loads(MANUELS_FILE.read_text(encoding="utf-8")):
        debut = date.fromisoformat(ev["debut"])
        liste.append({
            "id": ev.get("id") or f"{ev['nom']}-{ev['debut']}".lower().replace(" ", "-"),
            "nom": ev["nom"],
            "emoji": ev.get("emoji", "🏷️"),
            "debut": debut,
            "fin": date.fromisoformat(ev.get("fin", ev["debut"])),
        })
    return liste


def tous(aujourdhui: date) -> list:
    """Événements de l'année en cours et de la suivante, triés par date de début."""
    liste = evenements_annee(aujourdhui.year) + evenements_annee(aujourdhui.year + 1) + evenements_manuels()
    return sorted(liste, key=lambda ev: ev["debut"])


def en_cours(aujourdhui: date) -> list:
    return [ev for ev in tous(aujourdhui) if ev["debut"] <= aujourdhui <= ev["fin"]]


def prochain(aujourdhui: date):
    return next((ev for ev in tous(aujourdhui) if ev["debut"] > aujourdhui), None)


def fmt_date(jour: date) -> str:
    return jour.strftime("%d/%m/%Y")


def ligne_calendrier(aujourdhui: date) -> str:
    """Une ligne pour le bas des messages : l'événement en cours, puis le prochain avec son compte à rebours."""
    morceaux = [f"{ev['emoji']} En cours : {ev['nom']} (jusqu'au {fmt_date(ev['fin'])})" for ev in en_cours(aujourdhui)]
    ev = prochain(aujourdhui)
    if ev:
        jours = (ev["debut"] - aujourdhui).days
        quand = "demain" if jours == 1 else f"dans {jours} j"
        morceaux.append(f"{ev['emoji']} Prochain : {ev['nom']} le {fmt_date(ev['debut'])} ({quand})")
    return " · ".join(morceaux)


def rappel_a_poster(aujourdhui: date, deja_postes: list):
    """Renvoie (événement, étape) à annoncer maintenant, ou None.

    Étapes : J-7, J-1, puis « debut » le jour même. On ne poste que l'étape la plus proche :
    un bot lancé à J-3 annonce J-7 (une seule fois), jamais J-7 après J-1.
    """
    candidats = en_cours(aujourdhui) + ([prochain(aujourdhui)] if prochain(aujourdhui) else [])
    for ev in candidats:
        jours = (ev["debut"] - aujourdhui).days
        if jours <= 0:
            etapes = ["debut"]
        elif jours <= 1:
            etapes = ["J-1", "J-7"]
        elif jours <= 7:
            etapes = ["J-7"]
        else:
            continue
        cle = f"{ev['id']}:{etapes[0]}"
        if cle not in deja_postes:
            # On marque aussi les étapes plus lointaines, pour ne pas les poster en retard ensuite.
            return ev, etapes[0], [f"{ev['id']}:{e}" for e in etapes]
    return None
