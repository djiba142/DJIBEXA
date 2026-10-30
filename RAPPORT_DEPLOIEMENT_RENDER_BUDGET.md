# DJIBEXA — Préparation Render et maîtrise du budget

**Date de vérification :** 30 octobre 2026
**État :** préparation uniquement ; aucun déploiement, service Render, domaine,
DNS, sauvegarde cloud ou secret n'a été créé ou modifié.

## 1. Décision

**DJIBEXA n'est pas encore prêt pour une mise en production.** Le dépôt possède
une configuration Render et une CI, mais la configuration actuelle n'est pas
compatible avec toutes les hypothèses du budget cible :

- le frontend est un serveur **TanStack Start/Nitro SSR** exécuté par Node, et
  non un export statique prêt à servir ;
- le Blueprint utilise actuellement deux services `starter`, un disque de
  fichiers de 1 Go et PostgreSQL `basic-256mb` ;
- le PostgreSQL `basic-256mb` ne répond pas à la cible de 1 Go de RAM ;
- le PITR Render du plan Hobby est documenté avec une fenêtre de trois jours,
  inférieure à la rétention de sept jours visée ;
- les médias ne disposent pas encore d'une sauvegarde indépendante restaurée ;
- les tarifs de l'espace et les fonctions réellement activées n'ont pas pu être
  vérifiés dans le Dashboard. Les montants ci-dessous sont une estimation de
  catalogue, pas un devis ni un montant confirmé sur le compte.

Le choix prudent est de conserver provisoirement le frontend SSR afin de ne pas
retirer son serveur sans validation fonctionnelle, de dimensionner PostgreSQL
à 1 Go dans le Blueprint et de ne pas prétendre que le budget de 25 USD couvre
l'architecture et la sauvegarde indépendante.

## 2. Audit du dépôt

| Surface | État observé | Conséquence |
|---|---|---|
| `render.yaml` | API Django en `starter`, frontend Node en `starter`, PostgreSQL `basic-256mb`, disque API `/var/data` de 1 Go, région Frankfurt, `autoDeploy: false`, migrations dans `preDeployCommand` | Les noms `nexora-api`, `nexora-web` et les origines `onrender.com` doivent rester cohérents tant que les noms ne sont pas confirmés. Le plan PostgreSQL a été relevé à `basic-1gb`; le Blueprint n'a pas été appliqué. |
| `frontend/package.json`, `frontend/vite.config.ts`, `frontend/Dockerfile` | TanStack Start avec Nitro, sortie `.output/server/index.mjs` et lancement Node | Ce n'est pas une configuration Render Static Site. Le passage au statique demande une migration et des tests de routes profondes, de navigation, d'authentification et de cookies ; il ne faut pas substituer seulement le type de service. |
| `backend/nexora_backend/settings.py` | Les garde-fous de production vérifient secret fort, `DEBUG=False`, hôtes, origines HTTPS précises, CORS non global, HTTPS, cookies sécurisés et vrai backend e-mail | Les valeurs Render actuelles sont des domaines `onrender.com`. Le domaine personnalisé devra être ajouté explicitement à `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` et `FRONTEND_BASE_URL` après achat et configuration. |
| Connexion PostgreSQL | Les services et la base sont configurés dans la même région ; `DATABASE_URL` vient de la ressource liée du Blueprint | Utiliser l'URL interne fournie par Render et limiter les connexions externes dans le Dashboard. Ne jamais mettre une URL de connexion ou un mot de passe dans le dépôt. |
| Fichiers | Le disque Render de 1 Go héberge médias, factures privées, imports et vitrines sous `/var/data` | Un disque persistant n'est pas une sauvegarde indépendante. Le Cron Render ne peut pas monter ce disque ; la sauvegarde des médias doit être traitée séparément. |
| CI/Docker | `.github/workflows/ci.yml` couvre lint/build frontend, audits, Django, tests PostgreSQL isolés, Compose, builds et Trivy. Le workflow GHCR est manuel avec confirmation explicite. | Les tests décrits par la CI n'équivalent pas à une exécution réelle sur GitHub. Les images ne sont pas automatiquement publiées ni déployées. |
| Secrets | `.env.example` contient des valeurs de développement et des exemples de production commentés | Ajouter les vrais secrets uniquement au gestionnaire Render. `VITE_API_BASE_URL` est une valeur publique intégrée au bundle, jamais un secret. |

