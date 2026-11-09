# DJIBEXA — Audit responsive et PWA

**Date :** 9 novembre 2026  
**Périmètre :** audit statique du frontend et vérifications de build locales.  
**État :** audit préalable suivi d’une première tranche responsive/PWA; la
validation sur appareils réels et plusieurs parcours privés reste à faire.

## 1. Synthèse

Le frontend est une application React 19 basée sur TanStack Start/Router,
Vite, Nitro et Tailwind CSS 4. Il possède déjà des fondations responsive
utilisables : navigation latérale transformée en panneau mobile, en-tête
adapté et conteneur de tableau défilable horizontalement.

Le dépôt ne présente pas actuellement de configuration PWA identifiable :
aucun manifeste, service worker, page hors connexion dédiée, icônes PWA 192/512,
ni mécanisme d’installation. L’interface ne peut donc pas encore être déclarée
installable et utilisable hors connexion.

L’application comprend de nombreuses surfaces (routes ERP privées, Control
Center, pages publiques et vitrines d’entreprise). Une vérification exhaustive
sur appareils et navigateurs réels n’a pas été effectuée. Cet audit est une
analyse initiale du code, pas une certification d’accessibilité ou de
compatibilité multiplateforme.

## 2. Architecture et surfaces

- **Frontend :** React 19, TanStack Start/Router, Vite, Nitro, Tailwind CSS 4,
  Radix UI et composants maison.
- **Navigation :** routes fichiers TanStack sous `frontend/src/routes/`;
  les écrans sont principalement dans `frontend/src/pages/`.
- **Étendue observée :** 47 fichiers de routes, 45 fichiers de pages et
  53 composants dans `frontend/src/components/`.
- **Espaces privés :** routes regroupées sous `_authenticated`; l’accès est
  contrôlé par la session et les permissions, avec des restrictions distinctes
  pour le Super Admin.
- **Surfaces publiques :** accueil, authentification, aide, vérification,
  réinitialisation de mot de passe et vitrines `/entreprise/$slug` et
  `/entreprise/kourouma-auto-parts`.
- **Styles :** classes utilitaires Tailwind et tokens de thème dans
  `frontend/src/styles.css`; identité institutionnelle bleue déjà définie.

## 3. Responsive existant et points à inspecter

### Éléments déjà adaptés

- `AppSidebar` utilise un `Sheet` tactile sur les écrans sous 768 px; les liens
  ferment le menu après navigation.
- L’en-tête authentifié masque la recherche complète sur petit écran et
  conserve un raccourci de recherche.
- Le contenu principal utilise `min-w-0` et des espacements progressifs.
- Le composant partagé `Table` fournit un conteneur `overflow-x-auto` avec
  défilement horizontal contenu.
- Les pages comportent déjà de nombreuses classes responsives Tailwind et des
  conteneurs de débordement horizontal explicites.

### Risques et travail restant

- Le tableau partagé défile horizontalement; il ne se transforme pas par
  défaut en cartes. Les listes de ventes, commandes, produits, stock,
  inventaire et paiements doivent être vérifiées individuellement sur téléphone
  et tablette.
- Des panneaux de page définissent aussi leur propre débordement horizontal;
  il faut distinguer le défilement intentionnel d’un débordement global.
- Les hauteurs de dialogues, tailles tactiles, marges de zones sûres iOS,
  orientation tablette et navigation clavier n’ont pas été validées de manière
  systématique.
- Le test visuel déjà rapporté sur paiements/domaines couvre une page étroite,
  mais pas la matrice complète de routes, rôles, données ni navigateurs.

## 4. PWA, installation et fonctionnement hors connexion

Recherche effectuée dans le frontend : aucun `manifest.webmanifest`, service
worker, plugin PWA, gestionnaire `beforeinstallprompt`, page hors connexion ou
icône 192/512 dédiée n’a été trouvé.

