# Plan de travail — suite métier après l’import fournisseur

## Objectif

Poursuivre la chaîne métier logique après l’import fournisseur, en conservant le cadre actuel du projet et sans réintroduire la création de compte publique.

Flux cible :

Import fournisseur → Commande fournisseur → Réception → Frais d’acquisition → Coût réel → Prix de vente → Stock

## État actuel (2026-09-19)

Le bloc métier jusqu’au prix de vente conseillé est validé et couvert par tests backend :

- [x] Import fournisseur et commande associée
- [x] Réception fournisseur et statuts
- [x] Frais d’acquisition et répartition configurable
- [x] Coût réel unitaire / coût réel de réception
- [x] Prix de vente conseillé et application du prix final
- [x] Mise à jour du coût et du stock après validation

La prochaine étape la plus utile est maintenant l’exploitation opérationnelle du flux :

- [ ] Validation métier des écrans de gestion (commande, réception, frais, marge, prix de vente)
- [ ] Fiabilisation des règles de gestion sur les poids/volumes et margin rules
- [ ] Finalisation des API de consultation pour l’écran de gestion
- [ ] Exposition côté interface admin pour la gestion commerciale et stock

---

## 1. Bloc métier 1 — Commande fournisseur

### Objectif

Créer un workflow de commande fournisseur à partir des lignes importées et validées.

### Tâches

- [ ] Vérifier que chaque import validé génère une commande fournisseur associée
- [ ] Gérer le statut de la commande : brouillon / soumise / approuvée / réception partielle / reçue
- [ ] Vérifier qu’une commande ne contient que des produits autorisés / reconnus
- [ ] Contrôler les quantités commandées et les lignes du fournisseur
- [ ] Assurer la traçabilité entre import fournisseur, commande, fournisseur et produit

### Critères de validation

- Une commande créée depuis l’import contient toutes les lignes importées
- Un produit importé existant est réutilisé sans doublon
- Un produit absent est créé selon la règle métier définie
- Le statut de commande évolue correctement selon l’état opérationnel

---

## 2. Bloc métier 2 — Réception fournisseur

### Objectif

Recevoir les marchandises commandées et enregistrer les quantités réellement livrées.

### Tâches

- [ ] Créer une réception à partir d’une commande fournisseur
- [ ] Gérer la réception totale et partielle
- [ ] Vérifier que les produits reçus appartiennent bien à la commande
- [ ] Vérifier que les quantités reçues ne dépassent pas la commande sans autorisation
- [ ] Enregistrer les lignes de réception avec coût unitaire et quantité reçue
- [ ] Gérer les statuts de réception : brouillon / partielle / reçue / annulée

### Critères de validation

- La réception ne peut pas contenir un produit absent de la commande
- Une quantité reçue doit être positive
- Une réception partielle laisse la commande ouverte
- Une réception totale marque la commande comme reçue

---

## 3. Bloc métier 3 — Frais d’acquisition

### Objectif

Enregistrer les frais liés à l’acquisition du produit, hors coût d’achat initial.

### Tâches

- [ ] Ajouter les frais de transport
- [ ] Ajouter les frais de douane
- [ ] Ajouter les frais de manutention
- [ ] Ajouter les frais d’assurance
- [ ] Ajouter les autres frais d’acquisition
- [ ] Assurer le stockage et le calcul total des frais sur la réception
- [ ] Permettre la modification des frais avant validation finale

### Critères de validation

- La somme des frais est calculée proprement
- Les frais sont associés à la réception concernée
- Les frais sont réutilisables dans le calcul du coût réel

---

## 4. Bloc métier 4 — Répartition des coûts

### Objectif

Répartir les frais d’acquisition entre les produits reçus selon une méthode définie.

### Méthodes candidates

- [ ] Par quantité
- [ ] Par valeur
- [ ] Par poids
- [ ] Par volume

### Tâches

- [ ] Définir la méthode de répartition configurable
- [ ] Calculer la part de frais allouée à chaque produit
- [ ] Calculer la part de frais par unité reçue
- [ ] Préserver la logique métier même si la réception est partielle
- [ ] Garantir que la répartition est cohérente avec la quantité reçue

