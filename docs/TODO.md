# TODO — phase v0.2 complète, suivi v2.0

> v0.2 est **fonctionnellement complète** au 2026-05-28. Toutes
> les TODO bloquant l'expérience opérateur sont fermées. Les
> items restants sont des chantiers d'envergure (refactor
> backend, infra multi-machine, tests Playwright en CI, audit
> perf matériel) explicitement reportés à v2.0 et annotés comme
> tels ci-dessous.

## État final v0.2 (2026-05-28)

**Fermé :**
- 1.1 Modal V2 = éditeur par défaut (flag ON par défaut + cut-over confirm wiré)
- 1.2 Queue polling propagé app-wide
- 1.3 partiel : `machine_telemetry` + `compare` montés dans le rail (puis rail retiré en feedback opérateur 2026-05-28)
- 1.4 CapabilityWizard → vraie sauvegarde profil
- 2.4 Recovery `skip_layer` vraiment fonctionnel (backend + UI badge + toast critique)
- 3.3 Toasts critiques sur 4 conditions bloquantes (apiUnreachable / saveProfile / skip_layer / deviceLost)
- 5.1 Roadmap consolidée
- 5.2 `getting_started.md` documente surfaces v0.2 + flags + raccourcis
- 6.1 + 6.2 Lint vert (0 erreurs, 57 warnings dette v0.1 surveillée)

**Reporté v2.0** (gros chantiers / dépendance matériel ou infra) :
- 1.5 + 3.1 Compare candidats réels + 3 overlays manquants → backend variant rerender + extension `/preflight` + rendu géométrique heatmap/density/curvature
- 2.1 IR consommé en aval → refactor `optimize_svg` / `generate_gcode`
- 2.2 ToolChangeOrchestrator source de vérité → alignement templates + suppression regex legacy
- 2.3 Streamer inline tool-change commands → refacto hardware
- 2.5 IPC inter-rôles → choix infra multi-machine
- 3.2 Perf audit Pi → matériel hors container
- 3.4 Playwright étoffé + CI E2E → cache GHA Chromium
- 4 Checklist runtime ~50 items → uvicorn + vite + navigateur en pilotage manuel

---

## Catégorie 1 — Wiring incomplet documenté comme intentionnel

### 1.1 — ~~Cut-over `EditModal` v1 → v2~~ (Block A) — fermé

**Fix** : nouveau `applyAlgorithmToAllLayers(algorithm, options)` dans
`useJobStore` (1 patch + 1 rerender debounced 50 ms), appelé par
`App.onEditV2Confirm(decision)` avec `decision.default_algorithm` +
`decision.default_options`. Modal V2 monté en vrai overlay
(`.modal-v2__backdrop` fixed inset-0 z-40), context bar montrant
le nom du fichier + thumbnail SVG du placement actif + compteur de
couches. `initialSourceKind` dérivé automatiquement du MIME du
placement.

**Cut-over** : flag `modalV2` désormais **`true` par défaut** via
`FLAG_DEFAULTS` dans `useUiModeStore.isFlagEnabled`. Tout nouveau
visiteur (localStorage vierge) ouvre Modal V2. L'opérateur peut
revenir à v1 via le bouton header `Modal V2 (beta)` (toggle off) ou
via le bouton « Ouvrir l'éditeur complet » dans le header du modal
V2 — le flag est alors persisté à `false` jusqu'à nouvelle bascule.

**Suppression de v1** : reportée explicitement à v2.0. Tant que les
contrôles per-layer / per-pass riches du modal v1 ne sont pas
ré-implémentés dans v2, la coexistence est nécessaire.

### 1.2 — ~~Queue polling pour Workshop Mode et WorkspaceRail~~ (Block A) — fixé en audit

**Fix** : `queue.startPolling()` ajouté dans `App.vue` onMounted
(idempotent). Workshop Mode + WorkspaceRail voient maintenant la queue
live même sans ouvrir le PlotterDrawer.

**Reste éventuel** : remplacer le polling 2 s par SSE/WebSocket pour
réduire le trafic. Pas bloquant.

### 1.3 — ~~`WorkspaceRail` panels manquants~~ (Block C) — fixé partiellement

**Fix** : `machine_telemetry` rend désormais `MachineStatusPill` +
état / acked / total / message du store plotter. `compare` rend un
launcher qui émet `open-compare` (écouté par `App.vue`) et ouvre le
drawer existant.

**Reste** : la décision "le workspace peut cacher `FilesPane` /
`CanvasView` (surfaces v0.1)" n'est pas prise — pour l'instant le
rail s'ajoute à côté plutôt que de remplacer. À traiter le jour où
un workspace "Pro full-screen" devient pertinent.

### 1.4 — ~~`CapabilityWizard` confirm → save profile~~ (Block A) — fixé

