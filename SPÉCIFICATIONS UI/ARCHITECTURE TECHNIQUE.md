ARCHITECTURE TECHNIQUE
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence technique
Frontend : React + Vite + TypeScript
Backend : Django + Django REST Framework
Base de données : PostgreSQL
Architecture : Application Web moderne, modulaire et évolutive
Document précédent : Document 04 — Spécifications API et intégration
SOMMAIRE
Introduction
Vision générale de l'architecture
Objectifs de l'architecture technique
Principes architecturaux
Architecture globale du système
Architecture applicative Frontend
Organisation du projet React + Vite
Gestion de la navigation Frontend
Gestion des états et des données
Couche de communication API
Architecture Backend Django
Organisation des applications Django
Architecture des services métier
Gestion des règles métier
Architecture des API REST
Gestion des authentifications
Gestion des rôles et permissions
Architecture du stockage des données
PostgreSQL et intégrité des données
Gestion des fichiers et documents
Gestion des images produits
Gestion des QR Codes
Gestion des factures et PDF
Architecture des notifications
Intégration WhatsApp
Synchronisation des données&&&& 
Fonctionnement hors connexion
Gestion des transactions
Gestion des événements et tâches asynchrones
Journalisation et audit
Sécurité de l'architecture
Performance et évolutivité
Gestion des erreurs
Configuration et variables d'environnement
Environnements de développement
Déploiement
Sauvegarde et restauration
Monitoring et supervision
Maintenance et évolutions
Critères de validation
Conclusion
1. INTRODUCTION
Ce document décrit l'architecture technique retenue pour construire le système de gestion commerciale.
L'objectif est de définir comment les différentes parties de l'application vont être construites, comment elles communiquent et où les données sont stockées.
Le système repose principalement sur deux grandes parties :
une interface utilisateur développée avec React + Vite + TypeScript ;
un backend développé avec Django + Django REST Framework.
Les deux parties communiquent exclusivement à travers des API REST sécurisées.
La base de données PostgreSQL constitue la source de vérité du système.
L'architecture doit permettre à l'entreprise de commencer avec une application maîtrisable tout en conservant la possibilité d'augmenter progressivement sa capacité.
2. VISION GÉNÉRALE DE L'ARCHITECTURE
L'architecture suit le principe :
Utilisateur
↓
Interface React + Vite
↓
Couche API
↓
Django REST Framework
↓
Services métier
↓
PostgreSQL
Des services complémentaires peuvent être connectés au backend :
stockage de fichiers ;
génération PDF ;
QR Codes ;
service WhatsApp ;
service d'envoi d'e-mails ;
tâches planifiées ;
système de sauvegarde.
L'utilisateur ne doit jamais communiquer directement avec PostgreSQL.
3. OBJECTIFS DE L'ARCHITECTURE TECHNIQUE
L'architecture doit répondre à plusieurs objectifs.
3.1 Maintenabilité
Un développeur doit pouvoir modifier un module sans devoir modifier toute l'application.
3.2 Sécurité
Les données sensibles et les règles métier doivent rester protégées côté serveur.
3.3 Évolutivité
L'application doit pouvoir accueillir progressivement :
davantage de produits ;
davantage de ventes ;
davantage d'utilisateurs ;
plusieurs boutiques ;
plusieurs entrepôts ;
davantage de documents.
3.4 Réutilisabilité
Les mêmes services métier doivent pouvoir être utilisés par :
l'application Web ;
une future application mobile ;
d'autres interfaces autorisées.
3.5 Fiabilité
Les opérations critiques doivent être cohérentes même lorsqu'une erreur ou une interruption intervient.
4. PRINCIPES ARCHITECTURAUX
L'architecture repose sur quelques règles fondamentales.
Règle 1 — Le frontend n'est pas la source de vérité
React affiche et transmet les informations.
Django contrôle et valide.
Règle 2 — Les règles métier sont côté backend
Une règle telle que :
« Le stock ne peut pas devenir négatif »
doit être contrôlée par Django et la base de données, pas uniquement par React.
Règle 3 — Les données passent par les API
React ne communique jamais directement avec PostgreSQL.
Règle 4 — Les modules sont indépendants
Les produits, ventes, stocks, achats, clients et finances doivent être séparés logiquement.
Règle 5 — Les opérations importantes sont traçables
Une vente, une réception, un transfert ou un paiement doit pouvoir être retrouvé dans l'historique.
5. ARCHITECTURE GLOBALE DU SYSTÈME
L'architecture peut être représentée conceptuellement ainsi :
@startuml
actor Utilisateur

