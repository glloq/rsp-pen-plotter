# Audit UI — Réactivité, vitesse perçue & feedback de chargement

_Date : 2026-06-16 · Périmètre : `frontend/` (Vue 3 + TS + Pinia, ~50 k LOC) + endpoints `backend/` associés._

Objectif : rendre l'interface réactive côté utilisateur. Deux leviers complémentaires :
1. **Vitesse réelle** — réduire le travail bloquant sur le thread principal et au démarrage.
2. **Vitesse perçue** — donner du feedback immédiat, et pour les attentes incompressibles afficher
   un **toast de progression avec temps restant estimé (ETA)**.

---

## 0. Verdict

La base est **excellente**. Le projet possède déjà des briques de feedback de très haut niveau,
mais elles ne sont câblées **que sur la preview de l'éditeur**. Partout ailleurs (génération G-code,
mise à jour système, re-render, upload « Appliquer », file d'attente, commandes machine) l'opérateur
fixe soit une modale bloquante qui n'affiche que le **temps écoulé**, soit rien du tout.

**Le travail n'est donc pas de construire l'infrastructure — elle existe — mais de la généraliser.**

### Briques réutilisables déjà en place (à NE PAS reconstruire)

| Brique | Fichier | Rôle |
|---|---|---|
| `toasts.progress()` / `update()` / actions | `stores/toasts.ts:79,85` | Toast persistant avec spinner + bouton (annuler), transformable en succès/erreur |
| `useEstimatedProgress` | `composables/useEstimatedProgress.ts` | Barre déterministe lissée à partir d'un ETA (head-start → 80 % → plafond 98 % → snap 100 %) |
| `usePreviewCostEstimator` | `composables/usePreviewCostEstimator.ts` | EMA de latence par (algorithme × qualité), persistée en `localStorage` |
| `useProgressiveStream` + `/preview/stream` SSE | `composables/useProgressiveStream.ts` ; `backend/.../preview_stream.py` | **Vraie** progression couche par couche (`percent`, `elapsed_ms`, label) |
| `useEditorPreviewStream` | `composables/useEditorPreviewStream.ts` | Fusionne SSE réel + ETA estimée en un `displayPercent` monotone (ne recule jamais) |
| `usePreviewScheduler` | `composables/usePreviewScheduler.ts` | Debounce + `AbortController` + garde de péremption (revision) |
| `perf.summary(kpi)` | `stores/perf.ts:62` | p50/p95/dernier échantillon par KPI (`time_to_first_preview`, `preview_refresh`…) |
| `DetailPicker` cost chips | `components/edit/shared/DetailPicker.vue:50-74` | Pattern « pastille ~N s » avec teinte ambre pour les paliers lents |
| `PreflightReport.estimated_seconds` | `api/client.ts:421` | ETA du tracé physique, déjà produit par le backend |

**Implication clé** : la donnée pour estimer une durée existe quasiment partout (EMA de coût,
`estimated_seconds` du preflight, nombre de chemins, pixels × couleurs × complexité). Il « suffit »
de la brancher sur les toasts/barres.

---

## AXE A — Feedback de chargement & toasts à ETA _(priorité utilisateur)_

Légende : **(a)** aucun feedback · **(b)** spinner mais pas d'ETA alors que la donnée existe ·
**(c)** modale bloquante là où un toast non bloquant conviendrait mieux · **(d)** ré-déclenchable
en vol (double-clic) · **(e)** erreur silencieuse.

### P0 — l'utilisateur attend sans feedback visible

