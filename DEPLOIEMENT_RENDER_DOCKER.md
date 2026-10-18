# Déploiement NEXORA — Render et Docker

## État et limites

Le dépôt contient maintenant une configuration de préproduction Render et un
environnement Docker local composé de PostgreSQL, Django et TanStack Start.
La configuration Render est déclarative : aucun service n'a été créé et aucune
migration n'a été exécutée sur une base réelle.

NEXORA n'a pas encore passé l'audit complet d'isolation endpoint par endpoint.
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
   `rootDir: image-ad-studio` ; sinon, configurer le service frontend depuis son
   dépôt dédié plutôt que de lancer un build incomplet.
2. Vérifier la région Frankfurt et les noms `nexora-api`, `nexora-web` et
   `nexora-db`. Ils doivent rester cohérents avec les hôtes et origines définis
   dans le Blueprint, ou être mis à jour ensemble.
3. Fournir les variables SMTP demandées par Render (`EMAIL_HOST`,
   `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) avant le
   premier déploiement. Ne pas placer les identifiants dans Git.
4. Vérifier le coût et la taille des ressources avant d'appliquer le Blueprint :
   deux services `starter`, un disque persistant de 1 Go et un PostgreSQL
   `basic-256mb` sont déclarés.
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

Depuis la racine du dépôt, créer le fichier local ignoré par Git :

```powershell
Copy-Item deploy\docker.env.example deploy\docker.env
```

Après un clonage initial du dépôt principal, récupérer aussi le frontend :

```powershell
git submodule update --init --recursive
```

Remplacer `POSTGRES_PASSWORD` et `DB_PASSWORD` par la même valeur locale, puis
lancer :

```powershell
docker compose up --build
```

- Frontend : `http://localhost:3000`
- API : `http://localhost:8000`
- Contrôle API + PostgreSQL : `http://localhost:8000/healthz/`

Compose attend PostgreSQL avant de lancer Django, applique les migrations à sa
base locale, collecte les fichiers statiques et conserve PostgreSQL et les
uploads dans des volumes Docker nommés. `docker compose down` conserve ces
volumes ; ne pas ajouter `-v` si les données locales doivent être gardées.

Le fichier `deploy/docker.env.example` est réservé au développement. Ne pas
réutiliser ses valeurs, `DJANGO_DEBUG=true` ou le serveur de développement en
production. Le déploiement Docker en production doit fournir les mêmes secrets,
origines HTTPS, PostgreSQL et stockage persistant que Render, et appliquer les
migrations après sauvegarde et revue.

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
