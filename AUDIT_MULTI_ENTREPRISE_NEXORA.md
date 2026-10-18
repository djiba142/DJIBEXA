# Audit préalable — pilote multi-entreprise NEXORA

Date : 2026-10-16

## Objet et limite

Évaluer l'écart entre le fonctionnement actuel de NEXORA et la cible d'un
pilote avec administration centrale et espaces d'entreprise isolés. L'audit
initial est une lecture du code, pas une certification de sécurité. La
première tranche de fondation est ensuite décrite dans « État
d'implémentation » ; aucune base de production n'a été modifiée.

## État observé dans le dépôt

Le premier inventaire statique couvre les modèles Django, les URLconf des
modules, les classes de vues API, les contraintes d'unicité, les champs de
fichiers et les tâches de gestion périodiques. Les ensembles d'appartenance à
traiter sont les suivants :

| Domaine | Ressources observées | Propriété à établir |
|---|---|---|
| Plateforme | `Company`, `AppSetting`, `Partner`, `AuditLog`, `IdempotencyRecord`, `SyncOperation`, utilisateurs | Distinguer paramètres/licences et journal central des données métier ; scoper les opérations d'idempotence et de sync. |
| Catalogue et tiers | `Category`, `Product`, `ProductCatalogImport`, `Customer`, `Supplier`, `ExchangeRate`, imports et lignes fournisseur | Tenant propriétaire ; toute relation entrante doit référencer un produit/client/fournisseur du même tenant. |
| Stock et achats | `InventoryLocation`, `StockItem`, mouvements, transferts, ravitaillements, couches de coût, cartons, unités, inventaires, commandes et réceptions | Tenant propriétaire par emplacement/commande ; valider la cohérence tenant des produits, emplacements et documents liés. |
| Activité commerciale | ventes, devis/commandes client, lignes, retours, origines de stock, allocations, factures et tentatives de signature | Tenant propriétaire ; préserver les relations et identifiants de factures historiques. |
| Finance | paiements, crédits, comptes, transactions, fonds, dépenses et catégories | Tenant propriétaire ; conserver les allocations entre ventes, paiements, comptes et fonds du même tenant. |
| Documents et communication | documents, bons de livraison, pièces jointes, notifications, historiques et rappels | Tenant du parent ou du destinataire ; vérifier les liens de validation publique et le routage externe. |

- Le backend utilise PostgreSQL en production lorsque `DB_ENGINE=postgresql`,
  mais le moteur de base de données n'apporte pas à lui seul l'isolation entre
  entreprises (`backend/nexora_backend/settings.py`).
- `core.Company` reste le profil commercial historiquement unique, lu ou créé
  par `CompanyView` à l'identifiant `1` (`backend/core/models.py`,
  `backend/core/views.py`). Il possède maintenant un lien nullable vers
  `Tenant`, mais ses paramètres et usages ne sont pas encore scoppés.
- `User` possède maintenant les champs `tenant` et `is_platform_admin`, sans
  que tous les rôles et toutes les vues aient été adaptés. Les vues de gestion
  des utilisateurs étaient initialement globales ; elles limitent maintenant
  les lectures et modifications au tenant de l'administrateur, et affectent le
  tenant de l'appelant lors d'une création. Les autres usages d'utilisateurs
  restent à cartographier.
- Les modèles métier des ventes, comptes/mouvements financiers, fonds, dépenses
  et catégories de dépenses déclarent maintenant une clé étrangère nullable
  vers un tenant. Les paiements restent rattachés via leur client et leur vente,
  sans FK tenant dédiée. Documents et factures n'ont toujours pas tous un
  propriétaire tenant explicite. Les notifications ont maintenant un lien
  tenant nullable ; leur isolation API est décrite dans l'état d'implémentation.
  `InventoryLocation`
  est maintenant rattaché à un tenant ; les autres données de stock héritent
  encore leur périmètre de leur emplacement ou de leur document parent.
  `Category`, `Product`, `ProductCatalogImport`, `Customer`, `Supplier` et
  `PurchaseOrder` sont maintenant rattachés au tenant. Les routes de catalogue,
  clients, fournisseurs/imports, achats et plusieurs parcours d'inventaire
  filtrent leur propre périmètre. Les ventes sont maintenant rattachées à un
  tenant ; les paiements sont filtrés à travers le tenant du client et de la
  vente. Les routes finance/dépenses, leurs fichiers, rapports et opérations
  sur comptes/fonds sont maintenant scoppés ; les anciennes routes caisse,
  synthèse financière, rapport finance, tableaux de bord, rapport de ventes et
  recherche globale filtrent aussi leurs résultats au tenant courant. Les
  notifications disposent d'un premier cloisonnement décrit plus bas ; les
  chemins de stock non vérifiés de bout en bout ne sont pas isolés.
- La plupart des permissions contrôlent les rôles et certaines ressources,
  mais ne disposent pas encore de contexte d'entreprise. La permission du
  catalogue vérifie maintenant ce contexte. Le rôle `admin` est le rôle
  d'administration métier ; `is_superuser` est un contournement privilégié
  dans plusieurs permissions, et n'est pas un modèle d'accès central audité.
