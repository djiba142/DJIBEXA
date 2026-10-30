MODÈLE DE DONNÉES ET SCHÉMA DE BASE DE DONNÉES
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence
Base de données : PostgreSQL
Backend : Django + Django REST Framework
Frontend : React + Vite + TypeScript
SOMMAIRE
Introduction
Objectifs du modèle de données
Principes généraux de conception
Organisation générale des données
Gestion de l'entreprise
Gestion des utilisateurs
Gestion des rôles et permissions
Gestion des emplacements
Gestion des catégories
Gestion des marques
Gestion des produits
Gestion des variantes et références
Gestion des unités et conditionnements
Gestion des prix
Gestion des fournisseurs
Gestion des commandes fournisseurs
Gestion des lignes de commande
Gestion des importations fournisseurs
Gestion des réceptions
Gestion des frais d'approvisionnement
Gestion des stocks
Gestion des mouvements de stock
Gestion des cartons
Gestion des QR Codes
Gestion des transferts
Gestion des inventaires
Gestion des ventes
Gestion des lignes de vente
Gestion des ventes externes
Gestion des clients
Gestion des crédits clients
Gestion des paiements
Gestion des factures
Gestion des dépenses
Gestion de la caisse
Gestion des notifications
Gestion des documents et fichiers
Gestion de l'audit
Relations principales entre les données
Historisation des données
Contraintes d'intégrité
Gestion des suppressions
Indexation et performance
Sécurité des données
Sauvegarde et restauration
Évolution du modèle
Critères de validation
Conclusion
1. INTRODUCTION
La base de données constitue le cœur de l'application.
Elle doit permettre de conserver de manière fiable toutes les informations liées à l'activité de l'entreprise :
produits ;
prix ;
fournisseurs ;
commandes ;
réceptions ;
stocks ;
cartons ;
QR Codes ;
ventes ;
clients ;
crédits ;
paiements ;
factures ;
dépenses ;
caisse ;
utilisateurs ;
notifications ;
historique des opérations.
Le modèle doit être conçu pour éviter les doublons et garantir que les différentes informations restent cohérentes entre elles.
L'objectif n'est donc pas simplement de créer des tables, mais de construire un modèle capable de représenter la réalité commerciale de l'entreprise.
2. OBJECTIFS DU MODÈLE DE DONNÉES
Le modèle doit permettre :
de retrouver rapidement un produit ;
de connaître son stock ;
de savoir où il se trouve ;
de connaître son fournisseur ;
de connaître son coût d'acquisition ;
de suivre ses mouvements ;
de l'associer à des ventes ;
de générer les factures correspondantes ;
de suivre les clients qui achètent à crédit ;
d'enregistrer les paiements ;
de conserver les historiques.
La base doit également permettre de répondre à des questions telles que :
Combien de produits avons-nous actuellement ?
Dans quel entrepôt se trouvent-ils ?
Combien avons-nous vendu cette semaine ?
Quel vendeur a effectué cette vente ?
Combien un client doit-il encore ?
Combien avons-nous payé au fournisseur ?
Quel est le coût réel d'un produit après transport et douane ?
Combien avons-nous dépensé ?
Quelle est la valeur actuelle du stock ?
3. PRINCIPES GÉNÉRAUX DE CONCEPTION
Le modèle repose sur plusieurs principes.
3.1 Une donnée ne doit pas être inutilement dupliquée
Par exemple, les informations d'un produit ne doivent pas être copiées dans toutes les tables.
Les autres tables utilisent une référence vers le produit.
3.2 Les opérations commerciales doivent être historisées
Une vente validée doit rester identifiable.
Une modification ultérieure du produit ne doit pas modifier l'historique d'une ancienne facture.
3.3 Les montants doivent être précis
Les montants financiers doivent utiliser un type numérique adapté aux valeurs monétaires.
Les calculs ne doivent pas être effectués avec des nombres flottants pouvant introduire des erreurs d'arrondi.
3.4 Les dates doivent être correctement conservées
Les dates des opérations doivent permettre de reconstruire l'historique :
commande ;
réception ;
vente ;
paiement ;
dépense ;
transfert.
4. ORGANISATION GÉNÉRALE DES DONNÉES
Les données peuvent être regroupées en grands domaines :
Entreprise
    ↓
