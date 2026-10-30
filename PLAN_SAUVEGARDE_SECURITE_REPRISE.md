# DJIBEXA — Plan de sauvegarde, sécurité et reprise après incident

**État :** préparation à valider par le propriétaire ; aucune sauvegarde de
production, ressource cloud ou restauration de production n'a été exécutée.
**Périmètre observé :** code Django/React, `compose.yaml`, `render.yaml`,
workflows GitHub Actions et documentation du dépôt.

## 1. Résumé exécutif

La base PostgreSQL contient les données relationnelles métier ; les pièces
jointes et documents sont des fichiers séparés. En local Compose, ils résident
dans les volumes nommés `nexora-db` et `nexora-files`. Le Blueprint Render
monte un disque persistant de 1 Go sur `/var/data`, chemin utilisé par les
médias et les stockages privés.

Render documente, pour ses bases Postgres payantes, la récupération PITR
(récupération vers un point dans le temps), avec une fenêtre qui dépend du plan
de l'espace de travail. Render conserve les exports logiques sept jours après
leur création. Les disques persistants ont des snapshots automatiques toutes
les 24 heures, conservés sept jours et chiffrés au repos. Ces mécanismes sont
utiles pour une récupération rapide, mais ne constituent pas une copie
indépendante à long terme ; le snapshot du disque et la récupération PITR
peuvent aussi représenter des instants différents.

**État actuel :** pas de job de sauvegarde externe, de bucket, de politique de
rétention ou d'alerte configurés dans le dépôt. La sauvegarde des fichiers au-
delà des snapshots Render n'est pas démontrée. Un test local isolé de dump et
restauration du schéma PostgreSQL est passé, mais il n'incluait aucune donnée
métier réelle ni fichier téléversé. Tant que les sauvegardes indépendantes et
une restauration complète n'ont pas été vérifiées, DJIBEXA n'est pas déclaré
prêt pour la production.

**Décision à jour (30 octobre 2026) :** l'ancienne préférence Render uniquement
est remplacée par la demande d'une sauvegarde indépendante de PostgreSQL et des
fichiers. La rétention de sept jours, le RPO candidat 24 h et le RTO candidat
d'un jour ouvré restent à valider. Aucun fournisseur ou budget n'est approuvé,
et aucune ressource cloud n'a été créée. Render ne garantit pas sept jours de
PITR pour tous les plans ; confirmer les options du compte dans le Dashboard.
Voir [RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md](./RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md)
pour l'estimation et les arbitrages d'architecture.

## 2. Inventaire réel des données

Les modèles ci-dessous sont présents dans le registre Django du code actuel.
La base de production n'a pas été interrogée ; la présence de migrations et
modèles ne prouve pas qu'ils sont déployés ou peuplés dans une instance donnée.

| Domaine | Applications et modèles principaux |
|---|---|
| Identité, rôles, tenants, contrôle | `users.User` (hérite des utilisateurs Django ; rôles `admin`, `stock`, `sales`, rôles additionnels et administrateur plateforme), `core.Tenant`, `core.PlatformSettings`, `auth.Group`, `auth.Permission`, `admin.LogEntry` |
| Réglages, entreprise, journalisation, opérations | `core.Company`, `core.AppSetting`, `core.AuditLog`, `core.PlatformAuditLog`, `core.PlatformTaskRun`, `core.IdempotencyRecord`, `core.SyncOperation`, `core.Partner`, `core.TenantStorefront` |
| Produits et importations | `products.Category`, `products.Product`, `products.ProductCatalogImport` |
| Stock et traçabilité | `inventory.InventoryLocation`, `StockItem`, `StockMovement`, `StockTransfer`, `StockReplenishmentRequest`, `InventoryCostLayer`, `Carton`, `StockUnit`, `LabelPrintJob`, `SampleCarton`, `StockTransferCarton`, `InventoryCount`, `InventoryCountItem`, `StockFileImport` |
| Achats et fournisseurs | `suppliers.Supplier`, `ExchangeRate`, `SupplierImport`, `SupplierImportRow`; `purchases.PurchaseOrder`, `PurchaseOrderItem`, `ExternalPurchase`, `ExternalPurchasePayment`, `ExternalPurchasePaymentAllocation`, `ExternalPurchaseMovement`, `PurchaseReceipt`, `PurchaseReceiptItem`, `ReceiptQuarantine` |
| Clients, commandes et ventes | `customers.Customer`; `sales.Sale`, `CustomerOrder`, `SaleItem`, `CustomerOrderItem`, `SaleItemStockOrigin`, `SaleItemCostAllocation`, `SaleReturn`, `SaleReturnItem`, `SaleItemTrackedUnit`, `SaleReturnCostAllocation`, `SaleReturnQuarantine` |
| Factures et documents | `sales.Invoice`, `sales.InvoiceDocumentAttempt`, `invoices.InvoiceBranding`, `documents.Document`, `DeliveryNote`, `DeliveryNoteItem` |
| Paiements, créances, finances, dépenses | `payments.Payment`, `CreditLedger`, `PaymentAllocation`; `finance.FinancialAccount`, `FinancialTransaction`, `Fund`, `FundReturn`; `expenses.ExpenseCategory`, `Expense`, `ExpenseAttachment` |
| Notifications | `notifications.TenantCreditReminderSettings`, `notifications.Notification` |
| Infrastructure Django | `contenttypes.ContentType`, `sessions.Session`, `auth.Permission`, `auth.Group`, `admin.LogEntry`, et les tables de migrations `django_migrations` |