- Les factures sont isolées par le tenant de leur vente ; l'identité de facture
  et son branding sont configurés par tenant et le rendu utilise ce contexte.
  Les images de branding nouvellement téléversées sont stockées sous un chemin
  dédié au tenant. Les liens publics de vérification et les anciens fichiers
  doivent encore être validés de bout en bout en déploiement multi-entreprise.
- Plusieurs contraintes d'unicité sont actuellement globales, notamment les
  références de produits et d'emplacements, certains noms de catégories ou de
  comptes, et certaines références métier. Il faudra décider modèle par modèle
  lesquelles deviennent uniques par tenant, sans affaiblir les identifiants de
  vérification qui doivent rester globalement uniques.
- Les futurs uploads de branding des factures sont maintenant enregistrés sous
  un chemin dédié au tenant ; les références de fichiers existantes ne sont
  pas déplacées. Les imports fournisseurs, pièces jointes de dépenses et photos
  de profil restent à examiner : l'isolation doit couvrir leurs chemins,
  téléchargements et politiques d'accès, pas seulement les enregistrements ORM.
- Les liens publics de vérification de factures et de bons de livraison ainsi
  que la synchronisation hors ligne sont des parcours spécifiques à tester :
  les jetons publics doivent rester non énumérables et les opérations de sync
  doivent être liées au tenant de l'utilisateur.
- Les vues couvrent également tableaux de bord, rapports, recherche globale,
  caisse, finance, notifications, imports et exports. Ces vues agrègent souvent
  plusieurs modèles ; un filtrage du seul endpoint de liste ne suffira pas.
- Une commande Django planifiée génère et distribue des rappels de crédit
  (`notifications/management/commands/process_credit_notifications.py`). Elle
  applique maintenant les horaires de chaque tenant actif et utilise
  l'identité commerciale liée au tenant du client ; l'intégration externe reste
  configurée globalement.
- Le frontend utilise TanStack Router avec un groupe de routes authentifiées ;
  la navigation et les gardes actuels reposent sur les rôles métier, sans
  espace plateforme distinct lors de l'audit initial.
- Les routes API sont regroupées par module et la navigation frontend est
  pilotée par les rôles métier. L'audit initial n'avait identifié ni espace
  d'administration centrale ni route dédiée à la gestion de licences/essais ;
  une première tranche du Control Center est décrite ci-dessous.
- Le dépôt permet de rechercher les `Company` et les tables métier, mais la
  revue présente ne constitue pas encore une cartographie exhaustive de tous
  les chemins d'accès : tâches différées, exports, fichiers privés,
  synchronisation, recherche globale, notifications et intégrations restent à vérifier
  endpoint par endpoint avant toute mise en production.

## Conclusion

**NEXORA n'est pas actuellement multi-entreprise et ne doit pas être présenté
comme tel.** Ajouter seulement un écran central ou un filtre d'interface ne
séparerait aucune donnée. L'absence de clés d'entreprise sur les données
métier, combinée aux querysets globaux, crée un risque de divulgation et de
modification croisée si l'on crée un second espace sans refonte d'isolation
côté serveur.

La société KOUROUMA AUTO PARTS doit rester l'unique périmètre historique
pendant la préparation. Il ne faut ni créer des entreprises pilotes dans la
base active, ni modifier ou déplacer ses données avant une migration répétée et
vérifiée sur une copie isolée.

## Architecture cible retenue

1. Distinguer l'identité plateforme (`Tenant`/entreprise pilote et licence) du
   profil commercial utilisé sur les factures (`Company`). Le profil actuel
   devient explicitement rattaché à un seul tenant ; la licence et l'état du
   service ne sont pas déduits des paramètres métier.
2. Prévoir un rôle d'administration centrale séparé des rôles métier. Les
   actions centrales portent sur les métadonnées de licence et d'état, pas sur
   les ventes, factures ou clients. Aucun accès implicite aux données métier ;
   tout accès d'assistance éventuel doit être limité, autorisé et audité.
3. Attribuer un tenant à chaque utilisateur métier et à chaque enregistrement
   métier. Exiger le tenant côté serveur sur toutes les lectures, écritures,
   relations entrantes, rapports, téléchargements, imports, exports, recherche,
   notifications, tâches planifiées et opérations de synchronisation.
4. Appliquer les limites et l'état de licence côté serveur à la connexion et
   aux opérations protégées. La création de tenants reste réservée au niveau
   plateforme ; inscription publique désactivée.
5. Définir les contraintes d'unicité par tenant lorsque la donnée est
   naturellement propre à chaque espace, et conserver les identifiants
   historiques. Séparer aussi les chemins des fichiers privés par tenant.
6. Rendre les changements additifs et progressifs : créer les tenants et
   l'administration centrale, rattacher les données historiques à KOUROUMA
   AUTO PARTS, ajouter l'isolation aux parcours, puis contrôler l'absence de
   données orphelines et les accès croisés avant tout déploiement.

## Confidentialité du propriétaire de la plateforme

- Un compte `is_platform_admin` est un compte central, pas un administrateur
  métier. Ses rôles métier sont vides, même si d'anciens champs de rôle sont
  renseignés.
- L'authentification DRF refuse les API métier pour ce compte, y compris avec
  les mécanismes de session et Basic Auth. Seuls connexion/déconnexion et son
  profil ainsi que les API `/api/v1/platform/` lui sont accessibles. Les API
  centrales exigent `IsPlatformAdmin` ; elles ne donnent pas accès aux API
  métier.
