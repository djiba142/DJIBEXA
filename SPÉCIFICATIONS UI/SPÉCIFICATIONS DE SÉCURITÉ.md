SPÉCIFICATIONS DE SÉCURITÉ
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence final
Frontend : React + Vite + TypeScript
Backend : Django + Django REST Framework
Base de données : PostgreSQL
Architecture : Application Web sécurisée et modulaire
SOMMAIRE
Introduction
Objectifs de la sécurité
Principes généraux de sécurité
Modèle de sécurité global
Gestion des utilisateurs
Authentification
Gestion des mots de passe
Authentification multifacteur
Déverrouillage biométrique
Gestion des sessions
Gestion des rôles et permissions
Sécurité du frontend React
Sécurité des API Django REST
Sécurité du backend Django
Sécurité PostgreSQL
Protection des données
Chiffrement
Gestion des secrets
Sécurité des produits et stocks
Sécurité des achats et fournisseurs
Sécurité des ventes
Sécurité des ventes externes
Sécurité des crédits clients
Sécurité des paiements
Sécurité des factures et QR Codes
Sécurité des fichiers importés
Sécurité des documents et images
Sécurité des notifications et WhatsApp
Journalisation et audit
Détection des activités inhabituelles
Protection contre les attaques courantes
Gestion des erreurs
Sécurité des appareils
Gestion des accès administrateurs
Sauvegarde et restauration
Gestion des incidents de sécurité
Procédure d'urgence
Tests de sécurité
Validation avant mise en production
Maintenance de la sécurité
Responsabilités des utilisateurs
Critères de conformité
Conclusion finale du projet
1. INTRODUCTION
La sécurité constitue une partie fondamentale du système.
L'application manipule des informations importantes pour l'entreprise :
informations des utilisateurs ;
données des clients ;
produits ;
stocks ;
fournisseurs ;
commandes ;
ventes ;
factures ;
crédits ;
paiements ;
dépenses ;
données financières ;
documents ;
historiques des opérations.
Une compromission pourrait entraîner des conséquences importantes pour l'entreprise.
La sécurité ne doit donc pas être ajoutée à la fin du développement.
Elle doit être intégrée dès la conception de l'application.
L'objectif est de construire une application dans laquelle chaque utilisateur possède uniquement les accès nécessaires à son travail et où les opérations importantes peuvent être retracées.
2. OBJECTIFS DE LA SÉCURITÉ
La sécurité du système poursuit cinq objectifs principaux.
2.1 Confidentialité
Une personne ne doit pas pouvoir consulter des informations auxquelles elle n'a pas droit.
Par exemple, un vendeur ne doit pas automatiquement avoir accès aux paramètres sensibles de l'administration.
2.2 Intégrité
Les données doivent rester exactes.
Un utilisateur ne doit pas pouvoir modifier arbitrairement :
une facture validée ;
un paiement ;
un mouvement de stock ;
une opération financière.
2.3 Disponibilité
L'application doit rester accessible aux utilisateurs autorisés.
La sécurité doit donc également protéger l'infrastructure contre les interruptions et les attaques.
2.4 Traçabilité
Les opérations importantes doivent pouvoir être associées à leur auteur.
Le système doit pouvoir répondre à :
Qui a effectué cette opération ?
Quand ?
Sur quelle donnée ?
Quel était le résultat ?
2.5 Responsabilisation
Chaque utilisateur doit disposer de son propre compte.
Les comptes ne doivent pas être partagés entre employés.
3. PRINCIPES GÉNÉRAUX DE SÉCURITÉ
Le système applique le principe du moindre privilège.
Un utilisateur reçoit uniquement les permissions nécessaires à son travail.
Par exemple :
Un vendeur peut :
créer une vente ;
rechercher un produit ;
consulter les informations nécessaires à la vente.
Mais il ne doit pas nécessairement pouvoir :
modifier les stocks manuellement ;
supprimer une facture ;
modifier les paramètres de sécurité ;
gérer les comptes administrateurs.
4. MODÈLE DE SÉCURITÉ GLOBAL
La sécurité est organisée en plusieurs couches.
@startuml

