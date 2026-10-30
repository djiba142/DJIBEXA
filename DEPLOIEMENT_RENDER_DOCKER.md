# Déploiement DJIBEXA — Render et Docker

## État et limites

Le dépôt contient maintenant une configuration de préproduction Render et un
environnement Docker local composé de PostgreSQL, Django et TanStack Start.
La configuration Render est déclarative : aucun service n'a été créé et aucune
migration n'a été exécutée sur une base réelle.

DJIBEXA n'a pas encore passé l'audit complet d'isolation endpoint par endpoint.
Ne pas ouvrir l'inscription ni connecter une deuxième entreprise avant la
validation de toutes les API, fichiers, imports/exports, tâches différées et
relations inter-entreprises. Les services Render décrits ici nécessitent des
ressources payantes pour PostgreSQL et la conservation des fichiers.

## Préparer Render

1. Pousser la branche contenant `render.yaml`, puis créer une nouvelle Blueprint
   dans Render et sélectionner ce dépôt.
   Le frontend est un dépôt Git distinct déclaré comme sous-module : pousser
   d'abord son commit sur `djiba142/image-ad-studio`, puis le commit principal.
   Vérifier que le checkout Render initialise le sous-module avant d'utiliser
   `rootDir: frontend` ; sinon, configurer le service frontend depuis son
   dépôt dédié plutôt que de lancer un build incomplet.
2. Vérifier la région Frankfurt et les noms `nexora-api`, `nexora-web` et
   `nexora-db`. Ils doivent rester cohérents avec les hôtes et origines définis
   dans le Blueprint, ou être mis à jour ensemble.