Le HTML racine déclare le viewport et une icône SVG de marque, mais pas de lien
vers un manifeste ni de métadonnées d’installation iOS. Le build frontend
fonctionne via `npm run build`.

L’authentification existante utilise des cookies de session (`credentials:
"include"`) et le jeton CSRF; les requêtes applicatives vont vers l’API Django.
Le client React Query est créé en mémoire et aucun mécanisme de persistance du
cache n’a été identifié. Il faut préserver ce comportement privé :

- ne pas mettre en cache les réponses API, documents, HTML privé, sessions,
  jetons CSRF ni données propres à une entreprise;
- ne jamais valider localement une vente ou une action financière;
- limiter le cache aux ressources statiques immuables et à une page hors
  connexion générique;
- rendre la stratégie de mise à jour du service worker explicite, sans servir
  durablement une ancienne version de l’application.

Les vitrines publiques peuvent éventuellement bénéficier d’une stratégie de
cache séparée, mais seulement après validation de leurs données, de leurs
en-têtes et de la séparation par entreprise. Cette décision est hors du cache
initial de l’application installable.

## 5. Performance et accessibilité initiales

Le build de production local réussit. Les principaux bundles observés incluent
un fichier JavaScript de **1,13 Mo brut / 305 Ko gzip**, un chunk de **471 Ko
brut / 127 Ko gzip** et un chunk jsPDF de **399 Ko brut / 130 Ko gzip**. C’est
un signal pour inspecter les imports lourds et le chargement différé; ce n’est
pas une mesure du temps réel de chargement sur réseau mobile.

Le dépôt comprend des libellés accessibles, des composants Radix et un menu
mobile. Une évaluation WCAG complète, des mesures Core Web Vitals et des tests
avec lecteurs d’écran n’ont pas été effectués.

## 6. Plan proposé

1. **Référence et inventaire visuel** — figer les vues prioritaires et les
   largeurs de référence; tester accueil, connexion, tableau de bord, ventes,
   listes de gestion, Control Center, factures et vitrines. Corriger d’abord
   les débordements horizontaux globaux, actions inaccessibles et formulaires
   inutilisables, sans toucher aux règles métier.
2. **Responsive partagé** — améliorer navigation, zones tactiles, tableaux
   prioritaires (cartes si l’information le permet, sinon défilement local
   explicite), dialogues, formulaires, tablettes portrait/paysage et zones
   sûres iOS. Conserver les tableaux détaillés sur ordinateur.
3. **Fondations PWA** — ajouter le manifeste, les icônes validées avec la
   marque, métadonnées Web/iOS, enregistrement du service worker et écran
   hors connexion générique. Éviter de mettre en cache les routes ou réponses
   privées; ne pas ajouter de stockage de données métier hors connexion.
4. **Installation et mises à jour** — ajouter une action d’installation
   uniquement lorsque le navigateur l’autorise, détecter le mode installé,
   fournir les instructions iOS « Ajouter à l’écran d’accueil » et traiter
   proprement les mises à jour du service worker.
5. **Optimisation et qualité** — analyser les bundles, charger à la demande
   les dépendances PDF/images lourdes lorsque possible; contrôler contraste,
   clavier, focus, états de chargement/erreur et tailles tactiles.
6. **Validation et déploiement** — tests responsive sur navigateurs disponibles,
   vérification d’installation, cache/offline, session/authentification et
   isolation; fournir ensuite les consignes de déploiement HTTPS et les limites
   restant à tester sur appareils physiques.

## 7. Critères d’acceptation proposés

- Aucune page prioritaire ne provoque de débordement horizontal global à
  360, 390, 768, 1024 et 1365 px; le défilement de tableaux est local et
  explicite lorsqu’il est nécessaire.
- Les parcours de connexion, session, formulaires, ventes, paiements et
  permissions gardent leur fonctionnement serveur existant.