- L'administration Django `/admin/` est également refusée aux comptes de
  plateforme, ainsi que les médias servis par Django. En production, un proxy
  qui sert directement les médias devra appliquer une protection équivalente.
  Les accès d'assistance métier restent absents tant que leur autorisation
  temporaire et leur journalisation n'auront pas été conçues.
- Cette barrière applicative ne peut pas garantir une impossibilité absolue
  d'accès pour une personne qui contrôle le serveur, le code ou les sauvegardes.
  Une garantie plus forte nécessitera des privilèges d'infrastructure limités,
  des clés/sauvegardes séparées et des accès privilégiés journalisés. Les logs
  applicatifs ne doivent jamais inclure de données commerciales détaillées,
  mots de passe ou secrets.

## Adresses des espaces

- Cible recommandée pour le pilote : une seule application et un seul
  déploiement, avec un sous-domaine NEXORA par entreprise, par exemple
  `kourouma.nexora.com`. Aucun sous-domaine n'est actuellement réservé ou
  configuré ; le domaine racine, le DNS, le proxy TLS et les certificats restent
  à mettre en place.
- Les domaines propres aux entreprises sont reportés à une étape premium
  ultérieure. L'architecture devra permettre de les ajouter sans déploiement
  indépendant par entreprise.
- Le routage futur devra résoudre l'hôte canonique vers un seul tenant actif,
  puis vérifier côté serveur que l'utilisateur et chaque donnée/fichier
  appartiennent à ce même tenant. L'en-tête `Host` ou le sous-domaine seuls ne
  constituent jamais une autorisation.
- Les hôtes normalisés seront uniques globalement ; un domaine personnalisé
  exigera une preuve de contrôle, un routage HTTPS vérifié et une association
  non ambiguë. La suspension d'un tenant/domaine devra refuser l'accès, jamais
  réutiliser ce domaine pour servir un autre tenant.
- Les tests devront couvrir hôtes inconnus, collisions, usurpation d'hôte,
  changement d'URL, cookies, clés de cache, téléchargements et domaines
  suspendus. Aucun routage de domaine ni modèle de domaine n'est activé tant
  que l'isolation des données métier n'est pas complète.

## Vérifications obligatoires avant activation

- Tests d'isolation A/B sur chaque module et chaque API, incluant les
  identifiants devinés, références liées, exports, fichiers et tâches
  différées.
- Vérification des permissions et limites de licence pour les rôles plateforme,
  administrateur d'entreprise et utilisateurs métier.
- Test de migration PostgreSQL sur copie anonymisée ou synthétique : nombres de
  lignes avant/après, relations, contraintes, factures et historique inchangés.
- Tests de restauration, sauvegardes et rétention indépendants de l'état
  suspendu ou expiré d'un tenant.
- Revue de sécurité avant de créer les entreprises pilotes réelles.

## Décisions confirmées par le propriétaire

- Aucun plafond global d'entreprises par défaut ; une limite explicite de
  plateforme et les plafonds utilisateurs par entreprise/plateforme restent
  configurables.
- L'administration centrale crée l'entreprise et son administrateur initial ;
  l'administrateur d'entreprise invite ensuite les membres autorisés.
- La production KOUROUMA AUTO PARTS reste inchangée pendant les essais, menés
  sur une copie isolée. Le rattachement des données historiques sera préparé
  séparément et migré seulement après approbation.
- L'essai dure trois mois calendaires à partir de l'activation explicite de
  l'entreprise.
- À l'expiration ou à la suspension, les données sont conservées, les
  opérations sont bloquées selon le statut et aucune suppression automatique
  n'est effectuée sans décision explicite.
- L'accès d'assistance aux données métier est exceptionnel : autorisation de
  l'administrateur de l'entreprise, durée et périmètre limités, journalisation
  complète.
- L'espace et la licence seront portés par un `Tenant` distinct ; le profil
  commercial `Company` lui sera rattaché.

## État d'implémentation

La première tranche additive est en place dans le code :

- `Tenant` porte le nom et le slug d'espace, le statut, les dates d'essai,
  le plafond d'utilisateurs et les modules activés.
- `PlatformSettings` porte un plafond global optionnel d'espaces et le plafond
  global d'utilisateurs ; aucun plafond d'espaces n'est appliqué par défaut.
- Un tenant a par défaut un plafond de dix utilisateurs et une liste de modules
  activés vide ; le plafond est vérifié côté serveur lors de la création et de
  la réactivation des comptes.
- `Company` a un lien unique nullable vers `Tenant` ; `User` a un lien nullable
  vers `Tenant` et un indicateur distinct d'administration plateforme.
- Les comptes plateforme ont maintenant une liste de rôles métier vide. Les
  authentificateurs DRF de session et Basic refusent l'accès aux API métier ;
  leur profil/connexion/déconnexion restent accessibles. Un middleware leur
  interdit également l'admin Django et les médias servis par Django.
