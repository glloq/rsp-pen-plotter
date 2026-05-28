# TODO — restes après la phase de wiring v0.2

> Snapshot pris après les 10 commits du wiring v0.2 sur
> `claude/magical-davinci-U3mpB` + l'audit complet du 2026-05-28
> (34/36 ✅). Mis à jour à chaque PR qui ferme un point. Format : un
> titre court + contexte + critère d'acceptation précis.

## Résumé audit 2026-05-28

- **34 points sur 36 conformes** : tous les composants v2 sont montés
  et consommés (EditModalV2, WorkspaceRail, panels Settings, etc.),
  toutes les clés `v2.*` sont référencées, tous les routers backend
  sont mis en service par `main.py`, les modules domain (IR, recovery,
  SLO evaluator) sont dans les chemins chauds.
- **Seul gap structurel restant** : `ToolChangeOrchestrator` n'est
  consommé par aucun chemin de production hors tests (cf. §2.2 et §2.3
  ci-dessous).
- **Fix appliqué en audit** : queue polling démarré au boot dans
  `App.vue` pour que Workshop Mode + WorkspaceRail aient des données
  live sans dépendre de l'ouverture du PlotterDrawer.

---

## Catégorie 1 — Wiring incomplet documenté comme intentionnel

### 1.1 — Cut-over `EditModal` v1 → v2 (Block A)

**Contexte** : `EditModalV2` est monté à côté de `EditModal` v1 derrière
`?flag.modalV2=1`. Le `confirm` du modal V2 ferme juste le modal au lieu de
propager la `PolicyDecision` dans le placement draft.

**Travail restant**
- Câbler `onEditV2Confirm(decision)` dans `App.vue` pour mettre à jour
  `job.layer_algorithms` / `placement.svg` via `triggerRerender` avec
  l'algorithme recommandé.
- Décider du critère de cut-over (mode A/B sur N opérateurs ? feature flag
  par défaut on ?).
- Supprimer le code v1 + retirer le flag.

**Critère d'acceptation** : un opérateur peut faire un parcours complet
upload → édit V2 → confirme → preview se met à jour → generate, sans
toucher au flag.

### 1.2 — ~~Queue polling pour Workshop Mode et WorkspaceRail~~ (Block A) — fixé en audit

**Fix** : `queue.startPolling()` ajouté dans `App.vue` onMounted
(idempotent). Workshop Mode + WorkspaceRail voient maintenant la queue
live même sans ouvrir le PlotterDrawer.

**Reste éventuel** : remplacer le polling 2 s par SSE/WebSocket pour
réduire le trafic. Pas bloquant.

### 1.3 — `WorkspaceRail` ne rend pas les panels v0.1 (Block C)

**Contexte** : `WorkspaceRail.vue` filtre sur les v2 panels
(`layer_inspector`, `pipeline_inspector`, `magazine`, `queue`) et ignore
les ids v0.1 (`source`, `style`, `preview`, `plot`, `machine_telemetry`,
`compare`).

**Travail restant**
- Décider si le workspace doit pouvoir CACHER les surfaces v0.1
  (`FilesPane`, `CanvasView`) — actuellement elles sont toujours visibles
  dans `App.vue`.
- Si oui : conditionner leur affichage sur le contenu de
  `workspaces.active.panels`. Attention à l'UX : un workspace vide
  laisserait l'écran vide.
- Implémenter le rendu de `machine_telemetry` dans le rail (afficher
  `MachineStatusPill` + métriques live).
- `compare` dans le rail : un bouton "Comparer" inline qui réutilise
  le drawer de `App.vue`.

**Critère d'acceptation** : changer de workspace recompose réellement
l'écran ; un workspace `Pro` cache `FilesPane` si demandé, etc.

### 1.4 — `CapabilityWizard` confirm → save profile (Block A)

**Contexte** : le wizard émet `confirm` avec un `MachineCapabilities` ;
aujourd'hui ça produit juste un toast. Il faut le wirer dans le flow
`saveProfile`.

**Travail restant**
- Ouvrir un dialog "Nom du profil" après le confirm.
- Construire un `MachineProfile` minimal autour des capabilities (le
  reste vient des defaults / du preset choisi).