Utilisateurs
    ↓
Produits
    ↓
Achats ─── Fournisseurs
    ↓
Réceptions
    ↓
Stocks
    ↓
Ventes ─── Clients
    ↓
Factures
    ↓
Paiements
    ↓
Finance
Autour de ce noyau se trouvent :
QR Codes ;
cartons ;
notifications ;
fichiers ;
audit ;
rapports.
5. GESTION DE L'ENTREPRISE
Le système est conçu autour d'une entreprise.
Une entité Company peut contenir :
identifiant ;
raison sociale ;
nom commercial ;
téléphone ;
e-mail ;
adresse ;
logo ;
devise principale ;
informations fiscales ;
paramètres commerciaux.
Les données de l'entreprise doivent être centralisées afin d'éviter de répéter ces informations dans plusieurs tables.
6. GESTION DES UTILISATEURS
La table des utilisateurs contient notamment :
identifiant ;
nom ;
prénom ;
téléphone ;
e-mail ;
identifiant de connexion ;
statut ;
rôle ;
date de création ;
dernière connexion.
Un utilisateur peut effectuer plusieurs opérations.
Par exemple :
Utilisateur → plusieurs ventes
Utilisateur → plusieurs paiements
Utilisateur → plusieurs réceptions
7. GESTION DES RÔLES ET PERMISSIONS
Les rôles permettent de déterminer les actions autorisées.
Exemples :
administrateur ;
responsable ;
vendeur ;
gestionnaire de stock ;
responsable achats ;
comptable.
Une permission peut être :
consulter ;
créer ;
modifier ;
valider ;
annuler ;
exporter ;
imprimer.
La permission doit être contrôlée côté backend.
8. GESTION DES EMPLACEMENTS
Le système doit pouvoir gérer plusieurs emplacements.
Exemples :
boutique ;
entrepôt principal ;
entrepôt secondaire ;
dépôt.
Chaque emplacement possède :
identifiant ;
nom ;
type ;
adresse ;
statut.
Le stock est associé à un emplacement.
9. GESTION DES CATÉGORIES
Les produits doivent pouvoir être regroupés par catégorie.
Exemple :
Électronique
   ├── Téléphones
   ├── Ordinateurs
   └── Accessoires
