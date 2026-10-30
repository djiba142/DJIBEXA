# PLAN DE DÉVELOPPEMENT NEXORA

Projet : NEXORA
Type : Système de gestion commerciale, stocks, achats, ventes, facturation, paiements et notifications
Technologies : React + Vite + TypeScript, Django + Django REST Framework, PostgreSQL
Statut : Plan de suivi de projet
Version : 1.0
Date de création : 2026-09-12

---

## 1. OBJECTIF DU DOCUMENT

Ce document sert de feuille de route de développement pour la mise en œuvre progressive de NEXORA.

Il doit permettre de :
- suivre le projet par étapes claires ;
- éviter les régressions ;
- respecter les règles métier définies ;
- conserver l’existant déjà préparé dans le projet ;
- organiser les livrables par module ;
- sécuriser les développements avant mise en production ;
- faciliter la maintenance et l’évolution.

---

## 2. RÈGLES DE GESTION DE PROJET

### 2.1 Règle principale
Le projet doit évoluer progressivement, sans reconstruire inutilement l’application.

### 2.2 Principe de modularité
Chaque fonctionnalité doit être développée dans un module fonctionnel clair :
- users
- products
- suppliers
- customers
- inventory
- purchases
- sales
- invoices
- payments
- notifications
- core

### 2.3 Principe de sécurité
- Les règles métier doivent être validées côté backend.
- Le frontend ne doit pas être la seule couche de sécurité.
- Les permissions doivent être contrôlées par rôle.
- Les opérations critiques doivent être auditées.

### 2.4 Principe de validation
Aucune phase ne doit être considérée comme terminée sans :
- test fonctionnel ;
- validation technique ;
- vérification de cohérence métier ;
- validation de non-régression.

### 2.5 Principe d’intégrité des données
- le stock est une donnée métier officielle ;
- les ventes, achats, réceptions et transferts doivent être traçables ;
- les mouvements de stock ne doivent pas être modifiés silencieusement ;
- les données importantes ne doivent pas être écrasées sans confirmation.

### 2.6 Principe de respect de l’interface
L’interface existante doit être conservée autant que possible.
Les changements doivent viser la fonctionnalité et l’expérience utilisateur, pas une refonte arbitraire.

---

## 3. PHASES DE DÉVELOPPEMENT

## Phase 0 — Fondation technique

### Objectif
Mettre en place la base technique exploitable du projet.

### Tâches
- vérifier la cohérence du projet Django existant ;
- finaliser la configuration du backend ;
- configurer DRF et les paramètres du projet ;
- préparer le schéma de base et les settings d’environnement ;
- préparer l’environnement de développement ;
- intégrer les modules applicatifs principaux.

### Livrables
- backend Django fonctionnel ;
- accès API prêt ;
- modules Django initialisés ;
- project settings coherent.

### Critères de validation
- `python manage.py check` OK ;
- aucune erreur de démarrage ;
- modules Django chargés correctement.

---

## Phase 1 — Authentification, utilisateurs et permissions

### Objectif
Mettre en place une sécurisation réelle de l’application.

### Modules
- users

### Fonctionnalités
- création d’utilisateur ;
- login / logout ;
- profil utilisateur ;
- rôles et permissions ;
- contrôle d’accès par rôle ;
- protection des API ;
- session et autorisation ;
- historique des connexions/activités.

### Rôles attendus
- Admin
- Manager
- Sales
- Stock
- Viewer

### Livrables
- modèle d’utilisateur personnalisé ;
- API auth ;
- endpoints de profil ;
- permissions sécurisées.

### Critères de validation
- un utilisateur non authentifié ne peut pas accéder aux endpoints protégés ;
- les rôles affectent correctement les droits ;
- les actions sensibles sont restreintes.

---

## Phase 2 — Gestion des produits et catégories

### Objectif
Créer la base du catalogue produit.

### Modules
- products

### Fonctionnalités
- catalogue de produits ;
- catégories ;
- références internes ;
- marque ;
- description ;
- image ;
- prix d’achat / vente ;
- devise ;
- quantité ;
- seuil d’alerte ;
- emplacement ;
- QR code ;
- code-barres ;
- recherche rapide.

### Livrables
- modèle Category ;
- modèle Product ;
- serializers ;
- endpoints CRUD produits ;
- endpoints CRUD catégories ;
- recherche multi-critères.

### Critères de validation
- création d’un produit réussie ;
- recherche par nom, code et SKU fonctionnelle ;
- quantité et prix enregistrés correctement ;
- catégorie liée au produit.

---

## Phase 3 — Gestion des fournisseurs et clients

### Objectif
Mettre en place les référentiels externes ;

### Modules
- suppliers
- customers