- Appeler `saveProfile(...)` côté API.
- Recharger la liste des profils dans `job.loadProfiles()`.
- Sélectionner automatiquement le nouveau profil.

**Critère d'acceptation** : un opérateur peut créer un profil custom
"Rack 6 slots host_macro" depuis le wizard et l'utiliser dans le panneau
profile sans passer par YAML.

### 1.5 — `CompareView` candidats réels (Block A / G.1)

**Contexte** : le drawer Compare alimente `a` et `b` avec
`placement.svg` (le même SVG pour les deux candidats) parce que le
placement ne stocke que la variante active. Les overlays
`penup_heatmap` / `path_density` / `curvature` restent des stubs.

**Travail restant**
- Permettre au backend de rendre une variante donnée sans la promouvoir en
  active (`POST /rerender?variant_id=...` qui retourne le SVG sans
  patcher la placement). Ou cacher chaque variant côté front lors d'une
  bascule.
- Calculer les métriques `est_time_s`, `draw_length_mm`,
  `pen_up_length_mm`, `swap_count` côté backend pour chaque candidat
  (extension de `/preflight`).
- Implémenter les 3 overlays manquants :
  - `penup_heatmap` : passes pen-up extraites du G-code, projetées en
    heatmap 2D (canvas + densité gaussienne).
  - `path_density` : nombre de strokes par cellule de la grille.
  - `curvature` : stress de courbure (dérivée seconde) coloré selon
    seuil.

**Critère d'acceptation** : ouvrir Compare avec 2 variantes vraiment
différentes → preview SVG différent dans chaque colonne, 4 overlays
toggleables avec rendu visuel.

---

## Catégorie 2 — Backend domain pas (encore) source de vérité

### 2.1 — IR consommé en aval (Block E.1)

**Contexte** : `OMNIPLOT_IR_ENABLED=1` produit un `GeometryIR` et le
persiste dans `ir_artifact_cache`. Personne ne LIT le cache. Les
consommateurs aval (`optimize_svg`, `generate_gcode`) tournent toujours
sur du SVG-string.

**Travail restant**
- Refactor `optimize_svg` pour accepter un `GeometryIR` (en plus du SVG)
  en entrée.
- Idem pour `generate_gcode` (`PathPlanIR`).
- Adapter le bench `scripts/perf_baseline.py` pour mesurer la différence.
- Quand stable : flipper le défaut à `OMNIPLOT_IR_ENABLED=1`.

**Critère d'acceptation** : la même fixture passe par le pipeline IR par
défaut ; les SVG / G-code générés sont identiques aux byte près à la
version legacy sur N fixtures représentatives.

### 2.2 — `ToolChangeOrchestrator` source de vérité (Block E.3)

**Contexte** : aujourd'hui le prompt opérateur en mode manual_pause vient
de l'ancien `_prompt(comment)` regex dans `core/toolchange.py`. La raison
documentée : les profils bundled n'ont pas un `manual_prompt` aligné sur
le contrat texte que les golden tests vérifient.

**Travail restant**
- Aligner le `manual_prompt` des 5 presets (`AxiDraw V3`, `NextDraw A2`,
  `iDraw A3 GRBL`, `Custom CoreXY A3`, `Custom CoreXY A3 (rack)`) sur le
  format "Insert pen slot {slot}: {label}" / "Change pen to {label} ({color})".
- Mettre à jour les tests golden + `test_toolchange.py` /
  `test_mono_pen_pause.py` pour matcher le nouveau format orchestré.
- Supprimer la branche `_prompt(comment)` et basculer
  `guided_pause_points` sur l'orchestrateur exclusivement.

**Critère d'acceptation** : 633 backend tests verts avec la regex legacy
SUPPRIMÉE.

### 2.3 — Streamer inline tool-change commands (Block E.3)

**Contexte** : `ToolChangeOrchestrator.plan()` peut produire des
`SwapCommand[]` (firmware trigger ou host_macro multi-lignes). Aujourd'hui
le streamer (`hardware/streamer.py`) ne sait gérer que les
operator-confirm pauses (via `pause_points: {idx: prompt}`).

