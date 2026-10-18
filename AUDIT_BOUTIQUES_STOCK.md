# Audit — boutiques, stocks, ravitaillement et mise en service

Date : 2026-10-16

## Périmètre et méthode

Revue du backend Django, des routes API et des pages frontend concernant les
emplacements, les stocks, les ventes, les échantillons, les transferts,
l'approvisionnement et l'import de catalogue. Des corrections ciblées ont été
appliquées et vérifiées par tests ; aucune donnée de production n'a été
modifiée. Les constats ci-dessous distinguent les comportements livrés des
vérifications opérationnelles qui restent à exécuter.

## Constats prioritaires

### 1. Critique — vente API sans boutique ni stock local (corrigé)

`Sale.location` reste nullable pour préserver les ventes historiques, mais la
validation des nouvelles ventes internes exige maintenant une boutique active,
autorisée pour l'utilisateur, et une quantité disponible dans cette boutique.
Les réservations des commandes confirmées sont prises en compte ; les ventes
externes gardent leur parcours séparé. Les mouvements et quantités locaux sont
revérifiés sous verrou lors de la création transactionnelle
(`backend/sales/serializers.py`). Les tests couvrent l'absence d'emplacement, le
stock insuffisant et l'accès à une boutique non autorisée
(`backend/sales/tests.py`).

### 2. Élevé — demandes de ravitaillement (implémentées)

La page `image-ad-studio/src/pages/entrepots/page.tsx` lit maintenant les
demandes persistées de `StockReplenishmentRequest`. Un vendeur peut en créer
une pour une boutique qui lui est autorisée ; les responsables de stock et les
administrateurs peuvent traiter les demandes dans le périmètre d'emplacements
autorisé. Les doublons ouverts sont refusés et tout refus exige un motif.

L'acceptation crée des `StockTransfer` liés à la demande et dirigés vers la
boutique cible. Les contrôles de transfert existants gèrent validation,
expédition et réception ; les quantités ne sont mouvementées qu'au moment
prévu par ce cycle. Des tests couvrent les permissions, le refus, la réception
et la mise à jour du stock (`backend/inventory/tests.py`). La migration est
additive ; aucune donnée historique n'est supprimée.

### 3. Élevé — entrepôt implicite lors de la création (corrigé à l'étape 4)

Avant l'étape 4, la création d'un produit avec une quantité initiale positive
pouvait créer ou utiliser l'emplacement global `WH-DEFAULT` (« Entrepôt
principal »), puis y créer un `StockItem` et une couche de coût
(`backend/products/serializers.py`). La création du catalogue est maintenant
indépendante du stock : toute quantité initiale positive est refusée par l'API
et doit passer par une réception ou un inventaire validé pour l'emplacement
choisi. Les emplacements et lignes de stock `WH-DEFAULT` déjà présents ne sont
ni modifiés ni supprimés.

Le parcours d'inventaire séparé existe : un inventaire est créé par emplacement,
soumis par le stock et validé par un administrateur
(`backend/inventory/serializers.py`, `backend/inventory/views.py`).

### 4. Élevé — incohérence historique des échantillons (corrigée à l'étape 3)

`StockUnit` possède un statut `sample`. Les ventes FIFO ne consomment que les
unités au statut `available`, et le changement de statut d'une unité suivie
modifie les quantités de stock. L'interface et les routes ajoutées à l'étape 3
permettent désormais de gérer ces unités individuellement.

En revanche, `SampleCarton` enregistre seulement un produit, une boutique et un
nombre d'échantillons. Historiquement, sa création ne réservait ni ne déplaçait
de stock et aucun champ n'indiquait si ces échantillons étaient vendables
(`backend/inventory/models.py`, `backend/inventory/serializers.py`). Les
nouveaux enregistrements par cet ancien parcours sont désormais indisponibles ;
les lignes historiques restent consultables, mais ne sont pas automatiquement
converties en unités physiques.

### 5. Moyen — devis et ventes sur commande (corrigé à l'étape 5)

Les statuts de vente disponibles sont brouillon, payée, partielle et annulée.
La création d'une vente crée une facture et décrémente le stock, y compris
lorsque son statut reste brouillon
(`backend/sales/models.py`, `backend/sales/serializers.py`). Ce constat est
résolu par un modèle et des endpoints dédiés de devis/commande : devis sans
réservation, confirmation avec réservation, puis livraison complète créant une
vente et sa facture.

### 6. Moyen — le modèle d'entreprise est unique dans l'installation