Une catégorie peut contenir plusieurs produits.
Le système peut également permettre des catégories hiérarchiques.
10. GESTION DES MARQUES
Une marque possède :
identifiant ;
nom ;
description ;
logo éventuel ;
statut.
Un produit peut être associé à une marque.
11. GESTION DES PRODUITS
La table Product constitue une donnée centrale.
Elle doit notamment contenir :
identifiant ;
référence interne ;
nom ;
description ;
catégorie ;
marque ;
unité ;
image ;
statut ;
date de création.
Le produit peut également avoir :
référence fournisseur ;
code-barres ;
QR Code ;
poids ;
dimensions ;
caractéristiques.
12. GESTION DES VARIANTES ET RÉFÉRENCES
Certains produits peuvent exister en plusieurs variantes.
Exemple :
T-shirt
taille S ;
taille M ;
taille L ;
taille XL.
Ou :
Téléphone
128 Go ;
256 Go.
Chaque variante peut disposer de sa propre référence.
13. GESTION DES UNITÉS ET CONDITIONNEMENTS
Le système doit pouvoir gérer différents niveaux :
pièce ;
paquet ;
carton ;
lot.
Exemple :
1 carton = 20 pièces
Cette relation est importante pour les ventes et le stock.
Si le vendeur vend 5 pièces, le stock doit être diminué de 5 pièces.
14. GESTION DES PRIX
Le produit peut avoir plusieurs informations de prix :
prix d'achat ;
coût réel ;
prix de vente ;
prix promotionnel ;
prix grossiste ;
prix particulier.
Les prix doivent être historisés lorsque cela est nécessaire.
Une modification du prix actuel ne doit pas modifier le prix enregistré sur une ancienne vente.
15. GESTION DES FOURNISSEURS
La fiche fournisseur peut contenir :
nom ;
téléphone ;
e-mail ;
adresse ;
pays ;
devise ;
personne de contact ;
conditions de paiement ;
informations bancaires lorsque nécessaires ;
statut.
Un fournisseur peut avoir plusieurs commandes.
16. GESTION DES COMMANDES FOURNISSEURS
Une commande fournisseur possède :
numéro ;
fournisseur ;
date ;
devise ;
statut ;
montant ;
utilisateur créateur ;
document associé.
Statuts possibles :
BROUILLON
ENVOYÉE
CONFIRMÉE
PARTIELLEMENT_REÇUE
REÇUE
ANNULÉE
CLÔTURÉE
17. GESTION DES LIGNES DE COMMANDE
Une commande contient plusieurs lignes.
Chaque ligne peut contenir :
produit ;
quantité ;
prix unitaire ;
devise ;
remise éventuelle ;
montant.
Exemple :
Commande
 ├── Produit A × 20
 ├── Produit B × 10
 └── Produit C × 50