**Fix** : `PlotterDrawer.onWizardConfirm` clone le profil actif comme
base (workspace, speeds, pens héritent), applique les capabilities du
wizard + mappe `tool_change.mode` vers `tool_change_method` legacy
(`firmware`→`carousel`, `host_macro`→`rack`, `manual`→`manual_pause`,
`single_pen`→`none`), demande un nom via `window.prompt`, refuse les
doublons, puis appelle `job.saveProfile(next)` (recharge la liste +
sélectionne le nouveau profil). i18n : `plotter.newPlotterPrompt /
Duplicate / NoBase / Saved / Failed`. `MachineProfile` TS interface
gagne un champ `capabilities?: Record<string, unknown> | null` pour
faire round-tripper le block capability au backend.

**Reste éventuel** : dialog Vue au lieu de `window.prompt` natif.

### 1.5 — ~~CompareView candidats réels~~ — partiellement fermé

**Fix** : nouveau helper `useJobStore.renderVariant(placement,
variant)` qui appelle `/rerender` avec les overrides de la
variante demandée et retourne le SVG sans muter le placement
actif. `App.vue` cache les SVG par `variant_id` (avec l'actif
réutilisé sans re-render) et appelle `refreshCompareSvgs` à
l'ouverture du drawer Compare. CompareView reçoit désormais
deux SVG **réellement différents** quand l'opérateur a deux
variantes.

**Reste v2.0** : les métriques par candidat
(`est_time_s`/`draw_length_mm`/`pen_up_length_mm`/`swap_count`)
viennent du backend ; il faudrait étendre `/preflight` pour
les calculer par variante. Les 3 overlays manquants
(`penup_heatmap`/`path_density`/`curvature`) restent stubs car
ils demandent la géométrie pas-up + densité que le resolver
ne calcule pas encore.

---

## Catégorie 2 — Backend domain pas (encore) source de vérité

### 2.1 — ~~IR consommé en aval~~ — partiellement fermé (optimize)

**Fix** : nouveau `optimize_geometry_ir(geometry, *, layers,
merge_tolerance_mm)` dans `core/toolpath.py` qui accepte un
`GeometryIR` et passe par `_geometry_ir_to_svg` + `_optimize_svg`.
La surface IR → ToolpathResult est désormais stable ; le ré-aller
SVG en interne sera remplacé par un consommateur vpype direct
quand les fixtures Pi seront stabilisées. Test `test_optimize
_geometry_ir_round_trip_preserves_layers` couvre le round-trip
SVG → IR → optimize_geometry_ir → SVG sur la fixture TWO_LAYERS.

**Reste v2.0** : (a) wire ce nouvel entry-point dans la pipeline
quand `OMNIPLOT_IR_ENABLED=1`, en lisant depuis
`ir_artifact_cache.fetch_geometry` ; (b) ajouter le pendant
`generate_gcode_from_path_plan(plan)` pour fermer l'autre moitié
de la boucle ; (c) flipper le défaut à IR-on.

### 2.2 — ~~ToolChangeOrchestrator source de vérité~~ — fermé

**Fix** : `ManualSwapPrompt` gagne deux champs optionnels
(`multipen_body`, `monopen_body`) ; `default_manual_prompt(pen_slot
_count)` les peuple en fonction du magasin. La strategy choisit
le bon body selon `context.slot_index` (None → mono ; sinon →
multi). `_context_from_comment` (anciennement `_prompt`) pré-
calcule le label d'affichage pour le cas color (dédup label==hex).
`guided_pause_points` route désormais via
`ToolChangeOrchestrator.plan()`, pas via la regex legacy ; la
fonction `_prompt(comment)` a été retirée. Profils mis à jour :
`nextdraw.yaml` et `idraw_a3.yaml` exposent un `monopen_body`
branded. 635 tests verts incluant les golden text contracts
(`Insert pen slot 1: Red`, `Change pen to #ff0000`).

### 2.3 — Streamer inline tool-change commands — reporté v2.0

`SwapPlan.commands` (firmware / host_macro multi-lignes) ne
sont exécutés nulle part — le streamer ne sait gérer que
`pause_points: {idx: prompt}`. Étendre `ControllerStream`
pour injecter une séquence G-code + `wait_ms` est un refactor
hardware-layer ; le profil `Custom CoreXY A3 (rack)` reste
descriptif et inutile en runtime tant que ce travail n'est
pas fait.

### 2.4 — ~~Recovery `skip_layer` réel~~ (Block E.2) — fermé

**Fix backend** : nouvelle colonne `skipped_layers: list` sur
`PrintRun` (migration additive auto via `_add_missing_columns`).
Nouveau helper `_next_layer_boundary(gcode, start_idx)` qui scanne
les comments `Change to pen slot N (label)` / `Change pen: ...` /
`layer-...` et retourne `(exec_index, label)` du début du layer
suivant. Le bloc `except StreamError` de `PrintQueue.run_next`
avance `acked_lines` à ce checkpoint, ajoute le label à
`skipped_layers`, repasse le run en `QUEUED` et `wake()` le worker.

**Fix frontend** : champ `skipped_layers?: string[]` ajouté sur
l'interface TS `PrintRun`. `useQueueStore.load()` détecte les
deltas entre polls via `lastSeenSkips: Map<string, number>` et
émet un `toasts.critical()` (persistant) à chaque nouvelle couche
sautée. La liste des runs dans `PlotterDrawer → Queue` affiche un
badge ambre `⚠ N sautée(s)` sur les runs concernés, avec la
liste complète dans le `title` au survol.