**Travail restant**
- Étendre `ControllerStream` pour accepter un schéma `{idx: SwapPlan}` où
  un plan non-confirm pousse une séquence de lignes G-code + `wait_ms`.
- Adapter `pen_plotter.queue.enqueue` pour produire ces plans à la place
  du dict `{idx: str}` legacy.
- Migration : tolérer les 2 formats jusqu'à ce que tous les runs en file
  soient au nouveau format.

**Critère d'acceptation** : un profil `host_macro` (rack) exécute une
séquence de 7 lignes G-code automatiquement à chaque tool change, sans
opérateur, et l'opérateur peut suivre la progression dans la queue.

### 2.4 — Recovery `skip_layer` réel (Block E.2)

**Contexte** : `resolve_recovery` retourne `SKIP_AND_CONTINUE` quand la
politique est `skip_layer`, mais `queue.py` met le run en `PAUSED` et
attend l'opérateur (pas de skip automatique).

**Travail restant**
- Implémenter le saut de couche : déterminer l'index de la prochaine
  couche dans le G-code (re-scanner les comments) et reprendre à cet
  index.
- Marquer la couche skippée comme telle dans le run record (nouvelle
  colonne `skipped_layers: list[str]`).
- Émettre un toast critique côté front pour informer l'opérateur que
  des couches ont été sautées sur ce run.

**Critère d'acceptation** : sur un profil `skip_layer` + un G-code à 3
couches dont la 2ème lève `StreamError`, le run termine en `COMPLETED`
avec `skipped_layers=['layer-2']`.

### 2.5 — IPC inter-rôles (Block E.5 / audit #1 phase 3)

**Contexte** : `pen_plotter.deployment` définit 5 rôles
(`monolith`/`api`/`render`/`executor`/`telemetry`) mais aujourd'hui
chaque rôle est in-process — le lifespan FastAPI conditionne juste
quels subsystems se chargent.

**Travail restant**
- Choisir le transport : Redis pub/sub ? HTTP + signed JWT ?
  PostgreSQL `LISTEN/NOTIFY` ?
- Spécifier le contrat des messages inter-rôles : `JobReady`,
  `RenderComplete`, `ExecutorPaused`, `TelemetryFlush`, …
- Implémenter le client + serveur.
- Adapter `application/file_library` pour pointer sur un store
  partagé (S3-compatible ?) quand les rôles sont distants.
- Optionnel : adapter Postgres pour la queue SQLite quand multi-machine.

**Critère d'acceptation** : démarrer `OMNIPLOT_ROLE=api` sur une machine
et `OMNIPLOT_ROLE=executor` sur une autre, faire passer un job de bout
en bout sans intervention.

---

## Catégorie 3 — UX et perf différés

### 3.1 — Overlays Compare Mode (Block G.1)

**Contexte** : `bounds` rendu réellement (SVG rect dashed depuis viewBox).
Les 3 autres restent stubs.

**Travail restant** : voir 1.5 ci-dessus.

### 3.2 — Audit perf après IR + workers (Block F follow-up)

**Contexte** : F.2 (Jinja hoist) et F.3 (skip vpype monotone) livrés.
La baseline montre un possible bruit sur `gcode` (~67 → 92 ms p50). À
vérifier sur un échantillon plus large.

**Travail restant**
- Re-mesurer `scripts/perf_baseline.py --runs 30 --warmup 5` sur le
  matériel cible (Pi 4/5).
- Re-investiguer le bruit `gcode` p50 : profiler avec py-spy
  (`scripts/profile.sh record`).
- Documenter les écarts entre `perf-baseline.md` et la prod après
  déploiement.

**Critère d'acceptation** : nouvelle baseline avec p95/p99 stables et
documentés.

### 3.3 — Persistent toasts adoption (Block G.2)

**Contexte** : le helper `useToastStore.critical()` existe mais aucun
appelant production ne l'utilise pour l'instant.

**Travail restant**
- Identifier les conditions critiques actuelles à upgrader :
  `apiUnreachable` au boot, `device_disconnect` runtime, échecs de
  sauvegarde profile, intégrité library cassée.
- Remplacer leurs `toasts.error(...)` par `toasts.critical(...)`.