Les lignes de ventes, allocations de coût, mouvements de stock, paiements,
balances de crédit, transactions financières, factures et journaux d'audit
doivent être traités comme données critiques : une restauration partielle peut
créer des écarts entre soldes, stocks et pièces justificatives. Les comptes,
rôles, relations tenant/utilisateur, sessions et clés de configuration sont
également inclus dans une sauvegarde complète.

### Fichiers à sauvegarder avec la base

| Modèles/champs | Emplacement configuré | Nature |
|---|---|---|
| `users.User.photo`, `products.ProductCatalogImport.source_file`, `expenses.ExpenseAttachment.file` | `MEDIA_ROOT` ; Render `/var/data/media` | Photos, fichiers source de catalogues et justificatifs de dépenses |
| `sales.Invoice.signed_pdf`, `invoices.InvoiceBranding` (logo, image, filigrane, tampon, signature) | `PRIVATE_INVOICE_ROOT` ; Render `/var/data/private-invoices` | Factures signées et images privées de facture |
| `suppliers.SupplierImport.source_file` | `PRIVATE_SUPPLIER_IMPORT_ROOT` ; Render `/var/data/private-supplier-imports` | Imports fournisseurs et pièces justificatives sources |
| `core.TenantStorefront` (logos/couvertures brouillon/publiés) | `PRIVATE_STOREFRONT_ROOT` ; Render `/var/data/private-storefronts` | Images de vitrines privées |
| `documents.Document.file_url`, `products.Product.image`, `core.Partner.logo_url` | URL enregistrée en base, aucun `FileField` local pour ces champs | La sauvegarde PostgreSQL garde l'URL, pas le contenu hébergé par un tiers |

Les champs image/photo/import ont des `FileField`/`ImageField` et les stockages
privés sont des stockages locaux du système de fichiers. Le disque Render
`/var/data` couvre ces quatre racines selon `render.yaml`. Les fichiers
statiques collectés dans `/app/staticfiles` sont reconstruits depuis l'image ;
ils ne sont pas des données téléversées et n'ont pas besoin d'une sauvegarde
utilisateur.

Les certificats/clefs PDF de signature et autres fichiers d'exploitation
éventuels ne figurent pas dans ces champs et ne sont pas inclus automatiquement.
Inventorier leur emplacement séparément ; les conserver dans le gestionnaire de
secrets ou stockage chiffré, jamais dans le dump ni le dépôt Git.

## 3. Contrôles de sécurité et Docker/CI

- **Persistences locales :** `compose.yaml` déclare `nexora-db` pour
  `/var/lib/postgresql/data` et `nexora-files` monté sur `/var/data`. Les ports
  API et frontend sont liés à `127.0.0.1`; le port PostgreSQL n'est pas publié.
  Les volumes persistent à travers les redémarrages, mais restent sur le même
  hôte et ne sont pas une sauvegarde.