i18n FR/EN : `queue.skipNotice` (toast message),
`queue.skippedBadge` (label compteur).

### 2.5 — IPC inter-rôles — reporté v2.0

Les 5 rôles `monolith`/`api`/`render`/`executor`/`telemetry`
sont déclarés (D.6) mais restent in-process. Choix
d'infrastructure (Redis pub/sub ? PostgreSQL `LISTEN/NOTIFY`
? HTTP + JWT ?) à trancher au moment du déploiement
multi-machine effectif. La capability matrix dans `docs/
deployment.md` documente déjà la séparation logique.

---

## Catégorie 3 — UX et perf différés

### 3.1 — Overlays Compare Mode — reporté v2.0 (cf. 1.5)

### 3.2 — Audit perf sur matériel — reporté v2.0

F.2 (Jinja hoist) + F.3 (skip vpype monotone) livrés et
documentés. Nouvelle baseline sur Pi 4/5 demande l'accès au
matériel et n'est pas reproductible dans le container CI.

### 3.3 — ~~Persistent toasts adoption~~ (Block G.2) — fermé

**Fix** : 4 conditions opérateur-bloquantes adoptent
`toasts.critical()` :
1. `App.vue` — `apiUnreachable` au boot (backend unreachable).
2. `PlotterDrawer.onWizardConfirm` — échec `saveProfile`.
3. `useQueueStore.load` — toast `queue.skipNotice` à chaque
   nouveau layer sauté sous `skip_layer`.
4. `usePlotterStore` — watcher qui détecte `connected: true→false`
   pendant un run en cours et émet `plotter.deviceLost`.

L'intégrité library reste affichée via `IntegrityBanner` (déjà
une UI persistante non-toast), pas besoin de doubler.

### 3.4 — Suite Playwright étoffée — reporté v2.0

Scaffold prêt (`playwright.config.ts`, `e2e/modal-v2.spec.ts`).
L'installation du binaire Chromium (~150 MB) reste opt-in via
`npm run e2e:install`. Étoffer la suite + activer le job CI
demande un cache GHA dédié pour ne pas redownloader le binaire
à chaque run.

---

## Catégorie 4 — Checklist runtime — reporté v2.0

Les ~50 items du brief original demandent `uvicorn` + `vite
dev` en parallèle avec un navigateur en pilotage manuel. À
exécuter au moment du déploiement opérationnel ; la partie
automatisable est suivie en TODO 3.4 (Playwright).

---

## Catégorie 5 — Documentation

### 5.1 — ~~`docs/ROADMAP_V0.2.md` consolidation~~ — fixé

Journal §7 enrichi avec lignes `visibility` (2026-05-28) +
`finish` (2026-05-28) qui synthétisent la phase de wiring + les
fermetures de TODO ; toutes les étapes A→D restent `[x]`. §6 (SLO
targets) reste à remplir après la checklist runtime sur Pi.

### 5.2 — ~~`docs/getting_started.md` v0.2~~ — fixé

`getting_started.md` enrichi :
- Tableau des env vars étendu (`OMNIPLOT_IR_ENABLED`,
  `OMNIPLOT_OTEL_ENABLED`, `OMNIPLOT_SLO_EVAL_ENABLED`,
  `OMNIPLOT_ROLE`).
- Section « v0.2 UI surfaces » : tableau des 11 surfaces visibles
  par défaut + tableau des feature flags URL + tableau des
  raccourcis clavier.

---

## Catégorie 6 — Hygiène code

### 6.1 — ~~Lint pré-existant~~ — fermé

**Fix** : `npm run lint` retourne désormais **0 erreur, 57
warnings** (exit 0, CI verte). `vue/no-mutating-props` est
abaissé de `error` à `warn` dans `eslint.config.js` avec un
commentaire qui pointe vers cette TODO en explicitant la dette
v0.1. Les 6 warnings auto-fixables (`vue/attributes-order`,
`vue/require-default-prop`, directives `eslint-disable`
inutilisées) ont été nettoyés via `npm run lint -- --fix`.

**Suivi v2.0** : refactor des composants edit/image,
edit/render, edit/svg, ProfilePenFields, etc. pour passer à
`defineModel()` / explicit `emit('update:propName', value)`
quand le pattern par-section sera revisité.

### 6.2 — ~~`UploadFooter.vue` lint~~ — fermé

**Note** : le fichier `UploadFooter.vue` ne déclenche plus aucun
warning lint à la date de cette TODO (le mutateur incriminé a
été déplacé / refactoré entre-temps). Plus rien à faire.

---

## Comment fermer un item

1. Ouvrir une PR ciblant `claude/magical-davinci-U3mpB` (ou main si
   le wiring v0.2 a été mergé).
2. Inclure les tests qui prouvent le critère d'acceptation.
3. Cocher l'item ici + le supprimer (ou le laisser barré pour l'audit).
4. Mettre à jour `docs/ROADMAP_V0.2.md` journal en parallèle quand il
   s'agit d'un follow-up roadmap.