### Modifications de configuration faites

- `render.yaml` : PostgreSQL passe de `basic-256mb` à `basic-1gb`, en accord
  avec la cible de mémoire demandée. Le frontend reste un Web Service SSR tant
  que la conversion statique n'a pas été démontrée. La base et le service
  Render n'ont pas été modifiés.
- `render.yaml` : Gunicorn est configuré à un worker pour limiter le risque de
  dépassement mémoire sur le service API `starter` de 512 Mo. Cela ne garantit
  pas dix utilisateurs simultanés : les résultats du test de charge doivent
  décider s'il faut passer à deux workers, utiliser des threads ou augmenter
  le service.

## 3. Architecture proposée

### Option de départ, sans réécriture du frontend

- Workspace Hobby, sous réserve de confirmer le membre unique et les limites
  applicables au compte.
- API Django : Web Service payant `starter` (512 Mo), en Frankfurt.
- Frontend TanStack Start/Nitro : Web Service `starter` nécessaire pour le
  serveur actuel.
- PostgreSQL : `basic-1gb`, réseau privé Render, région Frankfurt ; choisir au
  Dashboard la capacité initiale d'au moins 2,5 Go si cette capacité est
  proposée. Ne pas augmenter ensuite à l'aveugle : Render indique que la
  capacité d'une base ne peut pas être réduite. Les augmentations ultérieures
  se font par multiples de 5 Go selon la documentation consultée ; confirmer
  cette règle pour le plan réel avant de choisir la capacité initiale.
- Disque médias privé : 1 Go actuellement déclaré ; mesurer le volume réel et
  prévoir une alerte avant saturation.
- `autoDeploy: false` reste en place. Aucun DNS n'est requis avant l'achat du
  domaine. Utiliser provisoirement les hôtes `onrender.com`.

### Option Static Site (économie à étudier, pas prête)

Render Static Sites n'ont pas de coût de calcul selon la documentation et
servent le contenu via CDN. Mais l'application actuelle démarre un serveur
TanStack Start/Nitro. Avant de remplacer ce service, il faut prouver une
construction statique compatible, configurer le fallback SPA pour les routes
profondes, puis tester navigation directe, actualisation, vérification de
facture, authentification, CSRF et téléchargement de fichiers. Aucun de ces
essais de conversion n'a été exécuté. Si la conversion échoue ou retire un
comportement serveur, conserver le SSR et son coût.

## 4. Budget estimatif