`CompanyView` récupère ou crée toujours la société d'identifiant `1`
(`backend/core/views.py`). Les boutiques et produits ne sont pas rattachés à
une société. Le modèle actuel correspond à une installation pour une seule
entreprise avec plusieurs emplacements ; il ne fournit pas d'isolation entre
plusieurs entreprises dans une même base.

### 7. Moyen — assistant de mise en service (traité)

Les briques sont accessibles par des écrans et API séparés : identité de
l'entreprise, emplacements, utilisateurs, import de catalogue, inventaire,
achats et tests d'exploitation. Un guide administrateur est maintenant
disponible à `/mise-en-service` (`image-ad-studio/src/pages/mise-en-service/page.tsx`).
Il vérifie les informations de facture, les boutiques actives, le catalogue et
le stock vendable, avec la création de comptes comme étape facultative. Ses
boutons renvoient vers les écrans de gestion existants ; il ne crée ni produit
ni quantité de stock. La lecture de l'identité de facturation renvoie les
valeurs par défaut sans créer de ligne en base si aucune configuration n'existe.
L'étape d'identité n'est désormais validée qu'après une modification explicite
par un administrateur. Le stock vendable du guide retranche les quantités
réservées par les commandes confirmées ; les devis ne sont pas retranchés.
L'import de catalogue et l'inventaire restent des flux distincts.

## Comportements déjà présents à préserver

- Une boutique est un `InventoryLocation` de type `shop`; les entrepôts sont
  d'autres emplacements. Aucun minimum d'entrepôt n'est imposé au modèle.
- Les quantités locales sont enregistrées dans `StockItem`, par produit et
  emplacement.
- Les ventes depuis le formulaire sélectionnent une boutique et affichent les
  quantités par emplacement.
- Les transferts ont des transitions de validation, d'expédition et de
  réception, avec prise en compte des écarts de réception et verrouillages
  transactionnels.
- L'inventaire initial peut passer par le cycle brouillon, soumission et
  validation administrative.
- L'import de catalogue ne doit pas être transformé en import de quantités.

## Proposition d'évolution, en étapes contrôlées

1. **Intégrité immédiate des ventes** : imposer côté API un emplacement de vente
   autorisé et refuser une vente sans stock local suffisant. Ajouter des tests
   pour l'API directe, les rôles et les quantités, sans modifier le catalogue
   historique.
2. **Ravitaillement réel** : remplacer les demandes calculées à l'affichage par
   un enregistrement durable lié à une boutique, un produit, une quantité, un
   demandeur, un motif/priorité et des dates. Ajouter les transitions réellement
   nécessaires, dont le refus motivé, et relier l'expédition à un transfert
   existant afin de réutiliser ses contrôles de stock. Une suggestion de seuil
   reste informative et ne crée aucun mouvement automatiquement.
3. **Échantillons** : suivre chaque unité individuellement au moyen de
   `StockUnit`, en séparant stock vendable et quantité physique.
4. **Catalogue et inventaire initial** : retirer l'affectation implicite à
   `WH-DEFAULT` du parcours de création de produit avec quantité. Le stock
   initial passe par un inventaire ou une réception validée pour l'emplacement
   choisi ; prévoir une transition explicite pour les installations existantes
   afin de ne pas déplacer ou perdre de données.
5. **Devis / commande client** : le flux séparé applique la règle confirmée :
   un devis ne réserve pas le stock ; la confirmation réserve le stock de la
   boutique ; l'annulation libère la réservation ; la livraison complète crée
   une vente et une facture en débitant le stock une seule fois.
6. **Mise en service** : assembler progressivement les parcours existants en
   étapes guidées, sans recréer les modèles d'entreprise, de produit ou
   d'emplacement.
7. **Compatibilité et livraison** : migrations additives uniquement, tests de
   régression, vérification visuelle des écrans concernés et aucune opération
   de remise à zéro des données.

## Décision de périmètre

Le périmètre confirmé est **une entreprise par installation, avec plusieurs
boutiques et entrepôts facultatifs**. Une refonte multi-entreprise n'est donc
pas incluse. Le profil `Company` existant reste l'identité globale de cette
installation ; les stocks et ventes restent répartis par emplacement.

## Plan proposé pour l'implémentation

1. Corriger d'abord la cohérence des ventes ordinaires côté API en exigeant une
   boutique autorisée et en validant le stock à cet emplacement. Garder les
   ventes historiques sans emplacement lisibles ; ne pas inventer leur boutique
   ni modifier leurs mouvements.
2. Remplacer les demandes synthétiques de l'écran entrepôts par des demandes
   persistantes, scellées à la boutique cible, avec permissions dédiées, motif
   de refus et notification. Réutiliser `StockTransfer` pour l'exécution
   physique, sans double mouvement.