### Fonctionnalités fournisseurs
- fiche fournisseur ;
- contact ;
- historique d’achats ;
- conditions commerciales ;
- documents associés.

### Fonctionnalités clients
- fiche client ;
- historique d’achats ;
- historique de paiements ;
- historique des crédits ;
- statut de compte ;
- solde client.

### Livrables
- modèles Supplier et Customer ;
- endpoints CRUD ;
- relations avec achats, ventes et paiements.

### Critères de validation
- création fournisseur/client OK ;
- données consultables ;
- historique associé ;
- aucune donnée incohérente.

---

## Phase 4 — Gestion des achats fournisseurs

### Objectif
Crée le flux achat fournisseur depuis la commande jusqu’à la réception.

### Modules
- purchases
- suppliers

### Fonctionnalités
- créer commande fournisseur ;
- gérer date et fournisseur ;
- ajouter produits commandés ;
- gérer prix et quantité ;
- gérer référence fournisseur ;
- gérer informations complémentaires ;
- document de commande.

### Livrables
- modèle PurchaseOrder ;
- modèle PurchaseOrderItem ;
- API de création et consultation ;
- validation métier de commande.

### Critères de validation
- commande créée avec produits corrects ;
- fournisseur associé ;
- total calculé correctement ;
- la commande ne modifie pas directement le stock.

---

## Phase 5 — Importation de fichiers fournisseurs

### Objectif
Permettre l’import de données commerciales depuis des fichiers externes.

### Sources possibles
- CSV
- Excel
- fichiers fournisseur exportés

### Fonctionnalités
- téléversement du fichier ;
- analyse des colonnes ;
- détection des champs reconnus ;
- mapping manuel ;
- création ou mise à jour de produits ;
- gestion erreurs ;
- confirmation avant écrasement de données importantes ;
- conversion des devises ;
- conservation des images si exploitables.

### Livrables
- service d’import ;
- mapping des colonnes ;
- validation des données ;
- logs d’importation.

### Critères de validation
- données inconnues identifiées ;
- import partiellement validé si nécessaire ;
- aucune écrasement automatique sans confirmation ;
- produits créés ou mis à jour selon les règles.

---

## Phase 6 — Réception fournisseur et coût d’acquisition

### Objectif
Distinguer la commande de la réception et calculer le coût réel d’acquisition.

### Fonctionnalités
- réception totale / partielle ;
- date de réception ;
- état de réception ;
- produit reçu ;
- contrôle des quantités ;
- frais de transport ;
- frais de douane ;
- assurance ;
- autres coûts ;
- calcul du coût réel d’acquisition.

### Livrables
- modèles PurchaseReceipt et PurchaseReceiptItem ;
- modèles de frais d’acquisition ;
- calcul du coût de revient ;
- mise à jour du stock selon réception validée.

### Critères de validation
- réception différenciée de la commande ;
- coût total calculé correctement ;
- le stock évolue seulement via une réception validée.

---

## Phase 7 — Gestion des stocks et mouvements

### Objectif
Faire du stock une donnée métier officielle et traçable.

### Modules
- inventory

### Fonctionnalités
- stock par emplacement ;
- stock par boutique ;
- stock par entrepôt ;
- mouvements contrôlés ;
- transfert entre emplacements ;
- ajustement autorisé ;
- inventaire ;
- suppression de mouvement non autorisée ;
- historique des mouvements.

### Règles
- le stock ne doit pas devenir négatif sans justification ;
- aucun mouvement silencieux ;
- chaque mouvement doit être traceable.

### Livrables
- modèles InventoryLocation ;
- modèles StockMovement ;
- API de mouvement ;
- historique des transactions de stock.

### Critères de validation
- mouvement validé ;
- historique consultable ;
- quantité cohérente avec l’opération.

---

## Phase 8 — Boutiques, entrepôts et transferts

### Objectif
Supporter les contraintes d’un réseau commercial multi-emplacement.

### Fonctionnalités
- boutique avec échantillons ;
- stock réel dans un entrepôt ;
- transfert entre entrepôt et boutique ;
- disponibilité d’un produit dans plusieurs emplacements ;
- vente lorsqu’une partie du stock est ailleurs ;
- logique de transfert/prélèvement.

### Livrables
- modèles de localisation ;
- API de transfert ;
- validation de disponibilité ;
- logique de décision commerciale et logistique.

### Critères de validation
- stock disponible calculé selon emplacement ;
- transfert validé avec trace ;
- vente autorisée si la règle métier le permet.

---

## Phase 9 — Ventes et facturation

### Objectif
Faire fonctionner le cœur commercial.

### Modules
- sales
- invoices

### Fonctionnalités
- sélectionner un client ;
- ajouter des produits ;
- recherche par QR code et par référence ;
- saisie manuelle ;
- gestion des quantités ;
- remise si autorisée ;
- mode de paiement ;
- validation ;
- génération facture ;
- QR code facture ;
- total, solde, montant payé.