3. Fournir les variables SMTP demandées par Render (`EMAIL_HOST`,
   `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) avant le
   premier déploiement. Ne pas placer les identifiants dans Git.
4. Vérifier le coût et la taille des ressources avant d'appliquer le Blueprint :
   deux services `starter`, un disque persistant de 1 Go et un PostgreSQL
   `basic-1gb` sont déclarés. Le chiffrage, les options de sauvegarde et les
   réserves de compatibilité Static Site sont dans
   [RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md](./RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md).
5. Les builds déploient séparément l'API et le SSR. Le `preDeployCommand` lance
   `migrate` contre le PostgreSQL Render ; examiner le plan des migrations et
   les sauvegardes avant d'autoriser ce premier déploiement.
6. Le PostgreSQL créé par le Blueprint est vide. `DATABASE_URL` est interprété
   par Django ; il ne copie pas `backend/db.sqlite3`. Restaurer ou importer les
   données de l'entreprise dans une base de préproduction et comparer les
   volumes, relations, utilisateurs, ventes, factures et mouvements avant toute
   bascule de production.
7. Le disque `/var/data` conserve les médias, les imports fournisseurs, les
   fichiers privés de factures et de vitrines lors des redéploiements. Mettre en
   place et tester une sauvegarde distincte de PostgreSQL et de ce disque.
8. Vérifier `https://nexora-api.onrender.com/healthz/`, l'authentification
   depuis l'URL frontend, les cookies de session/CSRF, les envois SMTP et les
   téléchargements de fichiers privés avant la recette.

Le Blueprint ne crée pas de tâche planifiée WhatsApp. Les rappels automatiques
ne doivent être activés qu'après configuration du fournisseur, vérification des
consentements et choix du coût/fréquence d'un service Cron Render. Ne pas lancer
manuellement le traitement sur des données réelles sans validation.

## Démarrer localement avec Docker Compose

Prérequis : Docker Desktop avec Docker Compose v2.

Depuis la racine du dépôt, créer le fichier local ignoré par Git s'il n'existe
pas déjà (ne pas écraser une configuration locale existante) :

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Après un clonage initial du dépôt principal, récupérer aussi le frontend :

```powershell
git submodule update --init --recursive
```

Remplacer `POSTGRES_PASSWORD` et `DB_PASSWORD` par la même valeur locale, puis
lancer :

```powershell
docker compose --parallel 1 build --pull backend frontend
docker compose up -d db
docker compose run --rm backend python manage.py migrate --noinput
docker compose up
```

- Frontend : `http://localhost:3000`
- API : `http://localhost:8000`
- Contrôle API + PostgreSQL : `http://localhost:8000/healthz/`

Compose lie le frontend et l'API à `127.0.0.1` uniquement, attend PostgreSQL
avant de lancer Django et conserve PostgreSQL et les uploads dans des volumes
Docker nommés. Les migrations sont une étape explicite, exécutée une fois avant
le démarrage de l'application ; elles ne sont pas relancées au redémarrage de
chaque conteneur. Les fichiers statiques sont collectés pendant la construction
de l'image backend. `GUNICORN_WORKERS` permet de régler les workers, avec une
valeur locale par défaut de 2.
PostgreSQL, Django et le frontend ont chacun un contrôle de santé ; Compose
attend PostgreSQL avant Django et Django avant le frontend. Vérifier l'état avec
`docker compose ps` et consulter les erreurs avec
`docker compose logs --tail=100 db backend frontend`.
L'URL de l'API du frontend est intégrée à la compilation de l'image. Le défaut
`http://localhost:8000/api/v1` convient uniquement à un navigateur exécuté sur
la machine Docker. Avant de construire le frontend pour des utilisateurs
distants, définir `VITE_API_BASE_URL` avec l'URL HTTPS publique réellement
configurée de l'API, terminée par `/api/v1` ; une variable d'environnement
ajoutée seulement au démarrage du conteneur ne suffit pas.

`docker compose down` conserve les volumes ; ne pas ajouter `-v` si les données
locales doivent être gardées.

## Intégration continue GitHub

Le workflow `.github/workflows/ci.yml` s'exécute sur les Pull Requests vers
`main`, les pushs sur `main` et à la demande. Il vérifie le lint et le build
frontend, audite npm et pip, lance les contrôles Django, les migrations et les
tests backend sur PostgreSQL 16, valide Compose, construit les images et analyse
la configuration Docker ainsi que les images avec Trivy (vulnérabilités
critiques/élevées et secrets). Les actions utilisées sont épinglées à des
versions. Les permissions du workflow sont limitées à la lecture du dépôt.

Le workflow `.github/workflows/docker-publish.yml` prépare également une
publication manuelle GHCR, uniquement par `workflow_dispatch`, avec
`confirm_publish=true` et une URL API HTTPS fournie. Il ne s'exécute pas sur
chaque push et n'a pas été déclenché. Il nécessite le droit de publication
`packages: write` fourni par `GITHUB_TOKEN` ; configurer des approbateurs sur
l'environnement `ghcr-publish` pour ajouter une validation GitHub avant
publication.

Après une exécution autorisée, ce workflow publie les deux images identifiées
par le SHA du commit et ajoute leurs digests, une provenance BuildKit et un
SBOM au résumé GitHub Actions. Déployer ensuite par digest lorsque la plateforme
le permet, après revue des scans et du commit source. Le workflow ne déploie
pas les images. Le Blueprint Render actuel construit le frontend et le backend
depuis leurs sources (runtime Node/Python) ; il ne consomme pas les images GHCR.
Ne pas confondre une image publiée dans GHCR avec une application déployée.

Le build local des images doit être vérifié avec Docker Desktop actif :

```powershell
docker compose --parallel 1 build --pull backend frontend
docker image ls djibexa-backend djibexa-frontend
```

Le tag local Compose est pratique pour les essais, pas une version de
production. Pour publier, utiliser exclusivement le workflow manuel approuvé,
puis conserver les deux digests comme références immuables. Ne jamais placer
de secret dans un argument `VITE_*` : ces variables sont intégrées au code
client et visibles par les utilisateurs. `VITE_API_BASE_URL` ne doit contenir
qu'une URL publique non secrète confirmée.

Le workflow CI ne publie aucune image et ne déploie aucun service. Après sa
première exécution sur GitHub, configurer dans les règles de protection de
`main` les contrôles `Frontend checks`, `Backend checks` et
`Docker build and image scans` comme validations obligatoires. Le frontend est
un sous-module Git distinct ; s'il devient privé, le checkout du sous-module
devra disposer d'un accès de lecture dédié. Le déploiement reste manuel et non
configuré.

Les dépendances frontend sont installées avec `npm ci` depuis le lockfile. Les
dépendances Python sont encore des plages de versions dans
`backend/requirements-render.txt`, sans lockfile avec hashes : le contrôle
pip-audit et le scan des images compensent partiellement ce manque, mais les
constructions backend ne sont pas entièrement reproductibles dans le temps.
Ne pas élargir les plages sans revue et validation.

Le fichier `.env.example` est réservé au développement. Copiez-le dans `.env`,
puis remplacez toutes les valeurs d'exemple avant un déploiement. Ne pas
réutiliser ses valeurs, `DJANGO_DEBUG=true` ou le serveur de développement en
production. Les variables de production commentées dans `.env.example` sont un
inventaire, pas des valeurs à activer telles quelles. Dans Render, saisir les
secrets dans les variables du service ; utiliser `DATABASE_URL` privé fourni
par Render et ne jamais commiter sa valeur.

Pour la configuration de production Django, définir explicitement
`DJANGO_ENV=production`, `DJANGO_DEBUG=false`, une `DJANGO_SECRET_KEY` forte,
`DJANGO_ALLOWED_HOSTS`, `FRONTEND_BASE_URL`, `CORS_ALLOWED_ORIGINS` et
`CSRF_TRUSTED_ORIGINS` avec les seuls hôtes HTTPS réellement provisionnés.
`DJANGO_SECURE_SSL_REDIRECT=true` est requis ; ne définir
`DJANGO_TRUST_X_FORWARDED_PROTO=true` que derrière le proxy TLS de confiance de
l'hébergeur. Les origines CORS et CSRF sont distinctes et validées séparément.
Ne pas activer HSTS sur les sous-domaines ni le preload tant que la propriété
et l'accès HTTPS de tous les sous-domaines ne sont pas confirmés.

Le frontend utilise `VITE_API_BASE_URL` dans les requêtes navigateur et y
envoie des cookies (`credentials: include`) avec le jeton CSRF. Les services
de préproduction Render utilisent pour l'instant leurs domaines
`.onrender.com`. `djibexa.com`, `app.djibexa.com` et `api.djibexa.com` sont
uniquement des propositions : ne créer aucun DNS avant achat et attribution des
cibles exactes par l'hébergeur. Utiliser uniquement les valeurs CNAME/A et la
validation de certificat fournies dans le tableau de bord Render.

Pour une installation Docker sur serveur :

1. Construire les images avec `docker compose --parallel 1 build --pull backend
   frontend`, puis démarrer uniquement
   PostgreSQL avec `docker compose up -d db`. Avant la construction, définir
   `VITE_API_BASE_URL` sur l'URL HTTPS publique confirmée de l'API.
2. Effectuer et vérifier une sauvegarde de la base et des fichiers persistants.
3. Exécuter `docker compose run --rm backend python manage.py migrate --noinput`
   une seule fois après revue des migrations.
4. Démarrer l'application derrière un reverse proxy HTTPS. Garder les ports
   Docker liés à `127.0.0.1` lorsque le proxy tourne sur l'hôte ; si le proxy
   tourne dans Docker, utiliser un réseau privé commun et ne pas publier les
   ports applicatifs sur toutes les interfaces.
5. Fournir des secrets forts, `DJANGO_DEBUG=false`, des hôtes et origines
   explicites, PostgreSQL et un stockage persistant. Ne pas utiliser les valeurs
   de l'exemple.

Ne pas démarrer plusieurs réplicas Compose partageant la même base sans une
étape de migration unique et un reverse proxy/load balancer approprié.
Dimensionner `GUNICORN_WORKERS` après mesure de la mémoire par worker et de la
charge ; la valeur `2` est seulement une valeur de départ, pas une recommandation
de capacité pour la production.

## Sauvegardes et restauration

Le volume PostgreSQL (`nexora-db`) et le volume de fichiers (`nexora-files`)
sont persistants, mais les volumes Docker ne sont pas des sauvegardes. Suivre la
procédure PostgreSQL de sauvegarde et de restauration avec essai sur base isolée
dans [MAINTENANCE.md](./MAINTENANCE.md) et le plan
[PLAN_SAUVEGARDE_SECURITE_REPRISE.md](./PLAN_SAUVEGARDE_SECURITE_REPRISE.md).
Render documente le PITR pour les bases payantes (fenêtre selon le plan de
l'espace) et des snapshots quotidiens des disques persistants conservés sept
jours ; confirmer l'éligibilité et la fenêtre dans le Dashboard. Ces copies
gérées ne remplacent pas une sauvegarde indépendante. Le propriétaire a choisi
initialement Render uniquement ; cette préférence est remplacée par la demande
du 30 octobre 2026 d'une sauvegarde indépendante de la base et des fichiers.
Chiffrer et configurer cette copie, puis restaurer dans une nouvelle base et un
emplacement de fichiers isolé avant toute mise en service. Les snapshots Render
ne constituent pas une copie indépendante. Le Cron Render ne montant pas le
disque `/var/data`, prévoir un stockage objet ou un export adapté des médias.
Ne jamais restaurer sur les données actives pour faire un essai.

## Vérifications avant mise en service

- Confirmer les variables d'environnement et les domaines dans le tableau de
  bord Render ; ne pas présumer que les URLs `.onrender.com` resteront les noms
  définitifs si des domaines personnalisés sont ensuite ajoutés.
- Tester l'envoi/réception de cookies dans un navigateur réel sur les domaines
  déployés et vérifier les protections CORS/CSRF.
- Vérifier les restaurations de sauvegardes et la persistance du disque après
  redéploiement.
- Créer les comptes plateforme et entreprise par les parcours d'administration
  contrôlés ; ne pas importer de base ni créer de comptes privilégiés sans
  validation des données et des rôles.
- Exécuter la suite de tests PostgreSQL et l'audit multi-tenant complet sur une
  copie isolée avant le pilote.
