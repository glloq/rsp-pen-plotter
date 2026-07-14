# Audit — mesure d'offset de pointe par caméra (2026-07)

> Objectif : auditer la chaîne complète « mesure de l'offset XY du stylo via
> la caméra » (ADR 0005, `docs/camera_tip_offset.md`), valider qu'elle est
> fonctionnelle de bout en bout, et vérifier que le système de mesure de la
> pointe est **simple et intuitif** tout en permettant d'**adapter la mesure à
> tous les types de pointes**.

Périmètre audité :

- Backend : `pen_plotter/vision/tip_detect.py` (détecteur, session
  `TipCalibrator`), `pen_plotter/api/tip_calibration.py` (endpoints measure /
  status / reset / calibrate-scale / gpio / light), `models.py`
  (`TipCalibrationConfig`, `PenSlot.xy_offset_mm`), `core/gcode.py`
  (application de l'offset + garde-fou d'enveloppe).
- Frontend : `OffsetCameraSettings.vue` (panneau guidé), `CameraPreview.vue`
  (aperçu live + ROI par glisser), `MagazineEditor.vue` (raccourci),
  `api/client.ts`, locales `en`/`fr`.
- Docs opérateur : `wiki/Offset-Camera.md`, `docs/profile_format.md`.

---

## 1. Verdict d'ensemble

La fonctionnalité est **complète et opérationnelle** : détection (`dark_blob`
Pillow+NumPy testée sur images synthétiques), session relative au stylo de
référence, moyenne médiane multi-images avec signal de répétabilité
(`spread_mm`), aperçu annoté systématique, trajet guidé vers la station,
récupération automatique du stylo (magasins host-macro/firmware), éclairage
GPIO, assistant mm/pixel, application de l'offset au G-code strictement
opt-in (`apply_pen_offsets`) et limitée aux traits de dessin, avec
élargissement du contrôle de limites (`_pen_offset_envelope`).

État des tests avant correctifs : **42 tests backend** (tip_calibration +
pen_offset) et **44 tests frontend** (OffsetCameraSettings, MagazineEditor,
CameraPreview) passaient tous ; lint/format/typecheck propres (les 8 erreurs
mypy présentes sont préexistantes sur `main` et hors périmètre).

Côté ergonomie, le flux est bien guidé : interrupteur maître → étape 1
caméra + aperçu live avec zone de détection dessinable à la souris → étape 2
échelle (assistant « objet de taille connue ») → étape 3 mesure par stylo avec
badges de provenance (référence / mesuré / manuel / à faire), chips de
prérequis (caméra / échelle / référence), assistant pas-à-pas
(« mesure guidée ») référence d'abord, test de détection à blanc, et
garde-fous côté UI (confiance < 35 % non appliquée, offset > 50 mm signalé,
instabilité inter-images > 1,5 mm signalée). La saisie manuelle sans caméra
reste disponible partout (profil `offset_source: manual`).

Deux vrais défauts ont été trouvés et **corrigés dans ce même changement**
(§2) ; le reste est constaté sain ou consigné en recommandations (§3).

---

## 2. Défauts corrigés

### 2.1 « Tester la détection » écrasait la référence de la session

`onTestDetection` appelait `POST /plotter/tip-calibration/measure` avec
`slot = reference_slot`, et le backend **stockait** toute mesure trouvée dans
la session (`TipCalibrator._tips`). Un essai de réglage (éclairage, seuil,
zone) fait avec un objet quelconque remplaçait donc silencieusement la mesure
de référence ; les offsets mesurés ensuite étaient calculés contre cette
image de test et **appliqués** au profil sans que rien ne le signale.

**Correctif** : nouveau champ `dry_run` sur la requête de mesure →
`TipCalibrator.measure(..., store=False)` détecte et rapporte sans rien
mémoriser ; l'UI l'envoie pour le test de détection. Tests :
`test_dry_run_does_not_store_the_measurement`,
`test_dry_run_does_not_overwrite_the_reference`, et assertion `dry_run: true`
côté frontend.