### Livrables
- modèle Sale ;
- modèle SaleItem ;
- modèle Invoice ;
- endpoints de vente ;
- API de facture.

### Critères de validation
- vente validée ;
- stock mis à jour selon la règle ;
- facture générée avec identifiant unique ;
- montant calculé correctement.

---

## Phase 10 — Ventes externes, crédit client et paiements

### Objectif
Gérer les cas de vente commerciale plus complexes.

### Fonctionnalités
- vente externe ;
- vente à crédit ;
- remboursement partiel ou total ;
- calcul du solde ;
- historique des paiements ;
- paiement d’une dette ;
- relance et rappel de crédit.

### Livrables
- modèles Credit, Payment, Debt ;
- page de détails de crédit client ;
- historique des paiements ;
- API de recouvrement.

### Critères de validation
- solde recalculé automatiquement ;
- paiement partiel sans rupture de logique ;
- historique conservé ;
- crédit clôturé proprement.

---

## Phase 11 — Notifications, WhatsApp et suivi d’événements

### Objectif
Notifier les opérations métier sans bloquer la logique fonctionnelle.

### Fonctionnalités
- notification Admin après validation de vente ;
- confirmation de paiement ;
- facture envoyée ;
- relance de crédit ;
- statut d’envoi : attente / envoyé / échec / retry.

### Livrables
- modèle de notification ;
- service d’envoi ;
- journal des statuts ;
- logique de retry sans perte de la transaction métier.

### Critères de validation
- une vente validée reste valide même si WhatsApp échoue ;
- notification est retryée plus tard ;
- statut visible dans l’API.

---

## Phase 12 — Administration, audit et sécurité avancée

### Objectif
Rendre le projet professionnel, traçable et conforme à l’usage d’entreprise.

### Fonctionnalités
- gestion des utilisateurs ;
- rôles ;
- permissions ;
- paramètres système ;
- historique ;
- statistiques ;
- journal d’audit ;
- logs d’opérations critiques.

### Livrables
- audit trail ;
- gestion des paramètres ;
- parcours sécurité et autorisation.

### Critères de validation
- actions importantes enregistrées ;
- qui / quand / quoi / résultat sont visibles ;
- comportement conforme aux rôles.

---

## Phase 13 — API, frontend et intégration

### Objectif
Relier l’interface utilisateur au backend via l’API Django REST.

### Tâches
- créer les endpoints API par module ;
- sécuriser les requêtes ;
- gérer les erreurs API ;
- structurer les serializers ;
- préparer la couche de services frontend ;
- lier les écrans React aux données réelles.

### Livrables
- API stable ;
- services frontend ;
- appels API authentifiés ;
- erreurs utilisateur lisibles.

### Critères de validation
- produit visible dans le frontend via API ;
- formulaire de création fonctionnel ;
- données réelles chargées ;
- non-régression sur les modules déjà validés.

---

## Phase 14 — Internationalisation

### Objectif
Permettre la multilingue sur toute l’interface.

### Fonctionnalités
- choix de langue ;
- langue persistante ;
- interface traduite ;
- messages d’erreurs ;
- notifications ;
- formulaires ;
- factures si applicable.

### Livrables
- configuration i18n ;
- stockage du choix de langue ;
- traduction des textes de base.

### Critères de validation
- changement de langue appliqué à l’interface complète ;
- langue conservée après actualisation ;
- aucune chaîne statique non traduite sur les écrans principales.

---

## Phase 15 — QR Codes, étiquettes et documents

### Objectif
Supporter les usages logistiques et commerciaux avancés.

### Fonctionnalités
- QR code produit ;
- QR code facture ;
- QR code emplacement / carton selon besoin ;
- scan sur compatible ;
- saisie manuelle ;
- impression d’étiquettes ;
- document de facture ;
- documents imprimables.

### Livrables
- service QR ;
- génération d’étiquette ;
- impression ;
- intégration documents.

### Critères de validation
- QR code généré ;
- scan fonctionnel ;
- impression lisible ;
- données associées correctement.

---

## Phase 16 — Reporting et tableaux de bord

### Objectif
Donner un panorama de gestion de l’entreprise.

### Rapports à prévoir
- ventes ;
- achats ;
- stock ;
- clients en crédit ;
- paiements ;
- rentabilité ;
- statistiques globales ;
- rapports par boutique / entrepôt.

### Livrables
- API dashboards ;
- statuts et agrégations ;
- visualisation front-end.

### Critères de validation
- données cohérentes ;
- calculs corrects ;
- visualisations utiles pour la décision.

---

## Phase 17 — Qualité, tests et non-régression

