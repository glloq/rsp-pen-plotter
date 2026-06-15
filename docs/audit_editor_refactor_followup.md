# Audit de refactorisation — éditeur V2, parties restantes (2026-06)

Scope : ce qui **reste à découper/durcir** dans l'éditeur V2 après le traitement du
ré-audit complet (corrections P0/P1, sécurité SVG, accessibilité, et une première
vague d'extractions Phase 4). Sert de feuille de route pour une **prochaine
discussion** — rien ici n'est encore fait.

> Contexte : le gros du ré-audit est livré (branche `claude/quirky-edison-xth92c`).
> Voir la section « Déjà fait » pour ne pas refaire le travail.

---

## 0. Déjà fait (ne pas refaire)

| Axe                                                                         | État                                                                                                                                                       |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0 — pipeline async robuste (try/catch/finally, statut, Générer verrouillé) | ✅ `useEditorPreviewPipeline`                                                                                                                              |
| P1 — fermeture sûre (dispose confirm, `requestClose`, rollback palette)     | ✅ `useEditorCloseGuard`, `useEditorConfirmation`                                                                                                          |
| P2 — frontière SVG explicite (DOMPurify)                                    | ✅ `SafeSvgHtml.vue`, `sanitizePreviewSvgCached`                                                                                                           |
| P2 — accessibilité (focus-trap inert/visibilité, tour = vrai modal, Escape) | ✅ `useEditorDialogAccessibility`, `EditModalV2`                                                                                                           |
| P2 — découpage (1ʳᵉ vague)                                                  | ✅ `useEditorInkSwatches`, `useEditorExpertPreview`, `useEditorPreviewZoomPan`, `useEditorPreviewSplit`, `PreviewToolbar.vue`, `PreviewLoadingOverlay.vue` |
| P3 — tests (intégration runnable + Playwright gated)                        | ✅ / ⚠️ Playwright non exécuté (voir §4)                                                                                                                   |

**Tailles actuelles** (point de départ de cette feuille de route) :

- `components/v2/EditModalV2.vue` : ~1384 lignes (script ~636, template ~327, style ~419)
- `components/v2/EditPreviewPane.vue` : **847 lignes** (script 444, template 144, style ~255)

Objectifs audit : `EditModalV2.vue` < 900, `EditPreviewPane.vue` < 500–700. Les deux
restent au-dessus à cause des gros blocs `<style scoped>` (qui ne s'extraient pas
idiomatiquement) — viser plutôt « logique métier hors DOM + surfaces template
isolées » que le nombre de lignes brut.

---

## 1. Cible principale — `EditPreviewPane.vue` (847 lignes)

Responsabilités encore dans le fichier, par bloc :

| Bloc                                                                                                                      | Lignes (~) | Nature         | Couplage                                |
| ------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------- | --------------------------------------- |
| État de vue (`viewMode`, `hasSource`, `canShowOriginal`, `canCompareOriginal`, `setMode`, `displayedSvg`, `plotLayerSvg`) | 90–125     | logique pure   | faible                                  |
| Géométrie feuille (`paneEl`, `ResizeObserver`, `paneWidth/Height`, `sheetStyle`)                                          | 146–183    | layout         | `previewRoot` indirect via stroke-floor |
| Taille artwork (`artworkFraction`, `artworkStyle`)                                                                        | 185–224    | calcul pur     | consommé par `useEditorPreviewSplit`    |
| Wiring split (appel composable)                                                                                           | 226–236    | déjà extrait   | dépend de `artworkFraction`             |
| Flux SSE (`useProgressiveStream`, `shouldStream`, `openTimer`, watch `loading`)                                           | 255–315    | cycle de vie   | timers + unmount                        |
| Overlay opacité par calque (`applyOpacityOverlay`, `previewRoot`, watches)                                                | 317–383    | **walk DOM**   | **`previewRoot`**                       |
| Stroke-floor d'affichage (`applyStrokeFloor`, `strokeFloorTimer`, watch)                                                  | 385–419    | **walk DOM**   | **`previewRoot`**, `zoom`, taille pane  |
| Computeds stream/estimation (`streamLabel/Percent/Active`, `displayPercent`, `estimatedProgress`)                         | 421–443    | logique pure   | —                                       |
| Template surface (pane → stage → sheet/artwork/split, fallback viewport)                                                  | 446–589    | template + CSS | **`previewRoot`**                       |

### Le point dur : `previewRoot`

`previewRoot` est un `ref` **partagé** par deux branches du template (le `artwork-box`
en mode feuille **et** le `preview-svg` en mode sans feuille). `applyOpacityOverlay` et
`applyStrokeFloor` font un `querySelector('svg')` à partir de ce ref. Toute extraction
de la surface de rendu doit **soit** garder `previewRoot` dans `EditPreviewPane` et ne
descendre que le markup, **soit** remonter le ref depuis l'enfant (`defineExpose` ou un
template-ref passé en prop). C'est la principale source de régression possible.

