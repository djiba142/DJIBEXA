SPÉCIFICATIONS API ET INTÉGRATION
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence technique et fonctionnel
Architecture cible : React + Vite ↔ Django REST Framework
Architecture actuelle : frontend HTML/Bootstrap/JavaScript ↔ Django REST Framework
Base de données cible : PostgreSQL
Base de données actuelle : MySQL `db_gestion` sur `127.0.0.1:3306`
Communication : API REST sécurisée
Document précédent : Document 03 — Spécifications UI/UX et Design System
SOMMAIRE
Introduction
Objectifs de l'API
Architecture générale de communication
Principes de fonctionnement
Architecture React + Vite
Architecture Django REST Framework
Organisation des routes API
Authentification et gestion des sessions
Gestion des utilisateurs et permissions
API Entreprise, boutiques et entrepôts
API Produits
API Fournisseurs
API Commandes fournisseurs
API Importation des fichiers fournisseurs
API Réceptions
API Frais et coût réel
API Stocks
API Transferts
API Cartons et QR Codes
API Ventes
API Ventes externes
API Factures
API Clients
API Crédits
API Paiements
API Caisse et finances
API Dépenses
API Notifications et WhatsApp
API Rapports et statistiques
API Recherche globale
Synchronisation des données
Gestion hors connexion
Gestion des erreurs
Validation des données
Transactions et cohérence des données
Idempotence et prévention des doublons
Sécurité des API
Journalisation et audit
Performance et pagination
Versionnement de l'API
Documentation technique de l'API
Flux fonctionnels complets
Critères de validation
Conclusion
1. INTRODUCTION
Ce document définit la manière dont le frontend React + Vite communique avec le backend Django REST Framework.
L'objectif est de créer une communication propre, sécurisée et prévisible entre l'interface utilisateur et le serveur.
Le frontend ne doit pas accéder directement à la base de données.
La circulation des données doit suivre le principe :
Utilisateur → React/Vite → API Django REST → Services métier → PostgreSQL
et dans l'autre sens :
PostgreSQL → Django → API REST → React/Vite → Utilisateur
Cette séparation permet de protéger les données, de centraliser les règles métier et de faire évoluer l'application plus facilement.
2. OBJECTIFS DE L'API
L'API doit permettre au frontend de :
récupérer les données ;
créer des enregistrements ;
modifier les informations autorisées ;
supprimer ou archiver certaines données ;
effectuer des recherches ;
enregistrer les ventes ;
gérer les stocks ;
gérer les achats ;
enregistrer les paiements ;
générer et consulter les factures ;
importer des fichiers ;
gérer les QR Codes ;
recevoir les notifications ;
consulter les rapports.
L'API doit également garantir que les règles métier ne sont pas contournées par le frontend.
3. ARCHITECTURE GÉNÉRALE DE COMMUNICATION
L'architecture de communication est organisée en trois niveaux principaux.
Frontend
React + Vite + TypeScript
Responsable de :
l'affichage ;
l'expérience utilisateur ;
les formulaires ;
la navigation ;
la validation visuelle ;
l'appel des API.
Backend
Django + Django REST Framework
Responsable de :
l'authentification ;
les permissions ;
les règles métier ;
les transactions ;
la validation serveur ;
la génération des documents ;
la gestion des stocks ;
la communication avec les services externes.
Base de données
PostgreSQL
Responsable de la persistance des données.
4. PRINCIPES DE FONCTIONNEMENT
Le frontend ne doit jamais décider seul d'une opération critique.
Par exemple, lorsqu'un vendeur valide une vente, React envoie la demande :
POST /api/v1/sales/
Le backend vérifie :
l'identité de l'utilisateur ;
ses permissions ;
le client ;
les produits ;
les quantités ;
le stock ;
les prix ;
les règles commerciales.
Si tout est valide, Django effectue l'opération dans une transaction.
5. ARCHITECTURE REACT + VITE
Le frontend doit être organisé de manière modulaire.
Une structure logique peut être :
src/
├── api/
├── components/
├── features/
├── layouts/
├── pages/
├── hooks/
├── services/
├── stores/
├── types/
├── utils/
├── routes/
└── i18n/
Le dossier api centralise les communications avec Django.
Les composants React ne doivent pas multiplier directement les appels HTTP partout dans le projet.
6. ARCHITECTURE DJANGO REST FRAMEWORK
Le backend doit être organisé par domaines fonctionnels.
Exemple :
backend/
├── accounts/
├── products/
├── suppliers/
├── purchases/
├── inventory/
├── sales/
├── invoices/
├── customers/
├── payments/
├── finance/
├── notifications/
├── reports/
├── audit/
└── core/
Chaque domaine possède ses propres :
modèles ;
serializers ;
vues ;
permissions ;
services ;
URLs ;
tests.
7. ORGANISATION DES ROUTES API
Toutes les API doivent être regroupées sous une version.
Format recommandé :
/api/v1/
Exemples :
/api/v1/products/
/api/v1/customers/
/api/v1/sales/
/api/v1/invoices/
/api/v1/payments/
Le versionnement permet de faire évoluer l'API sans casser immédiatement les anciennes versions.
8. AUTHENTIFICATION ET GESTION DES SESSIONS
L'application doit utiliser une authentification sécurisée adaptée à l'architecture retenue.
Après authentification réussie, le frontend reçoit les informations nécessaires pour maintenir la session.
Le backend doit identifier chaque requête authentifiée.
Une requête non authentifiée vers une ressource protégée doit retourner une réponse appropriée.
Exemple :
401 Unauthorized
9. GESTION DES UTILISATEURS ET PERMISSIONS
Endpoint
GET /api/v1/users/
POST /api/v1/users/
GET /api/v1/users/{id}/
PATCH /api/v1/users/{id}/
Les utilisateurs autorisés peuvent être :
créés ;
consultés ;
modifiés ;
désactivés.
Le backend doit vérifier les permissions pour chaque opération.
10. API ENTREPRISE, BOUTIQUES ET ENTREPÔTS
Entreprise
GET /api/v1/company/
PATCH /api/v1/company/
Emplacements
GET /api/v1/locations/
POST /api/v1/locations/
GET /api/v1/locations/{id}/
PATCH /api/v1/locations/{id}/
Chaque emplacement possède notamment un type :
STORE
WAREHOUSE
Le backend doit empêcher un utilisateur non autorisé de manipuler un emplacement auquel il n'a pas accès.
11. API PRODUITS
Liste
GET /api/v1/products/
Création
POST /api/v1/products/
Détail
GET /api/v1/products/{id}/
Modification
PATCH /api/v1/products/{id}/
Archivage
POST /api/v1/products/{id}/archive/
Recherche
GET /api/v1/products/?search=filtre
La réponse doit fournir les informations nécessaires à l'interface sans exposer inutilement des données internes.
12. API FOURNISSEURS
GET /api/v1/suppliers/
POST /api/v1/suppliers/
GET /api/v1/suppliers/{id}/
PATCH /api/v1/suppliers/{id}/
Une fiche fournisseur doit pouvoir être associée à :
commandes ;
produits ;
réceptions ;
documents.
13. API COMMANDES FOURNISSEURS
GET /api/v1/purchase-orders/
POST /api/v1/purchase-orders/
GET /api/v1/purchase-orders/{id}/
PATCH /api/v1/purchase-orders/{id}/
Actions métier
POST /api/v1/purchase-orders/{id}/send/
POST /api/v1/purchase-orders/{id}/confirm/
POST /api/v1/purchase-orders/{id}/close/
Les actions métier importantes doivent être traitées par des endpoints explicites plutôt que par une simple modification arbitraire du champ status.
14. API IMPORTATION DES FICHIERS FOURNISSEURS
Le frontend envoie le fichier au backend.
POST /api/v1/purchase-imports/
Le backend :
reçoit le fichier ;
vérifie son format ;
analyse son contenu ;
identifie les produits ;
recherche les correspondances ;
détecte les nouveaux produits ;
retourne un aperçu.
Exemple de résultat :
recognized: 45
new_products: 8
needs_review: 3
errors: 1
L'utilisateur valide ensuite l'importation.
POST /api/v1/purchase-imports/{id}/confirm/
15. API RÉCEPTIONS
Créer une réception
POST /api/v1/receipts/
Consulter
GET /api/v1/receipts/{id}/
Valider
POST /api/v1/receipts/{id}/validate/
La validation doit déclencher la mise à jour du stock dans la même transaction lorsque les conditions métier sont satisfaites.
16. API FRAIS ET COÛT RÉEL
POST /api/v1/acquisition-costs/
GET /api/v1/acquisition-costs/{id}/
PATCH /api/v1/acquisition-costs/{id}/
Le backend calcule le coût réel selon la méthode configurée.
Le frontend affiche le résultat mais ne doit pas être considéré comme la source de vérité pour ce calcul.
17. API STOCKS
Stock global
GET /api/v1/inventory/
Stock d'un produit
GET /api/v1/products/{id}/stock/
Stock par emplacement
GET /api/v1/locations/{id}/stock/
Mouvements
GET /api/v1/stock-movements/
Le stock disponible doit être calculé côté serveur.
18. API TRANSFERTS
GET /api/v1/transfers/
POST /api/v1/transfers/
GET /api/v1/transfers/{id}/
Actions :
POST /api/v1/transfers/{id}/validate/
POST /api/v1/transfers/{id}/ship/
POST /api/v1/transfers/{id}/receive/
Le backend doit garantir que les quantités sont cohérentes.
19. API CARTONS ET QR CODES
Cartons
GET /api/v1/cartons/
POST /api/v1/cartons/
GET /api/v1/cartons/{id}/
QR produit
GET /api/v1/products/{id}/qr/
QR carton
GET /api/v1/cartons/{id}/qr/
Recherche par code
GET /api/v1/qr/resolve/?code=...
Le serveur identifie le type de code et retourne la ressource correspondante lorsque l'utilisateur est autorisé à la consulter.
20. API VENTES
La vente est une opération critique.
Créer une vente
POST /api/v1/sales/
Le corps de la requête peut contenir logiquement :
client
location
items
payment
discount
Le serveur vérifie l'ensemble des données.
Validation
Une vente validée doit entraîner, selon le scénario :
Vente → Stock → Facture → Paiement/Créance → Audit
Toutes les opérations critiques doivent être réalisées dans une transaction.
21. API VENTES EXTERNES
Lorsque certains produits doivent être obtenus à l'extérieur :
POST /api/v1/sales/external/
Le backend doit conserver les informations nécessaires à la traçabilité.
La vente commerciale peut rester associée à une facture unique conformément aux règles fonctionnelles du projet.
22. API FACTURES
Liste
GET /api/v1/invoices/
Détail
GET /api/v1/invoices/{id}/
PDF
GET /api/v1/invoices/{id}/pdf/
QR
GET /api/v1/invoices/{id}/qr/
La facture doit être générée à partir des données validées côté serveur.
23. API CLIENTS
GET /api/v1/customers/
POST /api/v1/customers/
GET /api/v1/customers/{id}/
PATCH /api/v1/customers/{id}/
Historique
GET /api/v1/customers/{id}/sales/
GET /api/v1/customers/{id}/invoices/
GET /api/v1/customers/{id}/payments/
24. API CRÉDITS
GET /api/v1/credits/
GET /api/v1/customers/{id}/credit/
Le backend doit calculer le solde à partir des opérations enregistrées.
Le frontend ne doit pas simplement additionner ou soustraire localement les montants pour déterminer la dette officielle.
25. API PAIEMENTS
Enregistrer un paiement
POST /api/v1/payments/
Consulter
GET /api/v1/payments/
GET /api/v1/payments/{id}/
Reçu
GET /api/v1/payments/{id}/receipt/
Lorsqu'un paiement est validé, le système recalcule automatiquement le solde.
26. API CAISSE ET FINANCES
GET /api/v1/cash/
GET /api/v1/cash/transactions/
GET /api/v1/financial-summary/
Les données financières doivent être calculées côté serveur à partir des opérations validées.
27. API DÉPENSES
GET /api/v1/expenses/
POST /api/v1/expenses/
GET /api/v1/expenses/{id}/
PATCH /api/v1/expenses/{id}/
Les justificatifs peuvent être téléversés via une API dédiée lorsque nécessaire.
28. API NOTIFICATIONS ET WHATSAPP
Notifications internes
GET /api/v1/notifications/
POST /api/v1/notifications/{id}/read/
Historique des messages
GET /api/v1/messages/
Le backend gère la communication avec les services externes autorisés.
Le frontend ne doit jamais contenir directement les clés secrètes du service WhatsApp.
29. API RAPPORTS ET STATISTIQUES
Exemples :
GET /api/v1/reports/sales/
GET /api/v1/reports/inventory/
GET /api/v1/reports/credits/
GET /api/v1/reports/purchases/
GET /api/v1/reports/finance/
Les rapports doivent accepter des filtres :
date_from
date_to
location
product
category
seller
customer
30. API RECHERCHE GLOBALE
Endpoint :
GET /api/v1/search/?q=...
Le serveur peut retourner des résultats classés :
products
customers
invoices
cartons
sales
suppliers
Les résultats doivent respecter les permissions de l'utilisateur.
31. SYNCHRONISATION DES DONNÉES
La synchronisation entre React et Django doit être conçue pour éviter les incohérences.
Lorsqu'une opération est réalisée :
Frontend
→ envoie la requête
Backend
→ valide
Base de données
→ enregistre
Backend
→ retourne le résultat officiel
Frontend
→ met à jour l'interface.
Le frontend doit considérer la réponse du serveur comme la source de vérité.
32. GESTION HORS CONNEXION
Si le fonctionnement hors ligne est prévu pour certaines parties de l'application, il doit être limité aux opérations pouvant être correctement synchronisées.
Le frontend peut conserver temporairement certaines données locales.
Une opération hors ligne doit recevoir un identifiant local unique.
Lors de la reconnexion :
Données locales → File de synchronisation → API Django → Validation → Confirmation → Mise à jour locale
Exemple
Un vendeur effectue une opération hors connexion.
L'application crée :
LOCAL-SALE-87452
Lors de la synchronisation, Django vérifie l'opération.
Si elle est acceptée :
LOCAL-SALE-87452 → SALE-2026-00152
L'application remplace ensuite la référence temporaire par la référence officielle.
33. GESTION DES ERREURS
L'API doit utiliser des réponses cohérentes.
400
Données invalides.
401
Utilisateur non authentifié.
403
Utilisateur authentifié mais non autorisé.
404
Ressource inexistante.
409
Conflit métier.
Exemple :
Deux opérations tentent de modifier simultanément une même quantité de stock.
422
Données valides techniquement mais impossibles selon les règles métier, si ce code est retenu par la convention API.
500
Erreur serveur inattendue.
34. VALIDATION DES DONNÉES
La validation doit être effectuée à deux niveaux.
Frontend
Pour améliorer l'expérience utilisateur.
Exemple :
Le numéro de téléphone est obligatoire.
Backend
Pour garantir la sécurité et l'intégrité.
Même si React accepte une donnée, Django doit la vérifier.
Le backend est toujours la validation finale.
35. TRANSACTIONS ET COHÉRENCE DES DONNÉES
Les opérations critiques doivent être atomiques.
Prenons une vente :
création de la vente ;
diminution du stock ;
création de la facture ;
création du paiement ;
création éventuelle de la créance ;
création de l'audit.
Si une étape critique échoue, le système doit pouvoir annuler la transaction complète lorsque les règles de l'opération l'exigent.
Il ne doit pas être possible d'avoir :
Facture créée mais stock non diminué
ou :
Paiement enregistré mais aucune trace de la facture concernée.
36. IDEMPOTENCE ET PRÉVENTION DES DOUBLONS
Cette règle est particulièrement importante pour les ventes et paiements.
Une mauvaise connexion peut provoquer deux envois de la même requête.
Le backend doit donc pouvoir reconnaître une opération déjà traitée.
Exemple :
Idempotency-Key: SALE-CLIENT-2026-000874
Si la même requête est reçue deux fois, le serveur ne doit pas créer deux ventes.
37. SÉCURITÉ DES API
La communication doit utiliser HTTPS.
Les informations sensibles ne doivent pas être exposées dans :
le code frontend ;
les fichiers JavaScript publics ;
les logs ;
les réponses API inutiles.
Les clés des services externes doivent rester côté serveur.
Protection supplémentaire
L'API doit prévoir :
contrôle des permissions ;
limitation des requêtes sensibles ;
validation des fichiers ;
protection contre les injections ;
contrôle des uploads ;
journalisation ;
expiration des sessions selon la politique définie.
38. JOURNALISATION ET AUDIT
Les opérations importantes doivent être enregistrées.
Exemple :
Utilisateur : vendeur01
Action : CREATE_SALE
Ressource : SALE-2026-00152
Date : 2026-08-04
Résultat : SUCCESS
Pour une modification :
Avant : quantité = 20
Après : quantité = 15
Les données d'audit doivent être protégées contre les modifications ordinaires.
39. PERFORMANCE ET PAGINATION
Les endpoints retournant beaucoup de données doivent utiliser la pagination.
Exemple :
GET /api/v1/products/?page=1&page_size=25
La réponse doit fournir les informations nécessaires pour naviguer entre les pages.
Les recherches doivent être effectuées côté serveur lorsque les volumes deviennent importants.
40. VERSIONNEMENT DE L'API
L'API doit commencer avec :
/api/v1/
Lorsqu'une modification incompatible devient nécessaire, une nouvelle version pourra être introduite :
/api/v2/
L'objectif est de permettre au frontend et au backend d'évoluer sans provoquer une rupture brutale.
41. DOCUMENTATION TECHNIQUE DE L'API
L'API doit être documentée avec une spécification standard telle qu'OpenAPI.
La documentation doit présenter pour chaque endpoint :
URL ;
méthode ;
authentification ;
permissions ;
paramètres ;
corps de requête ;
réponse ;
erreurs possibles ;
exemples.
Elle doit permettre à un développeur frontend de comprendre une API sans devoir lire le code Django.
42. FLUX FONCTIONNELS COMPLETS
42.1 Flux d'une vente
React
  ↓