rectangle "Frontend" {
  component "React + Vite" as React
  component "Router" as Router
  component "State Management" as State
  component "API Client" as Client
}

rectangle "Backend" {
  component "Django" as Django
  component "Django REST Framework" as DRF
  component "Services métier" as Services
  component "Permissions / RBAC" as RBAC
  component "Audit" as Audit
}

database "PostgreSQL" as DB

cloud "Services externes" {
  component "WhatsApp" as WhatsApp
  component "Stockage fichiers" as Storage
}

Utilisateur --> React
React --> Router
React --> State
React --> Client
Client --> DRF
DRF --> RBAC
DRF --> Services
Services --> DB
Services --> Audit
Services --> Storage
Services --> WhatsApp
@enduml
Cette architecture doit rester logique même si l'infrastructure physique évolue.
6. ARCHITECTURE APPLICATIVE FRONTEND
Le frontend est développé avec :
React ;
Vite ;
TypeScript.
React est responsable de la présentation et de l'interaction avec l'utilisateur.
Vite est utilisé comme outil de développement et de construction de l'application.
TypeScript permet de mieux contrôler les structures de données utilisées dans l'application.
7. ORGANISATION DU PROJET REACT + VITE
Une organisation recommandée est :
src/
├── app/
├── assets/
├── components/
├── features/
├── layouts/
├── pages/
├── routes/
├── services/
├── api/
├── hooks/
├── stores/
├── types/
├── utils/
├── i18n/
└── main.tsx
components
Contient les composants réutilisables :
boutons ;
tableaux ;
formulaires ;
modales ;
cartes ;
badges ;
sélecteurs.
features
Contient les fonctionnalités métier.
Exemple :
features/
├── sales/
├── products/
├── inventory/
├── purchases/
├── customers/
├── payments/
└── reports/
Cette organisation permet de garder chaque domaine fonctionnel identifiable.
8. GESTION DE LA NAVIGATION FRONTEND
La navigation doit être gérée avec un routeur React.
Exemple conceptuel :
/dashboard
/products
/inventory
/purchases
/sales
/customers
/credits
/payments
/invoices
/reports
/settings
Les routes doivent être protégées.
Un utilisateur ne possédant pas les permissions nécessaires ne doit pas pouvoir accéder à une page simplement en saisissant son URL.
Cependant, cette protection frontend est uniquement une protection d'expérience utilisateur.
La vraie autorisation doit toujours être vérifiée par Django.
9. GESTION DES ÉTATS ET DES DONNÉES
Le frontend doit distinguer :
État local
Informations propres à un composant.
Exemple :
ouverture d'une modale ;
champ de formulaire ;
sélection temporaire.
État global
Informations nécessaires à plusieurs parties de l'application.
Exemple :
utilisateur connecté ;
permissions ;
langue ;
emplacement actif.
Données serveur
Informations provenant de Django :
produits ;
ventes ;
stocks ;
clients ;
factures.
Les données serveur doivent être gérées avec une stratégie adaptée de cache et de synchronisation afin d'éviter les requêtes inutiles.
10. COUCHE DE COMMUNICATION API
Toutes les communications avec Django doivent passer par une couche API centralisée.
Conceptuellement :
React
  ↓
Service métier frontend
  ↓
API Client
  ↓
HTTP
  ↓
