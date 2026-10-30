# DJIBEXA — Rapport d'industrialisation DevOps

**Date :** 29 octobre 2026
**Branche examinée :** `main`
**Conclusion :** **Recette incomplète**

## 1. Contexte et périmètre

Audit des configurations Docker et Compose existantes, des dépendances,
versions d'exécution, pratiques de persistance, paramètres de sécurité et
pipelines GitHub Actions. Mise en place d'une CI de validation sans publication
d'image ni déploiement.

Aucune donnée réelle n'a été modifiée. Aucune migration n'a été appliquée à
PostgreSQL, aucun volume n'a été supprimé, aucun déploiement ni publication
d'image n'a été lancé et aucun commit n'a été créé.

## 2. État initial et environnement

- Dépôt principal sur `main`, dernier commit `1c44cc8` (`Harden Docker Compose
  operations`). Le sous-module frontend est référencé par le dépôt principal au
  commit `909b0f7`.
- Le dépôt était déjà modifié avant cette intervention : fichiers backend,
  configuration Compose et documentation, suppressions locales de justificatifs,
  médias et fichiers privés, ainsi que des changements non commités dans le
  sous-module frontend. Ces changements ont été préservés.
- Les fichiers `.env` locaux n'ont pas été lus ni ajoutés. Les configurations
  d'exemple contiennent des valeurs explicitement réservées au développement.
- Environnement observé : Windows, Python 3.13.8 (venv du projet), Node.js
  24.15.0/npm 11.9.0. Les versions image sont Python 3.13.8, Node.js 22.14.0
  et PostgreSQL 16.
- Docker CLI 29.3.1 et Docker Compose 5.1.0 sont présents. Lors du premier
  contrôle, le pipe du daemon Docker Desktop Linux était absent. Lors d'un
  nouvel essai, le daemon a répondu, puis la construction simultanée des deux
  images s'est interrompue avec une erreur RPC/EOF ; un contrôle Docker
  ultérieur est resté sans réponse plus de 30 secondes.
- Les tests backend locaux ont utilisé SQLite et une base de test isolée. Aucun
  test n'a été exécuté contre une base PostgreSQL persistante.

## 3. Architecture existante et changements

### Architecture conservée

- **Frontend :** application React/TanStack Start construite avec Vite, image
  Node en deux étapes et serveur SSR `node .output/server/index.mjs`, exécuté
  comme utilisateur non privilégié.
- **Backend :** Django servi par Gunicorn, image Python dédiée, utilisateur non
  privilégié et collecte des statiques pendant le build. Le démarrage ne lance
  pas automatiquement de migration.
- **Données :** PostgreSQL 16 dans un volume nommé persistant et non publié sur
  un port hôte. Les médias et documents privés sont conservés dans un second
  volume nommé.
- **Réseau :** réseau Compose limité aux services du projet ; seuls les ports
  applicatifs sont liés à `127.0.0.1`. Les health checks PostgreSQL et backend
  existaient déjà.
- **Déploiement :** configuration Render déjà présente avec `autoDeploy: false`.
  Elle n'a pas été lancée ni modifiée pour publier ou déployer.

### Arborescence vérifiée

