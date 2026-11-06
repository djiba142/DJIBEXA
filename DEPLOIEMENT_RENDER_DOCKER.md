# DÃ©ploiement DJIBEXA â€” Render et Docker

## Ã‰tat et limites

Le dÃ©pÃ´t contient maintenant une configuration de prÃ©production Render et un
environnement Docker local composÃ© de PostgreSQL, Django et TanStack Start.
La configuration Render est dÃ©clarative : aucun service n'a Ã©tÃ© crÃ©Ã© et aucune
migration n'a Ã©tÃ© exÃ©cutÃ©e sur une base rÃ©elle.

DJIBEXA n'a pas encore passÃ© l'audit complet d'isolation endpoint par endpoint.
Ne pas ouvrir l'inscription ni connecter une deuxiÃ¨me entreprise avant la
validation de toutes les API, fichiers, imports/exports, tÃ¢ches diffÃ©rÃ©es et
relations inter-entreprises. Les services Render dÃ©crits ici nÃ©cessitent des
ressources payantes pour PostgreSQL et la conservation des fichiers.

## PrÃ©parer Render

1. Pousser la branche contenant `render.yaml`, puis crÃ©er une nouvelle Blueprint
   dans Render et sÃ©lectionner ce dÃ©pÃ´t.
   Le frontend est un dÃ©pÃ´t Git distinct dÃ©clarÃ© comme sous-module : pousser
   d'abord son commit sur `djiba142/image-ad-studio`, puis le commit principal.
   VÃ©rifier que le checkout Render initialise le sous-module avant d'utiliser
   `rootDir: frontend` ; sinon, configurer le service frontend depuis son dÃ©pÃ´t
   dÃ©diÃ© plutÃ´t que de lancer un build incomplet.
2. VÃ©rifier la rÃ©gion Frankfurt et les noms `nexora-api`, `nexora-web` et
   `nexora-db`. Ils doivent rester cohÃ©rents avec les hÃ´tes et origines dÃ©finis
   dans le Blueprint, ou Ãªtre mis Ã  jour ensemble.