| # | Endroit | Opération | Problème | Correctif |
|---|---|---|---|---|
| A1 | `App.vue:162,164` → `closeEditModal()` `:170` | Sauvegarde mode assisté → `applyPassesToAllLayers` / `applyAlgorithmToAllLayers` | (a)(e) Ces fns font `patchSelected` + `scheduleRerender(50)` et **rendent avant** que `/rerender` démarre : la modale se ferme, le `/rerender` (plusieurs s, tous les calques) tourne **invisible**, le SVG du plan mute plus tard. En cas d'échec, seul un `toasts.warning` perdu dans `triggerRerender` (`job.ts:914`). | Ouvrir un `toasts.progress()` avant de fermer, attendre la vraie fin (`trackRerender`/`rerenderInFlight`, `job.ts:549`), `update()` succès/erreur, ETA depuis le cost estimator. |
| A2 | `components/edit/tabs/StyleTab.vue:155` (mono), `:173` (multicolore) | Master-style → `applyLayerAlgorithm` → `scheduleRerender(250)` → `triggerRerender` | (a)(b)(c)(e) Seul edit expert qui passe par `/rerender` au lieu de `/preview` : `triggerRerender` (`job.ts:842`) ne pose **aucun flag loading**, donc l'overlay ne s'affiche jamais — la preview blanchit jusqu'au retour réseau. Pas de try/catch. | Piloter un flag busy observé par l'overlay (ou `toasts.progress` + ETA + annuler), envelopper en try/catch + toast d'erreur. |
| A3 | `stores/macros.ts:48` → `MacroPanel.vue:81` | `run()` → `runMacro` (commandes **machine**) | (a)(d)(e) Aucun flag, aucun toast ; erreur seulement en texte inline ; bouton gardé sur l'état connexion, **pas** sur la requête en vol → re-cliquable. | `toasts.progress("exécution…")` → succès/erreur + garde anti-renvoi. |
| A4 | `components/JogControls.vue:77` (home), `:122` (goto), `:130` (coins) | `plotter.home/goto` | (a)(b)(d) Contrairement à `connect`/`run`, **aucun** `progressMessage` passé à `withErrors` (`plotter.ts:138,140`) : un déplacement machine de plusieurs s n'affiche rien, boutons non désactivés. | Passer un `progressMessage` (le câblage existe déjà) + ETA (distance ÷ `travel_speed`) ; flag « déplacement en cours » pour désactiver. |
| A5 | `components/JogControls.vue:60-101` | 8 flèches de jog → `plotter.jog` | (a)(d) Rien en vol, flèches non désactivées → file de déplacements si on martèle. | Toast de progression + désactivation pendant le mouvement. |

### P1 — feedback présent mais sans ETA sur une opération longue _(cœur de la demande)_

| # | Endroit | Opération | Problème | Correctif |
|---|---|---|---|---|
| A6 | `components/GenerateProgressModal.vue:135` ; état `ui.ts:28` ; déclenché `SheetPreview.vue:319` | Pipeline optimize → preflight → generate (**minutes** sur Pi) | (b)(c) Modale **bloquante** plein écran, checklist 3 étapes + spinner indéterminé + **compteur de temps écoulé**, **aucune barre, aucun ETA**. `GcodeJobState` a `startedAt` mais pas `etaSeconds`. | Ajouter `etaSeconds` à `GcodeJobState`, barre déterministe + temps restant (seed = `preflight.estimated_seconds` + nb de chemins). **Idéalement remplacer la modale bloquante par un toast `progress`** (le travail survit en arrière-plan, auto-dismiss déjà géré `job.ts:1791`). |
| A7 | `components/UpdateProgressModal.vue:80` ; `SystemPanel.vue:63` | `systemUpdate` (plafond backend **10 min**) | (b)(c) Modale bloquante, spinner **indéterminé** + « ⚠ ne pas fermer » + temps écoulé. À 10 min, impossible de distinguer « à mi-chemin » de « planté ». Non annulable. | Barre `useEstimatedProgress` seedée d'une durée typique (~3-5 min) → « ~N min restantes ». Ou toast non bloquant pour continuer à lire les notes de version. |
| A8 | `composables/useFileManager.ts:309` | `uploadSelected` → `store.upload` (re-conversion « Appliquer ») | (b)(a)(e) Le bouton confirm montre `applying` (désactivé) mais **pas de barre/ETA**, et le progrès octets/conversion est **jeté** — `uploadSelected` ne passe pas le `onProgress` que `store.upload` supporte (`client.ts:927`). Appelants non-confirm : aucun flag + rejet non géré. | Brancher `onProgress` dans un `toasts.progress` (octets % → phase « conversion » → ETA estimateur). |
| A9 | `components/MagazineLoadModal.vue:87` | confirm → `applyPlan()` puis `job.generate()` | (b)(c) Re-entrée gardée, label « Préparation… » mais **pas de spinner/barre/ETA** sur un generate de plusieurs s. | `toasts.progress` + ETA du plan ; rendre non bloquant. |
| A10 | `components/edit/BlockMapCard.vue:39` | `analyzeDocument` (PDF, timeout 30 s) | (a)(b) Minuscule label texte `{{ blockMap.loading }}` (`:79`), auto-déclenché à chaque sélection PDF. Erreur inline, **pas** de toast. | Au minimum un spinner indéterminé (pas de donnée d'estimation pour cet endpoint) ; toast d'erreur. |
| A11 | `composables/useEditorConfirmation.ts:81,106` | `applyExpertDraft` / `reconvertForPlan` → `/upload` re-convert | (b) Flag `applying` → bouton désactivé, mais **pas de barre/ETA** sur un re-upload+rerender de plusieurs s à minutes. | Compléter le bouton désactivé par `toasts.progress` + ETA estimateur. |
| A12 | `usePreviewScheduler.ts:114` ; `useEditorExpertPreview.ts:85` | ETA typographie | Le branchement texte force `elapsed_ms: 0` et `previewEstimateMs` est clé sur l'algo **bitmap** → **ETA typo absent/erroné** (la barre s'affiche quand même via le scheduler partagé). | Faire remonter+enregistrer un vrai `elapsed_ms` depuis `/preview-text` pour alimenter une estimation typo. |