actor Utilisateur

rectangle "Sécurité Frontend" {
    component "Routes protégées"
    component "Validation interface"
    component "Gestion session"
}

rectangle "Sécurité API" {
    component "Authentification"
    component "Autorisation"
    component "Validation données"
    component "Rate Limiting"
}

rectangle "Sécurité Backend" {
    component "RBAC"
    component "Services métier"
    component "Audit"
    component "Protection transactions"
}

database "PostgreSQL sécurisé" as DB

cloud "Services externes" {
    component "WhatsApp"
    component "Stockage sécurisé"
}

Utilisateur --> "Routes protégées"
"Routes protégées" --> "Gestion session"
"Gestion session" --> "Authentification"
"Authentification" --> "Autorisation"
"Autorisation" --> "RBAC"
"RBAC" --> "Services métier"
"Services métier" --> DB
"Services métier" --> "Audit"
"Services métier" --> "WhatsApp"
"Services métier" --> "Stockage sécurisé"

@enduml
La sécurité du frontend ne doit jamais remplacer la sécurité du backend.
5. GESTION DES UTILISATEURS
Chaque utilisateur doit disposer d'un compte personnel.
Le compte contient notamment :
nom ;
prénom ;
téléphone ;
e-mail si nécessaire ;
identifiant ;
rôle ;
statut ;
date de création ;
dernière connexion.
Les statuts peuvent être :
actif ;
suspendu ;
désactivé ;
verrouillé.
Un compte désactivé ne doit plus pouvoir accéder à l'application.
6. AUTHENTIFICATION
L'utilisateur doit s'authentifier avant d'accéder aux fonctionnalités protégées.
Le processus général est :
Identifiant
↓
Mot de passe
↓
Vérification supplémentaire si activée
↓
Session sécurisée
↓
Accès à l'application
Le serveur doit effectuer les vérifications.
Le frontend ne doit jamais décider seul qu'un utilisateur est authentifié.
7. GESTION DES MOTS DE PASSE
Les mots de passe ne doivent jamais être stockés en clair.
Ils doivent être stockés sous forme de hash sécurisé.
Le système doit également prévoir :
longueur minimale ;
protection contre les mots de passe trop faibles ;
changement de mot de passe ;
récupération sécurisée ;
invalidation des anciennes sessions lorsque nécessaire.
Le mot de passe ne doit jamais apparaître dans les journaux.
8. AUTHENTIFICATION MULTIFACTEUR
Pour les comptes sensibles, notamment les comptes administrateurs, une authentification multifacteur peut être exigée.
Le principe est :
Mot de passe

