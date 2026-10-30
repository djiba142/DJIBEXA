# DJIBEXA — Rapport de recette technique post-renommage

**Date de recette :** 29 octobre 2026
**Conclusion :** Recette incomplète

## 1. Contexte et périmètre

Cette recette vérifie les changements de marque NEXORA → DJIBEXA, le démarrage
et la compilation du frontend React/TanStack, les contrôles Django, les
configurations Docker et les contrôles PostgreSQL réalisables dans
l'environnement local disponible. Elle ne constitue ni une recette de
production, ni un audit exhaustif de sécurité ou d'isolation multi-tenant.

Les contrôles ont été exécutés en lecture seule sur PostgreSQL. Aucune migration
n'a été appliquée, aucune donnée n'a été réinitialisée et aucun déploiement n'a
été effectué. Les tests applicatifs Django ont utilisé SQLite en mémoire.

## 2. Environnement réellement utilisé

- Windows, Python 3.13.8, Django 5.2.17.
- Node.js 24.15.0, npm 11.9.0, Vite 8.3.3.
- PostgreSQL 18 local : connexion vérifiée, base configurée non identifiée comme
  base de test ou de production.
- Docker CLI 29.3.1 et Compose 5.1.0 présents ; daemon Docker Desktop Linux
  indisponible.
- Frontend servi localement sur `http://127.0.0.1:3000` et Django sur
  `http://127.0.0.1:8000`.

## 3. Tests effectués et résultats

