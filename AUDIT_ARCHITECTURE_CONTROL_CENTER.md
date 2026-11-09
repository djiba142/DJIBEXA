# DJIBEXA — Audit et plan de mise en conformité du Control Center

**Date :** 9 novembre 2026  
**Périmètre :** dépôt local, modèles Django, migrations présentes, services
Control Center, isolation des données et tests consultés.  
**Limite :** cet audit ne certifie pas l’état d’une base PostgreSQL de production,
qui n’a pas été inspectée.

## 1. Résumé exécutif

Le projet dispose déjà d’une première architecture multi-tenant : un modèle
`Tenant`, un champ `User.tenant`, des champs tenant sur plusieurs modèles métier,
un Control Center protégé par le rôle `is_platform_admin`, des plans, abonnements,
paiements manuels, overrides de modules et journaux administratifs.

La cible produit n’est cependant pas intégralement mise en œuvre. Les écarts
majeurs concernent les adhésions distinctes, les invitations persistées et
révocables, l’outbox transactionnelle, les domaines tenant, les factures
d’abonnement, la couverture uniforme des clés tenant et l’isolation PostgreSQL
RLS. Certains modèles métier héritent du tenant par leur parent, mais cette
convention doit être recensée et protégée explicitement.

Le propriétaire a validé le plan d’implémentation progressive, hors migration
de production. Depuis l’audit initial, des modèles et migrations additives ont
été ajoutés au dépôt; leur application en production n’a pas été autorisée ni
effectuée. L’historique PostgreSQL réel n’a pas été inspecté. Les migrations
non validées `0013` à `0016` préexistantes ont été préservées.

## 2. État audité

| Domaine | Existant observé | Écart / risque à traiter |
|---|---|---|
| Tenants et utilisateurs | `TenantMembership` et UUID publics tenant/utilisateur ajoutés; `User.tenant` et les PK existantes restent compatibles. `tenant_for_user` refuse une adhésion inactive ou manquante dès qu’un compte possède des memberships. | La compatibilité des comptes historiques sans membership reste volontaire; l’application des memberships à toutes les vues et l’obligation d’un administrateur principal restent à terminer. |
| Données métier | Plusieurs modèles ont une FK tenant; des modèles enfants portent seulement une FK vers leur parent. Le helper `tenant_scoped_queryset` inclut les enregistrements sans tenant pour les comptes historiques dans une installation mono-tenant. | Les FKs tenant ne sont pas toutes obligatoires. La portée doit être vérifiée pour chaque vue, relation imbriquée, import, fichier et tâche asynchrone avant d’activer un mode multi-tenant strict. |
| Plans et droits | `PlanFeature` versionné et snapshots de fonctionnalités ajoutés; service central d’évaluation disponible. | Vérifier les règles de période d’effet dans tous les parcours; le frontend et la protection de chaque endpoint ne sont pas encore uniformément intégrés. |
| Abonnements et paiements | Les nouveaux abonnements créent une facture; les paiements manuels sont reliés à `PaymentRecord`, avec justificatif privé PDF/JPG/PNG (10 Mo max), puis confirmation/rejet synchronisés. L’API historique `PlatformPayment` reste compatible. | L’historique des paiements existants n’est pas encore rapproché/backfillé; un écran et des endpoints dédiés aux factures restent à ajouter. |
| Provisionnement | Création/invitation admin transactionnelle; création d’outbox dans la transaction et commande de livraison avec reprise exponentielle. | Pas encore de processus complet à états PROVISIONING/idempotence couvrant toutes les opérations de provisionnement. |
| Invitation | Jetons aléatoires à usage unique et expiration, hashés en base; mot de passe choisi via invitation; renvoi/révocation et outbox chiffrée intégrés. | La révocation n’a pas encore d’interface Super Admin dédiée; le worker outbox doit être planifié et surveillé en exploitation. |
| Administrateur principal | Memberships et contrainte garantissant au plus un administrateur principal actif par tenant; invitation initiale différée jusqu’à activation. | La base ne contraint pas encore chaque tenant à avoir obligatoirement un administrateur principal actif; vérifier les parcours d’activation/désactivation concurrents. |
| Domaines | Gestion Control Center ajoutée par entreprise; défis TXT aléatoires, hashés en base, expirant après sept jours, vérification DNS avec délais bornés, domaine principal seulement après vérification, justification et audit. | Les noms sont vérifiés par DNS public au moment de la demande; le routage vers le frontend, TLS/certificats et la configuration DNS de production restent externes à cette API. |
| Audit | `AuditLog` métier et `PlatformAuditLog` central existent; plusieurs opérations Control Center sont journalisées et filtrables. Le helper permet maintenant de conserver IP, user-agent, entité, états et motif; les nouveaux flux domaine et cycle de vie l’utilisent. | Les deux formats sont différents; les anciennes opérations ne remplissent pas encore ces champs systématiquement. La journalisation exhaustive n’est pas démontrée. |
| Cycle de vie | Les statuts `draft/provisioning/pending_activation/trial/active/suspended/blocked/expired/archived/deletion_pending` existent. Archivage, restauration en suspension et demande de suppression logique sont disponibles et n’effacent pas le tenant. | Les transitions d’abonnement ne couvrent pas encore uniformément tous ces états; la suppression définitive et les règles de rétention nécessitent une procédure distincte et approuvée. |
| RLS PostgreSQL | Aucun `CREATE POLICY`, `ENABLE ROW LEVEL SECURITY` ou contexte de tenant PostgreSQL trouvé dans le code inspecté. | L’isolation actuelle dépend donc du code applicatif. RLS requiert une configuration PostgreSQL, un contexte transactionnel fiable et un rôle de connexion qui ne contourne pas les politiques. |
| Tests | Tests ajoutés pour invitation hashée/à usage unique, outbox/reprise et memberships; migrations vérifiées sur SQLite de test. | La suite complète doit encore être exécutée après les derniers changements; PostgreSQL/RLS, fichiers et matrice exhaustive inter-tenant restent à valider. |