### Objectif
Assurer une fiabilité acceptable avant mise en production.

### Tests à prévoir
- tests d’API ;
- tests de permissions ;
- tests de validation métier ;
- tests d’intégration ;
- tests de règles de stock ;
- tests de vente / facture / paiement ;
- tests de création et modification des objets ;
- tests des cas limites.

### Livrables
- suite de tests automatisés ;
- gestion des erreurs ;
- couverture critique sur modules métier.

### Critères de validation
- les tests importants passent ;
- aucun bug critique sur les modules déjà validés ;
- logs et erreurs maîtrisés.

---

## Phase 18 — CI/CD, déploiement et maintenance

### Objectif
Préparer l’application à l’usage professionnel et à la publication.

### Tâches
- configure CI/CD ;
- build backend ;
- build frontend ;
- environnement de test ;
- environnement de production ;
- variables d’environnement ;
- backups ;
- monitoring ;
- journaux ;
- procédures de rollback.

### Livrables
- pipeline de validation ;
- documentation de déploiement ;
- procédure de maintenance ;
- stratégie de sauvegarde.

### Critères de validation
- build success ;
- environnement stable ;
- mise à jour sans interruption majeure ;
- rollback possible.

---

## 4. RÈGLES DE GESTION DES MODIFICATIONS

### 4.1 Une phase à la fois
Chaque phase doit être traitée de manière ciblée.

### 4.2 Tester après chaque phase
Aucune phase ne doit être considérée comme terminée sans validation fonctionnelle.

### 4.3 Documenter les changements
Tout changement important doit être documenté :
- objectif ;
- impact métier ;
- fichiers modifiés ;
- tests effectués ;
- résultat.

### 4.4 Éviter la surcharge technique inutile
Ne pas créer de nouvelles architectures sans besoin.

### 4.5 Progresser avec la logique du métier
La logique métier doit guider le développement, pas la logique purement technique.

---

## 5. MÉTHODE DE TRAVAIL PAR MODULE

Pour chaque module, appliquer la méthode suivante :

1. analyser l’existant ;
2. identifier l’écart entre l’existant et le besoin ;
3. définir le plan de travail ;
4. implémenter la logique métier ;
5. ajouter les API nécessaires ;
6. créer les tests minimaux ;
7. valider la cohérence ;
8. vérifier la non-régression ;
9. passer au module suivant.

---

## 6. LIVRABLES ATTENDUS FINAUX

À la fin du projet, l’application doit permettre de :
- gérer les produits, catégories, fournisseurs, clients ;
- gérer les achats et réceptions ;
- gérer les stocks et mouvements ;
- gérer les ventes et factures ;
- gérer les paiements et crédits ;
- afficher les notifications ;
- sécuriser l’application ;
- tracer les opérations sensibles ;
- utiliser l’API correctement ;
- disposer d’un frontend cohérent et connecté ;
- être exploitable en environnement réel.

---

## 7. RAPPORT DE PROGRESSION

Un rapport de progression doit être tenu à chaque étape avec :
- phase en cours ;
- tâches réalisées ;
- blocages rencontrés ;
- risques ;
- étapes suivantes ;
- validation effectuée.

---

## 8. CONCLUSION

NEXORA doit être développé selon une logique progressive, modulaire et testée. Le projet peut être construit sans détruire l’existant, en respectant les spécifications métier et en gardant une architecture solide.

L’objectif final est d’obtenir une application professionnelle, cohérente, sécurisée, exploitable, et facilement maintenable.

---

## 9. DOCUMENTS DE RÉFÉRENCE

- MAINTENANCE.md
- MODÈLE DE DONNÉES ET SCHÉMA DE BASE DE DONNÉES.md
- SPÉCIFICATIONS UI/ARCHITECTURE TECHNIQUE.md
- SPÉCIFICATIONS UI/CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE.md
- SPÉCIFICATIONS UI/SPÉCIFICATIONS API ET INTÉGRATION.md
- SPÉCIFICATIONS UI/SPÉCIFICATIONS DE SÉCURITÉ.md
- SPÉCIFICATIONS UI/SPÉCIFICATIONS FONCTIONNELLES DÉTAILLÉES.md
- SPÉCIFICATIONS UI/UX ET DESIGN SYSTEM.md

---

## 10. PROCHAINES ÉTAPES RECOMMANDÉES

1. Finaliser la configuration backend Django.
2. Rédiger les modules core et users complets.
3. Implémenter les produits et catégories.
4. Créer les fournisseurs et clients.
5. Développer le stock et les mouvements.
6. Mettre en place achats et réceptions.
7. Créer les ventes, factures et paiements.
8. Ajouter notifications, audit et sécurité.
9. Connecter le frontend React/Vite.
10. Valider, tester et préparer le déploiement.
