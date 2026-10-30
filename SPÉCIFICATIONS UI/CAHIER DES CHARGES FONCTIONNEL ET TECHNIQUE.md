CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version de référence
Document : Cahier des charges
Version : 1.0
Statut : Document de référence
Périmètre : Gestion de l’entreprise, boutiques, entrepôts, produits, achats, stocks, ventes, clients, crédits, paiements, fournisseurs, utilisateurs, sécurité, QR Codes, reporting et notifications.
SOMMAIRE
1. Présentation générale du projet
1.1 Contexte
1.2 Problématique
1.3 Justification du projet
1.4 Vision du système
1.5 Objectifs généraux
1.6 Objectifs spécifiques
1.7 Résultats attendus
2. Présentation de l’entreprise et modèle organisationnel
2.1 Structure générale de l’entreprise
2.2 Gestion des boutiques
2.3 Gestion des entrepôts
2.4 Différence entre boutique et entrepôt
2.5 Organisation des stocks
2.6 Gestion des emplacements
2.7 Évolution des responsabilités
3. Périmètre fonctionnel du système
3.1 Modules principaux
3.2 Fonctionnalités incluses
3.3 Fonctionnalités hors périmètre initial
3.4 Évolutivité du système
4. Gestion des utilisateurs, rôles et permissions
4.1 Principes de gestion des accès
4.2 Administrateur
4.3 Vendeur
4.4 Gestionnaire de stock
4.5 Autres profils
4.6 Création et activation des comptes
4.7 Attribution des permissions
4.8 Restrictions par fonctionnalité
4.9 Journalisation des actions
5. Gestion des produits
5.1 Catalogue produits
5.2 Références internes
5.3 Références fournisseurs
5.4 Catégories et sous-catégories
5.5 Marques et modèles
5.6 Images produits
5.7 Prix et devises
5.8 Conditionnement
5.9 Produits et cartons
5.10 QR Codes et identification
6. Gestion des fournisseurs
6.1 Fiche fournisseur
6.2 Informations administratives
6.3 Historique des commandes
6.4 Historique des achats
6.5 Conditions commerciales
6.6 Gestion des documents fournisseurs
7. Gestion des commandes fournisseurs
7.1 Création d'une commande
7.2 Transmission de la commande
7.3 Réception des fichiers fournisseurs
7.4 Importation des fichiers
7.5 Analyse et prévisualisation
7.6 Correspondance des champs
7.7 Détection des nouveaux produits
7.8 Gestion des images importées
7.9 Gestion des erreurs d'importation
7.10 Validation de la commande
8. Gestion des devises et taux de change
8.1 Devises supportées
8.2 Prix d'origine
8.3 Taux de change
8.4 Historisation du taux
8.5 Conversion
8.6 Règles de calcul
9. Gestion des réceptions
9.1 Réception totale
9.2 Réception partielle
9.3 Contrôle des quantités
9.4 Contrôle des produits
9.5 Contrôle des documents
9.6 Validation de réception
10. Gestion des frais d'acquisition
10.1 Transport
10.2 Douane
10.3 Manutention
10.4 Assurance
10.5 Autres frais
10.6 Répartition des frais
10.7 Calcul du coût réel d'acquisition
11. Gestion des prix de vente
11.1 Coût de revient
11.2 Marge
11.3 Prix de vente
11.4 Historique des prix
11.5 Modification des prix
11.6 Autorisations nécessaires
12. Gestion des stocks
12.1 Principes généraux
12.2 Stock par entrepôt
12.3 Stock par boutique
12.4 Stock disponible
12.5 Stock réservé
12.6 Stock physique
12.7 Mouvements de stock
12.8 Historique des mouvements
13. Gestion des transferts
13.1 Principe du transfert
13.2 Transfert entre entrepôts
13.3 Transfert entre entrepôt et boutique
13.4 Autorisation des transferts
13.5 Validation
13.6 Traçabilité
13.7 Réception d'un transfert
14. Gestion des boutiques et échantillons
14.1 Fonctionnement des boutiques
14.2 Gestion des échantillons
14.3 Stock disponible en boutique
14.4 Besoin de réapprovisionnement
14.5 Demande de produits depuis un entrepôt
15. Gestion des cartons et conditionnements
15.1 Création des cartons
15.2 Contenu d'un carton
15.3 Quantité par carton
15.4 Identification des cartons
15.5 QR Code carton
15.6 Déplacement des cartons
15.7 Ouverture et déconditionnement
16. Gestion des QR Codes et scan
16.1 QR Code produit
16.2 QR Code carton
16.3 QR Code facture
16.4 QR Code reçu
16.5 Scan avec caméra
16.6 Saisie manuelle
16.7 Scanner USB sur ordinateur
16.8 Prévention des doubles scans
17. Gestion des ventes
17.1 Création d'une vente
17.2 Recherche des produits
17.3 Vente par QR Code
17.4 Vente depuis un ordinateur
17.5 Vente depuis mobile
17.6 Gestion des quantités
17.7 Validation de la vente
17.8 Diminution automatique du stock
18. Gestion des ventes externes
18.1 Principe
18.2 Produit indisponible
18.3 Recherche auprès d'un partenaire ou fournisseur
18.4 Intégration à la vente
18.5 Facture unique
18.6 Traçabilité de l'origine des produits
19. Gestion des factures
19.1 Création automatique
19.2 Numérotation
19.3 Contenu
19.4 Facture unique
19.5 QR Code facture
19.6 Impression
19.7 Archivage
20. Gestion des clients
20.1 Fiche client
20.2 Historique des achats
20.3 Historique des paiements
20.4 Historique des crédits
20.5 État de compte
21. Gestion des ventes à crédit
21.1 Principe
21.2 Crédit total
21.3 Crédit partiel
21.4 Plusieurs crédits pour un même client
21.5 Créances
21.6 Solde global
21.7 Statuts des créances
22. Gestion des paiements et recouvrements
22.1 Enregistrement d'un paiement
22.2 Paiement partiel
22.3 Paiement total
22.4 Affectation des paiements
22.5 Solde automatique
22.6 Reçu de paiement
22.7 Historique
22.8 Relances
23. Notifications et WhatsApp
23.1 Notifications de vente
23.2 Notification administrateur
23.3 Confirmation de paiement
23.4 Envoi de documents
23.5 Relances de crédit
23.6 Historique des notifications
24. Gestion financière et caisse
24.1 Encaissements
24.2 Décaissements
24.3 Modes de paiement
24.4 Suivi de caisse
24.5 Rapports financiers
25. Gestion des dépenses et charges
25.1 Enregistrement des dépenses
25.2 Catégories de dépenses
25.3 Justificatifs
25.4 Impact sur la rentabilité
26. Reporting et tableaux de bord
26.1 Tableau de bord général
26.2 Ventes
26.3 Achats
26.4 Stocks
26.5 Crédits
26.6 Rentabilité
26.7 Rapports par boutique
26.8 Rapports par entrepôt
27. Recherche et filtres
27.1 Recherche globale
27.2 Recherche produits
27.3 Recherche clients
27.4 Recherche fournisseurs
27.5 Recherche factures
27.6 Recherche par QR Code
27.7 Filtres avancés
28. Internationalisation et gestion multilingue
28.1 Changement de langue
28.2 Traduction globale
28.3 Langue utilisateur
28.4 Langue des documents
28.5 Langue des notifications
28.6 Support des langues RTL
29. Sécurité et authentification
29.1 Authentification
29.2 Gestion des sessions
29.3 Verrouillage automatique
29.4 Déverrouillage biométrique
29.5 Empreinte digitale
29.6 Reconnaissance faciale
29.7 PIN de secours
29.8 Réauthentification des opérations sensibles
30. Audit et traçabilité
30.1 Journal des actions
30.2 Historique des modifications
30.3 Traçabilité des stocks
30.4 Traçabilité financière
30.5 Traçabilité des utilisateurs
31. Architecture fonctionnelle
31.1 Organisation générale
31.2 Relations entre modules
31.3 Flux des données
31.4 Principes d'intégration
32. Architecture technique
32.1 Frontend
32.2 Backend
32.3 Base de données
32.4 API
32.5 Stockage des fichiers
32.6 Services externes
33. Contraintes techniques et fonctionnelles
33.1 Compatibilité
33.2 Responsive design
33.3 Performance
33.4 Disponibilité
33.5 Sécurité
33.6 Maintenabilité
34. Gestion des fichiers et documents
34.1 Importation
34.2 Exportation
34.3 PDF
34.4 Excel
34.5 Archivage
34.6 Contrôle des fichiers
35. Sauvegarde et continuité
35.1 Sauvegardes
35.2 Restauration
35.3 Continuité d'activité
35.4 Reprise après incident
36. Tests et validation
36.1 Tests fonctionnels
36.2 Tests d'intégration
36.3 Tests de sécurité
36.4 Tests de performance
36.5 Tests utilisateurs
36.6 Validation avant production
37. Déploiement et mise en production
37.1 Environnements
37.2 Configuration
37.3 Déploiement
37.4 Migration
37.5 Surveillance
38. Maintenance et évolution
38.1 Maintenance corrective
38.2 Maintenance préventive
38.3 Maintenance évolutive
38.4 Gestion des versions
39. Formation et accompagnement
39.1 Formation administrateur
39.2 Formation vendeurs
39.3 Formation gestionnaires de stock
39.4 Documentation utilisateur
40. Critères d'acceptation du projet
40.1 Critères fonctionnels
40.2 Critères de sécurité
40.3 Critères de performance
40.4 Critères de qualité
40.5 Validation finale
41. Conclusion
42. Annexes
Annexe A — Glossaire
Annexe B — Règles métier
Annexe C — Matrice des permissions
Annexe D — Flux principaux
Annexe E — Référentiel des statuts
1. PRÉSENTATION GÉNÉRALE DU PROJET
1.1 Contexte
L'entreprise exerce une activité commerciale nécessitant la gestion quotidienne de produits, de fournisseurs, de commandes, de stocks, de boutiques, de ventes et de clients.
Dans le fonctionnement actuel, une partie importante des opérations peut être réalisée manuellement : réception des informations fournisseurs, suivi des marchandises, recherche des produits, mouvements entre différents lieux de stockage, calcul des coûts, facturation, suivi des crédits clients et recouvrement.
Cette organisation peut rapidement provoquer des difficultés : erreurs de saisie, informations dispersées, manque de visibilité sur les stocks, difficulté à connaître l'emplacement exact d'un produit, problèmes de suivi des créances ou encore absence d'une traçabilité complète des opérations.
Le présent projet consiste donc à mettre en place un système intégré de gestion commerciale permettant de centraliser ces opérations dans une seule application.
Le système doit accompagner l'entreprise depuis l'achat d'un produit auprès d'un fournisseur jusqu'à sa réception, son stockage, son transfert éventuel vers une boutique, sa vente au client, son paiement et son intégration dans les différents rapports de gestion.
1.2 Problématique
L'un des principaux enjeux du projet est de gérer correctement plusieurs réalités commerciales en même temps.
L'entreprise peut notamment disposer de plusieurs entrepôts ainsi que d'une ou plusieurs boutiques. Une boutique peut présenter des échantillons aux clients alors que les quantités importantes sont conservées dans les entrepôts.
Ainsi, lorsqu'un client demande une quantité supérieure à celle disponible dans la boutique, le vendeur doit pouvoir identifier rapidement dans quel entrepôt le produit est disponible et organiser son approvisionnement.
Le système doit également tenir compte du fait qu'une entreprise peut vendre un produit qu'elle ne possède momentanément pas. Dans ce cas, une vente externe peut être réalisée afin de satisfaire le client, sans créer une seconde facture lorsque la vente peut être regroupée dans une facture unique.
La gestion des fournisseurs constitue également un enjeu majeur. Les fournisseurs peuvent transmettre des fichiers contenant les informations détaillées des produits commandés, leurs quantités, leurs prix, leurs devises et éventuellement leurs images. Le logiciel doit exploiter ces fichiers afin d'éviter les ressaisies inutiles.
Enfin, les ventes à crédit nécessitent un suivi précis. Un même client peut effectuer plusieurs achats à crédit et effectuer ensuite plusieurs paiements partiels. Le système doit donc connaître en permanence le montant initial, les paiements réalisés et le solde restant.
1.3 Justification du projet
Le système est conçu pour répondre à quatre besoins fondamentaux :
Centraliser l'information.
Toutes les informations importantes doivent être accessibles depuis une plateforme unique.
Réduire les erreurs.
Les opérations répétitives, comme les calculs de stock, les soldes clients ou les conversions de devises, doivent être automatisées.
Améliorer la visibilité.
L'administrateur doit pouvoir connaître la situation de l'entreprise à tout moment : ventes, achats, stocks, crédits, paiements et mouvements.
Assurer la traçabilité.
Chaque opération importante doit pouvoir être associée à un utilisateur, une date, un document et un mouvement correspondant.
1.4 Vision du système
Le logiciel doit être considéré comme le système central de gestion de l'entreprise.
Il ne s'agit pas simplement d'une application de caisse.
Une vente doit avoir des conséquences sur le stock et la finance. Une réception fournisseur doit avoir une conséquence sur le stock et le coût de revient. Un paiement client doit modifier automatiquement la créance. Un transfert doit diminuer le stock source et augmenter le stock destination.
Le principe général est donc :
Une action métier → une mise à jour cohérente de toutes les données concernées.
1.5 Objectif général
L'objectif général est de développer un système intégré permettant de gérer de manière fiable, sécurisée et centralisée :
les produits ;
les fournisseurs ;
les commandes ;
les réceptions ;
les coûts d'acquisition ;
les stocks ;
les boutiques ;
les entrepôts ;
les transferts ;
les ventes ;
les factures ;
les clients ;
les ventes à crédit ;
les paiements ;
les notifications ;
les utilisateurs ;
les rapports ;
la sécurité et l'audit.
1.6 Objectifs spécifiques
Le système devra notamment permettre de :
gérer plusieurs entrepôts indépendamment ;
distinguer clairement les boutiques des entrepôts ;
gérer les stocks propres à chaque emplacement ;
gérer les échantillons présents dans les boutiques ;
transférer des produits entre emplacements selon les permissions ;
importer les informations fournies par les fournisseurs ;
récupérer les informations produits disponibles dans les fichiers ;
gérer les images des produits ;
gérer plusieurs devises ;
conserver le prix fournisseur dans sa devise d'origine ;
enregistrer les taux de change utilisés ;
intégrer les frais de transport, douane et autres charges ;
calculer le coût réel d'acquisition ;
déterminer le coût de revient ;
gérer les prix de vente ;
identifier les produits par QR Code ;
identifier les cartons par QR Code ;
permettre la saisie manuelle d'un code sur ordinateur ;
permettre le scan par caméra ;
gérer les ventes normales ;
gérer les ventes externes ;
générer une facture unique pour une vente ;
gérer les ventes à crédit ;
suivre plusieurs crédits pour un même client ;
enregistrer les paiements partiels ou complets ;
recalculer automatiquement les soldes ;
générer les reçus ;
envoyer les notifications WhatsApp ;
effectuer les rappels périodiques des crédits ;
gérer les utilisateurs et leurs permissions ;
sécuriser les opérations sensibles ;
permettre le déverrouillage biométrique lorsque le terminal le supporte ;
fournir des tableaux de bord et rapports ;
permettre le changement global de langue de l'application ;
conserver un historique complet des opérations.
1.7 Résultats attendus
À la fin du projet, l'entreprise devra disposer d'une solution permettant de suivre le cycle complet :
Fournisseur → Commande → Importation → Réception → Frais → Coût de revient → Entrepôt → Transfert → Boutique → Vente → Facture → Paiement → Crédit éventuel → Reporting.
Le système devra également permettre de répondre rapidement à des questions opérationnelles telles que :
Où se trouve un produit ?
Combien reste-t-il dans chaque entrepôt ?
Combien la boutique possède-t-elle ?
Quels produits doivent être réapprovisionnés ?
Combien l'entreprise doit-elle à ses fournisseurs ?
Combien les clients doivent-ils à l'entreprise ?
Quel est le coût réel d'un produit ?
Quelle quantité a été vendue ?
Qui a effectué une opération ?
Quand cette opération a-t-elle été effectuée ?
Quel est le chiffre d'affaires ?
Quel est le montant total des crédits encore ouverts ?
2. PRÉSENTATION DE L'ENTREPRISE ET MODÈLE ORGANISATIONNEL
2.1 Structure générale
Le système considère qu'il existe une seule entreprise.
Cette entreprise peut cependant disposer de plusieurs points physiques.
Exemple :
Entreprise
Boutique principale
Boutique secondaire
Entrepôt central
Entrepôt secondaire
Entrepôt spécialisé
Chaque emplacement possède ses propres caractéristiques et son propre stock.
2.2 Gestion des boutiques
Une boutique est principalement destinée à l'accueil des clients et à la réalisation des ventes.
Elle peut disposer d'un nombre limité de produits exposés sous forme d'échantillons.
L'objectif n'est donc pas nécessairement d'y conserver tout le stock disponible.
Lorsqu'un client demande une quantité importante, le vendeur doit pouvoir vérifier les stocks des entrepôts et organiser l'approvisionnement selon les procédures internes.
2.3 Gestion des entrepôts
Les entrepôts constituent les lieux de stockage des marchandises.
Chaque entrepôt possède un stock indépendant.
Le système doit donc être capable de répondre à une requête telle que :
« Combien de filtres Toyota sont disponibles dans l'entrepôt central, dans l'entrepôt de Matoto et dans la boutique ? »
Le résultat doit distinguer clairement chaque emplacement.
2.4 Différence entre boutique et entrepôt
Cette distinction constitue une règle fondamentale du système.
Une boutique n'est pas simplement un petit entrepôt.
Elle possède une fonction commerciale différente :
présentation des produits ;
accueil des clients ;
vente ;
caisse ;
échantillons.
L'entrepôt possède principalement une fonction logistique :
réception ;
stockage ;
préparation ;
transfert ;
inventaire.
Le logiciel doit respecter cette distinction dans ses interfaces, ses permissions et ses workflows.
2.5 Organisation des stocks
Le stock global de l'entreprise doit être calculable, mais il ne doit jamais remplacer la vision par emplacement.
Exemple :
Emplacement
Produit
Quantité
Boutique principale
Filtre A
20
Entrepôt central
Filtre A
500
Entrepôt Matoto
Filtre A
150
Stock global :
670 pièces
Mais le système doit toujours conserver les trois stocks séparément.
3. PÉRIMÈTRE FONCTIONNEL DU SYSTÈME
Le système couvrira l'ensemble du cycle commercial et logistique de l'entreprise.
Les modules devront être intégrés et partager les mêmes données de référence.
Il ne devra pas exister, par exemple, un catalogue produit différent pour les achats et un autre catalogue différent pour les ventes.
Le produit doit être une donnée centrale utilisée par les différents modules.
4. PRINCIPES DIRECTEURS DU PROJET
Plusieurs principes doivent guider toute la conception.
Principe 1 — Une seule source de vérité
Les données importantes ne doivent pas être dupliquées inutilement.
Principe 2 — Chaque stock est rattaché à un emplacement
Le stock ne doit jamais être une simple quantité globale sans localisation.
Principe 3 — Une commande n'est pas une réception
Commander 100 pièces ne signifie pas que 100 pièces sont entrées dans le stock.
Principe 4 — Une facture n'est pas un paiement
Une facture peut être totalement payée, partiellement payée ou rester impayée.
Principe 5 — Une vente à crédit crée une créance
Le système doit automatiquement suivre le montant restant.
Principe 6 — Une opération financière doit être traçable
Chaque paiement, remboursement ou correction doit laisser une trace.
Principe 7 — Le fournisseur ne modifie jamais directement le stock
Un fichier importé doit passer par une validation et une réception avant de modifier le stock.
Principe 8 — Les permissions sont appliquées côté serveur
Cacher un bouton ne constitue pas une sécurité suffisante.
Principe 9 — L'interface existante doit être conservée lorsqu'elle est conforme
Les futures évolutions doivent compléter le système sans reconstruire inutilement les écrans déjà validés.
Principe 10 — L'application doit être évolutive
Les fonctionnalités futures doivent pouvoir être ajoutées sans remettre en cause les fondations du système.
5. SYNTHÈSE DU FONCTIONNEMENT GLOBAL
Le fonctionnement de référence du système est le suivant :
1. Fournisseur
Le fournisseur reçoit une commande.
2. Fichier fournisseur
Il peut retourner un fichier contenant les informations détaillées des produits.
3. Importation
L'utilisateur téléverse le fichier.
4. Contrôle
Le système analyse les données et identifie les produits connus et inconnus.
5. Validation
L'utilisateur vérifie les informations.
6. Commande fournisseur
La commande est enregistrée.
7. Réception
Les marchandises réellement reçues sont enregistrées.
8. Frais
Les frais de transport, douane et autres charges sont ajoutés.
9. Coût réel
Le système calcule le coût réel d'acquisition.
10. Stock
Les marchandises sont affectées à l'entrepôt concerné.
11. QR Code
Les produits ou cartons peuvent être identifiés.
12. Transfert
Les produits peuvent être transférés vers une boutique ou un autre entrepôt selon les permissions.
13. Vente
Le vendeur recherche, saisit ou scanne le produit.
14. Facturation
Le système génère une facture unique.
15. Stock
La quantité vendue est automatiquement déduite de l'emplacement concerné.
16. Paiement
Le client paie immédiatement ou à crédit.
17. Crédit
Si le paiement est incomplet, une créance est créée.
18. Paiements ultérieurs
Les paiements suivants mettent automatiquement à jour le solde.
19. WhatsApp
Le client peut recevoir les confirmations et rappels prévus.
20. Reporting
Les opérations alimentent automatiquement les tableaux de bord et rapports.
6. CONCLUSION DU DOCUMENT
Ce cahier des charges constitue la référence fonctionnelle générale du projet.
Les documents suivants devront détailler progressivement chaque domaine sans modifier les principes fondamentaux établis ici.
L'objectif n'est pas simplement de créer une application permettant d'enregistrer des ventes, mais de construire un système intégré de gestion de l'entreprise, capable de suivre précisément les produits, les marchandises, les mouvements de stock, les achats, les ventes, les clients, les fournisseurs et les flux financiers.
La réussite du projet repose notamment sur la cohérence entre les modules. Une modification effectuée dans un module devra produire les conséquences attendues dans les autres modules concernés, tout en respectant les permissions de l'utilisateur et les règles de sécurité.