- L’installation n’est proposée que si disponible et n’est jamais simulée.
- Le service worker ne met pas en cache de réponses privées/API ni d’actions
  métier; la page hors connexion n’affiche aucune donnée d’entreprise.
- Les ressources du manifeste et les icônes chargent en HTTPS; une mise à jour
  ne laisse pas l’utilisateur sur une version incohérente.
- Les tests de navigateurs/appareils indisponibles sont explicitement signalés,
  et ne sont pas déclarés réussis par extrapolation.

## 8. Implémentation et validation de la première tranche

- Ajout du manifeste `manifest.webmanifest`, des icônes PNG 192 × 192 et
  512 × 512 (dont maskable), de métadonnées d’installation, d’un bouton
  d’installation et d’instructions alternatives pour iOS/navigateurs.
- Ajout d’un service worker qui précache seulement la page hors connexion, le
  manifeste et les icônes; les réponses API, pages HTML privées et données
  métier ne sont pas mises en cache. Les ressources statiques hachées peuvent
  être mises en cache.
- Ajout d’une page hors connexion générique; elle ne contient pas de données
  propres à une entreprise.
- Vérification visuelle automatisée de la page publique à 320, 390, 768, 1024
  et 1365 px : aucune largeur de document supérieure à la largeur du viewport.
  Le menu mobile est disponible aux largeurs 320, 390 et 768 px.
- Vérification de l’écran de connexion aux largeurs 320, 360, 390, 768, 1024
  et 1365 px : aucun débordement horizontal; le formulaire reste dans le
  viewport. Le libellé d’accès est « Connexion » dans l’accueil et la vitrine,
  et le texte de l’écran de connexion invite maintenant à se connecter à DJIBEXA.
- Le menu mobile de la page publique ouvre sa navigation à 390 px, et le lien
  « Connexion » mène à `/auth`. Le formulaire de réinitialisation du mot de
  passe s’ouvre à 320 × 640 px sans débordement; son envoi n’a pas été soumis
  et reste donc à valider.
- Les copies française, anglaise, arabe et chinoise du bouton d’accès, de
  l’écran de connexion et des appels à la connexion ont été harmonisées.
- Vérification en local : serveur de production accessible en HTTP, icône
  PNG répondant 200, manifeste lisible, service worker contrôlant la page et
  cache `djibexa-static-v2` présent. Le dialogue d’installation et ses
  instructions alternatives s’affichent.
- Le backend Django local a été démarré sur `127.0.0.1:8000` sans migration.
  Le navigateur révélait un blocage CORS depuis le frontend `127.0.0.1:4173`;
  cette origine locale a été ajoutée aux listes de développement CORS et CSRF.
  L’API répond maintenant avec les en-têtes CORS attendus. `GET /api/v1/users/me/`
  renvoie `403` sans authentification, comportement attendu; aucune connexion
  utilisateur n’a été effectuée.
- Vérification navigateur après le démarrage du backend : une requête depuis
  `http://127.0.0.1:4173` atteint l’API et reçoit le `403` JSON attendu sans
  identité de session (pas d’erreur CORS); le manifeste répond `200`, le service
  worker est `activated` et le cache hors connexion est présent.
- `npm run build` a réussi après les changements. ESLint ciblé sur les fichiers
  responsive/PWA ne rapporte aucune erreur; deux avertissements Fast Refresh
  préexistants subsistent dans `frontend/src/lib/locale.tsx`.
- Référence de build avant découpage : bundle principal client `1 129,25 Ko`
  (`306,37 Ko` gzip), chunk `input` `472,95 Ko` (`127,28 Ko` gzip) et chunk
  `button` `69,15 Ko` (`23,76 Ko` gzip). Le navigateur charge aussi le bundle
  principal et le chunk `input` sur la page publique. C’est un risque de poids
  initial notable qui justifie un chantier dédié de découpage/analyse; aucune
  optimisation de latence réseau ou mesure de charge de production n’est
  certifiée par ces chiffres locaux.
