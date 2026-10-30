MAINTENANCE, MONITORING, ÉVOLUTIVITÉ, CI/CD, DÉPLOIEMENT ET PUBLICATION
Projet : Système intégré de gestion commerciale, des stocks, des achats et des ventes
Version : 1.0
Statut : Document de référence
Frontend : React + Vite + TypeScript
Backend : Django + Django REST Framework
Base de données : PostgreSQL
Architecture : Application Web modulaire et sécurisée
SOMMAIRE
Introduction
Objectifs du document
Principes de maintenance
Organisation de la maintenance
Maintenance corrective
Maintenance préventive
Maintenance évolutive
Maintenance de sécurité
Gestion des incidents
Crash reporting
Gestion des logs
Architecture de journalisation
Monitoring de l'application
Monitoring du backend
Monitoring de la base de données
Monitoring du frontend
Monitoring de l'infrastructure
Monitoring des services externes
Analytics et statistiques d'utilisation
Indicateurs techniques
Indicateurs fonctionnels
Alertes automatiques
Gestion des mises à jour
Gestion des dépendances
Gestion des versions
Gestion du support utilisateur
Processus de traitement des tickets
Gestion des demandes d'évolution
Priorisation des évolutions
Gestion du code source
Stratégie Git
CI/CD
Pipeline d'intégration continue
Tests automatiques
Contrôle qualité du code
Build du frontend
Build et préparation du backend
Gestion des migrations
Déploiement
Environnements de développement, test et production
Publication d'une nouvelle version
Déploiement sans interruption
Retour arrière
Sauvegardes avant déploiement
Gestion des variables d'environnement
Sécurité du processus CI/CD
Procédure en cas d'échec de déploiement
Plan d'évolution du système
Scalabilité
Documentation et transfert de connaissances
Critères de validation
Conclusion
1. INTRODUCTION
Le développement de l'application ne s'arrête pas lorsque la première version est mise en production.
Une application utilisée quotidiennement dans une entreprise doit continuer à fonctionner, être surveillée, corrigée et améliorée.
Le présent document définit donc la manière dont le système sera :
maintenu ;
surveillé ;
mis à jour ;
corrigé ;
déployé ;
publié ;
supporté ;
amélioré.
L'objectif est d'éviter qu'une modification réalisée dans le futur ne compromette les fonctionnalités existantes.
2. OBJECTIFS DU DOCUMENT
Ce document doit permettre à l'équipe technique de disposer d'une méthode claire pour :
détecter les erreurs ;
comprendre les incidents ;
surveiller l'application ;
analyser les performances ;
effectuer les mises à jour ;
déployer de nouvelles versions ;
revenir à une version précédente ;
accompagner les utilisateurs ;
ajouter de nouvelles fonctionnalités.
Le système doit pouvoir évoluer sans nécessiter une reconstruction complète de l'application.
3. PRINCIPES DE MAINTENANCE
La maintenance repose sur quatre catégories principales.
Maintenance corrective
Elle consiste à corriger les problèmes existants.
Maintenance préventive
Elle vise à éviter l'apparition de problèmes.
Maintenance évolutive
Elle permet d'ajouter de nouvelles fonctionnalités.
Maintenance de sécurité
Elle consiste à corriger les vulnérabilités et renforcer la protection du système.
Ces quatre types de maintenance doivent fonctionner ensemble.
4. ORGANISATION DE LA MAINTENANCE
Une modification ne doit pas être directement réalisée sur la production.
Le principe recommandé est :
Développement
→ Tests
→ Validation
→ Préproduction
→ Production
Cette séparation permet de réduire les risques.
5. MAINTENANCE CORRECTIVE
Lorsqu'un problème est découvert, il doit être enregistré.
Exemple :
Un vendeur indique qu'une facture ne s'imprime plus correctement.
Le problème doit être documenté :
utilisateur concerné ;
fonctionnalité ;
date ;
environnement ;
message d'erreur ;
étapes pour reproduire ;
niveau de gravité.
Le développeur doit ensuite reproduire le problème avant de le corriger.
6. MAINTENANCE PRÉVENTIVE
La maintenance préventive consiste à intervenir avant qu'une panne importante apparaisse.
Elle comprend notamment :
mise à jour des dépendances ;
nettoyage des logs ;
contrôle de l'espace disque ;
vérification des sauvegardes ;
contrôle de la base de données ;
analyse des performances ;
surveillance des erreurs ;
vérification des certificats ;
contrôle des services.
7. MAINTENANCE ÉVOLUTIVE
L'application doit pouvoir recevoir de nouvelles fonctionnalités.
Exemples futurs :
nouveaux moyens de paiement ;
nouveaux canaux de notification ;
application mobile ;
programme de fidélité ;
promotions avancées ;
nouveaux rapports ;
intégration comptable ;
nouvelles fonctionnalités fournisseurs.
Une évolution ne doit pas casser les fonctionnalités existantes.
8. MAINTENANCE DE SÉCURITÉ
Les composants techniques doivent être régulièrement surveillés.
Cela concerne notamment :
Django ;
Django REST Framework ;
React ;
Node.js ;
PostgreSQL ;
bibliothèques Python ;
bibliothèques JavaScript ;
serveur Web ;
système d'exploitation.
Une vulnérabilité critique doit être traitée en priorité.
9. GESTION DES INCIDENTS
Un incident peut être :
panne complète ;
ralentissement ;
erreur de vente ;
erreur de paiement ;
problème de synchronisation ;
problème d'impression ;
problème de QR Code ;
erreur d'importation ;
problème de notification.
Chaque incident doit recevoir un niveau de priorité.
Critique
Le système est inutilisable ou une opération financière importante est bloquée.
Haute
Une fonctionnalité majeure est fortement perturbée.
Moyenne
Une fonctionnalité fonctionne mais présente un problème.
Faible
Problème mineur ou amélioration sans impact important.
10. CRASH REPORTING
Le système doit pouvoir détecter automatiquement certaines erreurs techniques.
Lorsqu'une erreur critique se produit, les informations utiles peuvent être enregistrées :
type d'erreur ;
date ;
environnement ;
version de l'application ;
fonctionnalité concernée ;
contexte technique nécessaire ;
identifiant de corrélation.
Il faut toutefois éviter d'envoyer dans les rapports :
mots de passe ;
tokens ;
clés secrètes ;
données personnelles inutiles ;
informations financières sensibles.
Le crash reporting doit permettre au développeur de comprendre rapidement :
Que s'est-il passé ?
Sur quelle version ?
Dans quelle fonctionnalité ?
Combien d'utilisateurs sont concernés ?
11. GESTION DES LOGS
Les logs servent à comprendre le fonctionnement interne du système.
Ils peuvent concerner :
authentification ;
API ;
erreurs ;
tâches en arrière-plan ;
importations ;
notifications ;
paiements ;
synchronisations.
Les logs doivent être structurés afin d'être facilement recherchables.
12. ARCHITECTURE DE JOURNALISATION
La logique peut être organisée ainsi :
@startuml