### Plan d'extraction proposé (ordre = risque croissant)

1. **`useEditorPreviewStream(props.loading, props.streamFileId, props.estimateMs)`**
   _(risque faible)_ — déplace tout le cycle SSE + `streamLabel/Percent/Active` +
   `displayPercent` + `estimatedProgress`. Auto-contenu, testable (faux timers).
   Sortie : ~80 lignes de script. **À faire en premier.**

2. **`useEditorPreviewSheetGeometry(() => props.sheet, () => props.artwork*Mm)`**
   _(risque faible)_ — regroupe `paneEl`, `ResizeObserver`, `sheetStyle`,
   `artworkFraction` et `artworkStyle` (pure géométrie, testable en injectant
   `paneWidth/Height`). Attention : `artworkFraction` doit rester disponible **avant**
   l'appel à `useEditorPreviewSplit`. Sortie : ~70 lignes.

3. **`useEditorPreviewSvgEffects({ previewRoot, viewMode, plotSvg, originalSvg, zoom, paneWidth, paneHeight, artworkStyle })`**
   _(risque moyen)_ — `applyOpacityOverlay` + `applyStrokeFloor` + leurs watches +
   `strokeFloorTimer`. `previewRoot` **reste déclaré dans le pane** et est passé au
   composable. Difficile à tester sous happy-dom (pas de layout réel ; `getClientRects`
   renvoie une box factice) → couvrir la logique de map d'opacité en isolant le walk,
   et laisser le stroke-floor en vérification manuelle/navigateur.

4. **`PreviewSheet.vue` + `PreviewViewport.vue` + `PreviewCompareSlider.vue`**
   _(risque élevé — à faire en dernier, avec vérif navigateur)_ :
   - `PreviewSheet.vue` : `sheet-outline` + `sheet-caption` + `artwork-box` + les deux
     `SafeSvgHtml` (plot/source) + `<img>` source + le `split-handle`. CSS scoped
     associée (`.sheet-outline`, `.artwork-*`, `.split-handle*`).
   - `PreviewViewport.vue` : le fallback sans feuille (`.preview-viewport`,
     `.preview-svg`).
   - `PreviewCompareSlider.vue` (optionnel) : isoler la poignée si `PreviewSheet`
     devient trop gros.
   - **Bloquant technique** : forwarder `previewRoot` (le walk DOM doit cibler le
     bon `<svg>`). Décider : remonter via `defineExpose({ rootEl })` lu par le parent,
     ou déplacer aussi `useEditorPreviewSvgEffects` dans `PreviewSheet`/`PreviewViewport`.
   - Le positionnement absolu des contrôles (`PreviewToolbar`, overlay) reste relatif à
     `.preview` du parent — vérifier qu'il ne casse pas quand l'artwork passe enfant.

**Gain attendu** : étapes 1–3 retirent ~230 lignes de script → `EditPreviewPane` ≈ 600
lignes, sous la cible haute sans toucher au template risqué. L'étape 4 descend encore
mais demande une validation visuelle réelle.

---

## 2. Extractions secondaires — `EditModalV2.vue` (script ~636)

Plus faible valeur (le script restant est surtout de l'orchestration légitime :
les 4 watchers de preview, `onMounted`, le wiring des composables). Candidats si on
veut passer sous 900 lignes total :

