# DJIBEXA

Application de gestion commerciale avec un frontend React/TanStack, une API
Django et PostgreSQL. Le frontend est un sous-module Git autonome dans
`frontend/`.

## Structure

```text
DJIBEXA/
├── frontend/
│   ├── Dockerfile
│   ├── .dockerignore
│   └── package.json
├── backend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── manage.py
│   └── requirements.txt
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── docker-publish.yml
├── compose.yaml
├── .env.example
├── .gitignore
└── README.md
```

Le frontend est maintenu comme sous-module Git dans l'environnement de travail.
Dans l'instantané public autonome, ses sources sont intégrées directement dans
`frontend/` afin que le clone du dépôt fonctionne sans accès à un dépôt de
sous-module distinct. L'arborescence ci-dessus montre les fichiers principaux
demandés ; des fichiers auxiliaires sont conservés pour le fonctionnement du
dépôt et des workflows, notamment les fichiers de verrouillage et de version
d'outils, `backend/requirements-render.txt`, `backend/.env.example`,
`render.yaml` et la documentation d'exploitation.

## Prérequis

- Git avec support des sous-modules
- Docker Desktop et Docker Compose v2

## Démarrer en local

Depuis la racine du dépôt, initialiser le frontend et créer la configuration
locale sans remplacer un éventuel fichier `.env` déjà existant :

```powershell
git submodule update --init --recursive
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Modifier `.env` pour remplacer les mots de passe de démonstration par une
valeur locale. Les valeurs d'exemple ne doivent jamais servir en production.
Puis construire et démarrer PostgreSQL :

```powershell
docker compose --parallel 1 build --pull backend frontend
docker compose up -d db
docker compose run --rm backend python manage.py migrate --noinput
docker compose up -d
docker compose ps
```

Les migrations sont une étape explicite : le démarrage des conteneurs ne les
applique pas automatiquement. Ne les exécuter contre une base réelle qu'après
revue et sauvegarde approuvée.

- Frontend : <http://localhost:3000>
- API : <http://localhost:8000>
- Santé API et base : <http://localhost:8000/healthz/>

Afficher les journaux et arrêter les services sans supprimer les données :

```powershell
docker compose logs --tail=100 db backend frontend
docker compose down
```

Ne pas ajouter `-v` à `docker compose down` si les volumes doivent être
conservés. Un volume persistant n'est pas une sauvegarde ; consulter
[MAINTENANCE.md](./MAINTENANCE.md) pour la sauvegarde et la restauration
PostgreSQL.

## Vérifications et images

La CI dans `.github/workflows/ci.yml` vérifie le lint, le build frontend,
l'audit npm/pip, Django, les tests backend PostgreSQL et les images Docker.
Les scans Trivy sont exécutés dans GitHub Actions.

La publication GHCR est définie dans `.github/workflows/docker-publish.yml`,
mais n'est jamais déclenchée automatiquement. Elle requiert un lancement
`workflow_dispatch` depuis `main`, la confirmation explicite
`confirm_publish=true` et une URL HTTPS valide se terminant par `/api/v1`.
Elle publie les images avec un tag correspondant au SHA du commit. Configurer
l'environnement GitHub `ghcr-publish` et ses approbateurs pour imposer une
validation manuelle supplémentaire.

La procédure Render, les paramètres d'exploitation, les sauvegardes et les
limites connues sont décrits dans
[DEPLOIEMENT_RENDER_DOCKER.md](./DEPLOIEMENT_RENDER_DOCKER.md) et
[MAINTENANCE.md](./MAINTENANCE.md). Le plan spécifique d'inventaire des
données, de sauvegardes, de restauration et de reprise après incident est dans
[PLAN_SAUVEGARDE_SECURITE_REPRISE.md](./PLAN_SAUVEGARDE_SECURITE_REPRISE.md).
Le budget, l'architecture Render, les limites du Static Site et les étapes de
validation avant déploiement sont détaillés dans
[RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md](./RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md).
