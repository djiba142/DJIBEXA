# Roadmap ERP Kourouma Auto Part

## Fait
- Cœur ERP (produits, stock, clients, ventes, caisse, facture imprimable)
- Utilisateurs & rôles, installation initiale, session renforcée, profil
- Commandes fournisseurs, rapports, recherche & filtres
- Réceptions & coût réel, entrepôts & transferts, notifications, cartons & QR
- Restauration complète de la base après réinitialisation de l'hébergement

## En cours
- QR de vérification sur la facture + page publique `/verifier/:token`
- Demande d'approvisionnement automatique depuis l'écran de vente
- Logo du partenaire officiel (BSG Auto Parts) sur les factures et les rapports

## À venir (base de données en pause)
- Enregistrer l'annulation de facture (cancel_sale)
- Associer un partenaire précis à chaque facture / commande (partner_id)
- Test complet du parcours de bout en bout
- Paramètres (front) et saisie manuelle du stock : faits, à tester avec la base
- Annulation de facture : écran prêt, enregistrement côté base en attente (cancel_sale)