- Le Control Center `/platform` dispose d'une vue de métadonnées, de la
  création d'espaces en attente, de l'ajustement de capacité, du démarrage
  explicite d'un essai de trois mois, de la suspension/reprise et d'un journal
  d'audit central distinct du journal métier. Il peut inviter le premier
  administrateur d'un espace via un lien à usage unique de choix de mot de
  passe ; le compte reste inactif jusqu'à validation du lien et l'accès métier
  reste bloqué tant que l'essai n'est pas activé. Le
  démarrage d'un essai et la suspension demandent une confirmation ; les
  mutations confirment leur succès ou exposent l'erreur de l'API. Les états et
  les dates sont localisés dans les quatre langues prises en charge. Le nombre
  d'espaces n'a pas de plafond par défaut ; un plafond global reste possible si
  une valeur est explicitement configurée. La limite antérieure de dix espaces
  est retirée par migration.
- Les rubriques centrales `/platform/services`, `/platform/incidents`,
  `/platform/security`, `/platform/backups`, `/platform/maintenance`,
  `/platform/plans`, `/platform/support`, `/platform/resources` et
  `/platform/audit` sont accessibles depuis le menu plateforme. Santé,
  ressources et audit réutilisent les API réelles. Les rubriques sans source
  opérationnelle affichent explicitement « non configuré » ; elles ne
  constituent pas encore des fonctions de production.
- Le journal central est paginé côté API, avec filtres d'action et recherche
  sur le nom/identifiant de l'espace ou le compte administrateur. L'interface
  expose les filtres, la navigation entre pages et les détails connus des
  opérations. L'API limite elle aussi les détails aux champs typés attendus
  selon l'action et ne transmet pas les propriétés JSON supplémentaires.
- Une première page `/platform/monitoring` et une API centrale protégée
  mesurent la réponse de l'application, une requête de santé PostgreSQL et
  l'espace disque du volume hébergeant le code. La commande planifiée
  `process_credit_notifications` conserve le résultat et les métadonnées des
  exécutions ; l'API n'expose que les dix plus récentes, avec horaires, durée et
  uniquement la classe d'exception. Ni le message d'erreur ni les données de
  notification ne sont exposés. L'écran précise que cet historique ne confirme
  pas la fréquence du planificateur.
  La collecte générale des erreurs serveur/applicatives, des autres tâches, des
  sauvegardes et des alertes de sécurité n'est pas configurée et reste signalée
  comme telle, pas comme opérationnelle. Le disque mesuré est celui de
  `BASE_DIR`, pas nécessairement celui des médias ou de la base si ces services
  résident sur d'autres volumes.
- Les authentificateurs de session et Basic bloquent les requêtes métier des
  comptes rattachés à un tenant absent, en attente, suspendu ou expiré. La
  connexion métier vérifie également le statut après validation des
  identifiants. Les limites d'utilisateurs par tenant et au niveau global sont
  contrôlées lors de la création/réactivation des comptes.
- Ces contrôles protègent les routes authentifiées au runtime standard ; les
  tests de sécurité correspondants utilisent des sessions et Basic Auth réels,
  car `force_authenticate` contourne volontairement les authentificateurs.
- Les endpoints de gestion des utilisateurs exigent maintenant un
  administrateur métier rattaché à un tenant, excluent les administrateurs de
  plateforme, limitent les lectures/écritures au tenant de l'appelant et
  affectent ce tenant côté serveur lors de la création.
- La migration de plateforme crée toujours les paramètres centraux, mais ne
  précrée plus de tenant sur une installation neuve. Lors d'une mise à niveau
  avec un profil commercial historique `Company` d'identifiant 1, elle conserve
  le rattachement historique KOUROUMA AUTO PARTS. Les migrations de backfill
  laissent les données sans tenant intactes lorsqu'aucun tenant historique
  n'existe ; aucun enregistrement métier n'est supprimé. Un premier tenant
  doit être créé explicitement avant l'accès métier sur une installation neuve.
- Première tranche de propriété métier : `Category`, `Product` et
  `ProductCatalogImport` ont un lien nullable vers `Tenant`. La migration
  rattache les lignes déjà présentes au tenant historique ; les routes du
  catalogue filtrent les catégories et produits, refusent une catégorie d'un
  autre tenant et limitent les imports à leur tenant. Le fallback vers des
  objets sans tenant ne fonctionne que dans une base mono-tenant pour
  préserver les parcours historiques pendant la transition.
- Deuxième tranche : `Customer` est rattaché au tenant historique par
  migration ; les listes, détails et historiques/avoirs client sont filtrés
  par tenant. Les créations affectent le tenant côté serveur et les comptes
  sans rattachement non ambigu sont refusés sur ces routes. Les relations
  inverses depuis les ventes, paiements, factures et notifications restent à
  scoper avant de considérer ces domaines comme isolés.
- Troisième tranche : `Supplier` est rattaché au tenant historique. Les listes,
  détails, imports, corrections, rapprochements, confirmations et
  téléchargements de fichiers fournisseur vérifient le tenant ; la détection
  et le rapprochement manuel ne peuvent sélectionner que des produits du même
  tenant. Les taux de change restent des données partagées globales, et les
  commandes d'achat générées depuis un import doivent encore être isolées dans
  le périmètre des achats.
- Quatrième tranche : `PurchaseOrder` est rattaché au tenant de son fournisseur
  pour les données historiques ; les commandes et les réceptions héritent de
  ce périmètre. Les commandes, réceptions, coûts d'acquisition, quarantaines,
  suggestions de réapprovisionnement et rapport achats sont filtrés côté
  serveur. La création empêche les associations à un fournisseur, produit ou
  commande d'un autre tenant ; les actions sensibles sur les réceptions et les
  quarantaines utilisent aussi des objets limités au tenant.