3. Fournir les variables SMTP demandÃ©es par Render (`EMAIL_HOST`,
   `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) avant le
   premier dÃ©ploiement. Ne pas placer les identifiants dans Git.
4. VÃ©rifier le coÃ»t et la taille des ressources avant d'appliquer le Blueprint :
   deux services `starter`, un disque persistant de 1 Go et un PostgreSQL
   `basic-256mb` sont dÃ©clarÃ©s.
5. Les builds dÃ©ploient sÃ©parÃ©ment l'API et le SSR. Le `preDeployCommand` lance
   `migrate` contre le PostgreSQL Render ; examiner le plan des migrations et
   les sauvegardes avant d'autoriser ce premier dÃ©ploiement.
6. Le PostgreSQL crÃ©Ã© par le Blueprint est vide. `DATABASE_URL` est interprÃ©tÃ©
   par Django ; il ne copie pas `backend/db.sqlite3`. Restaurer ou importer les
   donnÃ©es de l'entreprise dans une base de prÃ©production et comparer les
   volumes, relations, utilisateurs, ventes, factures et mouvements avant toute
   bascule de production.
7. Le disque `/var/data` conserve les mÃ©dias, les imports fournisseurs, les
   fichiers privÃ©s de factures et de vitrines lors des redÃ©ploiements. Mettre en
   place et tester une sauvegarde distincte de PostgreSQL et de ce disque.
8. VÃ©rifier `https://nexora-api.onrender.com/healthz/`, l'authentification
   depuis l'URL frontend, les cookies de session/CSRF, les envois SMTP et les
   tÃ©lÃ©chargements de fichiers privÃ©s avant la recette.

Le Blueprint ne crÃ©e pas de tÃ¢che planifiÃ©e WhatsApp. Les rappels automatiques
ne doivent Ãªtre activÃ©s qu'aprÃ¨s configuration du fournisseur, vÃ©rification des
consentements et choix du coÃ»t/frÃ©quence d'un service Cron Render. Ne pas lancer
manuellement le traitement sur des donnÃ©es rÃ©elles sans validation.

## DÃ©marrer localement avec Docker Compose

PrÃ©requis : Docker Desktop avec Docker Compose v2.

Depuis la racine du dÃ©pÃ´t, crÃ©er le fichier local ignorÃ© par Git :

```powershell
Copy-Item deploy\docker.env.example deploy\docker.env
```

AprÃ¨s un clonage initial du dÃ©pÃ´t principal, rÃ©cupÃ©rer aussi le frontend :

```powershell
git submodule update --init --recursive
```

Remplacer `POSTGRES_PASSWORD` et `DB_PASSWORD` par la mÃªme valeur locale, puis
lancer :

```powershell
docker compose build
docker compose up -d db
docker compose run --rm backend python manage.py migrate --noinput
docker compose up
```

- Frontend : `http://localhost:3000`
- API : `http://localhost:8000`
- ContrÃ´le API + PostgreSQL : `http://localhost:8000/healthz/`

Compose lie le frontend et l'API Ã  `127.0.0.1` uniquement, attend PostgreSQL
avant de lancer Django et conserve PostgreSQL et les uploads dans des volumes
Docker nommÃ©s. Les migrations sont une Ã©tape explicite, exÃ©cutÃ©e une fois avant
le dÃ©marrage de l'application ; elles ne sont pas relancÃ©es au redÃ©marrage de
chaque conteneur. Les fichiers statiques sont collectÃ©s pendant la construction
de l'image backend. `GUNICORN_WORKERS` permet de rÃ©gler les workers, avec une
valeur locale par dÃ©faut de 2.

`docker compose down` conserve les volumes ; ne pas ajouter `-v` si les donnÃ©es
locales doivent Ãªtre gardÃ©es.

Le fichier `deploy/docker.env.example` est rÃ©servÃ© au dÃ©veloppement. Ne pas
rÃ©utiliser ses valeurs, `DJANGO_DEBUG=true` ou le serveur de dÃ©veloppement en
production. Pour une installation Docker sur serveur :

1. Construire les images avec `docker compose build`, puis dÃ©marrer uniquement
   PostgreSQL avec `docker compose up -d db`.
2. Effectuer et vÃ©rifier une sauvegarde de la base et des fichiers persistants.
3. ExÃ©cuter `docker compose run --rm backend python manage.py migrate --noinput`
   une seule fois aprÃ¨s revue des migrations.
4. DÃ©marrer l'application derriÃ¨re un reverse proxy HTTPS. Garder les ports
   Docker liÃ©s Ã  `127.0.0.1` lorsque le proxy tourne sur l'hÃ´te ; si le proxy
   tourne dans Docker, utiliser un rÃ©seau privÃ© commun et ne pas publier les
   ports applicatifs sur toutes les interfaces.
5. Fournir des secrets forts, `DJANGO_DEBUG=false`, des hÃ´tes et origines
   explicites, PostgreSQL et un stockage persistant. Ne pas utiliser les valeurs
   de l'exemple.

Ne pas dÃ©marrer plusieurs rÃ©plicas Compose partageant la mÃªme base sans une
Ã©tape de migration unique et un reverse proxy/load balancer appropriÃ©.
Dimensionner `GUNICORN_WORKERS` aprÃ¨s mesure de la mÃ©moire par worker et de la
charge ; la valeur `2` est seulement une valeur de dÃ©part, pas une recommandation
de capacitÃ© pour la production.

## VÃ©rifications avant mise en service

- Confirmer les variables d'environnement et les domaines dans le tableau de
  bord Render ; ne pas prÃ©sumer que les URLs `.onrender.com` resteront les noms
  dÃ©finitifs si des domaines personnalisÃ©s sont ensuite ajoutÃ©s.
- Tester l'envoi/rÃ©ception de cookies dans un navigateur rÃ©el sur les domaines
  dÃ©ployÃ©s et vÃ©rifier les protections CORS/CSRF.
- VÃ©rifier les restaurations de sauvegardes et la persistance du disque aprÃ¨s
  redÃ©ploiement.
- CrÃ©er les comptes plateforme et entreprise par les parcours d'administration
  contrÃ´lÃ©s ; ne pas importer de base ni crÃ©er de comptes privilÃ©giÃ©s sans
  validation des donnÃ©es et des rÃ´les.
- ExÃ©cuter la suite de tests PostgreSQL et l'audit multi-tenant complet sur une
  copie isolÃ©e avant le pilote.