| Domaine / contrôle | Statut | Preuve et résultat |
|---|---|---|
| Branche et historique Git | **RÉUSSI** | `git status --short --branch` : dépôts principal et frontend sur `main`. Historique principal : `1c44cc8`, `e3c6d59` ; frontend : `909b0f7`. |
| État Git et fichiers locaux | **RÉUSSI avec réserves** | Des fichiers modifiés, supprimés et non suivis étaient déjà présents. Ils ont été préservés ; aucun nettoyage ou commit n'a été fait pendant cette recette. |
| Secrets dans les changements de recette inspectés | **RÉUSSI** | Revue des changements concernés : aucun secret ajouté ; le nouvel exemple utilise un mot de passe fictif. Le `.env` local préexistant n'a pas été lu ni modifié. Pas de scan automatisé exhaustif de tout l'historique. |
| Revue de sécurité des changements de renommage/Docker | **RÉUSSI avec réserves** | La revue dédiée des changements examinés n'a pas relevé de vulnérabilité exploitable. Cela ne constitue pas un pentest, une revue exhaustive de toutes les API ou la validation complète de l'isolation multi-tenant. |
| Build React/TanStack | **RÉUSSI** | `npm run build` : Vite a compilé les bundles client, serveur et SSR sans erreur. Avertissement de taille de chunk et avertissement de directive `use client` émis par le bundler. |
| Lint frontend | **RÉUSSI avec réserves** | `npm run lint` : 0 erreur, 16 avertissements `react-refresh/only-export-components`. |
| Parcours navigateur et identité | **RÉUSSI, parcours limité** | Page `/auth` chargée ; titre et logo DJIBEXA visibles. L'envoi du formulaire vide est bloqué par la validation navigateur. L'accès anonyme au dashboard redirige vers `/auth`. Aucun compte authentifié n'a été utilisé. |
| Favicon | **RÉUSSI après correction** | Le favicon référence `/brand/kourouma-mark.svg` ; requête navigateur locale : HTTP 200. L'ancienne référence PNG NEXORA a été remplacée dans `frontend/src/routes/__root.tsx`. |
| Appel API depuis le navigateur | **RÉUSSI après correction CORS** | Depuis `127.0.0.1:3000`, `fetch` vers `/api/v1/users/me/` sur le port 8000 se résout et retourne HTTP 403 avec `Informations d'authentification non fournies.`. Ce 403 est attendu sans session ; aucune erreur de blocage CORS. |
| Configuration CORS/CSRF locale | **RÉUSSI après correction** | `CORS_ALLOWED_ORIGINS` et `CSRF_TRUSTED_ORIGINS` incluent désormais `localhost:3000` et `127.0.0.1:3000` par défaut. Test de régression ajouté et exécuté : `manage.py test core.tests.DevelopmentCorsSettingsTests core.tests.DjangoAdminBrandingTests --verbosity 1` — 2 tests passés. |
| Contrôle Django | **RÉUSSI** | `python manage.py check` : aucun problème détecté. |
| Détection de migrations modèle Django | **RÉUSSI** | `python manage.py makemigrations --check --dry-run` : aucune modification de modèle ne nécessite de migration. |
| Suite de tests backend | **RÉUSSI sur SQLite mémoire** | `python manage.py test` : 350 tests passés. La suite couvre notamment les domaines produits/stocks, achats/fournisseurs, ventes/factures, clients, finances/paiements, utilisateurs, documents et santé API. Ce résultat ne remplace pas des parcours complets PostgreSQL ni une recette métier authentifiée. |
| Endpoint de santé et fichiers statiques | **RÉUSSI** | `GET /healthz/` : HTTP 200. `findstatic core/djibexa-admin-logo.svg` localise le logo d'administration. |
| PostgreSQL — connectivité | **RÉUSSI, portée limitée** | Requête en lecture seule `SELECT 1` : connexion fonctionnelle au service PostgreSQL local. |
| PostgreSQL — migrations appliquées/en attente | **ÉCHEC de conformité / réserve** | Le contrôle en lecture seule rapporte 91 migrations appliquées et 46 en attente. Aucune n'a été appliquée. La nature de la base configurée n'étant pas établie, son adéquation à un environnement de recette ne peut pas être certifiée. |
| PostgreSQL — accès aux données de test | **NON TESTÉ** | Aucune identité de base de test ni jeu de données de test n'a été confirmé. Aucun enregistrement métier n'a été lu ou modifié pour cette recette. |
| Docker Compose — syntaxe et interpolation | **RÉUSSI** | `docker compose config --quiet` a réussi avec l'exemple racine `.env.example`, puis avec `VITE_API_BASE_URL` défini. Le fichier temporaire `.env` utilisé a été supprimé. |
| Construction/lancement des images Docker | **BLOQUÉ** | `docker info` échoue car le pipe `dockerDesktopLinuxEngine` est absent et le daemon n'est pas démarré. Aucune image n'a été construite et aucun conteneur n'a été lancé. |
| Flux métier end-to-end / impression / exports | **NON TESTÉ** | Les tests backend passent, mais les parcours authentifiés complets, impressions, exports et vérification visuelle de documents n'ont pas été exécutés en navigateur. |
| `git diff --check` | **RÉUSSI** | Les dépôts principal et frontend ne présentent pas d'erreur d'espacement dans les diffs. Git signale seulement une conversion de fins de ligne à venir sur `src/routes/__root.tsx`. |

## 4. Anomalies et réserves

### Gravité moyenne — origines CORS/CSRF locales absentes

- **Composants :** `backend/nexora_backend/settings.py`,
  `backend/.env.example`, `backend/core/tests.py`.
- **Constat :** le frontend démarre sur le port 3000 tandis que les valeurs
  Django précédentes ne permettaient pas ce port. Les appels navigateur à l'API
  étaient bloqués par CORS.
- **Correction :** ajout des origines localhost et 127.0.0.1 sur le port 3000
  dans les valeurs par défaut CORS et CSRF, documentation de l'exemple local et
  test de régression. Le test ciblé et le smoke test navigateur passent.
- **Limite :** les origines de production doivent rester explicitement
  configurées ; les nouvelles valeurs ne valident pas la configuration d'un
  domaine déployé.

### Gravité moyenne — 46 migrations en attente dans PostgreSQL

- **Composant :** base PostgreSQL configurée localement.
- **Constat :** 91 migrations appliquées, 46 en attente ; aucun schéma n'a été
  modifié. La base configurée n'est pas identifiée comme base isolée de test.