Les fichiers de l'arborescence demandée sont présents. Cette vue reprend les
fichiers principaux demandés, sans prétendre être la liste exhaustive du dépôt :

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
├── README.md
└── ...
```

Les chemins principaux sont présents et la configuration Compose se valide.
Le frontend reste un sous-module (`.gitmodules`), et des fichiers auxiliaires
nécessaires au build et aux workflows sont conservés, notamment
`package-lock.json`, les fichiers de version d'outils, `backend/requirements-render.txt`,
`backend/.env.example`, `render.yaml` et la documentation d'exploitation.
Le sous-module a été déplacé de `image-ad-studio/` vers `frontend/`,
`docker-compose.yml` est devenu `compose.yaml`, et le modèle Compose utilise
`.env.example` à la racine.

### Modifications de cette intervention

- Ajout de `.github/workflows/ci.yml` : CI sur Pull Requests vers `main`, pushs
  sur `main` et déclenchement manuel. Les jobs vérifient le frontend, le
  backend sur PostgreSQL 16, les dépendances, Compose et les images.
- Ajout de `.github/workflows/docker-publish.yml` : publication GHCR uniquement
  par déclenchement manuel, avec confirmation explicite, URL d'API à fournir,
  restrictions à la branche `main`, permissions minimales `packages: write` et
  tags par SHA.
- Permissions Actions limitées à `contents: read`. Les actions sont référencées
  par versions explicites. Le workflow CI ne dispose d'aucune permission de
  publication et n'effectue aucun déploiement.
- Ajout d'un health check HTTP pour le frontend dans Compose. Ajout des caches
  BuildKit npm/pip dans les Dockerfiles et exclusion de `.npmrc` du contexte
  frontend.
- Correction des dépendances frontend après détection d'avis npm : mise à jour
  des dépendances transitives corrigibles et passage de Zod à `4.6.7`. Le code
  applicatif utilisé directement par Zod se limite à un schéma simple ; lint et
  build ont été relancés après la mise à jour.
- Mise à jour de `DEPLOIEMENT_RENDER_DOCKER.md` avec les contrôles CI, les
  commandes de diagnostic, les limites de reproductibilité et le renvoi aux
  procédures de sauvegarde/restauration dans `MAINTENANCE.md`.
- Correction du paramétrage des origines Django : `CSRF_TRUSTED_ORIGINS` lit
  désormais sa propre variable, et les paramètres de production refusent les
  origines absentes/non HTTPS, les jokers CORS, CORS global et la désactivation
  de la redirection HTTPS.
- Complément du workflow manuel GHCR : publication par SHA avec provenance,
  SBOM et digests inscrits au résumé du workflow. Aucun push n'a été exécuté.
- Augmentation du délai d'attente et des tentatives de téléchargement pip dans
  l'image backend après des timeouts réseau observés pendant le build local.
- Ajout de l'inventaire des variables de production commenté à `.env.example`
  et de la distinction documentée entre GHCR et le Blueprint Render actuel,
  qui construit encore depuis les sources.

## 4. Tests, contrôles et preuves

| Contrôle | Statut | Résultat observé |
|---|---|---|
| Branche et historique Git | **RÉUSSI** | `git branch --show-current` retourne `main`; dernier commit principal `1c44cc8`. |
| Préservation des changements préexistants | **RÉUSSI** | `git status --short --branch` confirme des changements locaux préexistants et ceux de cette intervention. Aucun nettoyage, commit ou changement d'historique. |
| Configuration Django | **RÉUSSI** | `python manage.py check` avec `DB_ENGINE=sqlite` et base `:memory:` : `System check identified no issues`. |
| État des migrations | **RÉUSSI** | `python manage.py makemigrations --check --dry-run` : `No changes detected`. Aucune migration appliquée. |
| Suite backend | **RÉUSSI, SQLite uniquement** | `python manage.py test --verbosity 1` depuis `backend` avec le venv du projet : **354 tests passés**, `Ran 354 tests in 1101.206s`, `OK`. Une trace `DatabaseError` du chemin de surveillance de base a été imprimée pendant la suite, mais l'exécution s'est terminée avec le code 0. |
| Lint frontend | **RÉUSSI avec réserves** | `npm run lint` : 0 erreur, 16 avertissements `react-refresh/only-export-components`. |
| Build frontend | **RÉUSSI** | `npm run build` : build client, serveur et SSR terminé sans erreur (`✓ built`). |
| Audit npm | **RÉUSSI après correction** | Le premier `npm audit --audit-level=high` détectait DOMPurify (critique), Zod (élevée) et Seroval (modérée). Après mise à jour ciblée, la même commande retourne `found 0 vulnerabilities`. |
| Tests unitaires frontend | **NON TESTÉ / non configuré** | `frontend/package.json` ne définit pas de script `test`; lint, audit et build ont été exécutés à la place. |
| Configuration Compose après restructuration | **RÉUSSI** | `docker compose config --quiet` avec `.env.example` : code 0. Le fichier `.env` temporaire a été supprimé après le contrôle. |
| Contrôle Django de déploiement | **AVERTISSEMENTS** | `manage.py check --deploy` avec les hôtes Render de préproduction identifie des avertissements HSTS concernant les sous-domaines et le preload. Le rapport inclut aussi les avertissements de schéma OpenAPI ; aucun n'a été masqué. |
| YAML du workflow | **RÉUSSI, validation syntaxique** | Lecture YAML réussie ; jobs `frontend`, `backend`, `docker` détectés. Aucun run GitHub Actions n'a été déclenché. |
| Contrôle whitespace | **RÉUSSI** | `git diff --check` et son équivalent dans le dépôt frontend passent. Git affiche des avertissements de conversion LF/CRLF sur des fichiers frontend préexistants. |
| Recherche de secrets dans les changements de cette intervention | **RÉUSSI, examen statique limité** | Aucun secret réel n'a été ajouté ; `.env` local n'a pas été lu et les fichiers d'environnement restent exclus des contextes Docker. Aucun scan exhaustif de l'historique Git n'a été exécuté. |
| Disponibilité Docker Desktop | **RÉUSSI** | Docker Desktop a été démarré ; daemon Linux/WSL2 Docker 29.3.1 répond. |
| Build frontend local | **RÉUSSI** | `djibexa-frontend:render-preview` construit avec `VITE_API_BASE_URL=https://nexora-api.onrender.com/api/v1`, valeur actuellement déclarée dans `render.yaml`. L'image locale `djibexa-frontend:latest` est aussi présente mais utilise localhost. |
| Build backend local | **RÉUSSI** | `docker compose --parallel 1 build backend` termine ; `collectstatic` copie 166 fichiers et post-traite 476 fichiers statiques. Les retries pip ont permis de terminer malgré des téléchargements lents. |
| Health checks des images | **RÉUSSI** | Le frontend conteneurisé renvoie HTTP 200. Le backend en configuration production répond `200 ok` en se connectant à un PostgreSQL 16 éphémère, avec l'en-tête TLS du proxy de confiance. Aucun service ou volume préexistant n'a été utilisé. |
| Références locales des images | **RÉUSSI, locales uniquement** | Backend `djibexa-backend:latest`, digest `sha256:74baa80456155d28848080f38537fd6e29eb71a9a5309e2dd7ed7d03af279a4f`; frontend Render `djibexa-frontend:render-preview`, digest `sha256:62be849847c4412265ddd9b7d4b75fd597c73308ce1e1ce09b88df7698e5e5a0`. Ces digests locaux ne sont pas publiés dans GHCR. |
| Scan Trivy des images/configurations | **NON TESTÉ** | Dépend d'un build d'image terminé. `trivy` n'est pas installé localement ; les scans restent à confirmer par la CI GitHub. |
| Audit pip local | **NON TESTÉ** | `pip-audit` n'est pas installé localement. Le workflow l'installe à une version déterminée et scanne `backend/requirements-render.txt`. |
| Tests backend sur PostgreSQL | **NON TESTÉ localement** | Le workflow contient un service PostgreSQL 16 isolé, mais il n'a pas été exécuté sur GitHub pendant cette intervention. |
| Publication d'image / déploiement | **NON EXÉCUTÉ** | Le workflow manuel GHCR publie des tags SHA, attestations de provenance et SBOM, et expose les digests. Il n'a pas été déclenché ; aucune image n'a été publiée et aucun service n'a été déployé. |
| Sauvegarde/restauration Render | **NON TESTÉ** | Le propriétaire souhaite rester sur Render avec une rétention visée de sept jours. L'éligibilité et l'état du PITR et des snapshots, ainsi que la restauration isolée de la base et des fichiers, restent à confirmer dans le Dashboard et à tester. |