18. GESTION DES IMPORTATIONS FOURNISSEURS
Le système doit permettre d'importer un fichier reçu du fournisseur.
Le fichier peut contenir :
références ;
noms ;
quantités ;
prix ;
devises ;
images ;
informations produits.
Le fichier original doit pouvoir être conservé comme document de référence.
Le système doit également conserver le résultat du traitement :
produits reconnus ;
nouveaux produits ;
éléments nécessitant une vérification ;
erreurs.
19. GESTION DES RÉCEPTIONS
Une réception correspond à l'arrivée réelle des marchandises.
Elle est associée à une commande fournisseur.
Elle peut être :
complète ;
partielle.
Exemple :
Commande :
100 pièces
Réception :
60 pièces
Le système conserve :
Commandé : 100
Reçu : 60
Reste : 40
20. GESTION DES FRAIS D'APPROVISIONNEMENT
Les frais liés à l'achat doivent pouvoir être enregistrés.
Exemples :
transport ;
douane ;
manutention ;
assurance ;
frais portuaires ;
autres frais.
Ces informations permettent de calculer le coût réel d'acquisition.
21. GESTION DES STOCKS
Le stock représente la quantité réellement disponible.
Le modèle doit permettre de connaître :
produit ;
emplacement ;
quantité disponible ;
quantité réservée ;
quantité éventuellement en transit.
La quantité disponible ne doit pas être modifiée arbitrairement.
Elle doit être liée aux mouvements enregistrés.
22. GESTION DES MOUVEMENTS DE STOCK
Chaque modification importante du stock doit produire un mouvement.
Types possibles :
ENTRÉE
SORTIE
TRANSFERT
AJUSTEMENT
RETOUR
RÉCEPTION
VENTE
Un mouvement doit conserver :
produit ;
quantité ;
emplacement ;
opération source ;
utilisateur ;
date.
23. GESTION DES CARTONS
Un carton peut être identifié individuellement.
Il peut contenir :
identifiant ;
référence carton ;
produit ;
quantité ;
emplacement ;
statut ;
QR Code.
Le système peut ainsi retrouver rapidement un carton lors d'un scan.
24. GESTION DES QR CODES
Les QR Codes peuvent être associés à :
produit ;
carton ;
facture.
La base doit conserver une référence unique.
Exemple :
QR-PRD-000125
QR-CART-000845
QR-FAC-2026-00152
Le contenu exact du QR Code est généré selon la stratégie technique retenue.
25. GESTION DES TRANSFERTS
Un transfert relie deux emplacements.
Exemple :
Entrepôt → Boutique
Le transfert doit conserver :
origine ;
destination ;
produit ;
quantité ;
utilisateur ;
date ;
statut.
Un transfert peut avoir les états :
BROUILLON
VALIDÉ
EXPÉDIÉ
REÇU
ANNULÉ
26. GESTION DES INVENTAIRES
L'inventaire permet de comparer :
Stock théorique
avec
Stock réellement constaté.
Le système conserve :
date ;
emplacement ;
utilisateur ;
produit ;
quantité théorique ;
quantité réelle ;
différence ;
justification.
Une correction de stock doit produire un mouvement d'ajustement.
27. GESTION DES VENTES
Une vente possède :
numéro ;
vendeur ;
client éventuel ;
emplacement ;
date ;
montant ;
remise ;
mode de paiement ;
statut.
La vente est associée à plusieurs lignes.
28. GESTION DES LIGNES DE VENTE
Chaque ligne contient notamment :
produit ;
quantité ;
prix unitaire ;
remise ;
montant ;
origine éventuelle du produit.
Le prix enregistré dans la ligne constitue le prix appliqué lors de cette vente.
Il ne doit pas dépendre du prix actuel du produit.
29. GESTION DES VENTES EXTERNES
Le système doit pouvoir gérer le cas où l'entreprise reçoit une commande mais ne possède pas immédiatement toute la quantité demandée.
Exemple :
Le client demande :
100 pièces
La boutique possède :
20 pièces
Le reste peut être obtenu auprès d'un partenaire ou d'un autre fournisseur.
La vente peut néanmoins être enregistrée selon la règle métier définie précédemment.
La facture reste une facture commerciale unique lorsque c'est le fonctionnement retenu.
Les mouvements de stock doivent cependant refléter la provenance réelle des produits.
30. GESTION DES CLIENTS
Un client peut posséder :
identifiant ;
nom ;
téléphone ;
e-mail ;
adresse ;
type de client ;
statut.
Le système doit conserver son historique commercial.
Un client peut avoir :
plusieurs ventes ;
plusieurs factures ;
plusieurs paiements ;
plusieurs opérations de crédit.
31. GESTION DES CRÉDITS CLIENTS
Lorsqu'une vente est effectuée à crédit, le système crée une créance.
Le modèle doit permettre de connaître :
montant initial ;
montant payé ;
solde ;
date d'échéance ;
statut.
Exemple :
Vente : 1 000 000 GNF
Paiement : 400 000 GNF
Solde : 600 000 GNF
Un client peut effectuer plusieurs achats à crédit.
Le système doit donc pouvoir présenter une vision globale de ce qu'il doit.
32. GESTION DES PAIEMENTS
Chaque paiement doit être enregistré individuellement.
Il contient :
montant ;
client ;
facture ou créance concernée ;
mode de paiement ;
date ;
utilisateur ;
référence ;
statut.
Le paiement ne doit pas simplement modifier un champ solde.
Il doit créer une véritable opération financière.
33. GESTION DES FACTURES
Une facture contient :
numéro unique ;
client ;
date ;
lignes ;
quantités ;
prix ;
remises ;
taxes si applicables ;
total ;
statut ;
QR Code.
La facture doit rester une représentation officielle de la vente.
Elle doit pouvoir être :
consultée ;
imprimée ;
exportée en PDF ;
envoyée au client selon les fonctionnalités activées.
34. GESTION DES DÉPENSES
Les dépenses permettent de suivre les sorties financières qui ne correspondent pas directement à une vente.
Exemples :
transport ;
électricité ;
fournitures ;
maintenance ;
frais divers.
Une dépense contient :
montant ;
catégorie ;
date ;
description ;
utilisateur ;
justificatif éventuel.
35. GESTION DE LA CAISSE
La caisse permet de suivre les mouvements financiers.
Elle peut recevoir :
ventes comptant ;
paiements de crédits.
Elle peut enregistrer :
dépenses ;
sorties ;
corrections autorisées.
Chaque mouvement doit conserver sa source.
36. GESTION DES NOTIFICATIONS
Une notification possède :
destinataire ;
type ;
titre ;
contenu ;
date ;
statut lu/non lu.
Les notifications peuvent concerner :
nouvelle vente ;
paiement ;
réception ;
stock ;
crédit ;
opération importante.
37. GESTION DES DOCUMENTS ET FICHIERS
Les documents peuvent être associés à différents objets.
Exemple :
Fournisseur
   ↓