### 2.2 Types de pointes : les pointes claires étaient immesurables

Seul le mode « pointe sombre sur fond clair » existait. Un stylo gel blanc,
pastel ou métallique — pointe claire — était indétectable quel que soit le
réglage de `dark_threshold`, alors que l'exigence est d'adapter la mesure à
tous les types de pointes.

**Correctif** : champ `tip_style: "dark" | "light"` sur
`TipCalibrationConfig` et sur les requêtes de mesure **et** de calibrage
d'échelle. `"light"` inverse la luminance avant seuillage : même détecteur,
même seuil, même centroïde — l'opérateur choisit simplement un fond de
station contrastant et règle un sélecteur « Type de pointe » placé à
l'étape 1, à côté de la caméra (pas enfoui dans « Avancé »). Libellés FR/EN
explicites (« Pointe sombre sur fond clair (la plupart des stylos) » /
« Pointe claire sur fond sombre (gel blanc, pastel, métallique) »). Tests :
détecteur (`test_light_tip_found_with_invert`), endpoint
(`test_measure_endpoint_light_tip_style`), échelle
(`test_calibrate_scale_light_target`), UI (persistance + envoi du style).

Pour les autres axes d'adaptation, déjà couverts : seuil réglable (pointes
pâles/grises), zone de détection ROI (pointes fines dans un cadre encombré,
excluant le corps du stylo), `samples` 1–20 avec médiane (pointes brillantes
au rendu instable), mm/pixel par assistant (toute focale/distance).

---

## 3. Constats sains et recommandations (non bloquants)

- **Application G-code** : offset ajouté après `transform`, uniquement aux
  polylignes de dessin ; jamais aux points d'engagement magasin / parking /
  changement d'outil. Offsets nuls ⇒ G-code identique octet pour octet
  (couvert par `test_pen_offset.py`).
- **Chip « échelle » toujours vert** : `mm_per_pixel > 0` est garanti par le
  modèle, donc l'indicateur de prérequis ne détecte pas une échelle jamais
  calibrée (défaut 0,1 plausible). Recommandation : tracer la provenance de
  l'échelle (comme `offset_source`) ou marquer le chip « à vérifier » tant
  que l'assistant n'a pas tourné.
- **Référence basse confiance** : une mesure de référence sous le seuil UI
  (35 %) n'est pas appliquée au profil mais reste stockée dans la session ;
  les offsets suivants se calculent contre elle. L'opérateur a vu
  l'avertissement, mais un garde-fou serveur (ne pas stocker sous un
  `min_confidence`) serait plus sûr.
- **Changement de `reference_slot` a posteriori** : les offsets déjà mesurés
  restent relatifs à l'ancienne référence sans invalidation ni avertissement.
  Recommandation : à la modification, proposer une remise à zéro des
  provenances `vision`.
- **Clés i18n `offsetCamera.next.zone` / `next.light`** référencées
  dynamiquement mais inatteignables (seuls les prérequis bloquants
  alimentent `setupHint`) — aucun impact, à nettoyer à l'occasion.
- **Biais de forme de pointe** (physique, documenté) : le centroïde d'un
  pinceau ne coïncide pas avec son point de contact comme pour une pointe
  conique ; la mesure étant relative, le biais ne s'annule qu'entre pointes
  de forme comparable. Le ROI serré + l'aperçu annoté restent les
  mitigations ; l'`aruco` sub-pixel (différé, ADR 0005) n'y changerait rien.

---

## 4. Validation après correctifs

- Backend : `pytest tests/test_tip_calibration.py tests/test_pen_offset.py`
  → **47 passed** ; `ruff check` / `ruff format --check` propres ; contrats
  (`check_contracts.py`) OK ; `openapi.json` et `api-types.ts` régénérés.
- Frontend : `vitest` OffsetCameraSettings + MagazineEditor + CameraPreview
  → **45 passed** ; `vue-tsc --noEmit` et `eslint` propres ; parité de clés
  FR/EN vérifiée.
