SPÉCIFICATIONS FONCTIONNELLES DÉTAILLÉES
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence fonctionnelle
Document associé : Document 01 — Cahier des charges fonctionnel et technique
SOMMAIRE
Introduction
Principes fonctionnels généraux
Module Tableau de bord
Module Utilisateurs, rôles et permissions
Module Entreprise, boutiques et entrepôts
Module Produits et catalogue
Module Fournisseurs
Module Commandes fournisseurs
Module Importation des fichiers fournisseurs
Module Devises et taux de change
Module Réception des marchandises
Module Frais d'acquisition et coût réel
Module Gestion des stocks
Module Transferts de stock
Module Cartons et conditionnements
Module QR Codes et scan
Module Ventes
Module Ventes externes
Module Facturation
Module Clients
Module Ventes à crédit
Module Paiements et recouvrement
Module Caisse et finances
Module Dépenses
Module Notifications et WhatsApp
Module Rapports et statistiques
Module Recherche globale
Module Multilingue
Module Sécurité et verrouillage
Module Audit et traçabilité
Module Gestion documentaire
Module Paramètres
Relations entre les modules
Règles métier transversales
Gestion des erreurs et cas particuliers
Critères fonctionnels de validation
1. INTRODUCTION
Le présent document décrit de manière détaillée le comportement attendu de chaque module du système.
Contrairement au cahier des charges général, qui présente les objectifs et le périmètre du projet, ce document précise ce que le logiciel doit faire, comment les utilisateurs doivent l'utiliser et quelles conséquences chaque opération doit produire dans le système.
L'objectif est de fournir une référence suffisamment précise pour permettre aux équipes de conception, de développement, de test et de validation de travailler sur une même compréhension du produit.
Le logiciel doit être conçu comme un système intégré. Les modules ne doivent donc pas fonctionner comme des applications indépendantes.
Par exemple, lorsqu'une vente est validée :
la facture est créée ;
le stock est diminué ;
le montant de la vente est enregistré ;
le paiement est enregistré s'il est effectué ;
une créance est créée si la vente est à crédit ;
les statistiques sont mises à jour ;
l'opération est inscrite dans l'audit ;
les notifications prévues sont déclenchées.
2. PRINCIPES FONCTIONNELS GÉNÉRAUX
2.1 Une seule entreprise
Le système est conçu autour d'une seule entreprise.
L'entreprise peut cependant posséder plusieurs structures physiques :
boutiques ;
entrepôts ;
autres emplacements de stockage autorisés.
Il ne faut donc pas confondre plusieurs emplacements avec plusieurs entreprises.
2.2 Boutique et entrepôt sont deux notions différentes
Une boutique est principalement un point de vente.
Un entrepôt est principalement un lieu de stockage.
Le système doit conserver cette distinction dans :
les données ;
les permissions ;
les mouvements ;
les rapports ;
les interfaces.
2.3 Le stock est toujours localisé
Une quantité de produit doit toujours être associée à un emplacement.
Exemple :
Filtre X — Boutique : 20
Filtre X — Entrepôt central : 300
Filtre X — Entrepôt secondaire : 150
Le stock global de 470 peut être calculé, mais il ne doit jamais remplacer le détail par emplacement.
3. MODULE TABLEAU DE BORD
3.1 Objectif
Le tableau de bord constitue la première interface de pilotage après connexion.
Il doit présenter une vision synthétique de la situation de l'entreprise.
3.2 Informations affichées
Selon les permissions de l'utilisateur, le tableau de bord peut afficher :
chiffre d'affaires ;
nombre de ventes ;
ventes du jour ;
ventes de la semaine ;
ventes du mois ;
paiements reçus ;
créances clients ;
achats ;
dépenses ;
valeur du stock ;
produits en rupture ;
produits sous seuil ;
mouvements récents ;
commandes fournisseurs en cours.
3.3 Personnalisation selon le rôle
Un vendeur ne doit pas recevoir le même tableau de bord que l'administrateur.
Administrateur
Il peut consulter les indicateurs globaux auxquels ses permissions lui donnent accès.
Vendeur
Il voit principalement :
ses ventes ;
ses factures ;
sa caisse si applicable ;
les produits disponibles pour la vente ;
les informations clients nécessaires.
Gestionnaire de stock
Il voit principalement :
les niveaux de stock ;
les transferts ;
les réceptions ;
les mouvements ;
les alertes de stock.
4. MODULE UTILISATEURS, RÔLES ET PERMISSIONS
4.1 Objectif
Le module contrôle qui peut accéder à quoi et qui peut effectuer chaque opération.
4.2 Création d'un utilisateur
L'administrateur peut créer un utilisateur avec :
nom ;
prénom ;
téléphone ;
adresse e-mail ;
identifiant ;
rôle ;
emplacement autorisé ;
statut du compte.
Le système génère ou demande les informations nécessaires à l'activation du compte.
4.3 Rôles
Le système doit supporter au minimum :
Administrateur ;
Vendeur ;
Gestionnaire de stock.
L'architecture doit permettre d'ajouter d'autres rôles ultérieurement.
4.4 Permissions
Les permissions doivent être granulaires.
Exemples :
consulter les produits ;
créer un produit ;
modifier un produit ;
supprimer ou archiver un produit ;
consulter le stock ;
effectuer un transfert ;
valider une réception ;
créer une vente ;
annuler une vente ;
modifier un prix ;
consulter les crédits ;
enregistrer un paiement ;
consulter les rapports.
4.5 Restriction de l'interface
L'application ne doit pas afficher à un utilisateur des fonctions qui ne le concernent pas lorsque celles-ci sont masquées par ses permissions.
Un vendeur ne doit donc pas voir les menus d'administration simplement parce qu'ils existent dans l'application.
Toutefois, la sécurité ne doit pas dépendre uniquement de l'interface.
Les permissions doivent également être contrôlées côté serveur.
5. MODULE ENTREPRISE, BOUTIQUES ET ENTREPÔTS
5.1 Entreprise
La fiche entreprise contient notamment :
raison sociale ;
nom commercial ;
logo ;
téléphone ;
e-mail ;
adresse ;
informations fiscales ;
devise principale ;
paramètres commerciaux.
5.2 Boutiques
Chaque boutique possède :
un nom ;
un code ;
une adresse ;
un responsable ;
des utilisateurs affectés ;
son stock ;
son historique de mouvements.
5.3 Entrepôts
Chaque entrepôt possède :
un nom ;
un code ;
une adresse ;
un responsable ;
des zones ;
éventuellement des rayons ;
des emplacements ;
son stock.
5.4 Stock par emplacement
Le système doit pouvoir présenter :
Produit X
Emplacement
Quantité
Boutique principale
20
Entrepôt central
300
Entrepôt secondaire
150
6. MODULE PRODUITS ET CATALOGUE
6.1 Création d'un produit
Une fiche produit peut contenir :
référence interne ;
nom ;
description ;
catégorie ;
sous-catégorie ;
marque ;
modèle ;
unité ;
conditionnement ;
image ;
prix d'achat ;
prix de vente ;
devise ;
référence fournisseur ;
seuil d'alerte.
6.2 Référence interne
Chaque produit doit avoir un identifiant unique.
Exemple :
PRD-000125
Cette référence est utilisée notamment pour la recherche et l'identification QR.
6.3 Références fournisseur
Un produit peut avoir une référence différente chez le fournisseur.
Le système doit pouvoir conserver les deux :
Référence interne : PRD-000125
Référence fournisseur : FT-9384
Cela facilite l'importation des fichiers fournisseurs.
6.4 Images
Une ou plusieurs images peuvent être associées à un produit selon les besoins.
L'image peut provenir :
d'une importation fournisseur ;
d'un téléversement manuel ;
d'une source autorisée par l'entreprise.
6.5 Statut du produit
Un produit peut être :
actif ;
inactif ;
archivé.
Un produit archivé ne doit pas disparaître de l'historique des anciennes ventes.
7. MODULE FOURNISSEURS
7.1 Fiche fournisseur
La fiche contient notamment :
nom ;
entreprise ;
téléphone ;
WhatsApp ;
e-mail ;
adresse ;
pays ;
devise habituelle ;
conditions commerciales ;
informations bancaires si nécessaires ;
documents associés.
7.2 Historique
Le système doit présenter :
commandes ;
réceptions ;
montants ;
paiements ;
produits achetés ;
documents associés.
8. MODULE COMMANDES FOURNISSEURS
8.1 Création
L'utilisateur autorisé sélectionne :
fournisseur ;
produits ;
quantités ;
prix prévisionnels ;
devise ;
date ;
conditions ;
destination prévue.
8.2 Statuts
Une commande peut passer par :
Brouillon → Envoyée → Confirmée → Partiellement reçue → Reçue → Clôturée
Les statuts doivent refléter la réalité de l'opération.
8.3 Une commande n'est pas une entrée de stock
Si l'entreprise commande :
100 pièces
mais reçoit :
80 pièces
le stock augmente uniquement de :
80 pièces.
9. MODULE IMPORTATION DES FICHIERS FOURNISSEURS
9.1 Objectif
Le fournisseur peut transmettre un fichier contenant les informations relatives à la commande.
Le système doit permettre de téléverser les formats pris en charge, notamment selon les besoins :
Excel ;
CSV ;
PDF structuré lorsque l'extraction est possible ;
autres formats prévus par le système.
9.2 Analyse
Après téléversement, le système analyse le fichier.
Il identifie notamment :
références ;
noms ;
quantités ;
prix ;
devises ;
images lorsqu'elles sont disponibles ;
informations complémentaires.
9.3 Correspondance automatique
Le système tente d'associer les produits du fichier aux produits existants.
Trois situations sont possibles :
Produit reconnu
Le système trouve une correspondance fiable.
Produit probablement reconnu
Une correspondance existe mais nécessite une validation.
Nouveau produit
Aucune correspondance n'est trouvée.
9.4 Validation humaine
L'utilisateur doit pouvoir vérifier les résultats avant de confirmer l'importation.
Le système ne doit pas modifier silencieusement les données importantes.
10. MODULE DEVISES ET TAUX DE CHANGE
10.1 Prix dans la devise d'origine
Le système doit conserver le prix transmis par le fournisseur.
Exemple :
Prix fournisseur : 10 USD
Le système conserve :
montant : 10 ;
devise : USD.
10.2 Conversion
Si la devise principale de l'entreprise est le GNF, le système peut afficher l'équivalent selon le taux applicable.
Exemple :
10 USD × taux de change = montant GNF
10.3 Historisation
Le taux utilisé pour une opération doit être conservé.
Une ancienne commande ne doit pas être recalculée avec un nouveau taux plusieurs semaines plus tard.
11. MODULE RÉCEPTION DES MARCHANDISES
11.1 Réception totale
Exemple :
Commandé : 100
Reçu : 100
La commande peut être clôturée après validation.
11.2 Réception partielle
Exemple :
Commandé : 100
Reçu : 70
Le système enregistre :
Reçu : 70
Restant : 30
Le stock augmente uniquement de 70.
11.3 Contrôle
La réception peut vérifier :
quantité ;
produit ;
référence ;
état ;
conditionnement ;
documents ;
anomalies éventuelles.
12. MODULE FRAIS D'ACQUISITION ET COÛT RÉEL
Les frais associés à l'importation doivent pouvoir être enregistrés.
Exemples :
transport ;
douane ;
manutention ;
assurance ;
frais portuaires ;
autres charges.
12.1 Répartition
Le système peut répartir les frais selon une méthode configurée :
quantité ;
valeur ;
poids ;
volume.
12.2 Coût réel
Le coût réel d'un produit devient :
coût d'achat + part des frais d'acquisition.
Ce coût sert ensuite à analyser correctement la rentabilité.
13. MODULE GESTION DES STOCKS
13.1 Consultation
L'utilisateur autorisé peut consulter :
stock par produit ;
stock par emplacement ;
stock global ;
stock disponible ;
stock réservé ;
seuil d'alerte.
13.2 Mouvements
Les mouvements peuvent provenir de :
réception ;
vente ;
transfert ;
retour ;
ajustement ;
inventaire ;
perte ;
correction autorisée.
13.3 Historique
Chaque mouvement doit comporter notamment :
produit ;
quantité ;
origine ;
destination si applicable ;
utilisateur ;
date ;
référence de l'opération ;
motif.
14. MODULE TRANSFERTS DE STOCK
14.1 Principe
Un transfert déplace une quantité d'un emplacement vers un autre.
Exemple :
Entrepôt central → Boutique
100 pièces deviennent :
Central : -100
Boutique : +100
14.2 Validation
Le transfert peut suivre :
Brouillon → Demandé → Validé → Expédié → Reçu
selon le niveau de contrôle choisi.
14.3 Permissions
Un utilisateur ne peut effectuer un transfert que s'il possède la permission correspondante.
Le système doit également vérifier qu'il existe une quantité suffisante dans l'emplacement source.
15. MODULE CARTONS ET CONDITIONNEMENTS
15.1 Conditionnement
Un produit peut être vendu à :
l'unité ;
la boîte ;
la pièce ;
le carton ;
autre unité configurée.
15.2 Carton
Un carton peut contenir :
100 pièces d'un même produit
et recevoir un identifiant :
CTN-000125
15.3 QR du carton
Le QR du carton permet de retrouver :
identifiant ;
produit ;
quantité ;
emplacement ;
date de création ;
informations de traçabilité.
16. MODULE QR CODES ET SCAN
16.1 QR produit
Chaque produit peut posséder un QR Code généré par le système.
16.2 QR carton
Chaque carton peut également avoir son propre QR Code.
16.3 QR facture
Chaque facture possède également un QR Code.
Celui-ci permet d'identifier rapidement la facture et de retrouver les informations prévues par le système.
16.4 Ordinateur
Le vendeur peut :
saisir le code ;
utiliser un scanner QR USB ;
rechercher manuellement.
16.5 Téléphone
Le vendeur peut utiliser la caméra du téléphone ou de la tablette.
16.6 Sécurité du scan
Un scan ne doit pas provoquer automatiquement une opération irréversible sans validation lorsque l'opération nécessite une confirmation.
Le système doit également empêcher les doubles traitements accidentels.
17. MODULE VENTES
17.1 Création d'une vente
Le vendeur sélectionne :
client éventuel ;
produits ;
quantités ;
prix ;
remise autorisée ;
mode de paiement.
17.2 Ajout d'un produit
Le produit peut être ajouté par :
recherche ;
référence ;
QR ;
scanner ;
sélection du catalogue.
17.3 Vérification du stock
Le système connaît la disponibilité du produit selon l'emplacement.
Exemple :
Boutique : 5
Entrepôt A : 100
Entrepôt B : 50
Le vendeur peut consulter ces informations selon ses permissions.
17.4 Validation
Lorsque la vente est validée :
la facture est générée ;
le stock est mis à jour ;
le paiement est enregistré si applicable ;
la créance est créée si nécessaire ;
l'audit est enregistré.
18. MODULE VENTES EXTERNES
18.1 Objectif
Ce module permet de satisfaire un client lorsque l'entreprise ne dispose pas immédiatement du produit demandé.
Exemple :
Client demande :
100 pièces
Stock interne :
0
L'entreprise peut rechercher le produit auprès d'un partenaire ou fournisseur.
18.2 Facture unique
La vente doit rester présentée comme une seule opération commerciale.
Si une commande contient :
produits disponibles en interne ;
produits obtenus à l'extérieur ;
ils peuvent apparaître ensemble sur la même facture selon les règles commerciales définies.
18.3 Stock
Le système doit néanmoins conserver la traçabilité interne de l'origine des produits.
Une vente externe ne doit pas créer artificiellement un stock qui n'existe pas.
19. MODULE FACTURATION
19.1 Génération automatique
Une facture est générée après validation de la vente.
Elle possède un numéro unique.
Exemple :
FAC-2026-000125
19.2 Contenu
La facture peut contenir :
logo ;
informations entreprise ;
client ;
numéro ;
date ;
produits ;
quantités ;
prix ;
remises ;
taxes si applicables ;
total ;
montant payé ;
reste à payer ;
mode de paiement ;
QR Code.
19.3 Une facture pour une vente
Le système doit éviter de fragmenter inutilement une même opération commerciale.
19.4 Impression et PDF
La facture doit pouvoir être :
affichée ;
imprimée ;
générée en PDF ;
archivée.
20. MODULE CLIENTS
20.1 Fiche client
Informations :
nom ;
téléphone ;
WhatsApp ;
e-mail ;
adresse ;
type de client ;
historique.
20.2 Historique
Le système présente :
achats ;
factures ;
paiements ;
crédits ;
soldes.
21. MODULE VENTES À CRÉDIT
21.1 Principe
Une vente peut être :
totalement payée ;
partiellement payée ;
entièrement à crédit.
21.2 Exemple
Facture :
5 000 000 GNF
Paiement :
2 000 000 GNF
Solde :
3 000 000 GNF
Le système crée automatiquement une créance de 3 000 000 GNF.
21.3 Plusieurs crédits
Un même client peut avoir plusieurs factures impayées.
Le système doit présenter :
Dette globale du client
tout en conservant le détail de chaque facture.
22. MODULE PAIEMENTS ET RECOUVREMENT
22.1 Enregistrement
Lorsqu'un client paie, l'utilisateur recherche sa fiche puis enregistre :
montant ;
date ;
mode de paiement ;
référence éventuelle ;
utilisateur ayant enregistré le paiement.
22.2 Paiement partiel
Si le client doit :
6 000 000
et paie :
2 000 000
le système calcule automatiquement :
Solde : 4 000 000
22.3 Paiement total
Si le client règle la totalité :
Solde = 0
La créance passe au statut approprié.
22.4 Reçu
Un reçu peut être généré après validation du paiement.
23. MODULE CAISSE ET FINANCES
Le système doit centraliser les mouvements financiers liés aux opérations commerciales.
Il peut suivre :
encaissements ;
paiements ;
ventes ;
remboursements ;
dépenses ;
autres mouvements autorisés.
Les informations financières doivent rester cohérentes avec les ventes et paiements enregistrés.
24. MODULE DÉPENSES
Les utilisateurs autorisés peuvent enregistrer :
transport ;
fournitures ;
entretien ;
frais administratifs ;
autres dépenses.
Chaque dépense peut contenir :
catégorie ;
montant ;
date ;
bénéficiaire ;
justificatif ;
commentaire ;
utilisateur.
25. MODULE NOTIFICATIONS ET WHATSAPP
25.1 Notification de vente
Après une vente, l'administrateur peut recevoir une notification selon la configuration.
La notification peut contenir :
vendeur ;
montant ;
numéro de facture ;
client ;
heure ;
mode de paiement.
25.2 Confirmation client
Le client peut recevoir un message après :
une vente ;
un paiement ;
une génération de facture ;
une autre opération configurée.
25.3 Rappel de crédit
Les clients ayant un solde impayé peuvent recevoir des rappels périodiques.
Le système doit arrêter automatiquement les rappels lorsque :
solde = 0.
26. MODULE RAPPORTS ET STATISTIQUES
Les rapports doivent pouvoir être filtrés par :
période ;
boutique ;
entrepôt ;
produit ;
catégorie ;
vendeur ;
client ;
fournisseur ;
mode de paiement.
26.1 Rapport ventes
Informations possibles :
chiffre d'affaires ;
nombre de ventes ;
quantité vendue ;
produits les plus vendus ;
ventes par vendeur ;
ventes par emplacement.
26.2 Rapport stock
Informations :
stock actuel ;
mouvements ;
entrées ;
sorties ;
ruptures ;
stocks faibles.
26.3 Rapport crédits
Informations :
total des créances ;
clients débiteurs ;
paiements ;
soldes ;
créances anciennes.
27. MODULE RECHERCHE GLOBALE
Une recherche centrale doit permettre de retrouver rapidement :
produit ;
client ;
fournisseur ;
facture ;
commande ;
carton ;
QR ;
paiement.
La recherche doit supporter les références internes et les références externes.
28. MODULE MULTILINGUE
Le changement de langue doit affecter l'ensemble de l'interface.
Il ne doit pas seulement traduire le menu principal.
Il doit également prendre en compte :
boutons ;
formulaires ;
messages ;
erreurs ;
notifications ;
tableaux ;
fenêtres de confirmation ;
paramètres ;
textes système.
Les identifiants commerciaux tels que références, numéros de facture et codes QR ne doivent évidemment pas être modifiés par la traduction.
29. MODULE SÉCURITÉ ET VERROUILLAGE
29.1 Connexion
L'utilisateur doit s'authentifier avec les mécanismes configurés.
29.2 Verrouillage automatique
Après une période d'inactivité configurée :
Session active → verrouillage.
29.3 Déverrouillage
Selon les capacités du terminal, le système peut proposer :
empreinte digitale ;
reconnaissance faciale ;
PIN ;
mot de passe.
La biométrie doit être utilisée via les mécanismes sécurisés du système d'exploitation lorsque cela est possible.
29.4 Opérations sensibles
Certaines actions peuvent demander une réauthentification :
changement important de prix ;
annulation de vente ;
suppression ;
correction de stock ;
remboursement ;
modification financière importante.
30. MODULE AUDIT ET TRAÇABILITÉ
Le système doit enregistrer les actions importantes.
Exemple :
Utilisateur : vendeur01
Action : Vente
Facture : FAC-2026-000125
Montant : 1 500 000 GNF
Date : 12/08/2026
30.1 Traçabilité stock
Le système doit permettre de répondre :
Pourquoi le stock est-il passé de 100 à 80 ?
Réponse :
Vente FAC-2026-000125 — 20 unités.
30.2 Traçabilité financière
Même logique pour les paiements et corrections.
31. MODULE GESTION DOCUMENTAIRE
Le système peut conserver :
factures ;
commandes ;
bons de réception ;
fichiers fournisseurs ;
reçus ;
justificatifs ;
documents administratifs.
Chaque document doit être rattaché à son opération lorsqu'une relation existe.
32. MODULE PARAMÈTRES
L'administrateur peut configurer :
entreprise ;
logo ;
devises ;
taux de change ;
langues ;
règles de stock ;
seuils d'alerte ;
modes de paiement ;
numérotation ;
notifications ;
paramètres WhatsApp ;
sécurité ;
paramètres de facturation.
33. RELATIONS ENTRE LES MODULES
Le système doit fonctionner selon les relations suivantes :
Produits ↔ Fournisseurs
Un produit peut être fourni par plusieurs fournisseurs.
Produits ↔ Stocks
Un produit peut être présent dans plusieurs emplacements.
Produits ↔ Ventes
Une vente contient un ou plusieurs produits.
Ventes ↔ Factures
Une vente validée génère sa facture.
Factures ↔ Paiements
Une facture peut recevoir un ou plusieurs paiements.
Clients ↔ Factures
Un client peut avoir plusieurs factures.
Clients ↔ Crédits
Un client peut avoir plusieurs créances.
Commandes ↔ Réceptions
Une commande peut être reçue en une ou plusieurs fois.
Réceptions ↔ Stocks
Une réception validée augmente le stock de l'emplacement concerné.
Transferts ↔ Stocks
Un transfert diminue le stock source et augmente le stock destination.
34. RÈGLES MÉTIER TRANSVERSALES
RB-001 — Une seule entreprise
Le système gère une seule entreprise dans le périmètre actuel.
RB-002 — Stock par emplacement
Chaque quantité est rattachée à un emplacement.
RB-003 — Commande ≠ réception
Une commande ne modifie pas directement le stock.
RB-004 — Réception validée = entrée
Seule une réception validée peut créer une entrée de stock.
RB-005 — Vente validée = sortie
Une vente validée entraîne la sortie correspondante du stock lorsque les produits proviennent du stock interne.
RB-006 — Facture unique
Une opération commerciale doit être représentée par une facture cohérente.
RB-007 — Crédit
Une facture partiellement ou non payée crée une créance.
RB-008 — Paiement
Chaque paiement modifie automatiquement le solde concerné.
RB-009 — Audit
Toute opération sensible doit être traçable.
RB-010 — Permission
Aucun utilisateur ne doit pouvoir effectuer une opération pour laquelle il ne possède pas la permission.
35. GESTION DES ERREURS ET CAS PARTICULIERS
Le système doit gérer proprement les situations inhabituelles.
Produit inexistant
Le système propose de créer ou d'associer le produit.
Stock insuffisant
Le système indique que la quantité disponible est insuffisante et propose, selon les permissions, de consulter les autres emplacements.
Réception partielle
La commande reste ouverte jusqu'à réception complète ou clôture autorisée.
Paiement partiel
Le système conserve automatiquement le solde.
Client sans téléphone
La vente reste possible si le téléphone n'est pas obligatoire.
Fichier fournisseur incorrect
Le système refuse ou isole les lignes problématiques sans corrompre les données existantes.
Double scan
Le système évite de traiter deux fois le même événement.
Suppression
Les données historiques importantes ne doivent pas être supprimées physiquement sans procédure appropriée. L'archivage ou l'annulation contrôlée doit être privilégié.
36. CRITÈRES FONCTIONNELS DE VALIDATION
Le système sera considéré fonctionnellement conforme lorsque les scénarios principaux suivants seront correctement exécutés.
Scénario 1 — Achat
Commande → Fichier fournisseur → Importation → Validation → Réception → Frais → Coût réel → Stock
Scénario 2 — Transfert
Entrepôt → Transfert → Validation → Boutique
Le stock source diminue et le stock destination augmente.
Scénario 3 — Vente
Produit → Scan → Panier → Validation → Facture → Stock diminué
Scénario 4 — Vente à crédit
Vente → Facture → Paiement partiel → Créance → Solde
Scénario 5 — Paiement ultérieur
Recherche client → Paiement → Affectation → Nouveau solde → Reçu → Notification
Scénario 6 — Vente externe
Client → Produit indisponible → Approvisionnement externe → Vente → Facture unique → Traçabilité
Scénario 7 — Recherche de stock
Produit → Recherche → Boutique + Entrepôts → Quantités disponibles
Scénario 8 — QR Code
Scan → Identification → Produit/Carton/Facture → Affichage des informations
CONCLUSION
Les spécifications fonctionnelles détaillées constituent désormais la référence opérationnelle de fonctionnement du logiciel.
Le point essentiel est que le système ne doit pas être développé comme une collection de pages indépendantes. Chaque écran doit être relié à une règle métier et chaque opération doit produire les mises à jour nécessaires dans les modules concernés.
Le parcours de référence reste :
Fournisseur → Commande → Importation → Réception → Frais → Coût réel → Entrepôt → Transfert → Boutique → Vente → Facture → Paiement → Crédit → Notification → Reporting → Audit.
Cette structure servira de base aux documents suivants, notamment les spécifications techniques, règles métier, modèle de données, architecture, API, interfaces, sécurité, tests et procédures de déploiement.