- Cinquième tranche : `InventoryLocation` possède un tenant et la migration
  rattache les emplacements historiques au tenant KOUROUMA AUTO PARTS. Les
  listes/détails d'emplacements, niveaux et mouvements de stock, transferts,
  cartons, unités, demandes de ravitaillement et inventaires sont filtrés via
  des emplacements accessibles au tenant. Les rapports d'inventaire et la
  sélection d'emplacements de vente utilisent également ce périmètre. Les
  serializers vérifient plusieurs associations produit/emplacement/transfert
  entre tenants et attribuent le tenant côté serveur aux nouveaux
  emplacements. Le mode historique mono-tenant garde un fallback limité pour
  les objets sans tenant ; les parcours directs ORM et toutes les relations
  indirectes stock/vente ne sont pas encore prouvés de bout en bout.
- L'activation calcule trois mois calendaires à partir de la date choisie et
  refuse de redémarrer un essai déjà activé.
- Lors d'une mise à niveau contenant le profil commercial historique, le tenant
  historique reste actif sans date de fin d'essai ; une installation neuve ne
  reçoit pas ce tenant implicitement. Les migrations n'activent aucun nouvel
  essai et n'imposent encore aucun blocage de licence.
- Sixième tranche : le tenant KOUROUMA AUTO PARTS n'est plus précréé sur une
  installation neuve. Les backfills dépendants ne lèvent plus d'erreur quand
  aucun tenant historique n'existe et conservent les lignes sans tenant ; le
  rattachement historique reste actif seulement quand un profil `Company`
  historique doit être préservé. Le lanceur de tests crée séparément un tenant
  de compatibilité dans sa base éphémère, sans modifier le comportement
  d'installation. Le premier tenant d'une installation neuve doit être créé
  manuellement avant d'autoriser des utilisateurs métier.
- Septième tranche : `Sale` et `CustomerOrder` ont maintenant une FK tenant
  nullable ; la migration rattache les ventes et commandes historiques sans
  supprimer de lignes et interrompt le déploiement si elle détecte des
  références principales contradictoires. Les routes de ventes, commandes,
  retours, quarantaines et catalogue de vente filtrent les objets et les
  relations entrantes par tenant. Les listes/détails de factures, QR,
  téléchargements PDF et émissions/signatures utilisent le tenant de la vente ;
  l'image QR, qui révèle le jeton de vérification public, exige maintenant une
  session métier du même tenant. La vérification publique reste accessible par
  jeton UUID et ne renvoie pas les informations client ni les lignes d'articles.
  L'identité de facture et ses fichiers restent globalement configurés : tant
  qu'ils ne sont pas isolés, les routes de configuration sont refusées dès que
  plusieurs tenants existent. Huitième tranche : les endpoints de paiement,
  reçus, soldes client et rapports de crédit exigent un utilisateur rattaché à
  une entreprise ; les paiements et ventes visibles, les ventes affectées et
  les allocations retournées sont filtrés par tenant. Les identifiants de
  clients/ventes étrangers sont rejetés, et les requêtes de détail client
  répondent 404 hors tenant. Les anciens objets sans tenant restent visibles
  uniquement via le mode de compatibilité mono-tenant. Le modèle `Payment`
  reste rattaché au tenant par son client (sans FK tenant dédiée).
- Neuvième tranche : comptes et mouvements financiers, fonds, catégories et
  dépenses portent maintenant leur tenant ; les migrations de rattachement
  historique s'arrêtent si l'appartenance est ambiguë et préservent l'unicité
  des noms sans tenant. Les créations de transactions issues des paiements,
  dépenses, transferts et retours de fonds conservent le tenant. Les lectures,
  modifications, rapports, pièces jointes et relations entrantes sont filtrés ;
  les routes historiques caisse, flux de caisse, synthèse financière, rapport
  finance, tableaux de bord, rapport de ventes et recherche globale utilisent
  aussi des données du tenant courant. Les paiements restent sans FK tenant et
  sont limités par leur client et leur vente.

**Ces tranches n'activent pas encore le multi-tenant complet** : le rattachement et le
scoping restent partiels et couvrent le catalogue, les clients, les
fournisseurs/imports, les achats, plusieurs parcours d'inventaire ainsi que
des routes de ventes, commandes, factures, paiements/crédits et finance.
Les notifications ont reçu un premier cloisonnement API et une planification
des rappels par tenant, mais les tâches différées autres que le planificateur
de rappels et les relations indirectes restent à valider de bout en bout.
L'intégration WhatsApp est encore configurée globalement. Les autres rapports,
tâches et fichiers hors
imports fournisseur, ainsi que les relations indirectes de stock et de vente,
ne sont pas isolés de bout en bout ; des relations peuvent encore relier des
ressources de tenants différents. Les contrôles de licence bloquent désormais
les connexions et requêtes métier selon le statut du tenant, mais ne remplacent
pas l'achèvement des contrôles d'isolation endpoint par endpoint. L'invitation
du premier administrateur est implémentée mais nécessite un service SMTP
configuré et vérifié en production. Le Control Center permet les opérations
centrales de base, mais ne crée pas encore de domaine. Ne pas créer de deuxième
entreprise pilote réelle avant la réalisation et la validation des phases
restantes. Le routage par domaine n'est pas implémenté.

