SPÉCIFICATIONS UI/UX ET DESIGN SYSTEM
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence
Document précédent : Document 02 — Spécifications fonctionnelles détaillées
Objet : Définir l'expérience utilisateur, l'organisation des écrans, la navigation, les composants d'interface, le responsive design et le système visuel de l'application.
SOMMAIRE
Introduction
Objectifs UI/UX
Principes généraux de conception
Profils utilisateurs et expérience adaptée
Architecture générale de l'interface
Navigation de l'application
Structure du Layout principal
Tableau de bord
Écran de gestion des produits
Écran de gestion des stocks
Écran boutiques et entrepôts
Écran des fournisseurs
Écran des commandes fournisseurs
Écran d'importation des fichiers fournisseurs
Écran de réception des marchandises
Écran des frais et du coût de revient
Écran des transferts
Écran des cartons et QR Codes
Écran de vente / caisse
Écran de vente externe
Écran de facturation
Écran clients
Écran crédits clients
Écran paiements et recouvrement
Écran caisse et finances
Écran dépenses
Écran notifications et WhatsApp
Écran rapports et statistiques
Recherche globale
Gestion multilingue
Authentification et sécurité UI
Responsive design
Design mobile
Design tablette
Design ordinateur
Design System
Couleurs
Typographie
Icônes
Boutons
Champs et formulaires
Tableaux
Cartes et indicateurs
Badges et statuts
Modales et confirmations
Notifications et messages système
États des interfaces
Accessibilité
Cohérence visuelle
Règles UX pour les opérations sensibles
Principes d'impression
Performance de l'interface
Critères de validation UI/UX
Conclusion
1. INTRODUCTION
Ce document définit la manière dont l'utilisateur doit voir, comprendre et utiliser le logiciel.
L'objectif n'est pas uniquement de rendre l'application esthétique. L'interface doit surtout permettre à chaque utilisateur d'effectuer son travail rapidement, avec le moins d'erreurs possible.
Le système gère des opérations commerciales importantes : achats, stocks, transferts, ventes, factures, crédits et paiements. Une mauvaise conception de l'interface pourrait donc provoquer des erreurs opérationnelles ou financières.
L'interface doit par conséquent être :
claire ;
professionnelle ;
rapide ;
cohérente ;
responsive ;
accessible ;
adaptée au rôle de l'utilisateur ;
adaptée au contexte d'utilisation.
Une personne travaillant à la caisse ne doit pas être obligée de parcourir plusieurs écrans complexes pour enregistrer une vente.
De la même manière, un gestionnaire de stock doit pouvoir comprendre immédiatement les niveaux de stock et les mouvements.
2. OBJECTIFS UI/UX
Le design doit répondre aux objectifs suivants.
2.1 Simplicité
L'utilisateur doit comprendre immédiatement où il se trouve et ce qu'il peut faire.
2.2 Rapidité
Les opérations fréquentes doivent nécessiter le moins d'étapes possible.
2.3 Cohérence
Un même élément doit toujours fonctionner de la même manière.
2.4 Prévention des erreurs
L'interface doit aider l'utilisateur à éviter les erreurs plutôt que de simplement les signaler après coup.
2.5 Adaptation au rôle
Chaque utilisateur doit voir principalement les fonctions qui correspondent à ses responsabilités.
2.6 Responsive
L'application doit fonctionner correctement sur :
ordinateur ;
tablette ;
téléphone.
3. PRINCIPES GÉNÉRAUX DE CONCEPTION
3.1 Ne pas surcharger l'écran
Une interface de gestion ne doit pas afficher toutes les informations simultanément.
Les informations principales sont affichées immédiatement.
Les informations secondaires peuvent être accessibles dans :
panneaux ;
onglets ;
fenêtres ;
détails ;
menus contextuels.
3.2 Une action principale par écran
Chaque écran important doit avoir une action principale clairement identifiable.
Exemple :
Produits → Ajouter un produit
Commandes → Nouvelle commande
Stock → Nouveau transfert
Ventes → Nouvelle vente
3.3 Navigation prévisible
L'utilisateur doit savoir :
où il se trouve ;
comment revenir ;
où trouver une fonction ;
quelle action est disponible.
4. PROFILS UTILISATEURS ET EXPÉRIENCE ADAPTÉE
Le système doit adapter l'interface selon les permissions.
Administrateur
Interface complète selon les droits attribués.
Il peut notamment accéder aux :
utilisateurs ;
produits ;
fournisseurs ;
stocks ;
ventes ;
finances ;
rapports ;
paramètres ;
audit.
Vendeur
Interface orientée vers :
ventes ;
clients ;
factures ;
paiements autorisés ;
consultation des produits ;
disponibilité des stocks autorisés.
Gestionnaire de stock
Interface orientée vers :
produits ;
stocks ;
réceptions ;
transferts ;
cartons ;
inventaires.
Important : masquer un menu ne suffit pas à sécuriser une fonctionnalité. Les permissions doivent également être appliquées côté serveur.
5. ARCHITECTURE GÉNÉRALE DE L'INTERFACE
L'application utilise une architecture de type Back-Office / Application métier.
Sur ordinateur, l'écran principal est organisé autour de :
une barre latérale ;
une barre supérieure ;
une zone de contenu ;
éventuellement un panneau secondaire.
Structure conceptuelle :
Navigation principale → Barre supérieure → Contenu → Actions
6. NAVIGATION DE L'APPLICATION
La navigation principale peut être organisée ainsi :
Accueil
Tableau de bord
Commerce
Ventes
Factures
Clients
Crédits
Stock
Produits
Stocks
Boutiques
Entrepôts
Transferts
Cartons / QR Codes
Approvisionnement
Fournisseurs
Commandes
Réceptions
Importations
Finance
Caisse
Paiements
Dépenses
Analyse
Rapports
Statistiques
Administration
Utilisateurs
Notifications
Audit
Paramètres
Les menus doivent être affichés selon les permissions.
7. STRUCTURE DU LAYOUT PRINCIPAL
7.1 Barre latérale
La sidebar contient :
logo de l'entreprise ;
nom de l'application ;
menus ;
sous-menus ;
profil utilisateur ;
bouton de verrouillage ou déconnexion.
Elle peut être :
développée ;
réduite ;
remplacée par un menu mobile.
7.2 Barre supérieure
Elle contient notamment :
titre de la page ;
fil d'Ariane si nécessaire ;
recherche ;
notifications ;
langue ;
profil utilisateur.
7.3 Zone principale
La zone principale contient :
titre ;
description courte ;
actions principales ;
filtres ;
contenu ;
pagination.
8. TABLEAU DE BORD
Le tableau de bord doit donner une compréhension immédiate de la situation.
Indicateurs principaux
ventes du jour ;
chiffre d'affaires ;
paiements ;
crédits ;
stock ;
commandes en cours.
Visualisations
Les graphiques doivent rester simples.
Exemples :
évolution des ventes ;
ventes par période ;
produits les plus vendus ;
état des crédits ;
évolution du stock.
Activité récente
Une liste chronologique peut afficher :
Vente enregistrée
Réception validée
Paiement reçu
Transfert effectué
9. ÉCRAN PRODUITS
L'écran produit doit proposer :
Titre : Produits
Actions :
Ajouter un produit ;
Importer ;
Exporter.
Filtres :
catégorie ;
marque ;
statut ;
fournisseur.
Le tableau peut afficher :
Produit
Référence
Catégorie
Stock
Prix
Statut
Chaque ligne peut ouvrir une fiche détaillée.
10. FICHE PRODUIT
La fiche doit être organisée clairement.
En-tête
image ;
nom ;
référence ;
statut.
Informations
description ;
catégorie ;
marque ;
fournisseur ;
conditionnement.
Prix
prix d'achat ;
coût réel ;
prix de vente ;
devise.
Stock
Afficher :
boutique ;
entrepôt 1 ;
entrepôt 2 ;
total.
QR Code
Afficher le QR Code du produit avec possibilité de :
l'imprimer ;
le régénérer selon les règles ;
télécharger l'étiquette.
11. ÉCRAN STOCKS
L'écran doit permettre de comprendre rapidement où se trouve la marchandise.
Filtres :
produit ;
emplacement ;
catégorie ;
statut.
Exemple :
Produit
Boutique
Entrepôt A
Entrepôt B
Total
Produit A
20
300
150
470
La consultation détaillée permet ensuite d'afficher les mouvements.
12. ÉCRAN BOUTIQUES ET ENTREPÔTS
Les boutiques et entrepôts doivent être présentés comme des emplacements distincts de la même entreprise.
La fiche d'un emplacement affiche :
nom ;
type ;
adresse ;
responsable ;
utilisateurs autorisés ;
stock ;
mouvements récents.
Le type doit être clairement visible :
BOUTIQUE
ou
ENTREPÔT
afin d'éviter toute confusion.
13. ÉCRAN FOURNISSEURS
L'écran contient :
recherche ;
filtres ;
bouton nouveau fournisseur ;
liste des fournisseurs.
La fiche fournisseur présente :
informations générales ;
contacts ;
commandes ;
réceptions ;
historique ;
documents.
14. ÉCRAN COMMANDES FOURNISSEURS
L'écran affiche :
numéro ;
fournisseur ;
date ;
montant ;
statut ;
réception ;
actions.
Une commande peut être ouverte pour afficher son détail.
15. ÉCRAN IMPORTATION DES FICHIERS FOURNISSEURS
Cet écran doit être particulièrement simple.
Étape 1 — Téléversement
Zone :
Glissez votre fichier ici
ou :
Choisir un fichier
Étape 2 — Analyse
Le système affiche :
Analyse du fichier en cours...
Étape 3 — Résultat
Les lignes sont regroupées par statut :
Produits reconnus ;
Produits nouveaux ;
Données nécessitant vérification ;
Erreurs.
Étape 4 — Validation
L'utilisateur vérifie les informations avant de confirmer.
Aucune modification importante ne doit être appliquée silencieusement.
16. ÉCRAN RÉCEPTION
L'interface doit clairement distinguer :
Quantité commandée
et
Quantité reçue
Exemple :
Produit
Commandé
Reçu
Restant
Produit A
100
80
20
L'utilisateur valide ensuite la réception.
17. ÉCRAN FRAIS ET COÛT DE REVIENT
Après réception, l'utilisateur peut saisir :
transport ;
douane ;
manutention ;
assurance ;
autres frais.
Un résumé doit montrer :
Prix d'achat