3. Clarifier et implémenter les échantillons au niveau d'un lot/unité, avec une
   quantité physique séparée du stock vendable et une option explicite de
   vendabilité.
4. Empêcher que la création du catalogue produise un stock local implicite.
   Conserver les lignes `WH-DEFAULT` existantes et les réconcilier
   manuellement, sans déplacement automatique.
5. Les devis et commandes clients sont suivis dans un flux séparé ; les
   réservations confirmées sont soustraites de la disponibilité des ventes
   ordinaires et sont libérées lors d'une annulation.
6. Ajouter un parcours d'initialisation guidé après stabilisation des flux
   précédents, en réutilisant les API et modèles existants.

Chaque étape comprend migrations additives si nécessaires, tests backend de
permissions et d'intégrité, tests de non-régression et vérification visuelle.
Les étapes sont livrées une par une ; aucune donnée historique n'est supprimée
ou réécrite.

## Avancement vérifié

Les étapes 1 à 5 du plan ont été implémentées :

- Une vente ordinaire exige une boutique active autorisée et un stock suffisant
  dans cette boutique. Les ventes externes conservent leur parcours existant ;
  les ventes historiques sans emplacement restent lisibles.
- Les demandes de ravitaillement sont persistées avec leur boutique, produit,
  quantité, demandeur, motif, état et dates. Les demandes ouvertes en double
  pour le même produit et la même boutique sont refusées.
- Les responsables habilités peuvent accepter une demande en répartissant le
  reliquat entre des emplacements sources autorisés, ou la refuser avec motif.
  L'expédition et la réception réutilisent les transferts et contrôles de stock
  existants ; aucun second mouvement n'est créé.
- Les demandes déclenchent des notifications internes ciblées. L'écran de
  vente permet au vendeur de soumettre une demande ; l'écran entrepôts permet
  aux responsables de consulter et traiter les demandes persistées.
- Les permissions filtrent les demandes par propriétaire pour les vendeurs et
  par boutiques autorisées pour les responsables de stock. Les rôles cumulés
  ne contournent pas ces contrôles.
- Les unités de stock sont listées et changées manuellement par emplacement,
  sans scanner ni QR. Le stock vendable demeure distinct du stock physique ;
  les unités issues de cartons existants peuvent être initialisées de façon
  idempotente et les unités déjà consommées sont marquées comme historiques
  inconnues.
- L'ancienne liste `SampleCarton` reste disponible en lecture pour préserver
  l'historique, mais sa création par cet ancien parcours n'est plus autorisée.
  Les unités sans carton ne sont pas automatiquement inventées : elles restent
  signalées comme stock non suivi et nécessitent une réconciliation ultérieure.
- Les nouveaux endpoints de lecture utilisent la permission métier `inventory`
  attribuée au rôle stock. L'initialisation requiert également cette permission
  et les contrôles de mutation/localisation ; la permission inexistante
  `stock.manage` n'est plus utilisée côté API.
- La création d'un produit ne peut plus initialiser un stock sans emplacement.
  Le formulaire ne propose plus de quantité initiale et l'API refuse une
  quantité positive, y compris pour l'administrateur ; les réceptions et
  inventaires validés restent les parcours autorisés. Aucun entrepôt
  `WH-DEFAULT` ni stock existant n'est supprimé ou déplacé.
- Le flux devis/commande de l'étape 5 est implémenté : création du devis sans
  mouvement de stock, confirmation transactionnelle avec réservation à la
  boutique, annulation libérant le stock réservé, puis livraison complète
  créant une seule vente et sa facture. Une livraison répétée est refusée.
- Les ventes ordinaires et le catalogue soustraient les réservations actives
  des quantités disponibles. Les vendeurs ne peuvent lire que leurs propres
  commandes et restent limités aux boutiques qui leur sont attribuées.
- L'écran « Devis clients » permet de rechercher et choisir manuellement des
  produits, préparer le devis, puis confirmer, annuler ou livrer la commande.
  Il est disponible pour les rôles autorisés à créer des ventes.

Les migrations additives du périmètre sont
`backend/inventory/migrations/0017_stockreplenishmentrequest_and_more.py`,
`backend/notifications/migrations/0004_notification_recipient_user_and_more.py`,
`backend/sales/migrations/0016_saleitemstockorigin.py` et
`backend/sales/migrations/0017_customerorder_customerorderitem.py`. Elles
ajoutent les données de traçabilité et de commande sans supprimer ni réécrire
les ventes, produits, transferts ou stocks existants.