### Actions de sécurité restant à terminer

1. Continuer à remplacer les parcours d’invitation/réinitialisation restants par
   le token hashé et l’outbox; planifier et surveiller
   `process_email_outbox` en exploitation.
2. Étendre l’usage des adhésions aux vues, fichiers, tâches et modèles métier,
   sans supprimer immédiatement `User.tenant`.
3. Garantir côté serveur les adhésions actives, le tenant cible et l’accès à
   chaque objet; ne jamais accepter le tenant du client comme autorité.
4. Ajouter les contraintes relationnelles nécessaires pour empêcher les
   relations croisées entre tenants, après inventaire et assainissement des
   données existantes.
5. Ne pas considérer les overrides d’interface comme une autorisation; le
   service backend de droits reste la source de vérité.

## 3. Modèle relationnel cible proposé

La migration doit être **additive**. Les PK entières existantes et les relations
ERP historiques sont conservées. Ajouter des UUID publics uniques, puis ne
considérer leur promotion en PK qu’après une décision séparée et une migration
de données réversible.

- **Tenant** : conserver `Tenant` comme racine; ajouter progressivement code,
  coordonnées, paramètres régionaux, archivage/suppression logique et statuts
  documentés. Garder `slug` unique comme alias de routage existant.
- **User** : conserver le modèle global et les hachages Django; normaliser
  l’e-mail sans rendre sa clé unique avant déduplication et décision sur les
  comptes historiques.
- **TenantMembership** : FK vers tenant et utilisateur, rôle, actif, dates;
  contrainte unique `(tenant, user)` et garantie d’un administrateur principal
  actif au plus par tenant. Décider comment gérer les utilisateurs appartenant
  à plusieurs tenants avant d’adopter un tenant actif en session.
- **TenantDomain** : hostname normalisé et unique globalement, type, vérification,
  principal et dates. Ne router un tenant que par domaine vérifié.
- **PlatformModule / Plan** : conserver le catalogue et les modèles actuels;
  introduire un catalogue de fonctionnalités ou étendre le module avec statut
  technique. Ajouter `PlanFeature` avec snapshot/versions et limites JSON.