actor Utilisateur

rectangle "Frontend React" as FE
rectangle "API Django REST" as API
rectangle "Services métier" as S
database "PostgreSQL" as DB
collections "Logs" as LOG
rectangle "Monitoring" as MON
rectangle "Alertes" as ALERT

Utilisateur --> FE
FE --> API
API --> S
S --> DB

FE --> LOG
API --> LOG
S --> LOG

LOG --> MON
MON --> ALERT

@enduml
Les logs techniques et les journaux métier doivent être distingués.
13. MONITORING DE L'APPLICATION
Le monitoring permet de connaître l'état du système en temps réel ou presque.
Il doit permettre de surveiller :
disponibilité ;
temps de réponse ;
taux d'erreur ;
utilisation des ressources ;
nombre de requêtes ;
erreurs critiques.
14. MONITORING DU BACKEND
Le backend Django doit notamment être surveillé sur :
temps de réponse API ;
erreurs HTTP ;
exceptions ;
nombre de requêtes ;
tâches en arrière-plan ;
connexions à la base ;
consommation mémoire ;
CPU.
Une augmentation soudaine des erreurs doit générer une alerte.
15. MONITORING DE LA BASE DE DONNÉES
PostgreSQL doit également être surveillé.
Les indicateurs comprennent :
taille de la base ;
connexions actives ;
requêtes lentes ;
utilisation CPU ;
espace disque ;
verrous ;
erreurs ;
état des sauvegardes.
Une base saturée peut provoquer un ralentissement global.
16. MONITORING DU FRONTEND
Le frontend React peut être surveillé sur :
erreurs JavaScript ;
erreurs de chargement ;
temps de chargement ;
erreurs réseau ;
échecs d'appels API ;
problèmes de navigation.
Les erreurs frontend doivent être associées à la version publiée.
17. MONITORING DE L'INFRASTRUCTURE
L'infrastructure doit être surveillée.
Cela comprend :
serveur ;
CPU ;
mémoire ;
disque ;
réseau ;
services applicatifs ;
certificats HTTPS.
Le système doit pouvoir signaler lorsqu'une ressource approche d'un seuil critique.
18. MONITORING DES SERVICES EXTERNES
L'application peut dépendre de services externes, notamment pour les notifications.
Le monitoring doit permettre de savoir si :
le service répond ;
les requêtes échouent ;
les notifications sont retardées ;
les appels sont rejetés.
Une panne d'un service externe ne doit pas provoquer automatiquement la perte d'une opération commerciale déjà enregistrée.
19. ANALYTICS ET STATISTIQUES D'UTILISATION
Les analytics doivent aider à comprendre comment l'application est utilisée.
Ils peuvent mesurer :
nombre de ventes ;
fréquence d'utilisation ;
modules les plus utilisés ;
volume de recherches ;
nombre d'importations ;
utilisation des fonctionnalités.
Les analytics ne doivent pas être utilisés pour collecter inutilement des données personnelles.
20. INDICATEURS TECHNIQUES
Les principaux indicateurs peuvent être :
Indicateur
Objectif
Disponibilité
Mesurer la continuité du service
Temps de réponse API
Détecter les ralentissements
Taux d'erreur
Identifier les problèmes
CPU
Surveiller la charge
Mémoire
Détecter les saturations
Stockage
Prévenir le manque d'espace
Requêtes lentes
Optimiser PostgreSQL
Crashs
Identifier les problèmes critiques
21. INDICATEURS FONCTIONNELS
Les indicateurs métier peuvent également être utiles.
Exemples :
nombre de ventes par jour ;
chiffre d'affaires ;
nombre de produits vendus ;
nombre de ventes à crédit ;
montant restant dû ;
nombre de commandes fournisseurs ;
volume des réceptions ;
mouvements de stock ;
dépenses.
Ces données doivent rester accessibles uniquement aux utilisateurs autorisés.
22. ALERTES AUTOMATIQUES
Le système peut déclencher des alertes lorsqu'un seuil est atteint.
Exemples :
Erreur critique
→ notification technique.
Stockage presque saturé
→ alerte infrastructure.
Sauvegarde échouée
→ alerte administrateur technique.
Service indisponible
→ alerte technique.
Les alertes doivent éviter de générer un volume excessif de notifications inutiles.
23. GESTION DES MISES À JOUR
Les mises à jour doivent être planifiées.
Avant une mise à jour importante :
analyser les changements ;
vérifier les dépendances ;
effectuer une sauvegarde ;
tester ;
préparer le déploiement ;
déployer ;
surveiller ;
confirmer le bon fonctionnement.
24. GESTION DES DÉPENDANCES
Les dépendances frontend et backend doivent être surveillées.
Une mise à jour ne doit pas être appliquée aveuglément.
Avant chaque mise à jour importante :
vérifier la compatibilité ;
exécuter les tests ;
vérifier les changements ;
contrôler les vulnérabilités ;
tester les fonctionnalités principales.
25. GESTION DES VERSIONS
Chaque publication doit avoir un numéro de version.
Exemple :
v1.0.0
v1.1.0
v1.1.1
v2.0.0
Le système doit pouvoir déterminer quelle version est actuellement déployée.
Les versions doivent également être conservées dans l'historique du projet.
26. GESTION DU SUPPORT UTILISATEUR
Les utilisateurs doivent pouvoir signaler un problème.
Une demande doit contenir autant que possible :
utilisateur ;
fonctionnalité ;
description ;
date ;
capture éventuelle ;
message d'erreur.
Le support doit pouvoir suivre l'état :
Nouveau
→ En analyse
→ En correction
→ Test
→ Résolu
→ Clôturé
27. PROCESSUS DE TRAITEMENT DES TICKETS
Chaque ticket doit recevoir :
un identifiant ;
une priorité ;
une catégorie ;
un responsable ;
un statut.
Le support doit éviter de perdre les demandes des utilisateurs.
28. GESTION DES DEMANDES D'ÉVOLUTION
Une nouvelle idée ne doit pas être directement transformée en code.
Elle doit d'abord être étudiée.
Exemple :
Ajouter un nouveau mode de paiement.
L'équipe doit déterminer :
besoin réel ;
impact frontend ;
impact backend ;
impact base de données ;
impact sécurité ;
impact financier ;
impact tests ;
estimation.
29. PRIORISATION DES ÉVOLUTIONS
Les évolutions peuvent être classées :
Priorité critique
Obligation réglementaire, sécurité ou blocage majeur.
Priorité haute
Fonctionnalité importante pour l'entreprise.
Priorité normale
Amélioration utile.
Priorité basse
Amélioration esthétique ou confort.
30. GESTION DU CODE SOURCE
Le code doit être conservé dans un dépôt Git.
Le dépôt doit contenir :
frontend ;
backend ;
documentation ;
configuration nécessaire ;
tests.
Les secrets ne doivent jamais être ajoutés au dépôt.
31. STRATÉGIE GIT
Une organisation simple peut être utilisée :
main
  ↓