- **Render :** `render.yaml` utilise `DATABASE_URL` fourni par la ressource
  Postgres et monte le disque persistant sous `/var/data`. La base et le service
  API sont dans la même région configurée (Frankfurt). Les accès réels,
  allowlists, utilisateurs et journaux du compte Render ne sont pas visibles
  depuis ce dépôt et doivent être audités dans le tableau de bord.
- **CI :** `.github/workflows/ci.yml` utilise un service PostgreSQL 16 créé pour
  le job avec données de test ; il n'est pas relié au Render Postgres. Aucun
  workflow examiné ne lance une suppression/restauration de base de production.
  Le workflow de publication d'images n'a pas accès à `DATABASE_URL`.
- **Contexte d'image :** les `.dockerignore` racine, backend et frontend
  excluent les fichiers `.env`, bases SQLite locales, médias/fichiers, caches,
  `node_modules` et sorties de build. À garder ainsi ; ne jamais ajouter un
  dump, une copie de `/var/data`, un certificat privé ou un fichier de secret
  au contexte Docker.
- **Secrets :** le Blueprint génère `DJANGO_SECRET_KEY`, reçoit `DATABASE_URL`
  de la ressource Postgres et demande les paramètres SMTP comme variables
  synchronisées non commitées. Le `.env.example` n'est pas un coffre-fort.
  Aucun fichier `.env` local n'a été lu dans cet audit. Vérifier la rotation,
  le MFA et les droits des personnes ayant accès au Dashboard, GitHub et au
  fournisseur de sauvegarde.
- **Rôles PostgreSQL :** le dépôt ne définit pas de compte séparé de
  sauvegarde, migration et exécution. Le compte rendu par le Blueprint est
  fourni par Render ; les privilèges effectifs et les rôles présents doivent
  être vérifiés sans afficher de secrets. Recommandation : accès réseau privé,
  compte d'exécution limité au besoin applicatif, privilèges DDL pour les
  migrations uniquement, rôle de sauvegarde séparé en lecture, accès admin
  nominatif et MFA. Valider que Render permet ce modèle avant modification.
- **Audit :** `core.AuditLog`, `core.PlatformAuditLog` et `admin.LogEntry`
  sont dans PostgreSQL ; ils ne sont pas une archive immuable hors base.
  Limiter leur consultation, conserver les événements critiques hors service
  si une exigence de preuve le demande et éviter d'y inscrire secrets ou
  données personnelles inutiles.

## 4. Stratégie recommandée

### Base PostgreSQL — Render plus copie indépendante à configurer

1. Utiliser le PITR géré Render tant que la base reste sur Render Postgres
   éligible. Render documente trois jours de fenêtre pour Hobby et sept jours
   pour Pro ; une montée de plan étend la fenêtre vers le futur, sans
   reconstituer rétroactivement la période antérieure. Le Blueprint préparé vise
   `basic-1gb` ; confirmer le plan, la capacité de stockage initiale et l'offre
   effective du workspace dans le Dashboard. Ne pas annoncer une rétention de
   sept jours tant que cette vérification n'est pas faite.
2. Les exports logiques Render sont conservés sept jours après leur création,
   mais ne constituent pas une archive quotidienne/longue durée garantie.
   Créer un export dans le Dashboard avant un changement important, puis
   vérifier son contenu par une restauration isolée. Aucun export automatique
   ni alerte de réussite n'est actuellement configuré.
3. Vérifier chaque export : code retour de `pg_dump`, taille non nulle,
   `pg_restore --list`, SHA-256 comparé au manifeste d'origine, puis restauration
   régulière dans une nouvelle base isolée. Consigner l'heure UTC, la version
   client, la source et le résultat sans URL, mot de passe, données métier ou
   contenu sensible. Cette vérification logique doit être exécutée par
   l'exploitant ; elle n'est pas automatisée.
4. La demande à jour exige une copie indépendante hors Render. Le fournisseur,
   sa région, le chiffrement, la rétention, les alertes et le budget restent à
   choisir et à approuver. Aucun bucket ni secret de stockage n'est configuré.

### Fichiers

- Selon Render, les snapshots automatiques du disque sont quotidiens, conservés
  sept jours et chiffrés au repos. Vérifier leur état et leur disponibilité sur
  le disque attaché au service réel.