**Critère d'acceptation** : couper le backend pendant un upload →
toast erreur persiste jusqu'à dismiss manuel.

### 3.4 — Suite Playwright étoffée (Block G.3)

**Contexte** : scaffold prêt (`playwright.config.ts`, `e2e/modal-v2.spec.ts`)
avec 3 smoke tests. Couvre le minimum vital.

**Travail restant**
- Ajouter `npm install --save-dev @playwright/test` en suivi CI.
- Étendre le suite avec les parcours canoniques (`fast default`,
  `expert override`, `error flow` — déjà couverts côté backend par
  `test_e2e_journeys.py`).
- Couvrir le bug du "fichier édité sans plan" (le bugfix 71805b6).
- Couvrir le parcours Capability Wizard.
- Activer le job CI `e2e` (avec `playwright install --with-deps chromium`
  cache GHA pour ne pas redownloader 150 MB à chaque run).

**Critère d'acceptation** : `npm run e2e` exécute ≥20 tests verts en
local + en CI.

---

## Catégorie 4 — Checklist de validation runtime

**Contexte** : le brief original liste ~50 items de smoke tests runtime
qui demandent `uvicorn` + `vite dev` lancés en parallèle (parcours bout
en bout : modal V2 fast / expert / erreur, queue pause/resume, Workshop
Mode, Workspaces, Compare, SSE preview, observabilité, etc.).

**Travail restant**
- Exécuter la checklist complète sur le matériel cible (Pi + machine
  de dev).
- Cocher chaque item dans le brief, documenter les anomalies.
- Convertir les items reproductibles en tests Playwright (cf. 3.4).

**Critère d'acceptation** : la checklist complète du brief est annotée
✅/❌ avec preuve (screenshot/log) par item.

---

## Catégorie 5 — Documentation

### 5.1 — `docs/ROADMAP_V0.2.md` consolidation

**Contexte** : le journal §7 a 10 nouvelles lignes "wire X". On peut
les consolider une fois la phase wiring fermée.

**Travail restant**
- Marquer toutes les étapes A→D `[x]` en haut (déjà fait).
- Ajouter une section "v0.2 wire" entre §3 et §4 qui synthétise les
  10 commits.
- Mettre à jour §6 (SLO targets) avec les valeurs réelles mesurées
  après runtime checklist.

### 5.2 — `docs/getting_started.md` v0.2

**Travail restant**
- Ajouter les feature flags v2 (`?flag.modalV2=1`,
  `?flag.workshopMode=1`, `?flag.compareMode=1`, `?flag.perf=1`) et
  comment les activer.
- Ajouter `OMNIPLOT_IR_ENABLED` / `OMNIPLOT_SLO_EVAL_ENABLED` côté
  backend.
- Section "raccourcis clavier" qui pointe vers `docs/shortcuts.md`.

---

## Catégorie 6 — Hygiène code

### 6.1 — Lint pré-existant

**Contexte** : `npm run lint` rapporte 63 erreurs / 7 warnings sur du
code v0.1 non touché (MagazineEditor.vue, MagazineView.vue
"attributes-order", etc.). Aucune n'est dans le code v0.2 livré.

**Travail restant**
- Faire un pass `eslint --fix` sur les warnings auto-fixables.
- Décider du sort des erreurs (vue/no-mutating-props) : refactor ou
  ajouter `eslint-disable-next-line` ciblé.

### 6.2 — `frontend/src/components/edit/UploadFooter.vue` lint

**Contexte** : "Unexpected mutation of bitmap prop" erreurs aux lignes
68 et 122 — flagged dans `npm run lint`.

**Travail restant** : refactor pour utiliser un emit ou un computed
writable, pas un mutateur direct sur la prop.

---

## Comment fermer un item

1. Ouvrir une PR ciblant `claude/magical-davinci-U3mpB` (ou main si
   le wiring v0.2 a été mergé).
2. Inclure les tests qui prouvent le critère d'acceptation.
3. Cocher l'item ici + le supprimer (ou le laisser barré pour l'audit).
4. Mettre à jour `docs/ROADMAP_V0.2.md` journal en parallèle quand il
   s'agit d'un follow-up roadmap.