Deuxième facteur
Le deuxième facteur peut être basé sur un mécanisme sécurisé compatible avec l'infrastructure retenue.
L'objectif est qu'un mot de passe compromis ne suffise pas à accéder au compte.
9. DÉVERROUILLAGE BIOMÉTRIQUE
L'application peut proposer un déverrouillage utilisant les mécanismes biométriques disponibles sur l'appareil :
empreinte digitale ;
reconnaissance faciale ;
autre mécanisme sécurisé fourni par le système d'exploitation.
Il faut cependant distinguer :
Authentification
et
Déverrouillage local.
La donnée biométrique elle-même ne doit pas être envoyée à Django.
L'application doit utiliser le mécanisme sécurisé fourni par l'appareil pour confirmer que l'utilisateur autorisé est présent.
Exemple :
Application verrouillée
↓
Empreinte / visage
↓
Appareil confirme l'identité
↓
Application déverrouillée
Si la biométrie échoue, le système peut demander le mécanisme d'authentification alternatif prévu.
10. GESTION DES SESSIONS
Les sessions doivent être sécurisées.
Le système doit notamment prévoir :
expiration après inactivité ;
déconnexion manuelle ;
révocation d'une session ;
protection contre le vol de session ;
reconnexion après expiration.
Pour les comptes sensibles, l'administrateur doit pouvoir consulter et révoquer certaines sessions actives selon les permissions prévues.
11. GESTION DES RÔLES ET PERMISSIONS
Le système utilise RBAC.
Les rôles définissent les capacités générales.
Exemples :
Administrateur
Gestion générale du système.
Responsable
Supervision de l'activité.
Vendeur
Gestion des ventes autorisées.
Gestionnaire de stock
Gestion des stocks et mouvements autorisés.
Responsable achats
Gestion des fournisseurs et commandes.
Comptable
Gestion des paiements, dépenses et données financières autorisées.
Les permissions doivent être définies précisément.
12. SÉCURITÉ DU FRONTEND REACT
React doit appliquer plusieurs protections.
Les pages sensibles doivent être protégées.
Exemple :
Un vendeur qui tente d'accéder directement à :
/settings/security
ne doit pas simplement être bloqué visuellement.
L'API doit également refuser l'opération.
Le frontend doit également :
valider les données saisies ;
éviter l'injection de contenu dangereux ;
ne jamais stocker de secrets ;
ne pas exposer les clés privées ;
gérer correctement les sessions.
13. SÉCURITÉ DES API DJANGO REST
Toutes les API doivent vérifier :
l'identité ;
le rôle ;
les permissions ;
la validité des données ;
les règles métier.
Une requête telle que :
POST /api/v1/sales/
ne doit pas être acceptée simplement parce que l'utilisateur est connecté.
Django doit également vérifier :
Cet utilisateur peut-il créer une vente ?
14. SÉCURITÉ DU BACKEND DJANGO
Le backend constitue le point de contrôle principal.
Les règles métier doivent être appliquées côté serveur.
Exemple :
Si un utilisateur tente de modifier directement une quantité de stock par une requête API, Django doit vérifier qu'il possède réellement la permission.
Il ne faut jamais faire confiance aux données envoyées par le frontend.
15. SÉCURITÉ POSTGRESQL
PostgreSQL doit être isolé du réseau public.
Les utilisateurs finaux ne doivent jamais communiquer directement avec la base.
L'accès doit être réservé au backend autorisé.
La base doit également utiliser :
comptes avec privilèges limités ;
mots de passe sécurisés ;
connexions protégées ;
sauvegardes ;
contrôle des accès.
16. PROTECTION DES DONNÉES
Les données doivent être classées selon leur sensibilité.
Données générales
nom produit ;
catégorie ;
description.
Données commerciales
prix ;
ventes ;
fournisseurs.
Données sensibles
informations financières ;
données d'authentification ;
informations personnelles ;
justificatifs.
Les accès doivent être adaptés au niveau de sensibilité.
17. CHIFFREMENT
Les communications entre le navigateur et le serveur doivent utiliser HTTPS.
Le système doit éviter la transmission de données sensibles sur des connexions non sécurisées.
Les données sensibles stockées peuvent également nécessiter des mécanismes de chiffrement adaptés à leur niveau de criticité et à l'infrastructure choisie.
18. GESTION DES SECRETS
Les secrets ne doivent jamais être écrits directement dans le code.
Cela concerne notamment :
clés API ;
mots de passe de base de données ;
secrets Django ;
identifiants WhatsApp ;
clés de stockage.
Ils doivent être gérés par les variables d'environnement ou un système sécurisé de gestion des secrets.
19. SÉCURITÉ DES PRODUITS ET STOCKS
Les stocks représentent une donnée critique.
Un utilisateur ne doit pas pouvoir modifier arbitrairement le stock.
Une variation doit normalement provenir d'une opération :
réception ;
vente ;
transfert ;
retour ;
inventaire ;
ajustement autorisé.
Chaque modification doit laisser une trace.
20. SÉCURITÉ DES ACHATS ET FOURNISSEURS
Les commandes fournisseurs doivent être protégées contre les modifications non autorisées.
Une commande validée doit avoir un statut contrôlé.
Une réception doit être liée à une commande ou à l'opération correspondante.
Les montants et quantités doivent être vérifiés côté serveur.
21. SÉCURITÉ DES VENTES
Une vente validée doit être considérée comme une opération importante.
Le système doit empêcher :
la modification arbitraire d'une vente finalisée ;
la suppression non autorisée ;
la modification d'un montant sans traçabilité.
Le vendeur doit disposer uniquement des actions nécessaires à son activité.
22. SÉCURITÉ DES VENTES EXTERNES
Le système peut autoriser une vente lorsque certains produits doivent être obtenus auprès d'une source externe.
La logique commerciale définie précédemment peut conserver :
une facture commune
tout en enregistrant correctement les mouvements de stock correspondants.
Cette opération doit toutefois être traçable.
Le système doit pouvoir déterminer :
qui a enregistré la vente ;
quels produits étaient disponibles ;
quelles quantités provenaient du stock interne ;
quelles quantités ont été obtenues ailleurs ;
quelle opération a alimenté le stock lorsque cela est nécessaire.
23. SÉCURITÉ DES CRÉDITS CLIENTS
Les crédits doivent être protégés car ils représentent une dette client.
Le système doit empêcher une modification arbitraire du montant dû.
Chaque paiement doit être enregistré comme une opération.
Exemple :
Crédit initial : 1 000 000 GNF
Paiement :       300 000 GNF
Solde :          700 000 GNF
Le solde doit être calculé à partir des opérations enregistrées.
24. SÉCURITÉ DES PAIEMENTS
Les paiements sont des opérations financières sensibles.
Le système doit enregistrer :
montant ;
date ;
utilisateur ;
client ;
référence ;
mode de paiement ;
opération concernée.
Un paiement validé ne doit pas être supprimé sans procédure appropriée.
Toute correction doit être traçable.
25. SÉCURITÉ DES FACTURES ET QR CODES
Les factures doivent posséder des références uniques.
Le QR Code présent sur une facture doit permettre de retrouver la facture ou de vérifier certaines informations prévues par le système.
Il ne doit pas exposer inutilement des données sensibles.
Un QR Code ne doit donc pas contenir :
mot de passe ;
clé secrète ;
information d'authentification ;
données privées inutiles.
26. SÉCURITÉ DES FICHIERS IMPORTÉS
Les fichiers reçus des fournisseurs peuvent contenir :
Excel ;
CSV ;
PDF ;
images ;
autres formats autorisés.
Le système doit vérifier :
extension ;
type réel ;
taille ;
contenu ;
nom ;
emplacement de stockage.
Les fichiers dangereux doivent être rejetés.
27. SÉCURITÉ DES DOCUMENTS ET IMAGES
Les documents doivent être accessibles uniquement aux utilisateurs autorisés.
Une URL de document ne doit pas permettre à n'importe qui d'accéder à un fichier privé.
Les documents doivent être associés à leur contexte métier.
Exemple :
Facture → document PDF correspondant
Produit → image
Paiement → justificatif
28. SÉCURITÉ DES NOTIFICATIONS ET WHATSAPP
Les notifications externes doivent être contrôlées.
Le système doit éviter d'envoyer accidentellement des informations sensibles à un mauvais numéro.
Avant l'envoi, les informations nécessaires doivent être correctement associées au client.
Le système doit également conserver un statut :
en attente ;
envoyé ;
échoué ;
à réessayer.
Une erreur WhatsApp ne doit pas annuler une vente ou un paiement déjà enregistré.
29. JOURNALISATION ET AUDIT
Les opérations importantes doivent être enregistrées.
Exemples :
connexion ;
déconnexion ;
création de produit ;
modification de prix ;
réception ;
vente ;
paiement ;
modification de stock ;
annulation ;
modification des permissions.
Le journal doit permettre de retracer l'activité.
30. DÉTECTION DES ACTIVITÉS INHABITUELLES
Le système peut surveiller certains comportements.
Exemples :
nombreuses tentatives de connexion ;
connexions inhabituelles ;
nombreuses annulations ;
modifications répétées du stock ;
tentatives répétées d'accès interdit.
Une activité inhabituelle peut générer une alerte à destination d'un utilisateur autorisé.
31. PROTECTION CONTRE LES ATTAQUES COURANTES
Le système doit prendre en compte les principales menaces Web.
Notamment :
injection SQL ;
XSS ;
CSRF lorsque applicable ;
usurpation de session ;
attaques par force brute ;
accès non autorisé ;
upload malveillant ;
exposition de secrets ;
manipulation des paramètres ;
abus des API.
Django et les composants utilisés doivent être configurés selon les bonnes pratiques de sécurité.
32. GESTION DES ERREURS
Les erreurs techniques détaillées ne doivent pas être exposées aux utilisateurs finaux.
Il faut éviter d'afficher :
stack trace ;
requête SQL ;
clé secrète ;
chemin interne du serveur ;
configuration ;
informations sensibles.
L'utilisateur doit recevoir un message compréhensible.
Les détails techniques doivent rester dans les journaux sécurisés.
33. SÉCURITÉ DES APPAREILS
L'application doit considérer l'appareil comme un élément supplémentaire de sécurité.
Lorsque cela est possible, elle peut permettre :
verrouillage automatique ;
déverrouillage biométrique ;
déconnexion ;
révocation d'une session.
En cas de perte d'un appareil, les sessions correspondantes doivent pouvoir être révoquées.
34. GESTION DES ACCÈS ADMINISTRATEURS
Les comptes administrateurs doivent bénéficier du niveau de protection le plus élevé.
L'administrateur peut disposer de permissions étendues, mais ses actions restent contrôlées.
Les opérations critiques doivent être auditées.
Exemples :
création d'un administrateur ;
modification d'un rôle ;
changement de permissions ;
suppression logique d'un utilisateur ;
modification de paramètres sensibles.
35. SAUVEGARDE ET RESTAURATION
La sécurité comprend également la protection contre la perte de données.
Des sauvegardes régulières doivent être effectuées.
Elles doivent couvrir notamment :
base de données ;
documents ;
fichiers importants ;
configuration nécessaire à la restauration.
Les sauvegardes doivent être protégées contre les accès non autorisés.
36. GESTION DES INCIDENTS DE SÉCURITÉ
Lorsqu'un incident est détecté, il doit être traité selon une procédure.
Exemple :
Détection
↓
Analyse
↓
Isolation
↓
Correction
↓
Vérification
↓
Rétablissement
↓
Rapport
L'objectif n'est pas seulement de résoudre le problème mais également de comprendre sa cause.
37. PROCÉDURE D'URGENCE
En cas de compromission présumée :
identifier le compte ou service concerné ;
suspendre l'accès si nécessaire ;
révoquer les sessions ;
changer les secrets compromis ;
analyser les journaux ;
vérifier les données sensibles ;
restaurer depuis une sauvegarde si nécessaire ;
corriger la vulnérabilité ;
tester le système ;
réactiver progressivement les services.
Toutes les actions doivent être documentées.
38. TESTS DE SÉCURITÉ
Avant la mise en production, plusieurs catégories de tests doivent être réalisées.
Tests d'authentification
Vérifier :
connexion ;
déconnexion ;
expiration ;
récupération de compte.
Tests de permissions
Vérifier qu'un vendeur ne peut pas effectuer une opération réservée à l'administration.
Tests API
Tester :
requêtes invalides ;
accès sans authentification ;
accès avec mauvais rôle ;
paramètres manipulés.
Tests de fichiers
Tester :
formats interdits ;
fichiers trop volumineux ;
fichiers malveillants ;
extensions falsifiées.
Tests de sécurité générale
Tester les principales vulnérabilités Web applicables au système.
39. VALIDATION AVANT MISE EN PRODUCTION
Avant de mettre l'application à disposition des utilisateurs, une checklist de sécurité doit être validée.
Authentification
☐ Connexion sécurisée
☐ Mots de passe correctement protégés
☐ MFA configuré pour les comptes concernés
☐ Sessions sécurisées
Autorisations
☐ Rôles vérifiés
☐ Permissions vérifiées côté backend
☐ Routes protégées
API
☐ HTTPS
☐ Validation des données
☐ Protection contre les abus
☐ Gestion des erreurs
Base de données
☐ Accès restreint
☐ Sauvegardes fonctionnelles
☐ Restauration testée
Fichiers
☐ Téléversement sécurisé
☐ Documents protégés
☐ Images contrôlées
Finance
☐ Paiements protégés
☐ Crédits protégés
☐ Factures protégées
☐ Audit fonctionnel
Infrastructure
☐ Secrets non exposés
☐ Configuration production sécurisée
☐ Services inutiles désactivés
40. MAINTENANCE DE LA SÉCURITÉ
La sécurité ne s'arrête pas à la mise en production.
L'équipe technique doit régulièrement :
mettre à jour Django ;
mettre à jour React et les dépendances ;
surveiller les vulnérabilités ;
vérifier les journaux ;
tester les sauvegardes ;
contrôler les permissions ;
supprimer les accès inutiles.
Les dépendances doivent être maintenues à jour selon une stratégie contrôlée.
41. RESPONSABILITÉS DES UTILISATEURS
La sécurité dépend également des utilisateurs.
Chaque utilisateur doit :
garder son mot de passe secret ;
ne pas partager son compte ;
verrouiller son poste lorsqu'il s'absente ;
signaler une activité suspecte ;
vérifier les informations avant une opération sensible ;
ne pas installer de logiciels inconnus sur les appareils professionnels.
L'administrateur doit également supprimer ou désactiver les comptes des personnes qui ne doivent plus accéder au système.
42. CRITÈRES DE CONFORMITÉ
Le système sera considéré comme conforme lorsque :
Authentification
Les utilisateurs sont correctement authentifiés.
Autorisation
Chaque rôle possède uniquement les permissions prévues.
Données
Les informations sensibles sont correctement protégées.
API
Les endpoints vérifient systématiquement l'identité et les permissions.
Stock
Les modifications sont contrôlées et historisées.
Ventes
Les ventes validées ne peuvent pas être arbitrairement modifiées.
Paiements
Les paiements sont traçables.
Crédits
Les dettes et remboursements sont correctement historisés.
Factures
Les factures possèdent une référence unique et leur intégrité est protégée.
Fichiers
Les documents sont contrôlés et protégés.
QR Codes
Les QR Codes n'exposent pas de secrets.
Audit
Les opérations sensibles sont enregistrées.
Sauvegardes
Les données peuvent être restaurées.
Incidents
Une procédure d'urgence existe.
43. CONCLUSION FINALE DU PROJET
Ce document clôt la documentation technique principale du système.
L'architecture globale repose désormais sur plusieurs niveaux complémentaires :
Cahier des charges
→ définit les besoins et les objectifs.
Spécifications fonctionnelles détaillées
→ définissent le comportement de chaque module.
Spécifications UI/UX et Design System
→ définissent l'interface, les écrans, les composants et l'expérience utilisateur.
Spécifications API et intégration
→ définissent la communication entre React et Django.
Architecture technique
→ définit la manière dont l'application est construite.
Modèle de données
→ définit la manière dont les informations sont organisées et conservées.
Spécifications de sécurité
→ définissent la manière dont l'ensemble doit être protégé.
L'ensemble forme donc une documentation cohérente pour passer de la conception au développement.
Le principe final du système peut être résumé ainsi :
L'utilisateur dispose d'une interface simple et adaptée à son rôle. React gère l'expérience utilisateur. Django contrôle les règles métier et les permissions. PostgreSQL conserve les données officielles. Chaque opération importante est traçable. Les documents, paiements, stocks, ventes et crédits sont protégés. Les services externes restent contrôlés par le backend.
L'objectif n'est pas seulement de créer une application qui fonctionne, mais de construire un véritable outil professionnel de gestion commerciale, capable d'accompagner l'entreprise dans son fonctionnement quotidien et dans son évolution future.