develop
  ↓
feature/*
bugfix/*
hotfix/*
Une fonctionnalité importante doit être développée dans une branche dédiée.
Elle est ensuite testée avant intégration.
32. CI/CD
Le processus CI/CD automatise la vérification et la publication du logiciel.
Le principe est :
@startuml

actor Developpeur

rectangle "Dépôt Git" as GIT
rectangle "CI" as CI
rectangle "Tests" as TEST
rectangle "Build" as BUILD
rectangle "Préproduction" as STAGE
rectangle "Validation" as VALID
rectangle "Production" as PROD
rectangle "Monitoring" as MON

Developpeur --> GIT
GIT --> CI
CI --> TEST
TEST --> BUILD
BUILD --> STAGE
STAGE --> VALID
VALID --> PROD
PROD --> MON

@enduml
33. PIPELINE D'INTÉGRATION CONTINUE
À chaque modification importante, le pipeline peut exécuter :
récupération du code ;
installation des dépendances ;
vérification du format ;
analyse statique ;
tests backend ;
tests frontend ;
build ;
vérification de sécurité ;
génération de l'artefact.
Une modification qui échoue aux tests ne doit pas être publiée.
34. TESTS AUTOMATIQUES
Les tests doivent couvrir notamment :
authentification ;
permissions ;
produits ;
stocks ;
achats ;
réceptions ;
ventes ;
factures ;
crédits ;
paiements ;
notifications ;
importations.
Les tests critiques doivent être exécutés automatiquement avant publication.
35. CONTRÔLE QUALITÉ DU CODE
Le projet doit utiliser des outils adaptés pour détecter :
erreurs ;
code inutilisé ;
problèmes de typage ;
vulnérabilités ;
incohérences.
L'objectif est de maintenir un code compréhensible et maintenable.
36. BUILD DU FRONTEND
Le frontend React + Vite doit être compilé avant publication.
Le build doit :
vérifier TypeScript ;
générer les fichiers optimisés ;
vérifier les dépendances ;
produire les ressources nécessaires à la production.
Une erreur de build doit bloquer la publication.
37. BUILD ET PRÉPARATION DU BACKEND
Le backend Django doit être préparé pour la production.
Cela comprend notamment :
installation des dépendances ;
configuration production ;
collecte des fichiers statiques ;
vérification de configuration ;
préparation des migrations ;
vérification des variables d'environnement.
38. GESTION DES MIGRATIONS
Les modifications de la structure PostgreSQL doivent passer par les migrations Django.
Avant d'appliquer une migration en production :
tester en développement ;
tester en préproduction ;
effectuer une sauvegarde ;
appliquer la migration ;
vérifier les données ;
surveiller l'application.
Les migrations destructrices doivent être traitées avec une attention particulière.
39. DÉPLOIEMENT
Le déploiement consiste à mettre une nouvelle version à disposition des utilisateurs.
Il doit être contrôlé.
Une procédure typique :
Build
→ Tests
→ Sauvegarde
→ Déploiement
→ Migration
→ Redémarrage contrôlé
→ Vérification
→ Monitoring
40. ENVIRONNEMENTS
Trois environnements principaux sont recommandés.
Développement
Utilisé par les développeurs.
Préproduction
Reproduit autant que possible les conditions de production.
Production
Utilisé par l'entreprise.
Les données réelles ne doivent pas être utilisées librement dans l'environnement de développement.
41. PUBLICATION D'UNE NOUVELLE VERSION
Avant publication :
☐ Code validé
☐ Tests réussis
☐ Sécurité vérifiée
☐ Build réussi
☐ Migration vérifiée
☐ Sauvegarde réalisée
☐ Documentation mise à jour
Après publication :
☐ Application accessible
☐ Connexion fonctionnelle
☐ API fonctionnelle
☐ Base fonctionnelle
☐ Vente testée
☐ Facture testée
☐ Monitoring actif
42. DÉPLOIEMENT SANS INTERRUPTION
Lorsque l'infrastructure le permet, les mises à jour peuvent être effectuées avec une interruption minimale.
Le système peut utiliser une stratégie de déploiement progressive.
Exemple :
Nouvelle version
→ déploiement
→ vérification
→ basculement
Cela réduit les interruptions pour les utilisateurs.
43. RETOUR ARRIÈRE
Une nouvelle version peut provoquer un problème.
Le système doit donc prévoir un mécanisme de rollback.
Exemple :
Version 1.4.0
      ↓
Publication 1.5.0
      ↓
Erreur détectée
      ↓
Arrêt de la publication
      ↓
Retour vers 1.4.0
Le rollback doit être préparé avant les déploiements importants.
44. SAUVEGARDES AVANT DÉPLOIEMENT
Avant une modification importante de la base :
Sauvegarde PostgreSQL vérifiée
→ Déploiement
→ Migration
→ Contrôles applicatifs
La préférence Render uniquement exprimée précédemment est remplacée par la
demande du 30 octobre 2026 d'une sauvegarde indépendante de la base et des
fichiers. Confirmer les fonctions Render dans le Dashboard, estimer les coûts
avant activation et configurer une copie hors Render avant la production. Une
commande pg_dump réussie ne prouve pas à elle seule que la sauvegarde est
restaurable ; effectuer périodiquement un essai dans une base isolée.
L'inventaire des données DJIBEXA, les limites Render, les
objectifs RPO/RTO et les réponses aux incidents sont détaillés dans
[PLAN_SAUVEGARDE_SECURITE_REPRISE.md](./PLAN_SAUVEGARDE_SECURITE_REPRISE.md).
Le détail du budget et de l'architecture envisagée figure dans
[RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md](./RAPPORT_DEPLOIEMENT_RENDER_BUDGET.md).

Exemple PowerShell pour sauvegarder la base configurée. Définir auparavant
DB_HOST, DB_PORT, DB_USER, DB_NAME et BACKUP_FILE dans la session ou le contexte
d'exploitation approuvé. pg_dump demande le mot de passe si aucun mécanisme
d'authentification PostgreSQL sécurisé n'est configuré. Ne pas mettre de mot de
passe dans la commande ni dans un fichier versionné.

```powershell
pg_dump --format=custom --no-owner --file="$env:BACKUP_FILE" `
  --host="$env:DB_HOST" --port="$env:DB_PORT" `
  --username="$env:DB_USER" --dbname="$env:DB_NAME"
if ($LASTEXITCODE -ne 0) { throw "Échec de pg_dump" }
pg_restore --list "$env:BACKUP_FILE" > $null
if ($LASTEXITCODE -ne 0) { throw "Sauvegarde PostgreSQL illisible" }
```

Pour tester une restauration, créer au préalable une base vide dédiée, par
exemple `nexora_restore_check`, sur un serveur non productif. Définir les
variables de connexion pour cette base isolée, puis restaurer et vérifier le
schéma sans appliquer de nouvelles migrations :

```powershell
createdb --host="$env:DB_HOST" --port="$env:DB_PORT" `
  --username="$env:DB_USER" --maintenance-db=postgres "$env:RESTORE_DB_NAME"
if ($LASTEXITCODE -ne 0) { throw "Échec de création de la base de restauration" }
pg_restore --exit-on-error --no-owner --host="$env:DB_HOST" `
  --port="$env:DB_PORT" --username="$env:DB_USER" `
  --dbname="$env:RESTORE_DB_NAME" "$env:BACKUP_FILE"
if ($LASTEXITCODE -ne 0) { throw "Échec de restauration PostgreSQL" }
```

Pointer ensuite temporairement l'environnement applicatif de test vers cette
base restaurée (`DB_ENGINE=postgresql`, `DB_NAME=RESTORE_DB_NAME` et identifiants
correspondants), puis exécuter `python manage.py check` et
`python manage.py migrate --check` depuis le répertoire backend. Vérifier aussi
les parcours métier critiques et les volumes de données attendus avant de
déclarer l'essai réussi. Ne jamais exécuter `pg_restore` sur la base de
production pour tester une sauvegarde ; la restauration de production est une
procédure d'incident distincte avec approbation et arrêt des écritures.
45. GESTION DES VARIABLES D'ENVIRONNEMENT
Les environnements doivent disposer de configurations distinctes.
Exemples :
DATABASE_URL
DJANGO_SECRET_KEY
API_BASE_URL
WHATSAPP_API_KEY
STORAGE_KEY
Ces valeurs ne doivent pas être incluses dans le code source.

Pour démarrer le backend en production, définir explicitement
DJANGO_ENV=production, DJANGO_SECRET_KEY (clé aléatoire d'au moins 50 caractères
et cinq caractères distincts), DJANGO_ALLOWED_HOSTS (liste sans joker, séparée
par des virgules), DJANGO_DEBUG=False et DB_ENGINE=postgresql. Le démarrage
échoue si la clé, les hôtes ou le moteur de base ne sont pas valides. Les cookies
de session et CSRF sont sécurisés, la redirection HTTPS et HSTS sont activés par
défaut. Si TLS est terminé par un proxy de confiance, vérifier sa configuration
avant d'activer DJANGO_TRUST_X_FORWARDED_PROTO=True. Les valeurs de production
doivent être configurées dans l'environnement de déploiement, jamais dans le
dépôt. Configurer également FRONTEND_BASE_URL avec l'URL HTTPS du
frontend : elle sert à la redirection de la racine backend et aux liens de
réinitialisation de mot de passe. Le backend refuse en production une URL
frontend HTTP, absente ou mal formée.
Configurer un backend e-mail réel (`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`,
`DEFAULT_FROM_EMAIL` et, selon le fournisseur, identifiants TLS/SSL). Les
backends console et mémoire sont refusés en production afin de ne pas écrire
les liens d'invitation ou de réinitialisation dans les journaux ou en mémoire.
SECURE_HSTS_INCLUDE_SUBDOMAINS reste désactivé par défaut : ne l'activer
qu'après avoir confirmé que tous les sous-domaines sont servis exclusivement en
HTTPS. SECURE_HSTS_PRELOAD est optionnel et ne doit être activé qu'après
vérification de l'éligibilité et de la stratégie de retrait du domaine.
46. SÉCURITÉ DU PROCESSUS CI/CD
Le pipeline CI/CD doit être protégé.
Seuls les utilisateurs autorisés doivent pouvoir :
modifier le pipeline ;
déclencher certains déploiements ;
accéder aux secrets ;
publier une version.
Les secrets doivent être stockés dans un mécanisme sécurisé fourni par l'infrastructure CI/CD.
47. PROCÉDURE EN CAS D'ÉCHEC DE DÉPLOIEMENT
Si le déploiement échoue :
arrêter la propagation ;
identifier l'erreur ;
vérifier l'état de la production ;
vérifier la base ;
consulter les logs ;
restaurer la version précédente si nécessaire ;
corriger ;
tester ;
redéployer.
Aucune correction improvisée ne doit être réalisée directement sur la production sans traçabilité.
48. PLAN D'ÉVOLUTION DU SYSTÈME
L'application doit être conçue pour accueillir progressivement de nouvelles fonctionnalités.
Les évolutions doivent respecter l'architecture existante.
Une nouvelle fonctionnalité doit être analysée avant son développement.
Elle doit notamment préciser :
besoin ;
utilisateur concerné ;
règles métier ;
interface ;
API ;
données ;
sécurité ;
tests ;
impacts.
49. SCALABILITÉ
Si l'entreprise augmente son activité, le système doit pouvoir évoluer.
Les éléments pouvant évoluer comprennent :
puissance serveur ;
mémoire ;
stockage ;
base de données ;
cache ;
traitement asynchrone ;
séparation des services.
L'architecture doit éviter autant que possible les dépendances qui empêcheraient cette évolution.
50. DOCUMENTATION ET TRANSFERT DE CONNAISSANCES
La documentation technique doit évoluer avec le projet.
Elle doit notamment conserver :
architecture ;
configuration ;
procédures de déploiement ;
procédures de sauvegarde ;
procédures de restauration ;
API ;
modèle de données ;
règles métier importantes ;
procédures d'urgence.
Un nouveau développeur doit pouvoir comprendre le projet sans dépendre uniquement de la mémoire d'un membre de l'équipe.
51. CRITÈRES DE VALIDATION
Le système sera considéré comme correctement maintenable lorsque :
Monitoring
☐ Les erreurs peuvent être détectées
☐ Les services critiques sont surveillés
☐ Les alertes fonctionnent
Logs
☐ Les erreurs importantes sont journalisées
☐ Les logs ne contiennent pas de secrets
☐ Les opérations importantes sont traçables
Crash reporting
☐ Les erreurs critiques peuvent être identifiées
☐ La version concernée est connue
☐ Les données sensibles sont protégées
CI/CD
☐ Les tests sont automatisés
☐ Le build est automatisé
☐ Les déploiements sont contrôlés
Déploiement
☐ Les sauvegardes sont réalisées
☐ Les migrations sont contrôlées
☐ Un rollback est possible
Support
☐ Les incidents peuvent être enregistrés
☐ Les demandes sont suivies
☐ Les évolutions sont priorisées
Évolutivité
☐ Le code est modulaire
☐ La base peut évoluer
☐ L'architecture accepte de nouvelles fonctionnalités
52. CONCLUSION
La maintenance et l'exploitation font partie intégrante du cycle de vie de l'application.
Une application professionnelle ne doit pas simplement être développée puis abandonnée après sa mise en production.
Elle doit être :
Surveillée
→ Maintenue
→ Sécurisée
→ Testée
→ Mise à jour
→ Déployée
→ Améliorée
Le système doit notamment permettre à l'équipe de savoir rapidement lorsqu'un problème survient, de comprendre son origine, de corriger le problème sans compromettre les données et de publier les améliorations de manière contrôlée.
Le processus cible est donc :
Développement → Git → CI/CD → Tests → Préproduction → Validation → Sauvegarde → Production → Monitoring → Support → Évolution
Cette organisation permettra au logiciel de rester fiable après sa première mise en production et de continuer à accompagner la croissance de l'entreprise.
Clôture de la documentation
Avec ce document, les principaux éléments de référence sont désormais couverts :
besoins et objectifs ;
fonctionnalités ;
interface et expérience utilisateur ;
API ;
architecture technique ;
modèle de données ;
sécurité ;
maintenance ;
monitoring ;
CI/CD ;
déploiement ;
publication ;
évolutivité.
Ce document peut donc servir de dernier document technique de référence du dossier, sauf si vous souhaitez ensuite créer des documents opérationnels séparés tels que le manuel utilisateur, le manuel administrateur ou les procédures de déploiement.