### Critères de validation

- Le coût alloué respecte la méthode définie
- Un produit sans quantité reçue ne reçoit pas de frais répartis
- La répartition reste stable au moment de la validation

---

## 5. Bloc métier 5 — Coût réel d’acquisition

### Objectif

Calculer le vrai coût de revient du produit après prise en compte de l’achat et des frais.

### Formule cible

Coût réel unitaire = coût unitaire d’achat + part des frais d’acquisition

### Tâches

- [ ] Calculer la part des frais allouée par unité
- [ ] Ajouter cette part au coût unitaire
- [ ] Calculer le coût réel d’une ligne de réception
- [ ] Calculer le coût réel total de la réception
- [ ] Exposer ce coût dans les APIs et réponses métier
- [ ] Mettre à jour le coût réel des produits concernés après validation

### Critères de validation

- Le coût réel unitaire reflète l’achat + frais
- Le coût est exposé de manière exploitable pour les écrans et API
- Les produits reçoivent un coût de revient réel cohérent après validation

---

## 6. Bloc métier 6 — Prix de vente

### Objectif

Définir le prix de vente après que le coût réel est connu.

### Tâches

- [ ] Calculer la marge souhaitée
- [ ] Déterminer le prix de vente conseillé
- [ ] Définir le prix de vente final après validation métier
- [ ] Calculer le montant de marge et le pourcentage de marge
- [ ] Gérer le changement de prix selon les règles de l’entreprise
- [ ] Ne pas recalculer le prix à partir du prix fournisseur brut sans cohérence métier

### Critères de validation

- Le prix de vente repose sur le coût réel et non sur une base incomplète
- La marge est calculable automatiquement
- Le produit affiche son coût réel et son prix de vente de manière claire

---

## 7. Bloc métier 7 — Stock et impact produit

### Objectif

Mettre le stock et le coût de revient à jour dès la validation de la réception.

### Tâches

- [ ] Mettre à jour la quantité du produit après validation
- [ ] Enregistrer le mouvement de stock lié à la réception
- [ ] Synchroniser le coût réel avec le produit concerné
- [ ] Vérifier qu’une réception partielle ne modifie pas le stock de manière incohérente
- [ ] Assurer la traçabilité du mouvement de stock

### Critères de validation

- Le stock augmente uniquement après validation
- La quantité ajoutée correspond à la réception
- Le coût réel est bien celui utilisé pour les calculs commerciaux

---

## 8. Bloc technique — API et interface

### API backend

- [ ] Endpoints de réception fournisseur
- [ ] Endpoints de frais d’acquisition
- [ ] Endpoint de coût réel d’acquisition
- [ ] Endpoint de prix de vente recommandé
- [ ] Endpoints de détail et liste pour les écrans de gestion

### Interface front

- [ ] Écran de commande fournisseur
- [ ] Écran de réception des marchandises
- [ ] Écran des frais d’acquisition
- [ ] Écran de coût réel
- [ ] Écran de prix de vente / marge

### Règles de conception

- [ ] Conserver l’architecture existante
- [ ] Ne pas reconstruire la solution à zéro
- [ ] Ne pas réintroduire la création de compte publique
- [ ] Utiliser les endpoints existants déjà validés plutôt que des doublons

---

## 9. Ordre recommandé de mise en œuvre

1. Validation réception + statut de commande
2. Saisie des frais d’acquisition
3. Répartition des frais selon méthode configurée
4. Coût réel unitaire et total
5. Mise à jour du produit / coût de revient
6. Calcul de marge et prix de vente
7. Écran de gestion et validations fonctionnelles

---

## 10. Résultat attendu

À l’issue de ce bloc, le système devra permettre de passer de l’import fournisseur au workflow réel d’acquisition :

Commande fournisseur → Réception → Frais → Coût réel → Prix de vente → Stock exploitable

Ceci correspond au bon point de travail métier suivant, en cohérence avec les spécifications et le niveau de maturité du projet actuel.