- En attendant la copie indépendante, les fichiers restent dépendants du disque
  et de ses snapshots. Les Cron jobs Render ne peuvent pas monter le disque
  persistant ; ils ne peuvent donc pas archiver `/var/data` directement. Il
  faut migrer les fichiers vers un stockage objet compatible ou concevoir et
  tester un export contrôlé côté service.
- Coordonner l'instant de la copie fichiers et de la sauvegarde DB : une
  sauvegarde de base peut référencer un fichier absent si le fichier n'est
  sauvegardé qu'ultérieurement. Faire une fenêtre de maintenance en lecture
  seule ou conserver un historique de fichiers/versioning suffisamment long
  pour couvrir le PITR retenu.
- Tester qu'un échantillon de `FileField` restauré est ouvrable, que son
  empreinte correspond, et que les permissions HTTP des factures/imports
  privés restent privées après restauration.

### Fréquence, conservation, alertes et coûts

| Couche | Cible proposée | Coût/dépendance à vérifier |
|---|---|---|
| PITR Render Postgres | Protection continue dans la fenêtre du plan (Hobby 3 j / Pro 7 j documentés) | Éligibilité du `basic-1gb`, fenêtre exacte et prix à vérifier dans Dashboard |
| Export logique Render | À déclencher dans le Dashboard avant changement risqué ; conservation 7 jours après création | Pas de job planifié dans le dépôt ; disponibilité et coût à confirmer |
| Fichiers `/var/data` | Snapshot Render quotidien, 7 j documentés, plus copie indépendante à concevoir | Disque 1 Go déclaré ; prix, quota, snapshots et stockage objet à vérifier |
| Test de restauration | Trimestriel et après changement majeur de schéma/stockage | Temps d'exploitation et coût temporaire d'une base/ressource de test |

Le propriétaire demande que les coûts soient estimés avant activation et
qu'une copie indépendante soit prévue. Tarifs cloud, taxes, coûts de transfert
et capacité peuvent évoluer. Aucun total ferme n'est calculable sans relever le
prix effectif dans le Dashboard, la taille réelle des données et l'éligibilité
des sauvegardes. Le Blueprint préparé déclare deux services `starter`, un
Postgres `basic-1gb` et un disque 1 Go ; ce n'est ni un devis ni une validation
de capacité.

## 5. Restauration PostgreSQL isolée

Pour une vérification, la cible doit être une nouvelle base de recette dédiée,
jamais la base de production. Une restauration dans une base existante ou avec
`--clean`, `DROP DATABASE`, `docker compose down -v` est interdite pour ce test.

1. Identifier l'export, le propriétaire/source, l'heure UTC, le commit/version,
   la taille, le manifeste et la clé/version de stockage. Vérifier que le
   checksum correspond à une référence conservée séparément et que l'accès est
   autorisé.
2. Télécharger le fichier par TLS vers un poste/runner approuvé, garder la
   copie chiffrée, restreindre ses permissions et ne pas la déposer dans Git,
   les journaux CI ou le contexte Docker.
3. Vérifier `pg_restore --list` et la somme de contrôle avant d'importer.
   Créer une instance/base neuve de même version majeure PostgreSQL, isolée du
   réseau de production, avec un compte dédié.
4. Restaurer sans propriétaire de production, dans une base vide :

   ```powershell
   createdb --host="$env:RESTORE_DB_HOST" --port="$env:RESTORE_DB_PORT" `
     --username="$env:RESTORE_DB_USER" --maintenance-db=postgres `
     "$env:RESTORE_DB_NAME"
   if ($LASTEXITCODE -ne 0) { throw "Échec de création de la base isolée" }

   pg_restore --exit-on-error --no-owner --host="$env:RESTORE_DB_HOST" `
     --port="$env:RESTORE_DB_PORT" --username="$env:RESTORE_DB_USER" `
     --dbname="$env:RESTORE_DB_NAME" "$env:BACKUP_FILE"
   if ($LASTEXITCODE -ne 0) { throw "Échec de restauration isolée" }
   ```

   Utiliser un mécanisme PostgreSQL de mot de passe protégé (ex. `PGPASSFILE`)
   dont l'ACL ne permet l'accès qu'au compte d'exploitation. Ne jamais placer le
   secret dans la ligne de commande ou le rapport. Les exemples ci-dessus ne
   suppriment pas les objets d'une base existante ; utiliser tout de même un
   nom neuf et vérifier avant connexion.