### P2 — erreurs silencieuses, double-clic, écran blanc pendant le chargement

- **Actions de file d'attente** — cause racine unique : le store `queue` ne pose que `error.value`,
  jamais `toasts.*`, et n'expose aucun flag en vol :
  - `stores/queue.ts:102` `enqueue` · `:111` `act` (pause/resume/cancel) · `:120` `remove` — **(a)(d)(e)**.
  - Câblé direct aux clics : `PrintQueuePanel.vue:182-203`, `components/v2/RunActionsPanel.vue:61-78`,
    `components/v2/WorkshopMode.vue:66-75`, `AppHeader.vue:50-96`. Boutons désactivés par `run.state`
    **seulement** (mis à jour après l'aller-retour) → re-cliquables en vol. WorkshopMode = pire endroit
    pour perdre une erreur (opérateur devant la machine).
  - **Correctif unique** : flag pending par action dans le store (désactive pendant action+reload) +
    router les échecs `queue.*` vers `toasts.error`.
- A13 `FilesPane.vue:229` `editFile` → `ensureDetail` (`getLibraryFile` sur cache-miss) : pas de spinner,
  Edit/dblclick non désactivés, échec → `library.error` seulement, no-op silencieux. **(a)(d)(e)**.
- A14 `library.ts:420` `ensureDetail` / `job.ts:1507,1513` `changePage`→`downloadOriginalFile` : échecs
  avalés (`catch { return }`). **(e)**.
- A15 `JobHistory.vue:14` `getJobs` `catch { jobs=[] }` : vide la liste sur échec, indistinct d'un
  historique vide ; pas de toast. **(e)**.
- A16 `macros.ts:22` `load()`, `job.ts:1135,1142` `loadProfiles`/`loadPresets` : awaités **sans** try/catch
  → rejet non géré silencieux. **(e)**.
- A17 `ProfileEditor.vue:564` `downloadYaml` → `exportProfileYaml` : pas de try/catch, bouton non désactivé. **(d)(e)**.
- A18 Boutons sans `:disabled` en vol (double-fire) : `PlotterSettingsModal.vue:262,127`,
  `AvailableColorsPanel.vue:119/129` (flèches = **deux** `rename` séquentiels, risque d'entrelacement),
  `:101,300,136`, `CanvasView.vue:96`, `PrintQueuePanel.vue:132`, `PlotterControl.vue:117,136`.
  Surtout ops rapides/idempotentes → P2/P3.
- A19 `FilesPane.vue:27` `library.refresh()` initial : `library.loading` existe mais n'est pas lié →
  l'état vide « aucun fichier » peut flasher avant l'arrivée des fichiers. **(a, léger)** → squelette.
- A20 `EditorExpertPanel.vue:39-43` chunks d'onglets async sans `loadingComponent` → corps blanc au
  changement d'onglet à froid → petit fallback spinner / `<Suspense>`.

### P3 — détails

- `MacroPanel.vue:44,56`, `MagazineEditor.vue:108` : erreurs en texte inline au lieu du pattern toast.
- `AuditPanel.vue:13` `catch { entries=[] }` (vide sur blip de poll 5 s) ; `TextTab.vue:28` `getFonts`
  catch vide (liste de polices vide silencieuse).
- `DetailPicker` : l'ETA de l'overlay a une frame de retard sur la sélection (la pastille donne déjà
  le bon chiffre avant clic — `useEditorExpertPreview.ts:85` estime le `max_dimension_px` courant).

### Où un toast-à-ETA est le bon correctif vs. juste du feedback

- **Toast + ETA** (lent par nature, donnée d'estimation dispo) : A6 generate, A7 update système,
  A1 rerender assisté, A2 rerender master-style, A8/A11 re-convert « Appliquer », A9 MagazineLoad, A4 home/goto.
- **Juste feedback/garde, pas d'ETA** : A3 macro, A5 jog, A10 analyze (pas de donnée), actions de file,
  boutons export/connect/reorder.
- **Déjà debouncé/géré — ne RIEN ajouter** : tous les edits de draft bitmap (Image/SVG/Detail/Segmentation),
  la preview live, la modale batch d'`uploads` (implémentations modèles).

---

## AXE B — Réactivité & rendu (jank sur le thread principal)

La défense est déjà bonne (RAF sur pan/resize, `shallowRef` sur le résultat sim, caches LRU autour de
DOMPurify/DOMParser). Points résiduels :

### P0 — gel sur interaction courante

- **B1 `components/SimCanvas.vue:115-170`** — redraw canvas **intégral** O(segments+events) à **chaque
  frame** de lecture (watch `simTime`, ~60×/s). Les tracés ont « des dizaines de milliers de segments » ;
  `project()` (`:72-83`) recalcule l'échelle de fit **par point**. → Rendu du préfixe déjà tracé une fois
  sur un canvas offscreen / `Path2D`, ne peindre que les nouveaux segments (compositing incrémental) ;
  sortir l'échelle de `project()` de la boucle ; batcher en `Path2D` par style.
- **B2 `lib/gcode.ts:108` via `useGcodePlayback.ts:130`** — `parseGcode` **synchrone** sur toute la
  chaîne (split `\n`, tessellation d'arcs), déclenché au montage du Simulateur et à chaque regénération.
  Un gros tracé gèle l'UI. → **Web Worker** (le résultat est déjà `shallowRef`, remplacé en bloc =
  frontière de transfert propre) ou chunking via `requestIdleCallback` + indicateur.
- **B3 `components/FilesPane.vue:41,68-76` + `stores/library.ts:251-273`** — grille bibliothèque **non
  virtualisée** : `ensureDetail(id)` fetch **chaque** fichier au montage et à chaque recherche/tri/dossier,
  + `DOMPurify.sanitize` du SVG complet **par ligne visible**. `filteredSorted` alloue un `Intl.Collator`
  **dans le corps du computed** (`:259`) et re-trie O(n log n) à chaque frappe. → Virtualiser (windowing /
  `IntersectionObserver`), hisser le `Collator` au scope module, limiter le prefetch au slice visible.

### P1 — lag perceptible

- **B4 `useBitmapDraft.ts:1404-1423`** — `isDirty` re-sérialise tout le draft via `JSON.stringify`
  (`_bitmap` + `_curves` + `_multicolor`) à **chaque** mutation (donc à chaque tick de slider, le
  close-guard gardant le computed « chaud »). → Flag dirty basculé par les setters, remis à zéro au commit.
- **B5 `useStylePropagation.ts:85-114` → `job.ts:642-658` → `library.ts:194-219`** — propagation d'un
  knob master-style = boucle par bande ; **chaque** itération fait `patchSelected({ layer_algorithms:{…spread} })`
  **et** `autoSyncFileSettings()` (clone du store `fileSettings`) — par calque, cadence 120 ms.
  O(N_calques × taille settings). → Construire le patch complet **une fois**, `patchSelected` **une seule
  fois**, `autoSyncFileSettings()` une fois en fin de boucle (variante bulk de `applyLayerAlgorithm`).
- **B6 `job.ts:167`** — `placements` est un `ref<Placement[]>` **profondément réactif** dont chaque item
  porte une grosse chaîne `svg` ; chaque mutation `patchPlacement` (`:186`) reconstruit le tableau (par
  frame en drag). Le tableau n'est jamais muté champ par champ → la réactivité profonde est pur surcoût.
  → `shallowRef` pour `placements` (le pattern « remplacement en bloc » colle déjà), ou `markRaw` le
  champ `svg`.
- **B7 `components/GcodePreview.vue:43`** — tout le gcode dans un seul `<pre>{{ gcode }}</pre>`, non
  virtualisé ; `lineCount` (`:11`) re-`split('\n')` réactivement. → Virtualiser / plafonner + « tout
  afficher / télécharger » ; dériver `lineCount` du parse.
- **B8 `components/AuditPanel.vue:23-45`** — log complet re-fetché toutes les 5 s + re-rendu non virtualisé,
  poll même non visible. → Virtualiser + delta/curseur backend + pause sur `visibilitychange`.

### P2

- **B9 `workspaces.ts:125-139`** — watcher `{ deep: true }` qui persiste en `localStorage` **sans**
  debounce (`JSON.stringify` + `setItem` à chaque mutation). Le même auteur a déjà debouncé ce pattern
  dans `library.ts:172-179`. → Réutiliser le debounce 300 ms + flush `beforeunload`.
- **B10 `useBitmapDraft.ts:1316,1323`** — `JSON.parse(JSON.stringify(...))` (double sérialisation) dans
  `buildBitmapOptions` (debouncé 500 ms donc pas du jank) → `structuredClone` ou clone de la seule slice.
- **B11** Watchers `{ deep: true }` sur objets entiers : `MasterStyleKnobs.vue:87`, `AlgoParamsForm.vue:72`,
  `LayoutSection.vue:35` (petits objets, coût faible) → cibler les clés.
- **B12 `Simulator.vue:196-215`** — `manualPenChange` boucle chaque calque de chaque placement avec
  `selectPlacement` + `updateLayer` (O(placements × calques)). Peu fréquent → batcher en un `patchSelected`.

### Non-problèmes vérifiés (laisser tel quel)

Modales lazy + gardées `v-if` (`App.vue:29-74`), pipeline preview éditeur (collapse de bursts, 1 debounce,
1 AbortController), `useSheetGeometry` (caches DOMPurify/DOMParser/crop par identité + éviction, fallback
raster `AUTO_SVG_PRIMITIVE_LIMIT=5000`), pan/resize RAF-coalescés, `uploads` garde `File`/`AbortController`
hors du graphe réactif.

---

## AXE C — Démarrage & bundle (time-to-interactive)

Déjà très optimisé (chunks lazy, prefetch idle, `manualChunks`). Résiduel :

- **C1 `App.vue:348-350`** — `await getHealth()` **sérialise** avant le `Promise.all([loadProfiles, loadPresets])` :
  premier rendu de données = `RTT(health) + RTT(profils)` au lieu du max. `getHealth` ne sert qu'au toast
  « API injoignable ». → Fondre dans le même `Promise.all([getHealth(), loadProfiles(), loadPresets()])`.
- **C2 `i18n.ts:2-12`** — les **deux** locales (`en` ~87 Ko + `fr` ~97 Ko, 1861 clés) bundlées et `JSON.parse`-ées
  au boot alors qu'une seule sert. → Charger la langue du navigateur en synchrone, importer l'autre en
  dynamique au changement (`setLocaleMessage`). ~90 Ko de moins au boot.
- **C3 `App.vue:369,374`** — `algorithms.refresh()` + `availableColors.refresh()` fetchés au boot mais
  consommés **uniquement** par la modale d'édition (fermée). → Différer à l'ouverture de la modale ou en
  idle (libère des sockets pour `loadProfiles`/`listQueue`/`library.refresh`).
- **C4 `stores/job.ts:1833` → `infrastructure/storage/sceneStorage.ts:83`** — hydratation de scène
  (placements **avec SVG complets**) `JSON.parse`-ée **synchrone** dans le constructeur du store, **avant**
  le premier paint. Pour un opérateur revenant avec plusieurs fichiers placés = parse de plusieurs centaines
  de Ko bloquant. → Hydrater après le premier paint, ou exclure les `svg` du blob persisté (ré-hydratation lazy).
- **C5 `lib/sanitizeSvg.ts:1` + `useSheetGeometry.ts:22` + `FilesPane.vue:2`** — `dompurify` (~20 Ko gz)
  dépendance **synchrone** du bundle principal (le chunk séparé n'est pas différé). → `import('dompurify')`
  dynamique à la première sanitization.
- **C6 `components/CanvasView.vue:11` → `Simulator.vue:26-27`** — `Simulator`/`SimCanvas`/`SimControls` +
  moteur de lecture RAF bundlés eagerly via `CanvasView` (statique dans `App.vue`), alors que l'onglet sim
  ne s'affiche qu'après génération. → `defineAsyncComponent` + prefetch idle.
- **C7 `App.vue:360`** — `systemCheckUpdate` (git fetch potentiellement lent) déclenché immédiatement →
  idle-schedule.

---

## AXE D — Polling & ressources

- **D1 `stores/queue.ts:127-152`** — poll adaptatif (3 s actif / 30 s idle) + backoff + single-flight =
  **bon**, mais **pas** de prise en compte de `visibilitychange` : un onglet en arrière-plan avec un run
  actif continue à taper `/queue` toutes les 3 s. → Forcer la cadence lente (ou pause) quand `document.hidden`,
  `load()` immédiat au retour.
- **D2 `AuditPanel.vue`** — voir B8 (poll 5 s même non visible). Atténué : composant dans le `SettingsDrawer`
  lazy, gardé `v-if`. → Pause sur visibilité.
- **OK** : reconnexion WebSocket plotter (timer seulement si connecté, teardown propre), timers de toast
  (Map + clear), tickers des modales de progression (gardés par watcher de phase).

---

## Opportunité transversale — généraliser la VRAIE progression (SSE)

Le backend expose déjà `/preview/stream` (SSE, 1 event `progress` par calque rendu avec `percent` +
`elapsed_ms` + label), et `render_from_segmentation` **accepte déjà** un `progress_callback` que
`/rerender` **ne passe pas**. Conséquences exploitables :

1. **`/rerender`** (action lente la plus cliquée de l'éditeur) peut obtenir une **vraie** progression
   par calque avec un effort backend modeste (même pont SSE que `/preview/stream`).
2. **`/upload`** rejoue le **même** pipeline `convert_file` que `/preview/stream` : le frontend pourrait
   router l'upload vers le SSE pour une vraie barre au lieu d'une estimation.

**Limites à connaître** (à documenter) :
- Le tick par calque ne sort que dans la branche de rendu **séquentielle** ; la branche **parallèle**
  (`n_workers>1`) n'émet qu'**un** callback final → progression inutile. `convert_file` est en `n_workers=1`
  par défaut donc OK aujourd'hui.
- Le **k-means** (`n_init=10` à l'upload) tourne **avant** le premier tick de calque → la barre stagne au
  « start » pendant la sous-étape la plus longue. Pondérer l'estimation en conséquence (segmentation ≈
  l'essentiel pour `num_colors`/px élevés ; rendu pour les algos TSP/2-opt).
- TSP/2-opt est **borné en temps** (`time_budget_s=1.5`/calque) → traiter comme une constante par calque,
  pas comme un coût scalant avec les points.

### Drivers d'ETA par opération (récapitulatif backend)

| Opération | ETA estimable depuis | Vraie progression dispo ? |
|---|---|---|
| `/upload`, `/files` | pixels (`max_dim²`) × `num_colors` × `complexity` (+ EMA `/preview`) | Oui via SSE (re-route) |
| `/rerender` | nb calques × complexité par calque (+ flag cache froid) | Oui (callback existe, à brancher) |
| `/optimize` | nb chemins × nb calques | Non (boucle par calque, à instrumenter) |
| `/generate` | nb chemins ≈ `line_count` (révélé par `/preflight`) | Non |
| `/preflight` | nb chemins | Non — **produit** `estimated_seconds` du tracé |
| `/document/analyze` | nb pages PDF | Non |
| `/files/{id}/preview-image` (DOCX/EPS/HTML…) | **imprévisible** (cold-start LibreOffice/Ghostscript) | Non — toast indéterminé |
| `/system/update` | **imprévisible** (npm/build/réseau) | Non — toast indéterminé |
| Tracé physique | `preflight.estimated_seconds` | Oui — WebSocket `acked/total` |

---

## Plan d'action proposé (par phases, du plus rentable au moins)

**Phase 1 — Socle ETA toasts (rentabilité immédiate, risque faible)**
1. Extraire un helper `useProgressToast({ estimateMs, label, onCancel })` qui combine `toasts.progress`
   + `useEstimatedProgress` + format « ~N s/min restantes » (clé i18n `toast.remaining` à créer — absente
   aujourd'hui ; seules `elapsed`/`estimatedTime` existent).
2. A6 Generate : ETA dans `GcodeJobState` + barre déterministe (seed `preflight.estimated_seconds`).
3. A7 Update système : barre seedée d'une durée typique.
4. A1 + A2 : rerender assisté & master-style derrière un toast de progression (fin réelle attendue).

**Phase 2 — Combler les trous de feedback (P0/P2)**
5. Store `queue` : flag pending par action + `toasts.error` (corrige Panel/RunActions/Workshop/Header d'un coup).
6. A3 macro, A4/A5 jog/home/goto : toast + garde anti-renvoi (+ ETA distance pour home/goto).
7. A8/A11 « Appliquer » : brancher `onProgress` + ETA.
8. Erreurs avalées A14-A17 : surfacer via toast.

**Phase 3 — Vitesse réelle (jank)**
9. B2 parse gcode en Web Worker · B1 redraw incrémental SimCanvas.
10. B3 virtualisation grille bibliothèque (+ `Collator` au scope module).
11. B4 `isDirty` flag · B5 batch propagation · B6 `shallowRef` placements.

**Phase 4 — Démarrage/bundle**
12. C1 `Promise.all` health · C2 locale lazy · C3 différer fetches modale · C4 hydratation scène non bloquante.

**Phase 5 — Vraie progression SSE**
13. Brancher `progress_callback` sur `/rerender` ; évaluer le re-route SSE de `/upload`.
14. D1 polling visibility-aware.

---

## Estimation d'impact

- **Vitesse perçue** : Phase 1 (toasts ETA sur generate/update/rerender) + Phase 2 (trous de feedback) =
  le gain ressenti le plus fort pour l'opérateur, effort modéré, infra déjà là.
- **Vitesse réelle** : B2 (worker gcode) + B1 (SimCanvas) suppriment les deux gels les plus visibles ;
  B3 (virtualisation) protège les grandes bibliothèques.
- **Démarrage** : C2 (locale) + C1 (health) + C4 (scène) = l'essentiel du time-to-interactive,
  surtout sur matériel Pi.

---

## Statut d'implémentation (mise à jour 2026-06-16)

### ✅ Fait & vérifié (suite 874 tests + typecheck + build verts)

**Phase 1 — Socle toasts à ETA**
- `lib/progressEstimate.ts` (courbe + temps restant + format), `lib/progressToast.ts`
  (`beginProgressToast` : toast progress + barre + ETA + affichage différé + annulation),
  `lib/durationEstimator.ts` (EMA de durée persistée). Barre déterministe ajoutée aux toasts.
- A1+A2 rerender : toast slow-only (>400 ms) + ETA (historique `preview_refresh`) + annulation.
- A6 Generate & A7 mise à jour système : barre déterministe + temps restant dans la modale.

**Phase 2 — Trous de feedback**
- macros (A3), jog/home/goto (A4/A5) : toasts + gardes anti-renvoi.
- store queue : `toasts.error` + `isBusy`/`enqueuing` (corrige Panel/RunActions/Workshop/Header).
- JobHistory (A14) : état d'erreur distinct. A8/A11 déjà couverts par `store.upload`.

**Phase 3 — Jank (sous-ensemble contenu)**
- B1 SimCanvas : hoist de l'échelle hors de `project()`. B6 : `shallowRef` placements.
- B7 GcodePreview : `<pre>` plafonné. B5 : propagation master-style batchée (`applyLayerRecipes`).
- B8 AuditPanel : poll gated par visibilité. B3 (partiel) : `Intl.Collator` hissé.

**Phase 4 — Démarrage** : C1 (health parallèle), C2 (locale lazy → chunks séparés confirmés au build),
C3/C7 (fetches advisory en idle).

**Phase 5 — Polling** : D1 (queue visibility-aware).

**Phase 3 (suite) — B2 : parse G-code en Web Worker** : `lib/gcodeParser.worker.ts` +
`parseGcodeMaybeAsync` (worker en navigateur, fallback synchrone hors navigateur). `useGcodePlayback`
gère valeur sync OU promesse async, avec garde de péremption (seq) ; build émet un chunk worker séparé.
Supprime le gel à l'ouverture du simulateur / à la régénération.

**Phase 5 (backend+frontend) — vraie progression SSE sur `/rerender`** : nouvel endpoint
`POST /rerender/stream` (SSE, 1 tick `progress` par couche + `done` portant le SVG), réutilisant le
schéma `PreviewProgressEvent` et le pont thread+queue de `preview_stream`. Côté frontend, `rerenderJob`
gagne un `onProgress` qui consomme le flux (`fetch` + `ReadableStream`) et retombe sur le POST simple si
indisponible ; le toast affiche la **vraie** barre par couche + libellé au lieu de l'estimation.

**Phase 3 (suite) — B3 : lazy-load des miniatures à la visibilité** : composable `useInViewport`
(`IntersectionObserver`, fallback eager), `FileListRow` émet `visible` à l'entrée dans la vue, et
`FilesPane` ne fetch/sanitize le détail d'une ligne qu'à ce moment-là (fin du burst N fetch + N
DOMPurify à l'ouverture / au filtrage). Toutes les lignes restent dans le DOM (scroll naturel).

### ⏸️ Différé sciemment (raison)

- **B4 — `isDirty` flag** : le remplacer changerait la sémantique value-based (revert = propre) ;
  gain marginal (stringify de petits objets) pour un risque de test.
- **B9 — debounce persistance workspaces** : le test attend une persistance synchrone, et l'usage
  est basse fréquence (pas de rafale comme les sliders) — gain négligeable.
- **C4 — hydratation de scène non bloquante** : déplacer/alléger l'hydratation `JSON.parse` du
  constructeur du store touche un chemin sensible (retour utilisateur avec scène peuplée) ; à faire
  avec un test dédié.
- **Phase 5 (backend) — vraie progression SSE sur `/rerender`** : feature transverse backend+frontend
  (brancher `progress_callback` + pont SSE) ; le toast d'ETA estimé de la Phase 1 couvre déjà le besoin
  immédiat côté UX.