Commande
   ↓
Document fournisseur
ou :
Produit
   ↓
Image
ou :
Paiement
   ↓
Justificatif
Les fichiers doivent être référencés proprement sans surcharger les tables métier.
38. GESTION DE L'AUDIT
L'audit conserve les opérations sensibles.
Une entrée d'audit doit pouvoir contenir :
utilisateur ;
action ;
ressource ;
identifiant de la ressource ;
date ;
résultat ;
données pertinentes avant/après lorsque nécessaire.
Exemple :
Utilisateur : vendeur01
Action : VALIDATION_VENTE
Référence : FAC-2026-00125
Résultat : SUCCÈS
39. RELATIONS PRINCIPALES ENTRE LES DONNÉES
Les relations fondamentales sont les suivantes :
@startuml

entity Company
entity User
entity Role
entity Product
entity Category
entity Brand
entity Supplier
entity PurchaseOrder
entity PurchaseLine
entity Receipt
entity Stock
entity StockMovement
entity Location
entity Customer
entity Sale
entity SaleLine
entity Invoice
entity Credit
entity Payment
entity Expense
entity CashTransaction
entity Carton
entity QRCode
entity AuditLog

Company ||--o{ User
Role ||--o{ User

Category ||--o{ Product
Brand ||--o{ Product

Supplier ||--o{ PurchaseOrder
PurchaseOrder ||--o{ PurchaseLine
Product ||--o{ PurchaseLine

PurchaseOrder ||--o{ Receipt
Receipt ||--o{ StockMovement

Product ||--o{ Stock
Location ||--o{ Stock
Product ||--o{ StockMovement

Location ||--o{ Carton
Product ||--o{ Carton
Carton ||--o| QRCode

Customer ||--o{ Sale
User ||--o{ Sale
Sale ||--o{ SaleLine
Product ||--o{ SaleLine

Sale ||--|| Invoice
Invoice ||--o{ Payment

Customer ||--o{ Credit
Credit ||--o{ Payment

Expense ||--o{ CashTransaction

User ||--o{ AuditLog

@enduml
40. HISTORISATION DES DONNÉES
Certaines données doivent conserver leur historique.
C'est particulièrement important pour :
prix ;
ventes ;
factures ;
paiements ;
stocks ;
crédits ;
dépenses.
Par exemple, si le prix d'un produit passe de :
50 000 GNF
à :
55 000 GNF
une ancienne facture à 50 000 GNF doit rester à 50 000 GNF.
41. CONTRAINTES D'INTÉGRITÉ
La base doit empêcher certaines incohérences.
Exemples :
quantité négative interdite lorsque la règle métier ne l'autorise pas ;
référence produit unique ;
numéro de facture unique ;
référence de paiement unique lorsque nécessaire ;
QR Code unique ;
relation fournisseur valide ;
relation produit valide.
Les contraintes doivent être appliquées au niveau Django et, lorsque pertinent, au niveau PostgreSQL.
42. GESTION DES SUPPRESSIONS
Les données historiques importantes ne doivent généralement pas être supprimées physiquement.
Pour les produits, utilisateurs, fournisseurs ou clients, il est préférable de pouvoir utiliser un statut :
ACTIF
INACTIF
ARCHIVÉ
Cela permet de conserver l'historique.
Une facture validée ne doit pas être supprimée comme une simple ligne de configuration.
43. INDEXATION ET PERFORMANCE
Des index doivent être prévus sur les champs fréquemment recherchés.
Exemples :
référence produit ;
code QR ;
code-barres ;
numéro facture ;
téléphone client ;
date de vente ;
fournisseur ;
emplacement ;
statut.
L'objectif est de permettre des recherches rapides même lorsque la base devient importante.
44. SÉCURITÉ DES DONNÉES
La base de données doit être accessible uniquement par les services autorisés.
Les utilisateurs finaux ne doivent jamais avoir un accès direct à PostgreSQL.
Les informations sensibles doivent bénéficier de mesures de protection adaptées.
Les accès à la base doivent être limités.
Les sauvegardes doivent également être protégées.
45. SAUVEGARDE ET RESTAURATION
La base PostgreSQL doit être sauvegardée régulièrement.
Les sauvegardes doivent permettre de restaurer :
les produits ;
les stocks ;
les ventes ;
les factures ;
les paiements ;
les clients ;
les fournisseurs ;
les historiques.
Des tests de restauration doivent être réalisés périodiquement.
46. ÉVOLUTION DU MODÈLE
Le modèle doit pouvoir évoluer sans casser les données existantes.
De nouvelles fonctionnalités pourront nécessiter de nouvelles tables ou relations.
Exemples :
programme de fidélité ;
promotions ;
nouveaux moyens de paiement ;
application mobile ;
gestion avancée des commandes ;
nouveaux canaux de vente.
Les migrations Django doivent être utilisées pour faire évoluer proprement le schéma.
47. CRITÈRES DE VALIDATION
Le modèle de données sera considéré comme conforme lorsque :
Produits
Chaque produit possède une référence identifiable et peut être associé à son stock.
Stock
Les mouvements permettent de comprendre les variations de quantité.
Achats
Les commandes fournisseurs peuvent être liées aux réceptions.
Réceptions
Une réception partielle est correctement représentée.
Frais
Les frais d'approvisionnement peuvent être associés à une réception ou une opération d'achat.
Ventes
Une vente possède ses propres lignes et conserve les prix appliqués au moment de la vente.
Factures
Chaque facture possède une référence unique et reste associée à la vente correspondante.
Crédits
Les crédits permettent de calculer correctement les montants restant dus.
Paiements
Chaque paiement constitue une opération identifiable.
QR Codes
Chaque QR Code est associé à une ressource identifiable.
Audit
Les opérations sensibles sont traçables.
Intégrité
Les relations entre les données ne permettent pas de créer facilement des incohérences.
48. CONCLUSION
Le modèle de données constitue la fondation de toute l'application.
Il doit représenter fidèlement le fonctionnement réel de l'entreprise tout en restant suffisamment structuré pour accompagner son évolution.
La logique générale est :
Produits → Achats → Réceptions → Stocks → Ventes → Factures → Paiements → Finance
avec en parallèle :
Clients → Crédits → Paiements
et :
Cartons → QR Codes → Stocks
L'objectif principal est que chaque opération importante puisse être retrouvée, expliquée et vérifiée.
Ainsi, lorsqu'une quantité de stock change, le système doit pouvoir expliquer pourquoi elle a changé. Lorsqu'un client doit de l'argent, le système doit pouvoir expliquer d'où vient sa dette et quels paiements ont déjà été effectués. Lorsqu'une facture est consultée, son contenu doit rester cohérent avec la vente qui lui a donné naissance.
C'est cette logique qui permettra au système d'être fiable dans une utilisation quotidienne réelle, et pas seulement fonctionnel au niveau de l'interface.