5. Avec les variables Django pointées exclusivement vers la cible isolée,
   exécuter `python manage.py check`, `python manage.py migrate --check` et
   vérifier le compte des migrations et l'existence des tables métier.
   Comparer des agrégats de volumes (nombre de tenants/utilisateurs/produits,
   ventes, paiements, mouvements de stock, factures et audits) à un manifeste
   préalablement produit ; ne pas exporter des données personnelles au rapport.
6. Vérifier les relations et contraintes d'intégrité par contrôles métier,
   puis tester les parcours de connexion, consultation catalogue/stock,
   création de vente de test, paiement, facture/PDF et accès aux justificatifs.
   N'effectuer aucune écriture de recette sur la base de production.
7. Restaurer séparément les fichiers dans un emplacement temporaire isolé ;
   comparer les références fichier en base, SHA-256 et permissions d'accès.
   Noter le temps, erreurs, tailles, version majeure, contrôles et responsable.
8. Détruire l'environnement temporaire uniquement après revue des journaux et
   accord de l'exploitant ; la règle de rétention des exports n'est pas
   modifiée par un test de restauration.

La commande `pg_restore --list` et un checksum prouvent seulement que l'archive
est lisible et inchangée par rapport au manifeste connu ; seule une restauration
et des tests applicatifs démontrent la récupérabilité. Les données réelles ne
doivent pas être copiées en CI ordinaire. Une recette issue de données
production doit être autorisée, minimisée ou anonymisée et isolée.

## 6. Réponse aux incidents

Pour tout incident, le responsable d'astreinte désigné consigne heure UTC,
symptômes, changements récents, personnes notifiées et décisions. Ne pas
publier de secrets, données client, export ou URL avec credentials dans les
tickets ou logs. Préserver les traces avant redémarrage si possible. Seul un
responsable autorisé peut approuver bascule, restauration, révocation ou
interruption des écritures.

| Incident | Premières vérifications et confinement | Récupération |
|---|---|---|
| Backend indisponible | Vérifier Render status, health check, logs expurgés, dernier deploy et DB reachability ; arrêter l'auto-déploiement si pertinent, ne pas redémarrer ou migrer à l'aveugle | Revenir à l'image/commit précédent si compatible avec le schéma ; vérifier `/healthz/`, auth, vente et journaliser. Un rollback d'image n'annule pas une migration |
| PostgreSQL indisponible | Vérifier statut Render, quota/disque, connexions, région, access rules et erreur applicative ; empêcher retries agressifs, ne pas supprimer/recréer la base | Si incident fournisseur, suivre support et status page. Si corruption/perte, démarrer PITR vers une nouvelle instance, comparer et valider avant de changer `DATABASE_URL` |
| Suppression ou corruption de données | Suspendre les écritures concernées, préserver heure exacte et journaux, identifier opérations/acteurs sans modifier la source | Préférer PITR vers une nouvelle base avant l'incident, vérifier les données, puis obtenir approbation explicite pour bascule ; réconcilier les écritures postérieures à l'heure restaurée |
| Secret compromis | Révoquer immédiatement le credential compromis (DB, SMTP, S3, GitHub) et limiter les comptes/session ; vérifier journaux d'accès sans recopier la valeur | Générer/mettre à jour dans le gestionnaire secret, redéployer contrôlé, tester accès et rotation des copies/clients ; vérifier les exports et audit |
| Déploiement défectueux | Stopper les déploiements, comparer version image/digest, migrations et logs ; préserver la base | Revenir à une version connue uniquement si le schéma reste compatible ; migration corrective en avant si besoin. Ne jamais prétendre que le rollback applicatif annule le schéma DB |
| Perte de fichiers téléversés | Passer les fichiers concernés en indisponibles/lecture seule, préserver le disque et les références en base, établir l'étendue | Restaurer snapshot ou copie objet vers un emplacement isolé ; valider hash et références, puis restaurer/basculer après approbation. Vérifier cohérence DB/fichiers |
| Indisponibilité hébergeur | Consulter status page officielle, éviter les changements répétés et collecter les heures d'incident | Attendre le rétablissement ou appliquer un plan de sortie approuvé depuis une sauvegarde externe ; vérifier DNS/domaines et certificat avant bascule. Ne pas inventer ni changer DNS sans autorisation |