- **TenantSubscription** : conserver montant, devise, modules, durée et
  contrainte d’abonnement courant; ajouter période de grâce et cycle d’état.
- **TenantFeatureOverride** : remplacer progressivement les états actuels par
  INHERIT/ENABLE/DISABLE/SUSPEND, dates, motif et acteur; conserver un adaptateur
  pendant la transition.
- **BillingInvoice / PaymentRecord** : factures immuables par abonnement; paiements
  manuels liés à la facture, avec justificatif privé, saisie et confirmation
  distinctes. Conserver `PlatformPayment` pendant migration et rapprochement.
- **Invitation** : tenant, e-mail normalisé, utilisateur optionnel, hash du jeton,
  expiration, usage, révocation et créateur. Le jeton brut ne vit que dans le
  lien envoyé; aucune valeur secrète ne sera stockée.
- **EmailOutbox** : tenant optionnel, destinataire, code de gabarit, payload,
  état, tentatives, prochain essai, date d’envoi et erreur expurgée; insertion
  dans la même transaction métier, livraison asynchrone idempotente.
- **AuditLog** : format central avec tenant, acteur, action, entité, changements,
  motif, IP, user-agent et date; accès en écriture seulement par les services
  backend. Préserver et migrer les deux journaux existants sans perte.
- **TenantUsageRecord** : ajouter seulement pour des quotas effectivement
  mesurés; distinguer mesure périodique d’un compteur transactionnel.
- **Tables métier enfants** : maintenir FK tenant directe lorsque nécessaire
  pour filtrer et contraindre; autoriser explicitement les enfants qui héritent
  sans ambiguïté du tenant par leur parent, documentés et testés.

## 4. Plan de migration et de déploiement — approuvé pour implémentation progressive

### Phase 0 — Préconditions (aucun changement de schéma)

1. Sauvegarder la base PostgreSQL et les médias; vérifier une restauration
   représentative avant toute opération.
2. Relever les versions de schéma et de code en production, le volume, les
   doublons d’e-mails, les utilisateurs sans tenant, les objets métier orphelins
   et les incohérences tenant-parent.
3. Faire approuver le présent modèle, les statuts, la politique multi-membership,
   les rôles et les règles de conservation.
4. Construire un inventaire table/endpoint/fichier/tâche de l’isolation; aucun
   passage à NOT NULL ni activation RLS avant résolution des exceptions.

### Phase 1 — Socle compatible

1. Ajouter des modèles et champs facultatifs (membership, domaines, invitation,
   outbox, feature/plan snapshots, audit étendu), sans supprimer ni renommer les
   tables actuelles.
2. Ajouter des index et contraintes uniquement après pré-vérification des
   doublons; réaliser le backfill par lots, idempotent et journalisé.
3. Représenter les tenants et utilisateurs existants comme memberships; vérifier
   chaque résultat et conserver `User.tenant` comme projection de compatibilité.
4. Écrire en parallèle les anciennes et nouvelles formes d’audit/paiement si
   nécessaire, avec réconciliation et métriques avant bascule.

### Phase 2 — Services et parcours

1. Utiliser un service unique de résolution du tenant et des droits effectifs,
   incluant les chemins HTTP, les fichiers et les tâches.
2. Migrer invitation, renvoi, révocation, activation et courriel vers token
   aléatoire hashé et outbox; ne plus envoyer de mot de passe.
3. Ajouter le provisionnement récupérable/idempotent et les opérations facture,
   enregistrement, confirmation, rejet, suspension et reprise auditées.
4. Exiger une justification et une expiration pour l’accès exceptionnel
   Super Admin aux données commerciales; sans dérogation active, aucune lecture.

### Phase 3 — Isolation et durcissement

1. Rendre les FKs obligatoires et ajouter les contraintes tenant-parent après
   nettoyage et tests des données existantes.
2. Activer RLS par table PostgreSQL, avec politique fail-closed, contexte établi
   côté serveur dans chaque transaction et rôle applicatif non propriétaire
   n’ayant ni BYPASSRLS ni privilège superuser.