Django REST
Cela évite de mettre des appels HTTP directement dans chaque composant.
Par exemple, la page de vente ne doit pas connaître les détails techniques de la connexion HTTP.
Elle demande simplement au service :
Créer la vente
Le service se charge de communiquer avec l'API.
11. ARCHITECTURE BACKEND DJANGO
Django constitue le cœur métier du système.
Le backend doit être organisé autour des domaines fonctionnels plutôt que de créer une seule application gigantesque.
Exemple :
backend/
├── config/
├── accounts/
├── company/
├── products/
├── inventory/
├── suppliers/
├── purchases/
├── sales/
├── customers/
├── invoices/
├── payments/
├── finance/
├── notifications/
├── reports/
├── audit/
└── common/
12. ORGANISATION DES APPLICATIONS DJANGO
Chaque application Django possède une responsabilité précise.
accounts
utilisateurs ;
rôles ;
permissions ;
authentification.
products
produits ;
catégories ;
marques ;
références ;
prix.
inventory
stocks ;
emplacements ;
mouvements ;
inventaires.
purchases
fournisseurs ;
commandes ;
réceptions ;
importations.
sales
ventes ;
lignes de vente ;
vente externe.
customers
clients ;
historique.
invoices
factures ;
PDF ;
QR Code.
payments
paiements ;
crédits ;
soldes.
finance
caisse ;
dépenses ;
opérations financières.
notifications
notifications ;
messages ;
intégrations externes.
audit
journal des opérations.
13. ARCHITECTURE DES SERVICES MÉTIER
Une règle importante est de ne pas placer toute la logique métier directement dans les vues API.
Pour les opérations complexes, Django doit utiliser des services métier.
Exemple :
SaleService
PaymentService
StockService
PurchaseService
ReceptionService
InvoiceService
NotificationService
14. GESTION DES RÈGLES MÉTIER
Prenons une vente.
La vue API reçoit la demande.
Elle transmet les informations au service :
SaleService
Celui-ci :
vérifie les données ;
vérifie les permissions ;
vérifie le stock ;
calcule les montants ;
crée la vente ;
met à jour le stock ;
crée la facture ;
crée éventuellement la créance ;
enregistre l'audit.
Cette organisation permet de conserver une logique métier claire.
15. ARCHITECTURE DES API REST
Django REST Framework constitue la couche de communication.
Les API sont versionnées :
/api/v1/
Exemples :
/api/v1/products/
/api/v1/sales/
/api/v1/inventory/
/api/v1/customers/
/api/v1/payments/
Les réponses doivent suivre un format cohérent.
16. GESTION DE L'AUTHENTIFICATION
L'authentification est gérée côté backend.
Après connexion :
Utilisateur → Django → Authentification → Session sécurisée
Le frontend conserve uniquement les informations nécessaires à son fonctionnement.
Les secrets et informations sensibles doivent rester côté serveur.
17. GESTION DES RÔLES ET PERMISSIONS
Le système doit utiliser une approche RBAC.
Exemple :
Administrateur
Vendeur
Gestionnaire stock
Responsable achats
Comptable
Responsable
Les permissions déterminent :
ce que l'utilisateur peut voir ;
ce qu'il peut créer ;
ce qu'il peut modifier ;
ce qu'il peut valider ;
ce qu'il peut annuler.
La sécurité doit être appliquée à deux niveaux :
Interface
et surtout :
Backend
18. ARCHITECTURE DU STOCKAGE DES DONNÉES
PostgreSQL est la base principale.
Les données structurées sont stockées dans PostgreSQL :
utilisateurs ;
produits ;
stocks ;
ventes ;
achats ;
clients ;
paiements ;
factures ;
mouvements ;
audit.
Les fichiers lourds ne doivent pas être stockés directement comme de gros champs dans les tables lorsque cela n'est pas nécessaire.
19. POSTGRESQL ET INTÉGRITÉ DES DONNÉES
La base doit utiliser :
clés primaires ;
clés étrangères ;
contraintes ;
index ;
transactions ;
relations cohérentes.
Les données commerciales doivent conserver leur historique.
Par exemple, une facture validée ne doit pas être modifiée arbitrairement simplement parce que le prix actuel du produit a changé.
20. GESTION DES FICHIERS ET DOCUMENTS
Les fichiers peuvent comprendre :
documents fournisseurs ;
images produits ;
justificatifs ;
factures PDF ;
documents administratifs.
Le backend doit gérer :
type ;
taille ;
nom ;
propriétaire ;
date ;
association avec l'objet métier.
Les fichiers doivent être protégés contre les téléversements dangereux.
21. GESTION DES IMAGES PRODUITS
Chaque produit peut posséder une image.
Le frontend permet :
Ajouter une image
Le backend :
vérifie le fichier ;
le stocke ;
associe son emplacement au produit ;
retourne une URL sécurisée ou contrôlée.
L'image ne doit pas être considérée comme obligatoire si le fournisseur ne l'a pas fournie.
22. GESTION DES QR CODES
Les QR Codes peuvent être associés à :
produits ;
cartons ;
factures.
Le QR Code ne doit pas contenir inutilement des informations sensibles.
Il doit principalement contenir une référence ou un identifiant permettant au système de retrouver l'objet.
Exemple conceptuel :
PROD-000125
Lors du scan :
Scanner → React → API → Django → Produit → Réponse
23. GESTION DES FACTURES ET PDF
La génération des factures doit être réalisée côté serveur afin de garantir une version officielle.
Le frontend demande :
GET /api/v1/invoices/{id}/pdf/
Django génère ou récupère le document officiel.
La facture peut contenir son QR Code.
24. ARCHITECTURE DES NOTIFICATIONS
Les notifications doivent être découplées des opérations principales lorsque cela est possible.
Exemple :
Après une vente :
Vente validée
↓
Événement de notification
↓
Notification interne
↓
WhatsApp si configuré
L'échec d'un message WhatsApp ne doit pas annuler automatiquement une vente déjà correctement enregistrée.
25. INTÉGRATION WHATSAPP
WhatsApp est considéré comme un service externe.
Les identifiants et clés d'accès doivent rester côté Django.
Le frontend ne doit jamais contenir les secrets de l'intégration.
Le backend peut envoyer :
confirmation de paiement ;
facture ;
reçu ;
rappel de crédit ;
notification commerciale.
26. SYNCHRONISATION DES DONNÉES
Le principe est :
Serveur = source de vérité
Après une opération :
React
↓
API
↓
Django
↓
PostgreSQL
↓
Réponse
↓
React
React actualise ensuite son interface à partir du résultat serveur.
27. FONCTIONNEMENT HORS CONNEXION
Si le mode hors ligne est activé pour certaines fonctions, l'application doit disposer d'une couche locale.
Conceptuellement :
React
↓
Stockage local
↓
File d'opérations
↓
Synchronisation
↓
Django
↓
PostgreSQL
Les opérations critiques doivent disposer d'un mécanisme de détection des doublons et de résolution des conflits.
28. GESTION DES TRANSACTIONS
Les opérations suivantes doivent être traitées avec une attention particulière :
vente ;
paiement ;
réception ;
transfert ;
inventaire ;
ajustement de stock.
Exemple :
Une vente de 10 unités ne doit pas produire :
Facture : 10
mais :
Stock : -5
Le traitement doit être atomique selon les règles métier.
29. ÉVÉNEMENTS ET TÂCHES ASYNCHRONES
Certaines opérations peuvent être exécutées en arrière-plan :
envoi WhatsApp ;
génération de certains documents ;
rapports lourds ;
rappels de crédit ;
traitement de fichiers volumineux ;
tâches planifiées.
Cela évite de faire attendre inutilement l'utilisateur.
Exemple :
Paiement validé
↓
Paiement enregistré immédiatement
↓
Tâche d'envoi WhatsApp
↓
Message envoyé
30. JOURNALISATION ET AUDIT
Le système doit conserver les événements importants.
Exemple :
Utilisateur : vendeur01
Action : vente
Référence : FAC-2026-00125
Montant : 2 500 000 GNF
Date : 04/08/2026
Résultat : succès
L'audit permet notamment de comprendre :
qui a effectué l'action ;
quand ;
sur quelle donnée ;
quelle modification a été effectuée.
31. SÉCURITÉ DE L'ARCHITECTURE
La sécurité doit être présente à chaque niveau.
Frontend
routes protégées ;
validation des formulaires ;
gestion sécurisée de session.
API
authentification ;
autorisation ;
validation ;
limitation des accès.
Backend
permissions ;
validation métier ;
protection des secrets.
Base
accès restreint ;
contraintes ;
sauvegardes ;
chiffrement selon l'infrastructure.
Infrastructure
HTTPS ;
firewall ;
protection des serveurs ;
sauvegardes.
32. PERFORMANCE ET ÉVOLUTIVITÉ
L'application doit être conçue pour évoluer progressivement.
Au début, une architecture modulaire de type monolithe Django est préférable à une multiplication prématurée des microservices.
Django peut regrouper les domaines métier tout en conservant une séparation claire.
Si l'activité devient importante, certains services pourront ultérieurement être séparés.
Cette approche évite de rendre inutilement le projet complexe dès le départ.
33. GESTION DES ERREURS
Les erreurs doivent être gérées de manière uniforme.
Exemple :
Erreur réseau
Impossible de contacter le serveur. Vérifiez votre connexion.
Erreur métier
Stock insuffisant pour cette opération.
Permission
Vous n'avez pas l'autorisation d'effectuer cette action.
Erreur serveur
Une erreur est survenue. L'opération n'a pas été finalisée.
Le frontend doit traduire les erreurs techniques en messages compréhensibles.
34. CONFIGURATION ET VARIABLES D'ENVIRONNEMENT
Les informations sensibles doivent être stockées dans des variables d'environnement.
Exemples :
DATABASE_URL
SECRET_KEY
API_BASE_URL
WHATSAPP_API_KEY
STORAGE_ACCESS_KEY
Elles ne doivent jamais être inscrites directement dans le code source ou envoyées au frontend.
35. ENVIRONNEMENTS DE DÉVELOPPEMENT
Trois environnements sont recommandés.
Développement
Utilisé par les développeurs.
Préproduction
Utilisé pour tester la version avant publication.
Production
Utilisé par l'entreprise.
Les données de production ne doivent pas être utilisées librement dans l'environnement de développement.
36. DÉPLOIEMENT
Le déploiement doit séparer logiquement :
Frontend
et
Backend
Le frontend construit avec Vite produit les fichiers nécessaires à la diffusion de l'application.
Le backend Django fonctionne sur un serveur applicatif adapté.
PostgreSQL est déployé comme service de base de données.
Un reverse proxy peut être placé devant les services.
37. SAUVEGARDE ET RESTAURATION
Les données critiques doivent être sauvegardées régulièrement.
Les sauvegardes doivent couvrir au minimum :
base PostgreSQL ;
fichiers importants ;
configuration nécessaire à la restauration.
Une sauvegarde n'est considérée comme réellement utile que si sa restauration a été testée.
38. MONITORING ET SUPERVISION
L'environnement de production doit permettre de surveiller :
disponibilité de l'API ;
erreurs serveur ;
utilisation CPU ;
mémoire ;
espace disque ;
base de données ;
temps de réponse ;
tâches asynchrones ;
échecs de notifications.
L'objectif est de détecter les problèmes avant qu'ils deviennent bloquants pour l'entreprise.
39. MAINTENANCE ET ÉVOLUTIONS
L'architecture doit permettre d'ajouter progressivement de nouvelles fonctionnalités.
Exemples :
application mobile ;
nouveaux moyens de paiement ;
nouveaux fournisseurs ;
nouvelles intégrations ;
nouveaux rapports ;
nouvelles langues.
Une future application mobile pourrait utiliser exactement les mêmes API Django que l'application Web.
40. CRITÈRES DE VALIDATION
L'architecture sera considérée comme conforme lorsque :
Frontend
React + Vite est correctement structuré et modulaire.
Backend
Django est organisé par domaines métier.
API
Toutes les communications passent par les API REST.
Base de données
PostgreSQL constitue la source de vérité.
Navigation
Les routes sont protégées selon les permissions.
Services
Les opérations métier complexes sont centralisées dans des services dédiés.
Sécurité
Les secrets ne sont jamais exposés au frontend.
Transactions
Les opérations critiques conservent la cohérence entre ventes, stocks, paiements et factures.
Fichiers
Les documents et images sont gérés séparément des données métier lorsque nécessaire.
QR Codes
Les QR Codes peuvent être utilisés pour retrouver les produits, cartons et factures.
Notifications
Les intégrations externes restent découplées du cœur des opérations commerciales.
Évolutivité
L'architecture permet l'ajout ultérieur d'une application mobile ou de nouveaux services.
41. CONCLUSION
L'architecture technique proposée repose volontairement sur une séparation claire des responsabilités :
React + Vite s'occupe de l'expérience utilisateur.
Django REST Framework expose les fonctionnalités et contrôle les accès.
Les services métier Django portent les règles de fonctionnement de l'entreprise.
PostgreSQL conserve les données officielles.
Les services externes comme WhatsApp, le stockage de fichiers ou d'autres intégrations sont connectés au backend sans donner directement accès aux données internes.
Cette architecture permet d'avoir une application suffisamment simple à maintenir au démarrage tout en étant suffisamment solide pour évoluer avec l'entreprise.
Le principe directeur reste :
Une interface simple pour l'utilisateur, une logique métier centralisée et rigoureuse côté serveur, et une base de données protégée qui reste la source officielle de toutes les opérations.