- **Action requise :** confirmer la base et examiner le plan des migrations sur
  une copie de recette sauvegardée avant toute application.

### Gravité moyenne — construction Docker non vérifiée

- **Composants :** `compose.yaml`, images backend et frontend.
- **Constat :** la syntaxe Compose et l'interpolation sont valides, mais le
  daemon Docker est indisponible ; build et démarrage impossibles.
- **Action requise :** démarrer Docker Desktop puis refaire build, lancement,
  health check et tests de persistance sur un environnement local isolé.

### Gravité faible — avertissements frontend

- **Composants :** plusieurs composants React et bundles frontend.
- **Constat :** 16 avertissements Fast Refresh ; le build indique aussi un
  chunk volumineux et une directive `use client` dont la sémantique n'est pas
  conservée par le bundler.
- **Action requise :** évaluer le découpage des chunks et les exports React dans
  un travail distinct ; aucune erreur de lint ni d'échec de build n'a été
  observé.

## 5. Corrections effectuées pendant cette recette

- Remplacement du favicon NEXORA encore référencé par le favicon SVG DJIBEXA.
- Ajout des origines loopback du port 3000 aux réglages CORS et CSRF par défaut.
- Ajout des variables correspondantes à `backend/.env.example` et d'un test
  ciblé pour éviter la régression CORS.
- La configuration Compose permet de fournir `VITE_API_BASE_URL` au build ;
  la documentation précise que cette URL est intégrée au bundle et doit être
  l'URL HTTPS publique lorsque le navigateur est distant.
- Aucune migration, donnée métier, ressource persistante ou configuration `.env`
  locale n'a été modifiée. Aucun commit ni déploiement n'a été effectué.

## 6. État Git et préservation

Les dépôts sont sur `main`. Les commits déjà présents au début de la recette
incluent `1c44cc8` (opérations Compose) et `e3c6d59` (renommage backend) dans le
dépôt principal, ainsi que `909b0f7` dans le dépôt frontend. Aucun remote Git
n'était configuré dans les dépôts locaux.

Le worktree contenait déjà des modifications, suppressions et fichiers non
suivis, notamment des `.env`, justificatifs et médias locaux. Ils n'ont pas été
réinitialisés, supprimés, ajoutés à l'index ou commités. Les corrections de
recette et ce rapport restent non commités.

## 7. Contrôles restant à effectuer

1. Confirmer l'identité et l'isolement de la base PostgreSQL de recette ; y
   vérifier les données de test en lecture seule.
2. Examiner les 46 migrations en attente sur une copie sauvegardée de cette
   base, puis décider explicitement de leur application. Ne pas les appliquer
   en production sans procédure et autorisation distinctes.
3. Rejouer les tests Django sur PostgreSQL isolé, en plus de la suite SQLite.
4. Avec Docker Desktop disponible, construire et lancer les services, vérifier
   `/healthz/`, la connexion PostgreSQL, les fichiers persistants et le parcours
   frontend/API.
5. Tester avec des utilisateurs de test les parcours complets de chaque module,
   les rôles/permissions, les impressions et exports, ainsi que l'authentification
   et les protections CSRF sur les véritables domaines de déploiement.
6. Vérifier la console navigateur et les ressources sur un déploiement HTTPS de
   préproduction ; aucun test de production ou déploiement n'a été effectué.
7. Effectuer un audit dédié de l'isolation multi-tenant endpoint par endpoint
   avant d'ouvrir l'inscription ou de connecter une seconde entreprise.

## 8. Conclusion

**Recette incomplète.** Les vérifications locales exécutées sont conformes pour
la compilation frontend, les contrôles Django, la suite backend SQLite, le
favicon et le comportement CORS local après correction. La recette PostgreSQL
reste réservée par 46 migrations en attente et l'absence de base de test
confirmée ; la construction Docker et plusieurs parcours métier réels n'ont pas
pu être exécutés. Cette conclusion ne vaut pas validation de la production.