3. Exécuter les tests inter-tenant négatifs sous le même rôle et les mêmes
   transactions que l’application; inclure les tâches asynchrones et documents.
4. Observer en mode shadow, comparer les résultats, puis activer progressivement
   les contrôles stricts. Prévoir procédure de rollback par migration additive,
   feature flag et restauration approuvée.

### Phase 4 — Retrait des compatibilités (décision ultérieure)

Après plusieurs versions stables, supprimer les champs/tableaux de compatibilité
uniquement sur décision explicite et après preuve qu’aucun client ou historique
ne les utilise. Ne jamais réinitialiser PostgreSQL ni effacer les données ERP.

## 5. Plan de sécurité et critères d’acceptation

- Matrice complète des routes et modèles : tenant actif, rôle, membership et
  entitlement vérifiés côté serveur; accès cross-tenant refusé même avec un ID
  valide ou un tenant forgé.
- Contraintes de cohérence des FK entre parent/enfant et unicité d’un
  administrateur principal actif; comportements de remplacement et de départ
  du dernier administrateur testés en concurrence.
- RLS testée sur PostgreSQL avec le rôle réel de l’application; absence de
  contexte, changement de tenant, erreur et rollback doivent refuser l’accès.
- Invitations : aléatoires, hash seulement en base, uniques, expirables,
  révocables, usage atomique unique; mot de passe défini par l’utilisateur,
  validé par Django, jamais envoyé.
- Outbox : création transactionnelle, reprise avec backoff, idempotence,
  erreurs expurgées; aucun succès d’envoi déclaré si le fournisseur échoue.
- Paiement : déclaration distincte de confirmation; seule la confirmation
  autorisée active/prolonge l’abonnement; factures et décisions restent
  historisées.
- Audit immuable des actions privilégiées et transitions d’accès, avec motif,
  acteur et tenant; exclusion des secrets, mots de passe et jetons.
- Fichiers privés : autorisation tenant avant téléchargement, stockage hors
  exposition publique, tests d’accès croisé et de liens expirés.
- Régression : scénarios existants ERP, sauvegarde/restauration, migrations
  depuis copie anonymisée de production et vérification du plan de retour.

## 6. État d’exécution

- Audit du dépôt et du code : effectué.
- Rapport et modèle cible : documentés ici.
- Plan de migration et de sécurité : documentés ici et approuvés pour
  l’implémentation progressive.
- Modèles et migrations additives : présents dans le dépôt; essais de migrations
  effectués sur une base SQLite temporaire de test. Aucune base de production
  n’a été modifiée.
- Invitation ERP : mot de passe provisoire supprimé; lien aléatoire hashé,
  unique, expirant et révocable; inscription outbox chiffrée et commande de
  livraison avec reprises implémentées.
- Membership et cycle de vie : vérification renforcée dans le résolveur partagé;
  transitions d’archivage, restauration en suspension et demande de suppression
  logique ajoutées sans suppression de données.
- Domaines : API et interface ajoutées; le domaine reste en attente tant que le
  TXT DNS n’est pas confirmé, le défi n’est exposé qu’à sa création/renouvellement
  et son hash seulement est conservé en base.
- Facturation : les nouveaux abonnements créent une facture numérotée; le flux
  historique de paiement écrit aussi un `PaymentRecord` associé, met à jour la
  facture lors de la confirmation et conserve les rejets distincts.
- Validation : Django check, `makemigrations --check --dry-run`, les suites
  `core.tests` et `users.tests` (131 tests), le build frontend et ESLint ciblé
  réussis; ESLint conserve deux avertissements Fast Refresh préexistants dans
  `locale.tsx`. Le rapprochement de l’historique, des endpoints dédiés aux
  factures, le RLS PostgreSQL, l’isolation exhaustive des endpoints, l’audit
  complet, le test visuel connecté, la charge et la validation du domaine de
  production restent des étapes séparées.

Ne pas appliquer les migrations en production avant une approbation distincte
du plan de déploiement, de la sauvegarde et des risques sur données réelles.
