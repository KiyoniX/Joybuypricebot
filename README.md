# Joybuy → Discord

Bot qui surveille les prix des produits de la wishlist Joybuy du BDE et prévient un salon Discord quand ça vaut le coup d'acheter.

Toutes les 2 heures, il lit la page publique de chaque produit de `produits.json`. Le prix et le stock sont dans les données structurées de la page, donc pas besoin de compte. Il poste un message quand :

| Alerte | Quand |
|---|---|
| 🎯 Sous ton prix cible | Le prix passe sous le `prix_max` du produit, puis à chaque nouvelle baisse sous ce seuil |
| 📉 Plus bas prix | Le prix est le plus bas vu depuis le début du suivi |
| 🔻 Baisse de prix | Le prix baisse d'au moins 5 % depuis le passage précédent |
| 📦 De retour en stock | Le produit était en rupture et revient |

Chaque message donne le prix, l'ancien prix, le **prix à l'unité** (canette, barre…), le plus bas vu, ton seuil et le stock. Si plusieurs alertes tombent en même temps pour un produit, le bot poste un seul message.

Le champ **« Il y a 30 j »** montre le prix d'il y a 30 jours. Le bot ajoute ⚠️ si le prix « en promo » n'est pas plus bas que ça : c'est le signe d'une fausse promo, avec un prix gonflé juste avant l'événement.

## Grands événements de remises

Le bas de chaque message affiche l'événement en cours et le **prochain, avec un compte à rebours**. Exemple : `🖤 Prochain : Black Friday → Cyber Monday le 27/11/2026 (dans 7 j)`.

Le bot poste aussi une annonce **une semaine avant**, **la veille** et **le jour même** de chaque événement. Chaque annonce donne le nombre de produits qui ont un prix cible et les plus fortes baisses des 7 derniers jours.

| Événement | Date (calculée chaque année, rien à mettre à jour) |
|---|---|
| ❄️ Soldes d'hiver | 2e mercredi de janvier, ou le 1er si le 2e tombe après le 12, pendant 4 semaines |
| 🧧 618 | 18 juin : grande fête de JD.com, la maison mère de Joybuy |
| ☀️ Soldes d'été | Dernier mercredi de juin, ou l'avant-dernier s'il tombe après le 28, pendant 4 semaines |
| 🛒 11.11 | 11 novembre (Singles' Day, l'autre grande fête de JD.com) |
| 🖤 Black Friday → Cyber Monday | Le lendemain du 4e jeudi de novembre, pendant 4 jours |

Joybuy ne fait peut-être pas le 618 ni le 11.11 en Europe : à vérifier la première année.

Pour les événements sans date fixe (French Days, campagnes Joybuy…), crée un fichier `evenements.json` :

```json
[{"nom": "French Days", "emoji": "🇫🇷", "debut": "2027-04-28", "fin": "2027-05-04"}]
```

Il tourne sur un mini PC à la maison, avec une tâche cron. Il ne se connecte jamais au compte du BDE.

> ⚠️ Le prix lu est le **prix affiché** sur la page : les coupons à activer et les réductions au panier ne sont pas comptés. Vérifie toujours sur le site avant d'acheter.

---

## Mettre à jour la liste des produits

`produits.json` est l'export de la wishlist : une liste de `{"nom", "lien"}`. Quand la wishlist change, remplace le fichier par le nouvel export, directement sur GitHub (crayon ✏️ → coller → *Commit changes*). **Le mini PC récupère la nouvelle liste tout seul au passage suivant** (`git pull` au début de chaque passage).

Pour fixer un prix cible, ajoute `prix_max` (en euros) au produit :

```json
{
  "nom": "MONSTER ENERGY Juiced Bad Apple 12x50cl",
  "lien": "https://www.joybuy.fr/dp/.../102...",
  "prix_max": 10.5
}
```

Sans `prix_max`, le produit est quand même suivi pour les plus bas prix, les baisses et les retours en stock.

---

## Pourquoi pas GitHub Actions ?

Joybuy répond par un CAPTCHA aux serveurs de GitHub dès la première page : ce sont des IP de datacenter, que le site filtre (vu le 20/11/2026). Le bot tourne donc sur une machine avec une connexion « maison ». Le workflow GitHub n'a plus de passage automatique ; il reste lançable à la main, mais il sera bloqué.

## Installation sur le mini PC (Linux, sans sudo)

Il faut `git` et `python3-venv` (sinon, une fois : `sudo apt install git python3-venv`).

```sh
git clone https://github.com/KiyoniX/Joybuypricebot.git ~/Joybuypricebot
sh ~/Joybuypricebot/installer.sh
nano ~/.config/joybuy-bot/env                       # colle l'URL du webhook après DISCORD_WEBHOOK_URL=
~/Joybuypricebot/lancer.sh --maintenant             # premier passage, tout de suite
tail -n 50 ~/.local/share/joybuy-bot/joybuy.log     # ce qu'il a fait
```

`installer.sh` :
- crée l'environnement Python (`.venv`) ;
- crée `~/.config/joybuy-bot/env`, lisible par toi seul, pour le webhook ;
- reprend l'historique du dépôt la première fois ;
- ajoute la tâche cron : un passage **toutes les 2 heures**, avec un délai aléatoire de 0 à 10 minutes.

Tu peux le relancer sans risque.

| Où | Quoi |
|---|---|
| `~/.config/joybuy-bot/env` | Le webhook (jamais dans le dépôt) et `BAISSE_MIN_PCT` |
| `~/.local/share/joybuy-bot/etat.json` | L'historique des prix et les annonces déjà postées |
| `~/.local/share/joybuy-bot/joybuy.log` | Le journal des passages (2 000 dernières lignes) |

Le premier passage enregistre seulement les prix actuels. Il ne poste rien, sauf pour un produit déjà sous son `prix_max`. Les alertes de baisse arrivent à partir des passages suivants.

**Webhook Discord** : clic droit sur le salon → **Modifier le salon** → **Intégrations → Webhooks → Nouveau webhook** → **Copier l'URL du webhook**. Garde cette URL secrète : n'importe qui la connaissant peut poster dans ton salon. Pour poster dans plusieurs salons, mets plusieurs URL séparées par des espaces.

## Dépannage

| Problème | Solution |
|---|---|
| ❌ `DISCORD_WEBHOOK_URL n'est pas défini` | La ligne est vide dans `~/.config/joybuy-bot/env`. |
| ⛔ `Bloqué par un CAPTCHA` | Joybuy a jugé qu'il y avait trop de requêtes depuis ta connexion. Le bot s'arrête aussitôt et réessaie au passage suivant ; le blocage se lève tout seul au bout de quelques heures. **Ne relance pas le bot en boucle pour tester** : c'est ce qui le déclenche (vu en test, après environ 200 pages en 30 minutes). Pour naviguer sur Joybuy pendant ce temps, réponds simplement au CAPTCHA dans ton navigateur. |
| ⚠️ `données produit (JSON-LD) introuvables` | Joybuy a changé la structure de ses pages, ou le produit n'existe plus. |
| Rien dans le journal | Vérifie la tâche avec `crontab -l` (ligne `# joybuy-bot`). |

## Lancer sur ton PC (test)

```powershell
pip install -r requirements.txt
python joybuy_bot.py --dry-run     # affiche les prix et les alertes, sans rien poster ni enregistrer
```

---

Projet du BDE, non affilié à Joybuy. Le bot ne lit que des pages publiques, au rythme d'une page toutes les 2 à 5 secondes, toutes les 2 heures, et s'arrête dès que Joybuy répond par un CAPTCHA.