POST /sales/
  ↓
Django Authentication
  ↓
Permission
  ↓
Validation
  ↓
Vérification stock
  ↓
Transaction PostgreSQL
  ↓
Vente + Stock + Facture + Paiement/Créance + Audit
  ↓
Réponse API
  ↓
React
  ↓
Affichage confirmation
42.2 Flux d'un paiement de crédit
React
  ↓
Recherche client
  ↓
GET /customers/{id}/credit/
  ↓
Affichage de la dette
  ↓
Saisie du paiement
  ↓
POST /payments/
  ↓
Django vérifie le montant
  ↓
Transaction
  ↓
Paiement enregistré
  ↓
Solde recalculé
  ↓
Notification éventuelle
  ↓
Réponse API
  ↓
Mise à jour de l'écran
42.3 Flux d'une réception fournisseur
Commande
  ↓
Réception
  ↓
POST /receipts/
  ↓
Validation
  ↓
Calcul des quantités
  ↓
Calcul des frais
  ↓
Mise à jour du stock
  ↓
Mise à jour du coût réel
  ↓
Audit
  ↓
Réponse React
42.4 Flux d'un scan QR
Scanner / Caméra
  ↓
Code QR
  ↓
React
  ↓
GET /qr/resolve/
  ↓
Django
  ↓