Vérifications effectuées :

- `manage.py test inventory.tests sales.tests purchases.tests products.tests` :
  113 tests réussis, dont les tests du nouveau cycle devis/commande.
- `manage.py check` : aucune anomalie Django.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `npm run build` : réussi avec l'écran « Devis clients » et sa route.
- ESLint ciblé sur les fichiers frontend modifiés : aucune erreur, deux
  avertissements Fast Refresh dans `locale.tsx`.
- Les quatre tests ciblés des permissions et opérations d'unités réussissent.
- Pour `src/pages/produits/page.tsx`, ESLint signale deux violations
  Prettier préexistantes dans du code inchangé ; le lint passe avec cette règle
  désactivée et le build complet réussit.

Le contrôle visuel a été réalisé avec un backend et une base SQLite temporaires :
le devis a été créé, confirmé (réservation visible), puis livré ; l'écran a
affiché la vente associée et l'API a créé la facture. La base de démonstration
temporaire n'est pas une base de données de l'application.

Le guide de mise en service (étape 6) est ajouté. La compilation frontend
réussit ; le lint ciblé ne rapporte aucune erreur et conserve deux
avertissements Fast Refresh préexistants dans `locale.tsx`. Le contrôle visuel
du guide a depuis été effectué sur une base SQLite isolée : une configuration
de facturation par défaut apparaît « À vérifier », et une réservation
confirmée est retranchée du stock vendable affiché. La base temporaire a été
supprimée après le test.
Pour les analyses, l'API borne déjà le rôle vendeur à ses propres ventes et
masque les coûts et marges. Le lien « Rapports » était toutefois caché par une
permission d'interface différente de celle de la route et de l'API ; il utilise
maintenant `sales.view`, sans élargissement de l'accès aux autres rapports.
Les indicateurs de stock du rapport vendeur sont calculés sur les boutiques
actives auxquelles le vendeur a accès, à partir des lignes `StockItem`, et non
sur le total global du catalogue.
Pour l'étape 7, migrations, régressions, compilations et contrôle visuel du flux
de devis ont été vérifiés. Une sauvegarde et une restauration PostgreSQL ont
depuis été exécutées avec succès sur deux bases locales temporaires créées
uniquement pour cet essai ; aucune donnée de production n'a été incluse. La
procédure opérationnelle de sauvegarde et restauration de production reste à
exécuter par l'équipe d'exploitation sur son environnement autorisé.

Vérifications supplémentaires du 2026-10-16 :

- Les tests ciblés du cycle de demande de ravitaillement réussissent : demande
  vendeur, transfert lié, réception, doublon et refus avec motif.
- Les tests Django des flux de facture et de commande client réussissent ;
  `manage.py check` et `manage.py makemigrations --check --dry-run` ne signalent
  aucun problème.
- Le build frontend et ESLint ciblé du guide de mise en service réussissent.
- PostgreSQL local : les 10 tests ciblés facture/commandes/ravitaillement
  réussissent sur une base de test dédiée. Les migrations ont été appliquées
  à une base temporaire, sauvegardées au format custom, restaurées vers une
  seconde base temporaire vide, puis contrôlées par la présence d'un marqueur
  synthétique et par `migrate --check`. Les deux bases temporaires et l'archive
  ont été supprimées après vérification.
- La suite PostgreSQL `inventory.tests sales.tests purchases.tests
  products.tests` réussit : 114 tests, aucun échec ; sa base de test dédiée a
  également été supprimée automatiquement.
- La suite `invoices.tests.InvoiceApiTests` réussit sur PostgreSQL et SQLite :
  15 tests par backend, sans échec. Deux tests fermaient manuellement un
  `FileResponse` avant la fin de l'itération dans un `TestCase`, ce qui
  invalidait la connexion PostgreSQL dans la transaction de test. Ils
  consomment désormais les flux comme un client HTTP ; l'endpoint applicatif
  n'a pas été modifié.
- Lors d'une exécution plus large, 259 des 260 tests backend ont réussi ; le
  test restant créait une vente synchronisée sans boutique ni stock local,
  contrairement aux règles actuelles des ventes. Son jeu de données a été
  complété avec une boutique et son `StockItem`. Les 33 tests de `core.tests`
  réussissent maintenant sur PostgreSQL et SQLite. La suite complète n'a pas
  été relancée après cette correction ciblée.
- Aucune sauvegarde ni restauration de la base de production n'a été lancée.
  Cet essai confirme la procédure technique sur PostgreSQL local, pas les
  accès, la rétention ni la restaurabilité d'une sauvegarde de production.
