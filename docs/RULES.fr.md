# Signal Hunt — règles du jeu

> Langues : [English](RULES.md) · [Русский](RULES.ru.md) · [Español](RULES.es.md) · **Français** · [中文](RULES.zh.md)
> Guide complet : [Français](GUIDE.fr.md)
> Terminologie : [glossaire de localisation](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) (section Signal Hunt)

## 1. Objectif

Identifier la condition d’un instantané réel AIMarket, exprimer une confiance calibrée et
obtenir le meilleur score reproductible. Aucun juge humain caché n’intervient.

Signal Hunt est **aussi un laboratoire éducatif** : chaque manche est un TP vivant sur la
télémétrie fédérée, le coût des preuves, le score probabiliste et les engagements
cryptographiques — pas une simulation à fixtures.

## 1.1 Valeur éducative

Une manche entraîne des compétences transférables au stack AIMarket / AICOM :

| Compétence | Ce que le laboratoire force à pratiquer |
|---|---|
| Lire l’état vivant de la fédération | Manifest, sources, prix, roster des peers, sondes de latence, provenance — uniquement mesuré |
| Discipline des preuves | Moins de blocs ouverts préserve le score ; les données ont un coût |
| Confiance calibrée | Le skill de Brier récompense l’honnêteté ; la surconfiance est pénalisée |
| Vérification cryptographique | Engagements de réponse et recalcul indépendant du verdict |
| Culture des détecteurs | Seuils nommés (isolement, disparition, churn des peers, météo de latence, concentration, …) dans l’ordre déclaré |
| Dynamique fédérée | Croissance, entrées/sorties de peers, météo de latence et prix changent les diagnostics |
| Preuve publique honnête | Le relais des héros ne porte que des orbites signées et vérifiées |

Lisez le produit comme **jeu + cours de laboratoire** : le jeu retient l’attention ; les
maths reproductibles et le Hub vivant forment le programme.

## 2. Manche

- Fenêtre par défaut : 1 800 secondes (30 minutes), configurable via
  `SIGNAL_HUNT_ROUND_SECONDS`.
- La manche est cléée par le state hash du champ, pas par l’horloge. Une manche
  résolue reste figée ; une manche non jouée peut se rafraîchir si des snapshots
  ultérieurs changent le diagnostic.
- La carte de mission publique reste **scellée** : seules la sévérité (`anomaly` / `calm`)
  et la profondeur de baseline jusqu’au verdict. La classe du détecteur est révélée avec la réponse.
- Une session soumet une fois ; une répétition renvoie le verdict stocké.
- Quatre diagnostics sont affichés. Leur ordre peut utiliser un VRF distant signé ; son
  indisponibilité est enregistrée explicitement.
- La bonne réponse est engagée avant toute action du joueur.

## 3. Priorité du détecteur

La première condition vraie l’emporte :

1. **Fédération isolée :** zéro capability externe.
2. **Source disparue :** absence d’une source dont la médiane historique valait au moins 3.
3. **Churn du roster peers :** l’endpoint peers est disponible et le roster mesuré a
   changé — un peer établi (≥2 snapshots) est parti et/ou un nouveau peer est apparu avec
   une profondeur d’historique ≥2. La disparition d’une source de capabilities est un
   autre signal et a priorité.
4. **Contraction :** au moins 3 capabilities et 15 % sous la médiane historique.
5. **Expansion :** au moins 3 capabilities et 15 % au-dessus de la médiane.
6. **Prix déplacé :** écart absolu ≥ `$0.001` et relatif ≥ 20 %.
7. **Météo de latence :** au moins un peer a un RTT de sonde **mesuré avec succès** au-
   dessus de `500 ms`. Les sondes échouées/ignorées gardent `latency_ms = null` et
   n’inventent pas de météo.
8. **Concentration :** avec au moins deux sources, la première porte au moins 60 %
   **et cette domination est nouvelle par rapport au snapshot précédent**. Une première
   observation sans historique peut encore se déclencher. Un 60 % persistant est `stable`.
9. **Stable :** aucun seuil déclaré franchi.