- Optimisation d’images effectuée après cette mesure : les trois photos JPEG de
  marque ont été réencodées en qualité 82, sans changer leurs dimensions ni
  leurs chemins. Leur poids cumulé passe de `612 495` à `296 741` octets
  (−`315 754` octets, soit `51,6 %`). La photo principale chargée au premier
  affichage passe de `212 964` à `102 599` octets (−`51,8 %`). Les fichiers
  restent décodables et chargent en HTTP 200 dans le build local. Le poids total
  JavaScript initial reste élevé.
- Découpage ciblé de l’accueil : son composant est maintenant chargé à la
  demande depuis un chunk de `40,70 Ko` (`11,89 Ko` gzip). Le bundle principal
  passe de `1 129,25 Ko` (`306,37 Ko` gzip) à `1 086,92 Ko` (`294,53 Ko`
  gzip), soit `42,33 Ko` de moins dans le bundle de base. Sur la page d’accueil,
  le chunk différé est aussi chargé : le total JavaScript transféré reste donc
  pratiquement identique (`306,42 Ko` gzip cumulés). Le bénéfice est que les
  autres routes n’embarquent plus le code de l’accueil. Les autres pages métier
  restent à découper; cette tranche ne suffit pas à certifier une amélioration
  générale de latence.
- Deuxième découpage ciblé : la page « Nouvelle vente » est chargée à la demande
  dans son chunk de `26,19 Ko` (`6,68 Ko` gzip), au lieu d’être incluse dans le
  JavaScript de base. Le bundle principal passe de `1 086,92 Ko` (`294,53 Ko`
  gzip) à `996,35 Ko` (`266,64 Ko` gzip), une baisse de `90,57 Ko` brut
  (`27,89 Ko` gzip). Le chunk de la page « Nouvelle vente » n’apparaît pas dans
  les ressources chargées sur l’accueil en prévisualisation.
- Cette version conserve l’avertissement Vite sur le chunk principal dépassant
  `500 Ko`. Le build passe, mais le bundle principal reste important; les poids
  de build ne mesurent pas la latence réelle. Le parcours de vente n’a pas été
  testé avec un compte authentifié; l’API de développement refuse le CORS du
  port de prévisualisation `4174`.
- Vérification après découpage : build de production réussi, ESLint ciblé sans
  erreur, page d’accueil rendue avec le titre et le contenu attendus, et aucun
  débordement horizontal à `320 px`. La prévisualisation a utilisé le port
  `4174`; l’API de développement n’autorise pas cette origine CORS, donc cette
  vérification ne valide ni l’API ni l’authentification.
- `npx tsc --noEmit` reste en échec sur des erreurs TypeScript préexistantes
  réparties dans plusieurs fichiers non touchés, notamment `AppSidebar.tsx`,
  `SupplierDebtsTab.tsx`, les pages commandes/produits/ventes et plusieurs
  pages Control Center. Aucune erreur n’a été signalée dans les deux fichiers
  de la tranche de découpage.
- Le test hors connexion après correction de l’icône n’a pas pu être conclu :
  la navigation automatisée est restée en attente. La route de connexion a
  ensuite été rechargée dans un contexte où l’état réseau n’était pas stable;
  la page générique hors connexion et son icône ne sont donc pas validées par
  une navigation réellement hors ligne. Ne pas considérer ce test comme réussi.

## 9. Limites

Les tests Android (Chrome/Samsung Internet), iOS/iPadOS Safari, macOS Safari
et plusieurs appareils physiques ne sont pas disponibles dans cet audit
statique. L’installation réelle, la mise à jour PWA, le réseau lent,
l’accessibilité exhaustive, la charge, les parcours authentifiés, les tableaux
et formulaires privés, les vitrines par tenant et l’isolation des données
restent à valider. Le build local et les contrôles responsive effectués ne
remplacent pas ces tests.