Le lint/build frontend ont été exécutés depuis `frontend/`. Les contrôles
Django et la suite de tests ont été exécutés dans le venv du dépôt. Le premier
essai avec le Python global était incomplet (`pypdf` absent) ; la validation a
été reprise avec le venv du projet, qui contient cette dépendance.

## 5. Anomalies, risques et corrections

### Corrigé — vulnérabilités des dépendances frontend

L'audit initial signalait une vulnérabilité critique de DOMPurify, une élevée
de Zod et une modérée de Seroval. Les mises à jour compatibles puis le passage
à Zod 4.6.7 ont supprimé les alertes : `npm audit --audit-level=high` rapporte
maintenant zéro vulnérabilité. Build et lint passent après le changement.

### Réserve élevée — images locales non publiées ni scannées

Les images backend et frontend ont été construites et leurs contrôles de santé
ont répondu localement. Elles ne sont ni publiées dans GHCR ni scannées par
Trivy. L'image frontend `render-preview` contient l'adresse API configurée
actuellement dans `render.yaml` ; ce domaine Render doit être confirmé lors du
provisionnement, et toute URL différente impose une reconstruction. Le tag
`latest` frontend utilise localhost et n'est pas destiné aux utilisateurs
distants. Ne pas traiter les images locales comme artefacts de livraison
autorisés.

### Réserve moyenne — CI non exécutée et sous-module non commité