Sans historique suffisant, aucun seuil historique ne s’active. Aucune référence
synthétique n’est inventée. Le RTT est mesuré via `/.well-known/ai-market.json` du peer.

## 4. Preuves

- **Distribution :** total externe, compte et part de chaque source.
- **Évolution :** total courant, échantillons historiques et médiane mesurée.
- **Prix :** agrégats courants et médianes historiques disponibles.
- **Roster :** peers de la fédération (url, nom, capabilities), entrées/sorties vs historique.
- **Latence :** RTT mesurés, seuil (`500 ms`), nombre de lents.
- **Provenance :** URL, dates, state hash, signer key et états des sources.

Chaque bloc distinct réduit le facteur de 0,05. Six blocs donnent 0,70 (le plancher).
Rouvrir un bloc ne crée pas de pénalité supplémentaire.

## 5. Confiance

Probabilité du diagnostic choisi, de 0,25 à 1,00. Le reste est réparti entre les trois
autres options :

```text
r = (1 − confidence) / (K − 1), avec K = 4
```

La somme des probabilités vaut toujours un.

## 6. Score

```text
Brier = Σ(pᵢ − oᵢ)²
baseline = 1 − 1/K
skill = max(0, 1 − Brier / baseline)
evidence_factor = max(0.70, 1 − 0.05 × opened_evidence)
base_score = round(1000 × skill × evidence_factor)
```

**Second verrou** optionnel (micro-question sur le même champ mesuré) :

```text
follow_up_bonus = 150 si le follow-up est correct, sinon 0
combined = base_score + follow_up_bonus
```

**Fenêtre PRIME :** les 15 premières minutes de chaque heure UTC. Les manches créées
pendant PRIME figent `×1.5` :

```text
round_score = round(combined × (1.5 si prime_locked, sinon 1.0))
```

Une confiance juste est récompensée. Une erreur très confiante coûte plus qu’une erreur
prudente. Un choix uniforme à 25 % donne un skill nul. L’API rend tous les opérandes.

## 7. Règles d’engagement (en clair)

Ces boucles s’appuient sur les mêmes données Hub mesurées. Rien n’est inventé « pour le
spectacle ».

### 7.1 Second verrou (double coup)

Après le diagnostic, vous pouvez répondre à une micro-question optionnelle construite sur
la même observation, par exemple :

- quelle source mène le champ,
- si le prix effectif médian a monté / baissé / resté plat face à l’histoire,
- quelle bande contient le nombre de capabilities externes,
- quel peer mesuré est le plus lent maintenant (`latency_weather`),
- si le roster a rejoint / quitté / les deux / tenu (`peer_churn`).

Passer est autorisé. Un second verrou correct ajoute **+150** à `base_score` **avant**
PRIME. Diagnostic correct **et** follow-up correct dans la même manche débloquent le
**Double verrou**.

### 7.2 Fenêtre PRIME

Chaque heure UTC, les minutes **0–14** sont PRIME (`×1.5`).

- Le multiplicateur est **figé à la création de la manche**.
- Soumettre plus tard dans une manche née en PRIME conserve `×1.5`.
- Une manche née hors PRIME reste à `×1.0` même si vous répondez pendant une fenêtre
  chaude ultérieure.

### 7.3 Série quotidienne et bouclier

Jouer sur des jours calendaires UTC construit une **série de retour quotidienne**. Un
**bouclier** peut couvrir exactement un jour manqué. À trois jours vivants, **Gardien de
série** devient accessible. L’UI indique si la série est vivante et si le bouclier reste
disponible.

### 7.4 Présence en direct

La carte de manche montre combien de sessions ont été actives récemment et combien ont
déjà résolu **cette** manche. Ce sont des agrégats réels de la base, pas une foule
simulée.

### 7.5 Passeport de saison hebdomadaire

Chaque semaine ISO a son passeport :

| Objectif | Badge |
|---|---|
| 3 diagnostics corrects distincts | Polyglotte de saison |
| 3 000 de score hebdomadaire | Chasseur de saison |
| 3 verdicts corrects en fenêtre PRIME | Coureur PRIME |