| Extraction                    | Contenu                                                                                                     | Valeur                                        | Risque |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ------ |
| `useEditorCustomStyles`       | `customStyles`, `customStylesActive`, `customPasses`, `seedCustomStylesFromCommitted`, `canCustomizeStyles` | moyenne (testable)                            | faible |
| `useEditorSheetOutline`       | computed `sheetOutline`                                                                                     | faible                                        | faible |
| `useEditorLayerVisibility`    | `isLayerVisible`, `toggleLayerVisibility`                                                                   | faible                                        | faible |
| `useEditorDocumentNavigation` | `pageCount`, `currentPage`, `hasPages`, `goToPage`                                                          | très faible (wrappers fins sur `fileManager`) | faible |

Recommandation : **ne faire que `useEditorCustomStyles`** (vrai bloc métier, ~50
lignes, testable hors DOM) ; les autres sont trop fins pour justifier un fichier.

---

## 3. Tests à ajouter en parallèle des extractions

- `useEditorPreviewStream` : ouverture différée < 350 ms (pas d'ouverture), ouverture
  après le délai, fermeture sur `loading=false`, `displayPercent = max(stream, estimé)`,
  pas d'ouverture sans `streamFileId`.
- `useEditorPreviewSheetGeometry` : ancrage largeur vs hauteur, clamp d'overflow
  proportionnel, `null` quand pas de feuille / dimensions manquantes.
- `useEditorPreviewSvgEffects` : map opacité (calque masqué → 0, inconnu → 1) — isoler
  le calcul de la map du walk DOM pour le rendre testable.
- `useEditorCustomStyles` : seed depuis `layer_algorithms` committés, projection
  `PolicyPass`, no-op pour sources non-bitmap.

---

## 4. Items d'audit ouverts hors refactorisation

1. **Playwright `e2e/editor-parcours.spec.ts` — NON exécuté.** Écrit + typé + listé,
   mais l'environnement d'écriture n'a pas d'accès au navigateur Playwright
   (`cdn.playwright.dev` hors allowlist). **À valider dans un environnement avec
   navigateur + backend** (`E2E_BACKEND_RUNNING=1`, `OMNIPLOT_FAKE_HARDWARE=1`) avant
   de s'en servir comme garde-fou. Ajuster les sélecteurs si besoin.
2. **Audit accessibilité automatisé** (axe-core / Playwright-axe) sur la modale —
   recommandé par la Phase 5 de l'audit, pas encore branché.
3. **Cible de lignes** : si on tient absolument aux seuils chiffrés, ils ne tomberont
   qu'après l'étape 4 du §1 (split template) — à mettre en balance avec le risque.

---

## 5. Pièges connus / notes d'implémentation

- **happy-dom sans layout** : `getClientRects()` renvoie une box factice (≥1) et
  `checkVisibility` n'existe pas. Conséquences : (a) le filtre de visibilité du
  focus-trap est un no-op en test (volontaire) ; (b) le stroke-floor n'est pas
  vérifiable en unitaire — prévoir une vérif navigateur.
- **`watch` hors composant** : le callback flush en microtâche → `await nextTick()`
  dans les tests de composables qui dépendent d'un watch (cf. `useEditorPreviewSplit`).
- **DOMPurify + `<script>`** : dans cet environnement, un `<script>` dans un SVG fait
  tomber les frères suivants — comportement sûr, mais en tenir compte en écrivant les
  fixtures de test (utiliser `<path>`/`<rect>` propres pour vérifier le rendu).
- **CSS scoped + `:deep()`** : les surfaces qui injectent du SVG via `SafeSvgHtml`
  reposent sur `.parent :deep(svg)` ; un niveau de wrapper supplémentaire reste compatible
  (combinateur descendant), mais le vérifier à chaque extraction template.
- **`previewRoot`** : voir §1 — le ref partagé est le point de rupture n°1 du split
  template.

---

## 6. Ordre recommandé pour la prochaine session

1. `useEditorPreviewStream` (+ tests)
2. `useEditorPreviewSheetGeometry` (+ tests)
3. `useEditorPreviewSvgEffects` (+ tests de la map opacité)
4. `useEditorCustomStyles` côté modale (+ tests) — optionnel
5. Validation Playwright en environnement navigateur + audit axe
6. (Si souhaité, après vérif visuelle) split template `PreviewSheet` / `PreviewViewport`

Critères d'acceptation transverses : suite verte (actuellement 804 tests), `vue-tsc`
OK, ESLint/Prettier OK, **aucun** changement de comportement visible de la modale,
chaque composable extrait livré **avec** son test hors DOM.