Avant le scoping ciblé des utilisateurs, la suite backend complète a réussi
sur PostgreSQL (**262 tests**, contrôle système sans problème). Après les
modifications d'isolation et de confidentialité, la suite `users.tests` a
réussi sur PostgreSQL (**38 tests**) ; trois tests couvrant l'isolation des
comptes et les authentificateurs plateforme passent aussi sur SQLite. La suite
complète a ensuite réussi sur PostgreSQL après l'ajout du Control Center
(269 tests), puis après la première tranche catalogue (**271 tests**). Après
les derniers ajustements du catalogue, ses **21 tests ciblés** réussissent
aussi sur PostgreSQL. Les **7 tests clients ciblés** réussissent sur PostgreSQL.
Les **24 tests fournisseurs** et les **18 tests achats** ciblés réussissent
sur PostgreSQL ; ils couvrent notamment les rapprochements de produits et
commandes d'un autre tenant. Les **3 tests A/B achats** vérifient les listes,
les actions de commandes/réceptions/quarantaines, le rapport, les suggestions
et les créations avec des identifiants étrangers. La suite backend complète
après la tranche achats passe sur PostgreSQL (**277 tests**, contrôle système
sans problème) ; `makemigrations --check --dry-run` ne détecte aucune migration
manquante. Pour la tranche inventaire, les **42 tests d'inventaire** passent sur
PostgreSQL, ainsi que **14 tests ciblés de non-régression** achats/rapports/
ventes et tenant A/B. La tranche de retrait du tenant implicite a été validée
par une migration SQLite vierge (**0 tenant, 1 PlatformSettings**), les tests
de préservation avec/sans profil commercial historique, et la suite backend
complète PostgreSQL (**282 tests réussis**). `manage.py check`,
`makemigrations --check --dry-run` et `git diff --check` passent. Une première
exécution plus large de 161 tests avait révélé 11 erreurs/régressions de
compatibilité mono-tenant ; les cas concernés ont été corrigés, puis les tests
ciblés et la suite complète ont réussi. Ces résultats ne prouvent pas
l'isolation de bout en bout de l'inventaire, des ventes ni des autres API
consommatrices. Après la septième tranche, les **19 tests ciblés** des factures,
de leurs API et de l'isolation des ventes passent sur PostgreSQL ; la suite
backend complète passe sur PostgreSQL (**286 tests réussis**). `manage.py check`
ne signale aucun problème et `makemigrations --check --dry-run` ne détecte
aucune migration manquante sur SQLite en mémoire. La même vérification de
migrations n'a pas pu terminer sur PostgreSQL local : le pilote a remonté une
erreur de décodage UTF-8 à la connexion après la suite de tests. Après la
huitième tranche, les **22 tests ciblés** paiements/ventes passent sur
PostgreSQL, dont les lectures A/B des paiements et crédits, les réponses 404
pour les clients hors tenant, le rejet des références de clients et ventes
étrangers, le masquage d'allocations vers des ventes d'un autre tenant et le
refus des utilisateurs non rattachés en environnement multi-tenant.
`manage.py check`, `makemigrations --check --dry-run` sur SQLite
en mémoire et `git diff --check` réussissent. La suite backend complète n'a
pas été relancée après cette tranche. Après la neuvième tranche, les suites
PostgreSQL `core`, finance, dépenses, paiements et ventes passent (**119 tests
réussis**), incluant les scénarios A/B des routes caisse, rapports, tableaux de
bord et recherche globale, ainsi que l'unicité des noms historiques sans
tenant. `manage.py check`, `makemigrations --check --dry-run` sur SQLite en
mémoire et `git diff --check` passent. La suite backend complète n'a pas été
relancée après cette tranche. Après la première tranche opérationnelle du
Control Center, les suites `core.tests.CoreApiTests` et `users.tests` passent
sur PostgreSQL (**82 tests**). `manage.py check`,
`makemigrations --check --dry-run` et `git diff --check` passent. Le frontend
construit avec `npm run build`. Le contrôle visuel sur une base SQLite isolée
a exercé la création d'un espace, l'activation, la suspension, la reprise,
l'ajustement de capacité et l'affichage du journal central. Cette vérification
visuelle n'est pas une validation complète de l'isolation métier.
La page Monitoring et l'API `/api/v1/platform/monitoring/` ont ensuite été
ajoutées : les **2 tests dédiés** vérifient l'autorisation plateforme et la
réponse des mesures ; `manage.py check`, `makemigrations --check --dry-run`,
`git diff --check` et `npm run build` réussissent. Le parcours navigateur
authentifié confirme l'affichage du statut de l'application, de la base, du
disque et des cinq sources encore non configurées.
Le parcours d'invitation du premier administrateur est maintenant connecté au
Control Center : l'e-mail contient un jeton de définition de mot de passe, le
compte reste inactif avant acceptation, l'acceptation contrôle de nouveau les
plafonds de capacité et l'action est journalisée sans adresse e-mail ni jeton.
Les tests `core.tests.CoreApiTests`, `core.tests.ProductionSettingsTests` et
`users.tests` réussissent sur SQLite éphémère (**102 tests**), incluant l'échec
d'envoi e-mail avec rollback et le blocage de connexion tant que l'essai n'est
pas activé. `manage.py check`, `makemigrations --check --dry-run`,
Ruff ciblé, Prettier, ESLint ciblé et `npm run build` passent ; ESLint signale
deux avertissements Fast Refresh préexistants dans `locale.tsx`, et Vite
signale un bundle client supérieur à 500 Ko. L'envoi e-mail, la migration et
les parcours métier restent à valider avec les services et données réels de
préproduction ; ces vérifications locales ne certifient pas la production.