Identification du code
  ↓
Vérification permission
  ↓
Produit / Carton / Facture
  ↓
Réponse
  ↓
Affichage dans React
43. CRITÈRES DE VALIDATION
L'intégration React ↔ Django sera considérée comme conforme lorsque :
Authentification
Les utilisateurs peuvent se connecter et accéder uniquement aux ressources autorisées.
Produits
React peut consulter et gérer les produits via l'API.
Stocks
Les quantités affichées correspondent aux données validées par Django.
Achats
Les commandes et réceptions sont correctement synchronisées.
Ventes
Une vente validée met à jour toutes les données concernées.
Facturation
Une facture peut être récupérée et générée en PDF.
Crédit
Les paiements mettent automatiquement à jour les soldes.
QR
Les codes permettent de retrouver les ressources correspondantes.
Notifications
Les événements configurés peuvent déclencher les notifications.
Sécurité
Aucune API protégée ne peut être utilisée par un utilisateur non autorisé.
Cohérence
Une erreur au cours d'une opération critique ne doit pas laisser la base de données dans un état incohérent.
44. CONCLUSION
L'API constitue le pont central entre l'interface React/Vite et le cœur métier Django.
Le principe fondamental du projet est le suivant :
React affiche et facilite l'utilisation ; Django décide, contrôle et garantit l'intégrité des opérations.
Le frontend doit donc rester responsable de l'expérience utilisateur tandis que le backend demeure la source de vérité pour :
les stocks ;
les ventes ;
les prix ;
les factures ;
les paiements ;
les crédits ;
les permissions ;
les opérations financières.
Cette séparation permettra également de faire évoluer ultérieurement l'application vers d'autres clients, par exemple une application mobile, sans devoir réécrire toute la logique métier.