Le workflow est ajouté mais n'a pas encore été exécuté sur GitHub. Le dépôt
principal pointe toujours vers le commit frontend `909b0f7`; les changements
frontend présents localement, y compris les mises à jour de `package.json` et
`package-lock.json`, ne sont pas inclus dans ce commit référencé. Il faudra
commiter les changements frontend prévus, actualiser la référence du
sous-module, puis pousser les changements autorisés pour que la CI vérifie cet
état. Aucun commit n'a été créé ici.

### Réserve moyenne — verrouillage des dépendances Python

`backend/requirements-render.txt` utilise des plages de versions, sans
lockfile/hash complet. Les builds Python peuvent donc résoudre des versions
différentes dans le temps. Aucun fichier de verrouillage n'a été généré
arbitrairement.

### Réserve moyenne — sauvegardes des fichiers

Les volumes Compose assurent la persistance, pas la sauvegarde. Le choix actuel
est de s'appuyer uniquement sur Render, avec une rétention visée de sept jours ;
il ne prévoit donc pas de copie indépendante hors hébergeur. Il faut confirmer
dans le Dashboard les sauvegardes réellement disponibles pour le plan choisi,
notamment le PITR PostgreSQL et les snapshots du disque de fichiers, puis
effectuer une restauration isolée de la base et des médias/documents. Le test
local PostgreSQL ne valide pas ces fonctions Render ni la restauration des
fichiers. Les objectifs RPO de 24 h et RTO d'un jour ouvré restent des candidats
à valider, et ne sont pas des garanties de service.

### Réserve faible — avertissements lint

Les 16 avertissements Fast Refresh ne bloquent pas le lint. Ils sont conservés
car ils ne relèvent pas de l'industrialisation Docker/CI et aucune erreur n'est
émise.

### Ressources et coûts Render à confirmer

Le Blueprint déclare deux services web au plan `starter`, un PostgreSQL
`basic-256mb` et un disque persistant de 1 Go. Ces tailles ne constituent pas
une validation de capacité ou de disponibilité pour les données métier. Aucun
service n'a été créé et aucun prix n'a été figé : confirmer les tarifs et les
limites affichés par Render pour la région et la durée de conservation voulues
avant de provisionner. Estimer les coûts des ressources Render et vérifier
l'inclusion ou le coût des sauvegardes correspondant à la rétention visée avant
toute activation. Les frais SMTP, stockage/egress éventuels et taxes ne sont pas
inclus dans le Blueprint. Une copie hors Render entraînerait des coûts
additionnels, mais n'est pas incluse dans le choix actuel.

## 6. Contrôles restant à effectuer

1. Confirmer les noms de services et l'URL API Render, lancer la CI complète
   avec Trivy, puis reconstruire toute image frontend si son URL API change.
   Vérifier les health checks sur l'environnement Render avant d'autoriser la
   diffusion. Ne pas considérer les images locales comme publiées.
2. Mettre à jour le commit/référencement du sous-module frontend selon les
   changements que le propriétaire souhaite conserver, puis exécuter la CI
   GitHub et examiner les résultats PostgreSQL, pip-audit, Trivy et builds.
3. Rendre obligatoires les trois contrôles CI dans la protection de la branche
   `main`. Vérifier que le checkout GitHub peut lire le dépôt du sous-module.
4. Examiner les résultats de scan des images avant toute mise en service. Les
   images de production devraient être identifiées par digest ; les tags de
   base actuels ne sont pas épinglés par digest.
5. Confirmer dans Render les fonctions et la rétention de sauvegarde réellement
   disponibles pour le plan retenu, ainsi que leur coût ; réaliser un essai de
   restauration isolé de PostgreSQL et des fichiers depuis ces sauvegardes.
6. Configurer les approbateurs de l'environnement GitHub `ghcr-publish` et
   vérifier les droits GHCR avant tout déclenchement manuel de publication. Le
   workflow exige une confirmation explicite et n'a pas été exécuté.
7. Exécuter les migrations uniquement après revue, sauvegarde vérifiée et
   validation sur une base de recette isolée. Aucune validation de production
   n'est apportée par ce rapport.

## 7. Conclusion

**Recette incomplète.** Les contrôles Django, les 354 tests backend isolés, le
lint/build frontend, l'audit npm corrigé, la syntaxe Compose et le YAML du
workflow sont validés. Les deux images Docker sont construites localement et
leurs endpoints de santé ont été vérifiés, y compris le backend configuré en
production face à un PostgreSQL 16 éphémère. Le scan Trivy, la CI GitHub, la
publication des images, les tests backend PostgreSQL complets, les sauvegardes
de fichiers et toute recette de déploiement restent à exécuter. Ce résultat ne
vaut pas validation de la production.
