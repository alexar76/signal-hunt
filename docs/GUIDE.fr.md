# Signal Hunt — guide complet

> Langues : [English](GUIDE.md) · [Русский](GUIDE.ru.md) · [Español](GUIDE.es.md) · **Français** · [中文](GUIDE.zh.md)
> Règles : [English](RULES.md) · [Русский](RULES.ru.md) · [Español](RULES.es.md) · [Français](RULES.fr.md) · [中文](RULES.zh.md)

## 1. Définition

Signal Hunt est un jeu d’enquête natif de la fédération **et un laboratoire éducatif**.
Chaque manche provient d’un instantané réel d’un Hub AIMarket ordinaire : capabilities
externes, répartition des sources, prix effectifs, identité signée et historique conservé.
Le joueur examine les preuves, choisit un diagnostic et déclare sa confiance.

Voyez-le comme un **cours de laboratoire enveloppé dans un jeu** : la boucle divertit,
mais le programme est la littératie fédérée en direct — lire la télémétrie Hub, payer les
preuves, calibrer la confiance avec Brier, vérifier les engagements cryptographiques et
voir comment croissance, entrées/sorties de peers et météo de latence changent les
diagnostics.

Ce n’est pas un tableau de bord simulé. Si le Hub ne peut être mesuré, le jeu annonce
l’indisponibilité au lieu d’injecter une fixture. L’histoire ou le prix absent reste absent.

### Résultats éducatifs

Après plusieurs manches, un joueur attentif devrait pouvoir :

1. Expliquer une observation Hub à partir de sources mesurées, non de spéculation.
2. Arbitrer le coût des preuves contre le score via le evidence factor publié.
3. Déclarer une confiance qui tient face au Brier plutôt que de bluffer la certitude.
4. Recalculer un verdict à partir du sel, de l’engagement et des opérandes renvoyés.
5. Relier les classes de détecteurs (isolement, disparition, churn des peers, météo de
   latence, concentration, …) à la dynamique réelle du catalogue, du roster et de la
   latence quand la fédération grandit.

## 2. Services du serveur

Le déploiement comprend PostgreSQL, un Hub AIMarket ordinaire, le moteur de jeu et Caddy
pour TLS. Un bootstrap unique enregistre cinq capabilities locales :

| Capability | Fonction |
|---|---|
| `signal.case@v1` | Enquête courante et immuable |
| `signal.evidence@v1` | Révéler un bloc de preuve engagé |
| `signal.submit@v1` | Vérifier le diagnostic et calculer le score |
| `signal.leaderboard@v1` | Classement issu des verdicts persistés |
| `signal.heroes@v1` | Jalons publics volontaires et signés |

L’aléatoire général n’est pas recopié localement. Lorsqu’il est disponible, le moteur
découvre `sortes.draw@v1` via son Hub et garde la route, le Hub source, le receipt nonce
et le result hash. Un échec est marqué `unavailable`, jamais présenté comme un succès.

## 3. Parcours du joueur

1. **Observer.** Le premier écran expose Hub, sources, volumes, latence du manifest,
   identifiant d’observation et state hash mesurés.
2. **Enquêter.** Six blocs existent : distribution, évolution, prix, roster des peers,
   surface de latence et provenance.
3. **Décider.** Choisir un diagnostic sur quatre, éventuellement le second verrou
   (follow-up), et une confiance de 25 à 100 %.
4. **Vérifier.** Le serveur révèle le sel, contrôle l’engagement préalable, applique le
   bonus follow-up et le multiplicateur PRIME figé, conserve un verdict immuable et
   affiche le cliffhanger de la prochaine fenêtre.
5. **Progresser.** Les points fixent le statut ; série quotidienne, passeport hebdomadaire
   et prédicats explicites ouvrent des reliques. Les orbites fortes peuvent être diffusées
   en un toucher après opt-in. Aucun actif financier n’est créé.

Voir [les règles complètes](RULES.fr.md) (§6–7 pour le score et l’engagement).

## 4. Vérité et provenance