La fondation de vitrine d'entreprise est également ajoutée : le brouillon et
la version publiée sont stockés par tenant, l'édition/publication est réservée
à l'administrateur de cet espace et la publication est journalisée. L'éditeur
est accessible dans l'ERP à `/vitrine` ; la route publique
`/entreprise/<slug>` ne sert que les vitrines publiées d'espaces actifs.
L'ancienne page Kourouma reste un fallback pour préserver son contenu jusqu'à
la publication de sa configuration, uniquement tant que son espace est actif ;
un espace suspendu ou expiré ne reçoit pas ce fallback. Les six tests dédiés
passent sur une base SQLite temporaire ; le build frontend réussit. Le
contrôle visuel du parcours public a utilisé une réponse API simulée, car le
serveur Django n'était pas démarré ; l'éditeur et la vitrine publiée ont été
contrôlés à 390 px, avec vérification des sections activées et désactivées, du
titre de page et de l'absence de débordement horizontal. Une erreur réseau
n'active pas le fallback Kourouma. Aucun DNS, sous-domaine ou domaine
personnalisé n'est configuré par cette tranche. La gestion des médias de
vitrine est décrite ci-dessous.
Pour activer ensuite
des sous-domaines, il faudra configurer le DNS wildcard et TLS, autoriser les
hôtes côté déploiement, puis implémenter et tester la résolution serveur
hôte-vers-tenant ; le slug URL actuel ne constitue pas une configuration de
domaine. La migration de vitrine et les migrations d'identité de facture
restent à appliquer uniquement après validation sur une copie de
préproduction.

La vitrine accepte maintenant un logo et une image de couverture dans un
stockage privé distinct des médias génériques. Les fichiers sont limités aux
formats PNG/JPEG/WebP, à 5 Mo et à 16 millions de pixels ; le backend vérifie
le contenu réel et l'extension. Les images de brouillon ne sont accessibles
qu'à l'administrateur du tenant ; leur publication copie les références dans
les champs publiés, seuls accessibles par l'URL publique d'un espace actif.
Remplacer ou retirer un brouillon ne modifie donc pas la vitrine publiée avant
publication. Les 10 tests de `core.test_storefront`, y compris le chemin de
stockage par tenant, le contrôle d'accès, le cycle brouillon/publication et le
rejet de fichiers invalides, passent sur SQLite éphémère.
`manage.py check` et `makemigrations --check --dry-run` passent également.
Le contrôle visuel a détecté puis corrigé un refus 406 de l'aperçu privé :
l'en-tête `Accept: image/*` ne correspondait à aucun renderer DRF. Le
téléchargement de l'aperçu utilise maintenant `Accept: */*`. L'éditeur et la
vitrine publique affichent les deux images, et les deux endpoints privés
répondent 200 avec `image/png`. Le contrôle navigateur à 390 px confirme
l'absence de débordement horizontal ; les aperçus logo/couverture chargent
leurs dimensions attendues (360×120 et 1440×480). ESLint ciblé et `npm run
build` passent ; le build conserve un avertissement existant de bundle
JavaScript supérieur à 500 Ko.

Une section publique « Quelques produits à découvrir » est ajoutée au bas de
la vitrine publiée. Son endpoint dédié ne renvoie que les produits actifs avec
photo du tenant demandé, huit au maximum, et n'expose ni prix ni quantité.
Il ne répond pas tant que la vitrine n'est pas publiée ou que le tenant n'est
pas actif. Les dix tests de `core.test_storefront` couvrent aussi la sélection
et l'isolation A/B de ces produits. Le contrôle navigateur avec données et
images de démonstration confirme les cartes à 390 px et 1440 px, une colonne
sur mobile, quatre emplacements de grille sur desktop et aucun débordement
horizontal. Le contrôle visuel utilise des réponses API/images simulées ;
la réponse réelle est couverte par les tests backend.