Frais
=
Coût réel
Cette présentation doit être particulièrement lisible car elle influence ensuite la fixation du prix de vente.
18. ÉCRAN TRANSFERT
L'écran doit présenter clairement :
Source
→
Destination
Exemple :
Entrepôt central
→
Boutique principale
Puis :
produit ;
quantité ;
commentaire ;
validation.
Le système doit afficher le stock disponible avant validation.
19. ÉCRAN CARTONS ET QR CODES
La page doit permettre de :
créer un carton ;
consulter un carton ;
scanner un carton ;
rechercher un carton ;
imprimer les étiquettes.
Une fiche carton affiche :
QR Code ;
référence ;
produit ;
quantité ;
emplacement ;
statut.
Les étiquettes imprimées en A4 présentent 20 unités par page (4 colonnes × 5 rangées), avec un cadre compact et un QR code lisible. L’étiquette d’un carton de réception indique la quantité initiale, le restant et, si la réception est connue, sa position dans le lot (ex. : carton 1/4).
Les cartons d’échantillons sont enregistrés séparément pour une boutique, avec leur propre référence et QR code ainsi que le nombre réel d’échantillons contenus. Ils ne modifient pas le stock vendable.
20. ÉCRAN DE VENTE / CAISSE
Cet écran doit être l'un des plus rapides de l'application.
Il doit permettre de commencer immédiatement une vente.
Zone recherche
Le vendeur peut :
rechercher le produit ;
saisir une référence ;
scanner un QR ;
utiliser un scanner USB sur ordinateur.
Panier
Le panier affiche :
Produit
Quantité
Prix
Total
En bas :
Sous-total
Remise
Total
21. VENTE AVEC QUANTITÉ IMPORTANTE
L'interface doit gérer le cas où la boutique possède seulement une petite quantité mais qu'un stock existe ailleurs.
Exemple :
Le client demande :
100 pièces
Boutique :
20
Entrepôt :
500
L'écran peut présenter la disponibilité par emplacement afin que le vendeur sache où se trouve le stock nécessaire.
22. ÉCRAN VENTE EXTERNE
Lorsque l'entreprise doit se procurer un produit à l'extérieur pour satisfaire le client, l'interface doit permettre de l'intégrer à l'opération commerciale.
La facture reste présentée comme une facture unique selon la règle métier définie.
L'information concernant l'origine externe est conservée dans les données internes et les écrans autorisés, sans rendre l'expérience client inutilement complexe.
23. ÉCRAN FACTURE
La facture doit être conçue pour être lisible aussi bien :
à l'écran ;
sur téléphone ;
en PDF ;
sur papier.
Elle contient notamment :
logo ;
entreprise ;
client ;
numéro ;
date ;
lignes produits ;
quantités ;
prix ;
total ;
paiement ;
reste ;
QR Code.
24. ÉCRAN CLIENTS
La liste affiche :
nom ;
téléphone ;
nombre de commandes ;
montant acheté ;
solde éventuel.
La fiche client doit présenter une vue synthétique.
Résumé
Total achats
Total payé
Reste à payer
Historique
factures ;
paiements ;
crédits.
25. ÉCRAN CRÉDITS
Cet écran est essentiel pour le suivi des clients débiteurs.
Il doit permettre de voir rapidement :
clients ayant une dette ;
montant total dû ;
dernière opération ;
ancienneté ;
statut.
Exemple :
Client
Total dû
Dernier paiement
Statut
Client A
2 000 000 GNF
01/08/2026
En cours
26. ÉCRAN PAIEMENT
L'utilisateur recherche le client.
Le système affiche immédiatement :
Dette totale : 5 000 000 GNF
L'utilisateur saisit :
Paiement : 2 000 000 GNF
Le système affiche avant confirmation :
Nouveau solde : 3 000 000 GNF
Après validation :
paiement enregistré ;
solde recalculé ;
reçu généré ;
notification déclenchée selon configuration.
27. ÉCRAN CAISSE
La caisse doit présenter :
solde initial ;
entrées ;
sorties ;
solde actuel ;
opérations récentes.
Les opérations doivent pouvoir être filtrées par période.
28. ÉCRAN DÉPENSES
L'écran permet :
ajouter une dépense ;
sélectionner une catégorie ;
saisir un montant ;
ajouter un justificatif ;
consulter l'historique.
29. NOTIFICATIONS ET WHATSAPP
Une interface dédiée permet de consulter :
notifications envoyées ;
notifications en attente ;
erreurs d'envoi ;
historique.
Le système peut afficher différents statuts :
Envoyé
En attente
Échec
30. RAPPORTS
Les rapports doivent utiliser une interface uniforme.
En haut :
période ;
filtres ;
bouton actualiser ;
export.
Le contenu peut être affiché sous forme :
tableau ;
graphique ;
indicateurs.
31. RECHERCHE GLOBALE
La recherche globale doit être accessible depuis la barre supérieure.
L'utilisateur peut rechercher :
PRD-000125
Le système peut retourner :
Produit
Carton
Ventes
Factures
Mouvements
selon les permissions.
32. GESTION MULTILINGUE
Le changement de langue doit être global.
Lorsque l'utilisateur sélectionne une langue :
menus ;
boutons ;
formulaires ;
messages ;
tableaux ;
notifications système
doivent changer de langue.
Le changement doit être cohérent dans toute l'application.
33. AUTHENTIFICATION ET SÉCURITÉ UI
L'écran de connexion doit rester simple.
Il peut contenir :
logo ;
identifiant ;
mot de passe ;
bouton connexion ;
récupération du compte.
Après connexion, le système peut proposer le déverrouillage rapide selon les capacités du terminal.
34. RESPONSIVE DESIGN
Le système doit adopter une approche responsive-first.
Les interfaces ne doivent pas être simplement réduites sur téléphone.
Elles doivent être réorganisées.
35. DESIGN MOBILE
Sur téléphone :
sidebar remplacée par un menu ;
tableaux transformés en cartes ou listes ;
actions importantes facilement accessibles ;
boutons suffisamment grands ;
formulaires organisés verticalement.
La vente doit être particulièrement optimisée pour le mobile.
Le scan QR doit pouvoir utiliser directement la caméra lorsque l'appareil le permet.
36. DESIGN TABLETTE
La tablette constitue un format intermédiaire.
Le système peut conserver :
une navigation compacte ;
des tableaux simplifiés ;
des panneaux adaptatifs.
37. DESIGN ORDINATEUR
Sur ordinateur :
sidebar complète ;
tableaux riches ;
plusieurs colonnes ;
raccourcis clavier lorsque pertinents ;
scanner QR USB ;
impression.
L'écran de vente doit être optimisé pour une utilisation rapide au clavier et à la souris.
38. DESIGN SYSTEM
Le Design System constitue la bibliothèque visuelle commune de l'application.
Il doit définir :
couleurs ;
typographie ;
espacements ;
boutons ;
champs ;
tableaux ;
cartes ;
badges ;
modales ;
alertes ;
icônes ;
composants de navigation.
L'objectif est d'éviter que chaque développeur crée son propre style.
39. COULEURS
La palette doit être professionnelle et sobre.
Elle doit comprendre au minimum :
Couleur principale
Utilisée pour :
actions principales ;
liens ;
éléments actifs.
Couleur secondaire
Utilisée pour certains éléments complémentaires.
Succès
Pour :
opération réussie ;
paiement validé ;
stock disponible.
Avertissement
Pour :
stock faible ;
attention ;
action nécessitant une vérification.
Erreur
Pour :
opération échouée ;
données invalides ;
permission refusée.
Neutres
Utilisés pour :
arrière-plans ;
bordures ;
textes secondaires ;
surfaces.
Les couleurs ne doivent jamais être le seul moyen de transmettre une information.
40. TYPOGRAPHIE
La typographie doit privilégier la lisibilité.
Hiérarchie :
Titre principal
Titre de section
Sous-titre
Texte normal
Texte secondaire
Les nombres importants comme :
2 500 000 GNF
doivent être suffisamment visibles dans les tableaux de bord financiers.
41. ICÔNES
Les icônes doivent être cohérentes.
Une même action doit utiliser la même icône partout.
Exemples :
recherche ;
ajout ;
modification ;
suppression ;
impression ;
téléchargement ;
scan ;
paiement ;
transfert ;
paramètres.
Les icônes critiques doivent être accompagnées d'un texte lorsque leur signification pourrait être ambiguë.
42. BOUTONS
Les boutons doivent avoir une hiérarchie.
Primaire
Action principale.
Enregistrer
Valider la vente
Secondaire
Action complémentaire.
Annuler
Retour
Danger
Actions sensibles.
Supprimer
Annuler la facture
Une action destructive ne doit jamais être présentée comme une action ordinaire.
43. CHAMPS ET FORMULAIRES
Les formulaires doivent :
avoir des labels explicites ;
indiquer les champs obligatoires ;
afficher les erreurs près du champ ;
conserver les données saisies lorsque possible ;
utiliser les bons types de clavier sur mobile.
Exemple :
Quantité
[ 100 ]
Prix
[ 250 000 ]
Devise
[ GNF ▼ ]
44. TABLEAUX
Les tableaux doivent être :
lisibles ;
filtrables ;
triables lorsque pertinent ;
paginés ;
responsive.
Sur mobile, un tableau complexe doit être transformé en liste de cartes plutôt que de devenir illisible.
45. CARTES ET INDICATEURS
Les cartes KPI permettent de présenter rapidement :
Ventes aujourd'hui
12 500 000 GNF
ou :
Créances
8 200 000 GNF
Les cartes ne doivent pas être utilisées partout. Elles sont réservées aux informations synthétiques.
46. BADGES ET STATUTS
Les statuts doivent être immédiatement reconnaissables.
Exemples :
Payé
Partiellement payé
Impayé
En attente
Validé
Annulé
Reçu
Expédié
Un statut doit être accompagné d'un libellé textuel et non seulement d'une couleur.
47. MODALES ET CONFIRMATIONS
Les modales doivent être utilisées pour les actions qui nécessitent réellement une confirmation.
Exemple :
Confirmer l'enregistrement de cette vente ?
Le résumé doit afficher :
client ;
montant ;
nombre de produits.
Pour une action sensible :
Cette opération modifiera définitivement le stock. Confirmer ?
48. NOTIFICATIONS ET MESSAGES SYSTÈME
Après une opération, l'utilisateur doit recevoir un retour clair.
Exemple :
Vente enregistrée avec succès.
Facture FAC-2026-00125 créée.
Stock mis à jour.
En cas d'erreur :
La vente n'a pas été enregistrée. Vérifiez les informations et réessayez.
Le message doit expliquer autant que possible le problème et la prochaine action attendue.
49. ÉTATS DES INTERFACES
Chaque écran doit prévoir au minimum les états suivants :
Chargement
Une indication claire que les données sont en cours de chargement.
Vide
Exemple :
Aucun client ne correspond à votre recherche.
Erreur
Exemple :
Impossible de charger les données.
Succès
Confirmation de l'opération.
Hors connexion
Lorsque l'architecture prévoit un fonctionnement hors ligne, l'interface doit informer clairement l'utilisateur de l'état de synchronisation.
50. RÈGLES UX POUR LES OPÉRATIONS SENSIBLES
Les opérations financières et de stock doivent être particulièrement contrôlées.
Avant validation, l'utilisateur doit pouvoir vérifier :
produit ;
quantité ;
montant ;
emplacement ;
client ;
mode de paiement.
Une fois l'opération validée, le système doit clairement confirmer son résultat.
51. PRINCIPES D'IMPRESSION
Les documents imprimables doivent être optimisés pour le papier.
Cela concerne notamment :
factures ;
reçus ;
bons ;
étiquettes QR ;
rapports.
Les informations importantes doivent rester lisibles en impression noir et blanc lorsque nécessaire.
52. PERFORMANCE DE L'INTERFACE
L'interface doit rester fluide même lorsque :
le catalogue contient beaucoup de produits ;
plusieurs années de ventes sont enregistrées ;
de nombreux mouvements de stock existent ;
les rapports contiennent beaucoup de données.
Les listes importantes doivent utiliser :
pagination ;
chargement progressif ;
recherche serveur ;
filtrage optimisé.
Le navigateur ne doit pas charger inutilement des milliers de lignes à la fois.
53. CRITÈRES DE VALIDATION UI/UX
L'interface sera considérée comme conforme lorsque :
Navigation
L'utilisateur peut accéder rapidement aux fonctionnalités autorisées.
Cohérence
Les composants visuels sont homogènes.
Responsive
Les principales fonctionnalités fonctionnent sur ordinateur, tablette et mobile.
Vente
Une vente peut être créée rapidement par recherche ou scan.
Stock
La disponibilité par boutique et entrepôt est compréhensible.
Crédit
Le solde d'un client est immédiatement identifiable.
Paiement
Un paiement met clairement à jour le solde.
Facture
La facture est lisible à l'écran et à l'impression.
QR
Les QR Codes peuvent être utilisés depuis les appareils compatibles.
Permissions
Les utilisateurs ne voient et ne peuvent utiliser que les fonctions autorisées.
Multilingue
Le changement de langue s'applique à l'ensemble de l'interface.
54. CONCLUSION
Le Design System et les spécifications UI/UX doivent servir de référence commune pour toute l'équipe de développement.
L'objectif n'est pas de créer une interface uniquement moderne ou esthétique. L'objectif est de construire une interface qui accompagne réellement le travail quotidien de l'entreprise.
Un vendeur doit pouvoir vendre rapidement.
Un gestionnaire de stock doit pouvoir localiser une marchandise rapidement.
Un responsable doit pouvoir comprendre la situation de l'entreprise rapidement.
Un utilisateur chargé du recouvrement doit pouvoir identifier immédiatement les clients débiteurs et enregistrer leurs paiements.
L'ensemble doit rester cohérent sur ordinateur, tablette et téléphone, tout en conservant les mêmes règles métier et les mêmes données.
Enfin, l'interface devra respecter une règle essentielle du projet :
La complexité doit rester dans le système ; elle ne doit pas être imposée inutilement à l'utilisateur.
