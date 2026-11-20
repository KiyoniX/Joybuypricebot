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

Il tourne gratuitement sur GitHub Actions. Il ne se connecte jamais au compte du BDE.

> ⚠️ Le prix lu est le **prix affiché** sur la page : les coupons à activer et les réductions au panier ne sont pas comptés. Vérifie toujours sur le site avant d'acheter.

---

## Mettre à jour la liste des produits

`produits.json` est l'export de la wishlist : une liste de `{"nom", "lien"}`. Quand la wishlist change, remplace le fichier par le nouvel export, directement sur GitHub (crayon ✏️ → coller → *Commit changes*).

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

## Installation

### 1. Créer le webhook Discord
Clic droit sur le salon → **Modifier le salon** → **Intégrations → Webhooks → Nouveau webhook** → **Copier l'URL du webhook**.

> ⚠️ Garde cette URL secrète : n'importe qui la connaissant peut poster dans ton salon.

### 2. Mettre le projet sur GitHub
Crée un dépôt et pousse ce dossier dessus.

**Dépôt public ou privé ?**
- **Public** : les minutes de GitHub Actions sont illimitées. Seuls la liste des produits et l'historique des prix sont visibles, et ce sont des infos publiques.
- **Privé** : 2 000 minutes gratuites par mois. Un passage dure environ 2 à 3 minutes, et GitHub arrondit chaque passage à la minute supérieure. Un passage toutes les 2 heures fait donc environ 1 000 minutes par mois : ça passe.

### 3. Ajouter le webhook en secret
**Settings → Secrets and variables → Actions → New repository secret** : nom `DISCORD_WEBHOOK_URL`, valeur l'URL du webhook. Pour poster dans plusieurs salons, mets plusieurs URL dans ce même secret, **une par ligne**.

### 4. Autoriser le bot à enregistrer l'historique
Le bot garde les prix vus dans `etat.json` et le commite lui-même, seulement quand un prix ou un stock change.
**Settings → Actions → General → Workflow permissions → Read and write permissions → Save.**

### 5. Tester
**Actions → Joybuy -> Discord → Run workflow.**

Le premier passage enregistre seulement les prix actuels. Il ne poste rien, sauf pour un produit déjà sous son `prix_max`. Les alertes de baisse arrivent à partir des passages suivants.

---

## Réglages (optionnel)

Dans **Settings → Secrets and variables → Actions → onglet Variables** :
- `BAISSE_MIN_PCT` : la baisse minimale qui déclenche une alerte, en % (5 par défaut).

## Dépannage

| Problème | Solution |
|---|---|
| ❌ `DISCORD_WEBHOOK_URL n'est pas défini` | Le secret manque ou est mal nommé (étape 3). |
| ❌ Erreur au `git push` | Les permissions ne sont pas en lecture et écriture (étape 4). |
| ⛔ `Bloqué par un CAPTCHA` | Joybuy a jugé qu'il y avait trop de requêtes. Le bot s'arrête aussitôt (le workflow passe en rouge) et réessaie au passage suivant. Le blocage se lève tout seul au bout d'un moment. **Ne relance pas le workflow en boucle** : c'est ce qui le déclenche (vu en test, après environ 200 pages en 30 minutes). Si ça arrive à chaque passage, espace les passages dans `.github/workflows/joybuy.yml`. |
| ⚠️ `données produit (JSON-LD) introuvables` | Joybuy a changé la structure de ses pages, ou le produit n'existe plus. |
| Le bot ne tourne plus tout seul | GitHub met en pause les workflows programmés après 60 jours sans activité sur le dépôt. Réactive-le dans l'onglet Actions. |

## Lancer en local

```powershell
pip install -r requirements.txt
python joybuy_bot.py --dry-run     # affiche les prix et les alertes, sans rien poster ni enregistrer
$env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python joybuy_bot.py
```

---

Projet du BDE, non affilié à Joybuy. Le bot ne lit que des pages publiques, au rythme d'une page toutes les 2 à 5 secondes, toutes les 2 heures, et s'arrête dès que Joybuy répond par un CAPTCHA.