## 7. Objectifs de reprise à approuver

Les valeurs ci-dessous sont des scénarios de discussion, non des engagements
validés par l'entreprise.

| Scénario | RPO candidat | RTO candidat | Implications |
|---|---:|---:|---|
| Render + copie indépendante quotidienne (cible à préparer) | 24 h candidat pour base et fichiers | 1 jour ouvré candidat, à mesurer | Stockage objet hors Render, alertes, coût récurrent, restauration documentée et validation propriétaire requis |
| PITR Render seul (couverture complémentaire) | Selon la fenêtre du plan | À mesurer | Ne couvre pas la perte du compte/hébergeur et ne remplace pas la sauvegarde indépendante |

**Décisions et limites :** les valeurs RPO 24 h/RTO un jour ouvré et la
rétention cible de sept jours sont des candidats ; le propriétaire demande
maintenant une copie indépendante et un chiffrage avant activation. La fenêtre
PITR effective (3 ou 7 jours selon le workspace) doit être confirmée dans le
Dashboard. Les objectifs demeurent candidats jusqu'à un exercice chronométré
et une validation formelle.

## 8. Résultats de l'audit et opérations non effectuées

- Lecture statique des modèles, champs de fichiers, chemins de stockage,
  paramètres Compose/Render, `.dockerignore`, workflows CI/publication et
  runbook maintenance. Aucun compte de production ou tableau de bord privé n'a
  été interrogé.
- Render documentation consultée : [PostgreSQL backups/PITR](https://render.com/docs/postgresql-backups),
  [snapshots des disques persistants](https://render.com/docs/disks),
  [sauvegarde Postgres vers S3](https://render.com/docs/backup-postgresql-to-s3),
  [Cron jobs](https://render.com/docs/cronjobs),
  [connexion PostgreSQL](https://render.com/docs/postgresql-creating-connecting).
- L'existence et le contenu d'une sauvegarde de production, les utilisateurs/
  privilèges réels, la capacité du disque, la taille/volume réel des données,
  les alertes, l'accès MFA, l'export hors compte et les coûts facturés ne sont
  pas vérifiables depuis le dépôt.
- Essai local jetable avec Postgres 16 : migrations appliquées à une base source
  neuve, export `pg_dump -Fc` non vide (386 282 octets), `pg_restore --list`,
  restauration sans suppression vers une base neuve, puis comparaison de
  82 tables et 138 lignes `django_migrations` source/restauration. `manage.py
  check` et `migrate --check` réussissent sur la cible restaurée. Les conteneur,
  réseau et bases de test éphémères ont été supprimés ; aucune donnée de
  production n'a été utilisée.
- Limite de cet essai : base fraîche sans clients, ventes ou autres données
  métier, et sans fichiers médias. Les relations avec des données, les
  agrégats métier, les droits de fichiers, l'intégrité SHA des vrais uploads,
  les snapshots Render et l'export externe restent à tester.
- Aucun dump de production, PITR, snapshot, changement IAM, export de fichiers,
  changement DNS, déploiement, migration production ou suppression n'a été
  déclenché.

## 9. Sources et étapes avant production

Avant validation production :

1. Confirmer par écrit les candidats RPO 24 h/RTO un jour ouvré et la limite
   visée de sept jours ; chiffrer Render et le stockage indépendant dans le
   Dashboard et chez le fournisseur avant toute activation.
2. Confirmer dans Render que le plan Postgres déployé est éligible à PITR, sa
   fenêtre, la région, les règles réseau, le rôle et la capacité effective.
3. Configurer une sauvegarde indépendante de la base et des médias après
   validation du fournisseur et du budget ; contrôler la réussite et la
   rétention des copies.
4. Exécuter une restauration complète à partir de cette copie dans un
   environnement isolé, avec vérification des agrégats, relations, fichiers
   et parcours métier.
5. Documenter les personnes responsables, les coûts constatés et le temps de
   reprise mesuré ; répéter au moins trimestriellement et après changement
   majeur de DB, de fichiers ou d'hébergeur.
6. Valider séparément un plan de migration hors Render et le changement de DNS
   avec autorisation expresse avant tout incident qui l'exigerait.