Les notifications ont maintenant une FK nullable vers le tenant. Le backfill
de migration ne rattache que les notifications dont les relations identifient
un tenant unique ; les enregistrements ambigus restent intacts. Les API de
liste, détail, historique, export, lecture et envoi filtrent les notifications
par tenant, et les créations valident la cohérence tenant des références de
vente et de client. Les rappels créés par API sont limités à l'entreprise
appelante ; les anciens comptes sans tenant gardent un accès de compatibilité
uniquement lorsqu'il n'existe qu'un seul tenant, sans rendre visibles les
notifications attribuées à un autre utilisateur. Les réglages de rappels
possèdent maintenant une configuration par tenant ; la migration copie les
valeurs historiques vers les tenants existants sans supprimer les anciens
paramètres globaux. La tâche planifiée génère selon le calendrier propre à
chaque tenant actif, tout en conservant le mode historique mono-tenant. Les
messages WhatsApp en attente ne sont distribués que pour les tenants actifs ;
les notifications sans rattachement identifiable ne sont pas distribuées en
mode multi-tenant, et les références héritées ne sont admises qu'en mode
mono-tenant si leurs relations restent cohérentes.
les notifications de paiement sont rattachées au tenant du client et le
paramètre de devise est résolu depuis l'entreprise de ce même tenant. Les
notifications internes de ravitaillement conservent leur politique de
destinataires et leur visibilité historiques. Les paramètres de connexion du
fournisseur WhatsApp restent globaux. Les 84 tests `notifications.tests`,
`payments.tests` et `inventory.tests` passent sur SQLite éphémère. Le backfill
de paramètres a été vérifié sur SQLite isolée. `manage.py check`,
`makemigrations --check --dry-run` et `git diff --check` passent.

## Plan d'ingénierie autorisé — livraison par étapes

1. **Cartographier exhaustivement les données et accès** : inventaire des
   modèles, API, requêtes ORM, validations de relations, permissions, tâches,
   rapports, exports, fichiers, notifications et synchronisation. Établir pour
   chaque ressource si elle appartient au tenant, à un utilisateur ou à la
   plateforme.
2. **Préparer la migration sur copie isolée** : produire une copie synthétique
   ou anonymisée de la base de référence ; mesurer les volumes et relations ;
   établir des contrôles avant/après ; préserver les identifiants et l'historique.
3. **Terminer le périmètre d'entreprise côté backend** : compléter l'entité
   plateforme `Tenant`/licence distincte du profil commercial `Company`,
   rattacher les données métier, filtrer les querysets côté serveur et valider
   que les clés étrangères entrantes appartiennent au même tenant. Les
   migrations doivent d'abord conserver les données comme un seul tenant
   historique.
4. **Compléter les invitations et licences** : la création centrale d'espaces
   en attente, l'invitation du premier administrateur par lien à usage unique,
   l'activation explicite pour trois mois, suspension/reprise et contrôles
   serveur de statut et de capacité sont en place. Vérifier le SMTP réel et le
   parcours d'acceptation avant un pilote. L'inscription publique reste
   désactivée.
5. **Ajouter le routage des domaines** après l'isolation métier : sous-domaines
   NEXORA pour le pilote, vérification stricte hôte/tenant/utilisateur et tests
   de collisions, suspension, caches et fichiers ; domaines personnalisés
   seulement dans une phase ultérieure.
6. **Étendre l'espace NEXORA Control Center** : la première tranche existe,
   séparée des rôles métier et limitée aux métadonnées de gestion, avec un
   journal central ; la garder sans accès courant implicite aux données
   commerciales.
7. **Prouver l'isolation** : tests multi-tenant A/B couvrant chaque API,
   identifiants manipulés, recherches, rapports, téléchargements, import/export,
   synchronisation et tâches différées ; tests limites/licences ; migrations et
   restauration sur PostgreSQL isolé ; contrôles visuels.
8. **Autoriser le pilote seulement après validation** des résultats sur copie,
   de la politique de conservation après expiration et du processus
   d'assistance exceptionnelle audité.

Le modèle `Tenant` séparé de `Company`, les règles de pilote et la réalisation
sur copie isolée sont confirmés. La migration de fondation a été testée sur une
base synthétique ; le rattachement de toutes les données métier et la
cartographie endpoint par endpoint restent à terminer. Toute validation ou
migration doit se faire sur une copie isolée, sans modification de la
production.

## Recette complémentaire du 2026-10-18

Sur la base SQLite temporaire dédiée à l'audit, le parcours visuel a permis de
créer un produit synthétique, un emplacement de stockage et une entrée de
10 unités. La page Stock a ensuite affiché 10 unités, un coût de 1 000 000 GNF,
une valeur de vente de 1 500 000 GNF et l'entrée correspondante dans
l'historique. La commande fournisseur de 5 unités a été créée puis soumise.

Le premier essai de réception a été rejeté comme prévu, car l'API exige
l'approbation préalable. L'écran de détail ne proposait pas cette action aux
administrateurs ; une action d'approbation réservée au rôle administrateur a
été ajoutée et le parcours doit être rejoué après validation du build. Le
sélecteur de réception présentait aussi la commande comme « Sans fournisseur » :
son modèle d'affichage n'utilisait pas le champ `supplier_name` fourni par l'API.
Le nom du fournisseur est maintenant repris dans cette liste ; ce parcours doit
également être rejoué après validation du build.

Le parcours de vente ne peut pas être finalisé avec l'administrateur de test,
car aucune boutique de vente ne lui est attribuée ; le produit apparaît alors
indisponible et les actions d'ajout restent désactivées. Aucune vente ni
facture n'a donc été créée dans cette recette visuelle. Les factures restent
liées au détail d'une vente (la route `/factures` n'existe pas) ; leur accès
API est couvert par les tests automatisés, sans que cela remplace un scénario
visuel de vente validé.

Les fichiers de stock partagés n'ont pas été importés : les données de
référence et plusieurs valeurs sont signalées comme devant être vérifiées
manuellement. La recette a utilisé uniquement des données synthétiques dans la
base temporaire ; elle n'a modifié ni la base de l'application ni des données
de production.