L’observation garde les heures upstream et locale, l’URL et la signer key du Hub, les
comptages par source, les prix agrégés, les états de requête et un state hash canonique.
Une manche pointe vers cet instantané immuable : une mesure plus récente ne modifie pas
ses preuves.

Le diagnostic suit des seuils déterministes déclarés. Avant exposition de la manche, le
moteur crée un sel aléatoire et publie :

```text
SHA256(round_id:answer_code:answer_salt)
```

Réponse et sel ne sont révélés qu’au verdict. Tout tiers peut recalculer l’engagement et
les opérandes du score.

## 5. Identité, confidentialité et héros

Le jeu est anonyme par défaut. Le navigateur reçoit un token opaque signé et le conserve
sur l’appareil. Aucun wallet, e-mail ou login social n’est requis ; les tables de jeu ne
gardent pas les IP brutes.

Le partage public est désactivé et ne concerne que les futurs jalons après consentement.
Le feed contient indicatif, statistiques agrégées, codes de récompense et références de
preuve ; jamais token, IP ou preuve privée.

DIOSCURI tire ce feed et contrôle la clé Ed25519 épinglée par l’opérateur. Discord et X
ont des états de livraison indépendants. Le jeu ne stocke aucun secret social.

## 6. API HTTP

| Méthode | Route | Accès |
|---|---|---|
| `POST` | `/api/v1/session` | public |
| `GET`, `PUT` | `/api/v1/profile` | bearer session |
| `GET` | `/api/v1/rounds/live` | bearer session |
| `GET` | `/api/v1/rounds/{id}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/evidence/{evidence}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/submit` | bearer session |
| `POST` | `/api/v1/rounds/{id}/broadcast` | bearer session |
| `GET` | `/api/v1/leaderboard` | public |
| `GET` | `/api/v1/leaderboard/weekly` | public |
| `GET` | `/api/v1/heroes/feed` | public, payload signé |
| `GET` | `/provider/public-key` | public |
| `POST` | `/provider/invoke` | surface provider AIMarket |

## 7. Développement local

Lancez d’abord un Hub AIMarket, puis backend et interface :

```bash
cd signal-hunt
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
SIGNAL_HUNT_HUB_URL=http://127.0.0.1:9183 .venv/bin/python -m signal_hunt.main
```

```bash
cd signal-hunt/frontend
npm ci
npm run dev
```

La page échoue explicitement si le Hub configuré ne fournit pas de manifest valide.

## 8. Production

1. Pointez DNS A/AAAA vers le serveur et ouvrez TCP 80/443 et UDP 443.
2. Copiez `.env.example` vers `.env`.
3. Générez séparément `AIMARKET_ADMIN_TOKEN` et `POSTGRES_PASSWORD`.
4. Vérifiez les clés publiques seed par un canal indépendant.
5. Exécutez `scripts/deploy.sh`.
6. Depuis une machine de confiance, utilisez `scripts/register-upstream.sh` pour
   annoncer, approuver et crawler le nouveau Hub.
7. Exécutez `scripts/verify.sh https://<domaine-signal-hunt>`.

Seul Caddy publie des ports. Sauvegardez les clés Hub/provider avec PostgreSQL et l’état
du jeu.

## 9. Exploitation et pannes

- `503 federation_unavailable` : aucune manche live valide n’a pu être produite.
- Baseline `null` : historique mesuré insuffisant, pas variation nulle.
- `federation_assist.status=unavailable` : dégradation honnête sans prétendre à un VRF.
- Un nouvel envoi identique rend le verdict stocké sans nouvelle récompense.
- Perdre une clé change l’identité et exige une restauration explicite de confiance.
- Une erreur relay est visible dans `/health` de DIOSCURI sans bloquer le jeu.

## 10. Vérification et contribution

```bash
cd signal-hunt && pytest -q
cd frontend && npm run build
```

GitHub Actions exécute la suite pytest Signal Hunt, le build frontend et `docker compose config`.
Le contrat de signature DIOSCURI du hero feed est couvert par les tests du paquet DIOSCURI dans le monorepo.
Le code est sous [licence MIT](../LICENSE). Toute modification du score, de la priorité
du détecteur ou des récompenses doit mettre à jour tests et règles dans les cinq langues.