La progression se réinitialise avec la semaine ISO. Un **classement hebdomadaire** séparé
ordonne le score gagné dans la semaine en cours.

### 7.6 Cliffhanger

Après le verdict, l’interface indique l’ouverture de la prochaine fenêtre de champ
scellée. C’est un rappel lié au `expires_at` réel de la manche, pas un teaser d’anomalie
inventée.

### 7.7 Diffusion Perfect Orbit

Avec un score ≥ 950, vous pouvez envoyer le résultat au feed signé des héros en un
toucher après avoir activé le relais public. L’opt-in tardif fonctionne aussi : résoudre
en privé → activer le relais → diffuser. Les événements automatiques pour récompenses /
score ≥ 900 restent décrits au §11.

## 8. Statuts

| Statut | Score minimum |
|---|---:|
| Observateur des étoiles | 0 |
| Éclaireur | 500 |
| Analyste du signal | 1 500 |
| Navigateur du vide | 3 500 |
| Gardien des constellations | 7 500 |
| Oracle de la fédération | 15 000 |

Le statut dépend uniquement du score persisté et ne peut être acheté.

## 9. Reliques

| Badge | Prédicat exact |
|---|---|
| Premier contact | Terminer une manche vérifiée |
| Esprit calibré | Brier courant ≤ 0,08 |
| Scan profond | Réponse juste après six preuves ouvertes |
| Vecteur net | Réponse juste et score ≥ 800 |
| Instinct du signal | Juste, aucune preuve, confiance ≥ 75 % |
| Triple verrou | Meilleure série correcte de trois |
| Observateur aguerri | Cinq manches vérifiées |
| Orbite parfaite | Réponse juste et score ≥ 950 |
| Double verrou | Diagnostic et follow-up corrects dans une manche |
| Gardien de série | Série de retour de trois jours (un bouclier pour un trou) |
| Polyglotte de saison | ≥ 3 diagnostics corrects distincts dans la semaine ISO |
| Chasseur de saison | ≥ 3 000 de score hebdomadaire dans la semaine ISO |
| Coureur PRIME | ≥ 3 verdicts corrects en fenêtre PRIME dans la semaine ISO |

Chaque badge est stocké une fois. Ce sont des traces cosmétiques, pas argent, tokens,
NFT, propriété transférable ni promesse de valeur.

## 10. Classement

Il publie indicatif, points, manches, bonnes réponses, rang et statut. Ordre : score,
bonnes réponses, Brier moyen inférieur, puis dernière partie la plus ancienne. Tokens et
preuves privées restent absents.

Un **classement hebdomadaire** séparé additionne le score de la semaine ISO en cours.

## 11. Héros

Le partage est désactivé par défaut. Après consentement, une future manche ouvrant
une récompense **ou** marquant ≥ 900 points crée au plus un événement.

Vous pouvez aussi **diffuser** en un toucher un Perfect Orbit / score ≥ 950 après avoir
activé le relais (y compris opt-in tardif après un fort verdict privé).

Le feed signe les octets JSON canoniques avec Ed25519. DIOSCURI refuse les feeds périmés,
futurs, modifiés ou mal signés ; les livraisons Discord et X sont ensuite idempotentes
séparément.

## 12. Jeu équitable

- N’automatisez pas les soumissions et ne multipliez pas les sessions pour le classement.
- N’utilisez pas le token d’autrui et ne présentez pas une base locale modifiée comme
  déploiement public.
- Vérification, lecture du code et auto-hébergement sont encouragés.
- L’opérateur peut filtrer automatisation et indicatifs abusifs, jamais modifier la
  mathématique persistée en faveur d’un joueur.

## 13. Vérification indépendante

```text
SHA256(round_id:answer_code:answer_salt) == answer_commitment
```

Recalculez ensuite probabilités, Brier, skill, evidence factor, bonus de follow-up,
multiplicateur PRIME et score arrondi. Signalez un écart avec round ID et state hash,
jamais avec le session token.