Références : [tarifs Render](https://render.com/pricing),
[fonctionnalités par plan](https://render.com/docs/platform-features-by-plan),
[tarifs et stockage PostgreSQL](https://render.com/docs/postgresql-creating-connecting),
[disques persistants](https://render.com/docs/disks),
[sites statiques et bande passante](https://render.com/docs/static-sites),
[domaines](https://render.com/docs/custom-domains).

La documentation publique confirme la facturation à l'usage, mais le rendu
consultable ici ne fournit ni une grille de prix complète ni un devis lié au
compte. Aucun accès au Dashboard Render du propriétaire n'est disponible dans
cette tâche. Les montants ci-dessous sont donc des **hypothèses de calcul
indicatives**, et non des tarifs confirmés ; vérifier chaque ligne dans
Billing avant toute création.

| Ressource | Estimation mensuelle | Commentaire |
|---|---:|---|
| Workspace Hobby | 0 USD | Aucun frais mensuel de workspace indiqué par Render ; le plan limite à un membre et 25 services selon la documentation. |
| API Django `starter`, 512 Mo | ~7 USD | Service payant ; vérifier le tarif affiché pour la région et le type exacts. |
| Frontend SSR `starter`, 512 Mo | ~7 USD | Nécessaire tant que le frontend reste un serveur Node. |
| PostgreSQL `basic-1gb` | ~19 USD | Tarif indicatif de catalogue ; plan retenu dans le Blueprint. |
| Stockage PostgreSQL 2,5 Go | ~0,75 USD si facturé à 0,30 USD/Go-mois | Le Dashboard doit confirmer si cette capacité est incluse ou facturée séparément. |
| Disque persistant de fichiers 1 Go | ~0,25 USD si facturé à 0,25 USD/Go-mois | Le montant réel dépend du disque et de la facturation Render affichés au compte. |
| **Sous-total SSR estimatif** | **~34 USD/mois** | Hors sauvegardes indépendantes, dépassement bande passante, taxes et domaine. Dépasse la cible de 25 USD d'environ **9 USD/mois**. |
| Frontend Static Site, si migration validée | ~0 USD de calcul | Peut réduire le sous-total d'environ 7 USD, mais n'est pas compatible directement avec le serveur SSR actuel. |
| **Sous-total après conversion statique hypothétique** | **~27 USD/mois** | Dépasse encore la cible d'environ **2 USD/mois**, avant sauvegardes indépendantes, trafic excédentaire, domaine et taxes. |

**Conclusion budget : 25 USD/mois ne couvrent pas de façon prudente la
configuration proposée avec base 1 Go et sauvegardes indépendantes.** Ne pas
réduire la base à 256 Mo, supprimer le disque ou désactiver les sauvegardes pour
faire apparaître un total inférieur.

### Postes non confirmés ou exclus

- **Sauvegardes PostgreSQL :** Render documente trois jours de PITR pour Hobby
  et sept jours pour les plans Workspace qui y donnent droit (notamment Pro).
  Les exports logiques Render sont conservés sept jours après leur création,
  mais leur création n'est pas une copie indépendante ni une politique
  automatisée. Confirmer le plan, le PITR et ses coûts dans le Dashboard.
  Si sept jours de PITR géré sont obligatoires, un workspace donnant droit à
  cette fenêtre peut être requis ; son éventuel coût par membre n'est pas inclus
  dans les sous-totaux.
- **Copie indépendante :** recommander un stockage objet distinct (ex. S3) pour
  les dumps et fichiers. Le coût dépend de la région, de la taille compressée,
  de la durée, des requêtes, du trafic et du Cron. La migration des fichiers
  locaux Django vers un stockage objet partagé est à préparer avant d'affirmer
  que les médias sont sauvegardés automatiquement. Ces coûts ne sont pas inclus
  dans les sous-totaux.
- **Domaine :** prix d'achat et renouvellement facturés par le registrar, donc
  impossibles à chiffrer avant le choix du fournisseur et du nom. Render fournit
  le TLS et HTTPS pour les domaines configurés ; les domaines supplémentaires
  au quota du workspace sont facturés selon sa page de domaines.
- **Trafic :** le site statique utilise le quota de bande passante inclus du
  workspace ; le montant d'un dépassement et le trafic API réel doivent être
  contrôlés dans Billing. Le SSR et les téléchargements de fichiers influent
  aussi sur le trafic.
- **E-mail SMTP, taxes et éventuel support** : exclus ; confirmer auprès du
  fournisseur choisi et du compte.

## 5. Sauvegarde et restauration

1. Confirmer que le PITR est activé pour PostgreSQL et noter sa fenêtre réelle.
   Avec Hobby, ne pas annoncer sept jours de PITR.
2. Configurer une copie logique planifiée `pg_dump` vers un stockage objet hors
   Render, avec chiffrement, versioning/rétention, droits minimaux et alertes.
   Render documente un modèle Cron vers S3, mais celui-ci demande un compte et
   des secrets AWS séparés.
3. Sauvegarder aussi les médias. Le Cron Render ne monte pas `/var/data` :
   déplacer les `FileField` vers un stockage objet compatible ou fournir une
   méthode d'export côté service, puis tester cette méthode. Les snapshots
   Render de disque sont une récupération de plateforme, pas la copie
   indépendante demandée.
4. Restaurer chaque copie dans une nouvelle base et un espace de fichiers
   isolé ; ne jamais remplacer la base de production lors d'un test.
5. Vérifier tables et relations, utilisateurs/rôles, ventes, paiements,
   stocks, factures, journaux, fichiers et principaux parcours métier.
   Consigner durée et résultat. Le test antérieur sur PostgreSQL temporaire
   portait sur une base fraîche sans données métier ni fichiers et ne valide
   pas le mécanisme Render.

RPO 24 h et RTO un jour ouvré restent des objectifs candidats, à approuver par
le propriétaire et à mesurer lors d'un exercice de restauration.

## 6. Déploiement, retour arrière et charge

### Déploiement contrôlé

1. Examiner et merger les changements dans le dépôt principal et le sous-module
   frontend ; lancer les workflows CI et exiger leurs validations sur `main`.
2. Vérifier la configuration Blueprint, les ressources, le prix final, le
   checkout du sous-module, les origines HTTPS et le contenu du build frontend.
3. Déployer d'abord en environnement isolé avec base distincte et données
   anonymisées ; vérifier `/healthz/`, connexion, CSRF, SMTP, fichiers et
   principaux parcours.
4. Faire une sauvegarde restaurable, examiner les migrations, puis obtenir
   approbation explicite avant les migrations et tout déploiement de production.
5. Après déploiement, surveiller erreurs, latence, mémoire, connexions DB,
   espace disque et sauvegardes.

### Retour arrière

Conserver l'image/build identifié par commit. Revenir au déploiement applicatif
précédent si le changement est compatible ; traiter une restauration de base
comme une opération séparée, approuvée et validée. Revenir à une ancienne image
**n'annule jamais** les migrations SQL. Ne jamais restaurer ou réinitialiser
PostgreSQL automatiquement dans un script de rollback.

### Test de charge proposé pour dix utilisateurs

- En préproduction uniquement, base et fichiers de test, aucun compte ni
  parcours de production.
- Utiliser k6 ou un outil équivalent : montée de 1 à 10 VU en 2 minutes,
  maintien 10 minutes, puis descente sur 2 minutes. Répéter une fois sur les
  parcours de lecture et une fois avec un petit volume de créations/éditions
  métier contrôlées dans l'environnement jetable.
- Prendre les routes authentifiées et les opérations réellement disponibles
  dans le schéma API du déploiement ; ne pas supposer des URL ni lancer des
  écritures sur la production.
- Proposition de seuil initial à valider : erreurs HTTP inattendues <1 %,
  p95 <1,5 s sur lectures usuelles, aucune croissance soutenue de mémoire,
  aucun épuisement des connexions PostgreSQL ni saturation du disque.
- Garder les sorties sans cookies, mots de passe, tokens ni données métier.
- Le test n'a pas été exécuté. Ajuster workers/RAM et plan DB à partir des
  résultats ; dix utilisateurs humains ne signifient pas nécessairement dix
  requêtes simultanées constantes.

## 7. Commandes et résultats de cette préparation

Commandes de vérification exécutées :

```text
python -c "import yaml; ... yaml.safe_load(render.yaml) ..."
docker compose -f compose.yaml config --quiet
PYTHON_DOTENV_DISABLED=1 DJANGO_ENV=development DB_ENGINE=sqlite \
  .venv\Scripts\python.exe manage.py check
npm run lint
npm run build
git diff --check
```

Résultats : YAML Render parsé ; Compose valide avec un `.env` temporaire copié
de `.env.example`, puis supprimé ; `manage.py check` réussit avec SQLite et
sans chargement du `.env` local ; lint passe avec 0 erreur et 16 avertissements
Fast Refresh ; build frontend client, SSR et Nitro réussi, avec avertissements
de bundling. Le premier lancement npm depuis la racine a échoué faute de
`package.json`, puis les mêmes contrôles ont réussi depuis `frontend/`.

Aucun test backend PostgreSQL, suite complète de tests, rebuild d'image Docker,
test de charge, run GitHub, commande de déploiement Render, migration ou
opération sur une base n'a été exécuté pour ce rapport. Les éventuels résultats
antérieurs des rapports DevOps ne valident pas ces changements. Les montants
n'ont pas été confirmés au Dashboard. Le `.env` local n'a pas été lu ni écrasé.

## 8. Étapes avant la production

1. Dans le Dashboard, relever le prix réel du workspace, du Web Service 512 Mo,
   de PostgreSQL 1 Go, des 2,5 Go de stockage, du disque, de la bande passante
   et des sauvegardes ; approuver le dépassement mensuel.
2. Choisir soit de garder le frontend SSR et budgéter son service, soit de
   financer et valider séparément une conversion Static Site.
3. Choisir et configurer la sauvegarde indépendante PostgreSQL **et médias** ;
   tester la restauration isolée.
4. Exécuter CI complète sur les commits exacts à déployer, puis le test de
   charge en préproduction.
5. Acheter le domaine plus tard, puis appliquer uniquement les valeurs DNS
   fournies par Render et configurer les origines Django exactes.
6. Obtenir l'approbation explicite avant la création des ressources et le
   premier déploiement de production.

**Aucun achat, DNS, secret, service ou déploiement Render n'a été déclenché.**
