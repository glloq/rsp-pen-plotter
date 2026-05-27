# Roadmap v0.1 → v0.2 — Refonte propre du projet

> **Document vivant.** À mettre à jour à chaque étape complétée, dans le même commit/PR que le code livré.
> Source de vérité unique pour la progression de la refonte.

---

## 0. Contexte & objectifs v0.2

Cette roadmap consolide **7 audits ciblés** réalisés sur `rsp-pen-plotter` (architecture, tool-change, algorithm policy, matrice décisionnelle, contrat de données, observabilité, UX opérateur) en un plan d'exécution unique.

**Objectifs v0.2 :**

- Architecture modulaire prête pour V2 multi-OS / multi-machine
- Geometry IR typé + pipeline DAG avec cache par hash d'artefact
- Système de manifestes versionnés comme source de vérité backend → frontend
- Capability Model explicite dans les profils machine (4 modes de tool-change)
- `AlgorithmPolicyResolver` avec choix automatique par défaut (matrice décisionnelle)
- UX opérateur en 2 modes (Assisté / Expert) avec modal V2 en 6 étapes
- Observabilité complète (logs JSON, OTel, Prom/Grafana, py-spy) + budgets SLO
- Tests de contrat + smoke perf en CI
- Aucune régression fonctionnelle existante

**Branche de développement :** `claude/pensive-shannon-nvZDY`

---

## 1. Synthèse des 7 audits

| #  | Sujet                                              | Type        | Phase cible |
|----|----------------------------------------------------|-------------|-------------|
| #1 | Architecture globale, IR, pipeline DAG, plugins    | Stratégique | A           |
| #2 | Tool change orchestrator (4 modes), Capability     | Tactique    | A/B         |
| #3 | Algorithm Policy Resolver + UX modal V2            | Tactique    | B/C         |
| #4 | Matrice décisionnelle resolver (exécutable)        | Spec        | B           |
| #5 | Contrat backend/frontend versionné                 | Transverse  | A           |
| #6 | Observabilité + profiling + SLO                    | Transverse  | A→D         |
| #7 | UX opérateur avancée + modal V2 complet            | Frontend    | C           |

---

## 2. Décisions techniques arrêtées

### Architecture & contrat

| Domaine                       | Décision                                                              |
|-------------------------------|-----------------------------------------------------------------------|
| Versionnage manifestes        | `manifest_version: int` obligatoire + `schema_semver` informatif      |
| Types frontend                | OpenAPI → `openapi-typescript` (API) + JSON Schema runtime (manifests)|
| Validation runtime frontend   | **zod**                                                               |
| Validation backend            | Pydantic strict, erreurs normalisées (code/message/details/path)      |
| Observabilité                 | Prometheus + Grafana + OTEL traces (Signoz plus tard si besoin)       |
| Storage métriques (appliance) | SQLite ring buffer local + OTLP export optionnel                      |
| Sampling traces appliance     | 100%                                                                  |
| Sampling traces multi-machine | Tail-sampling (erreurs + latences élevées)                            |
| Fallback manifestes frontend  | Build-time snapshot + cache localStorage                              |
| Profiling Python              | py-spy                                                                |
| Feature flags                 | Par feature (rollback chirurgical, A/B)                               |
| Deprecation window manifestes | max(2 versions majeures, 2 mois) + `deprecated_since`/`remove_after`  |

### Métier

| Domaine                        | Décision                                                            |
|--------------------------------|---------------------------------------------------------------------|
| `palette_mode = machine_only`  | Hard-block en Assisté, override autorisé en Expert                  |
| Détection photo/illustration   | Auto (entropie, edges, aplats) + badge modifiable                   |
| HostMacroStrategy              | Format YAML dédié exposé (Jinja2 reste moteur interne)              |
| RecoveryPolicy                 | Profil par défaut + override par job                                |
| Mono-pen densité variable      | Passes multiples d'abord, paramètres ensuite                        |
| Presets initiaux               | AxiDraw, NextDraw, iDraw/EleksDraw (GRBL), custom CoreXY            |

### UX

| Domaine                       | Décision                                                             |
|-------------------------------|----------------------------------------------------------------------|
| Mode Assisté / Expert         | Par tâche dans modal + mémorisation user                             |
| « Pourquoi ce choix ? »       | Généré dynamique depuis règles + templates texte                     |
| Override expert               | Progressive disclosure 2 niveaux                                     |
| Perf overlay frontend         | Prod activable `?perf=1` + feature flag serveur                      |
| Curseur Intent                | 3 niveaux discrets (fast / balanced / quality)                       |
| Workspaces                    | Local d'abord (localStorage), sync serveur en V2                     |

---

## 3. Roadmap par phases

**Légende de statut :** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` skipped/deferred

---

### Phase A — Fondations transverses

> Objectif : poser les fondations contractuelles, observabilité et IR sans rien casser. Permet de **mesurer la baseline** avant tout refacto métier.
> Découpage PR : **tronches fines** (1 PR par étape).

- [x] **A.1** — Logging JSON structuré + correlation IDs
  - Middleware FastAPI génère `request_id`, propage `job_id`/`run_id`/`placement_id`
  - Champs standards : `ts`, `level`, `msg`, `request_id`, `job_id`, `run_id`, `placement_id`, `algorithm_id`, `quality_tier`, `profile_name`, `source_kind`
  - Redaction PII/secrets
  - **DoD :** tous les endpoints émettent du JSON parsable, correlation IDs visibles bout en bout, doc dans `docs/observability.md`
- [x] **A.2** — OpenTelemetry baseline + perf baseline mesurée
  - `opentelemetry-instrumentation-fastapi` + exporter OTLP
  - Spans manuels sur phases pipeline existantes (upload, segmentation, render, optimize, gcode)
  - Sampling 100% en dev/appliance
  - Fixtures de référence (1-2 par `source_kind`), p50/p95/p99 par phase
  - **DoD :** baseline documentée dans `docs/perf-baseline.md`, dashboard Grafana minimal exporté
  - **Note :** dashboard Grafana JSON reporté au moment où une stack OTel sera réellement déployée (D.4) ; le script `scripts/perf_baseline.py` produit le tableau mesurable en attendant.
- [x] **A.3** — Geometry IR + artifact hashing
  - `backend/domain/ir/{geometry.py, pathplan.py, artifacts.py}`
  - Types : `SourceAsset`, `SegmentationArtifact`, `GeometryIR`, `PathPlanIR`, `MachineProgram`, `ExecutionRun`
  - Hash déterministe par artefact (contenu + version IR)
  - Adapter de compat depuis pipeline SVG-string actuel (pas de big-bang)
  - **DoD :** types + tests round-trip, ancien pipeline passe encore, nouveau pipeline opt-in via feature flag (`OMNIPLOT_IR_ENABLED`)
- [x] **A.4** — Système de manifestes versionnés + génération types frontend
  - Modèle générique `Manifest`/`ManifestEntry`/`ManifestMeta`/`Deprecation`
  - Endpoints `/manifests` (index) + `/manifests/{domain}` versionnés (`manifest_version: int`)
  - Metadata : `manifest_version`, `schema_semver`, `generated_at`, `deprecations`, `feature_flags`
  - Erreurs normalisées (`ApiError` → `{code, message, details, path}`)
  - Script `scripts/generate_openapi.py` (consommé par `openapi-typescript` en A.7)
  - Doc `docs/contract_architecture.md`
  - **DoD :** types TS générés en CI, snapshot embarqué, tests de contrat
  - **Note :** snapshot frontend + wiring CI de `openapi-typescript` arriveront en A.7 (consommation). Backend complet ici.
- [x] **A.5** — Capability Model dans profil machine + migration YAML additive
  - Enums : `ToolingMode`, `CommandSource`, `RecoveryPolicy`
  - `MachineCapabilities` + `ToolChangeStrategy` (avec `ManualSwapPrompt` / `HostMacroStep`)
  - Migration additive : `capabilities` optionnel, dérivé automatiquement depuis `tool_change_method` quand absent
  - Validation Pydantic stricte (StrEnum + erreurs explicites)
  - Doc `docs/profile_format.md` mise à jour avec mapping legacy → v0.2
  - **DoD :** tous les profils existants chargent sans warning, nouveaux champs validés, tests parsing (11 tests)
- [x] **A.6** — Manifeste algorithmes versionné (consommateur du système A.4)
  - Manifestes par algo : id, version, kind, complexity, params (JSON Schema), recommended_presets
  - `/manifests/algorithms` enveloppé avec version + meta (consommé par le frontend en A.7)
  - Legacy `/algorithms` conservé (mêmes données) — pas de breaking change
  - **DoD :** `/algorithms` et `/manifests/algorithms` retournent le même set d'algos, paramètres exposés via JSON Schema
  - **Note :** bornes/defaults précis par algo + `recommended_presets` + `cost_estimate` arrivent en Phase B avec le resolver (les manifestes versionnent leur enveloppe maintenant ; les payloads s'enrichissent au fil de B).
- [x] **A.7** — Validation runtime frontend (zod) + erreurs normalisées + fallback
  - Schémas zod pour manifestes (`ManifestMeta`, `Deprecation`, `AlgorithmManifestEntry`, `AlgorithmsManifest`, `ApiErrorBody`)
  - Client `fetchAlgorithmsManifest` avec stratégie live → cache localStorage → snapshot build-time
  - `ManifestVersionMismatchError` + `assertSupportedVersion` quand `manifest_version` backend > version supportée frontend
  - Composant `ManifestFallbackBanner.vue` (cause + détail erreur)
  - Script `gen:manifests` (npm) pour rafraîchir le snapshot
  - **DoD :** parsing strict des manifestes en frontend, UI affiche cause + action en cas de mismatch (8 tests vitest)
  - **Note :** intégration dans les stores/modal arrive en Phase B (consommation effective des manifestes par les composants).

---

### Phase B — Logique métier

> Objectif : consommer les fondations Phase A pour livrer les briques métier (resolver, orchestrator, recovery).
> Découpage PR : 1 PR par module métier.

- [x] **B.1** — `AlgorithmPolicyResolver` avec matrice décisionnelle (audit #4)
  - `pen_plotter.domain.policy` : types (`SourceKind`/`Goal`/`PaletteMode`/`QualityTier`/`SegmentationMethod`), rules (matrice A/B/C/D/E), constraints (mégapixels / mono-pen / palette ≤2), resolver pur
  - `RuleHit` + `ConstraintHit` traçables pour le « Pourquoi ce choix ? » du modal V2
  - **DoD :** 41 tests (toutes branches matrice + tous hard constraints + parametrized smoke sur l'ensemble du produit cartésien `SourceKind × Goal`)
- [x] **B.2** — `ToolChangeOrchestrator` + 4 stratégies
  - `pen_plotter.domain.toolchange` : `ToolChangeOrchestrator` + `SwapPlan` + `SwapContext` + `PauseKind`
  - 4 stratégies (`FirmwareStrategy` / `HostMacroStrategy` / `ManualStrategy` / `SinglePenStrategy`) ; sélection automatique via Capability Model (A.5)
  - Substitution `{slot}`/`{color}`/`{label}`/`{layer}` dans prompts manuels et macros host (`HostMacroStep`)
  - **DoD :** 16 tests E2E (4 modes + dispatch + dérivation legacy + prompt manuel + macro multi-lignes + recovery policy + registry complet)
- [x] **B.3** — Pipeline pause/resume robuste + RecoveryPolicy
  - `pen_plotter.domain.recovery` : `Directive` (ABORT_RUN / WAIT_FOR_OPERATOR / SKIP_AND_CONTINUE), `FailureKind` (5 valeurs), `JobRecoveryOverride` (per-failure > job-wide > profil), `resolve_recovery()` pur
  - Table de transitions (3 politiques × 5 kinds) explicite et testée
  - Test e2e pause → swap → resume sur G-code synthétique (préambule G21 + retour position + reste du programme préservé)
  - **DoD :** 23 tests (table totale, précédence overrides, e2e checkpoint, prompt manuel via orchestrator)
  - **Note :** intégration de `resolve_recovery` dans `pen_plotter.queue` se fait dans une PR dédiée (le module `queue.py` est dans `ignore_errors=true` mypy override, refacto en chantier propre).
- [x] **B.4** — Frontend : consommation dynamique des manifestes
  - Pinia store `useAlgorithmsStore` adossé à `fetchAlgorithmsManifest` (live → cache → snapshot, A.7)
  - Bascule des deux call sites (`EditPreviewPane.vue`, `useLayerCardState.ts`) du legacy `getAlgorithms()` vers le store
  - `byId`/`fromFallback`/`source`/`lastError` exposés pour la bannière + intégrations futures
  - **DoD :** un nouvel algo backend devient exploitable frontend sans patch type/schema (4 tests vitest)
  - **Note :** suppression complète de `getAlgorithms()` + génération de formulaires depuis JSON Schema (`params`) lands en Phase C avec la refonte du modal V2, après que la matrice B.1 ait calibré les bornes/defaults par algo.
- [x] **B.5** — Instrumentation détaillée par phase pipeline
  - Sub-step spans : `pipeline.bitmap.load`, `pipeline.bitmap.preprocess`, `pipeline.bitmap.fit_within`, `pipeline.bitmap.segment` (method/num_colors/n_init attrs), `pipeline.bitmap.drop_small_regions`, `pipeline.bitmap.merge_similar_colours`, `pipeline.bitmap.render_layer` (one per layer, séquentiel + parallel), `pipeline.bitmap.render_parallel`, `pipeline.bitmap.compose_svg`
  - Fixture `memory_exporter` mutualisée dans `tests/conftest.py` (OTel n'autorise qu'un seul TracerProvider, partagé entre `test_tracing.py` et `test_pipeline_spans.py`)
  - **DoD :** 3 tests dédiés vérifiant émission des spans + attributs (mime/size/method/num_colors), suite full green
  - **Note :** métriques cache/workers/queue + dashboard Grafana JSON arrivent avec D.4 (SLO budgets + alerting) — l'instrumentation OTel des phases est en place dès maintenant pour collecter la baseline.
- [x] **B.6** — Presets plotters marché (≥4) + docs capability matrix
  - 5 profils bundled : `AxiDraw V3`, `NextDraw A2` (capabilities explicit), `iDraw A3 (GRBL)` (capabilities explicit + arcs), `Custom CoreXY A3` (legacy), `Custom CoreXY A3 (rack)` (host_macro complet avec 7 lignes + waits + placeholders)
  - Documentation `docs/presets.md` avec capability matrix + notes par preset + guide « comment ajouter un preset »
  - **DoD :** 5 profils chargent et passent les tests d'intégration (12 tests dont substitution `{slot}` dans rack macro), endpoint `/profiles` sert les 5

---

### Phase C — UX opérateur

> Objectif : livrer l'expérience opérateur cible (modes Assisté/Expert, modal V2, vues avancées, queue UX pro).
> Découpage PR : 1 PR par vue majeure.

- [x] **C.1** — Architecture 2 modes (Assisté / Expert) + feature flags + mémorisation user
  - Pinia store `useUiModeStore` (mode + `expertDisclosureLevel` 1/2 + flags), persistance localStorage
  - Composable `useFeatureFlag(name)` (computed) ; URL `?flag.X=1` override persisted
  - Composant `AssistantModeToggle.vue` (segmented Assisté/Expert avec `aria-pressed`)
  - **DoD :** 9 tests vitest (défauts, toggle, persistance, restauration, override URL, payload corrompu, niveaux disclosure)
- [x] **C.2** — Modal V2 refondu en 6 étapes
  - Endpoint backend `POST /policy/resolve` (wrap du resolver B.1, validation Pydantic stricte)
  - Frontend zod schemas `domain/policy/` + client `resolveAlgorithmPolicy`
  - Composants `v2/StepperHeader.vue` (6 chips + accessibilité aria-current) et `v2/EditModalV2.vue` avec les 6 étapes Source/Intent/Algorithme/Couleurs/Couches/Préflight
  - « Pourquoi ce choix ? » rendu depuis `reasoning[]` du resolver, indicateurs de risque depuis `hard_constraints_applied[]`
  - **DoD :** 10 tests (3 backend HTTP + 7 vitest), modal V2 vit en parallèle du modal v0.1 (pas de big-bang)
  - **Note :** ETA continue précise + override expert "progressive disclosure 2 niveaux" arrivent en C.8 (instrumentation) + C.5 (compare mode) — squelette des 6 étapes en place pour les itérer.
- [x] **C.3** — Layer Inspector + Pipeline Inspector
  - `LayerInspector.vue` : tableau ordonné par `draw_order`, compteur de swaps qui tient compte de `pause_before` (auto/always/never), longueur totale formatée (mm/cm/m), couleur de slot
  - `PipelineInspector.vue` : chaîne Source → Segmentation → Algorithme → Fallbacks → Contraintes, depuis `PolicyDecision` du resolver
  - Pure / props-driven : intégrables dans le modal V2 ou comme panneaux indépendants
  - **DoD :** 7 tests vitest (ordre par draw_order, swap count avec policy, totalisation longueur, decision null, chaîne, contraintes, fallbacks)
  - **Note :** consommation des spans OTel (timing par couche) arrive en C.8 (perf overlay) ; pour l'instant on consomme `LayerInfo.total_length_mm` du v0.1 store, suffisant pour la valeur opérateur immédiate.
- [x] **C.4** — Wizard capability + vue magazine améliorée
  - zod schemas `domain/capability/` mirroring backend `MachineCapabilities`
  - `CapabilityWizard.vue` 3 étapes (mode → knobs spécifiques au mode → recovery + magazine), validation `canAdvance` (host_macro requires ≥1 ligne non vide)
  - UI conditionnelle : prompt knobs visible **uniquement** en mode manual, macro editor visible **uniquement** en host_macro, single_pen affiche un placeholder explicite
  - `MagazineView.vue` : grille de slots avec couleur + install toggle + calibration `(x,y)` ou « non calibré », `simulationSlot` highlight (préparation pour replay run)
  - **DoD :** 12 tests vitest (wizard branches + magazine padding/installer/calibration/simulation)
- [x] **C.5** — Compare Mode A/B + overlays debug
  - `CompareView.vue` : 2 candidats side-by-side avec SVG preview + métriques (`est_time_s`, `draw_length_mm`, `pen_up_length_mm`, `swap_count`) + diff colonnes avec winner highlight
  - Overlay toggles : `penup_heatmap` / `path_density` / `bounds` / `curvature` (UX seam ; rendering effectif des overlays différé à une PR dédiée, l'opérateur peut déjà activer/désactiver les flags)
  - Émet `pick-winner(id)` et `toggle-overlay(key)`
  - **DoD :** 7 tests vitest (rendu A/B, winner sur temps + longueur, pick-winner émis, toggle-overlay émis, overlay stub visible, undefined → em-dash)
  - **Note :** rendu effectif des 4 overlays (heatmap GL, density filter, bounds rect, curvature shader) arrive dans une PR overlay dédiée — la surface UX est prête.
- [x] **C.6** — Queue UX pro avec timeline + checkpoints + actions sécurisées
  - `RunTimeline.vue` : phases queued→running→paused→completed avec `aria-current="step"`, badges terminal (failed/canceled), barre de progression `acked_lines/total_lines`, gestion `total_lines=0` sans division
  - `RunActionsPanel.vue` : Pause/Reprendre/Annuler avec **confirm** sur Pause + Cancel, Reprendre direct (one-click), `nextActionHint` quand paused (visible **uniquement** si paused)
  - **DoD :** 14 tests vitest (timeline 6 + actions 8 dont confirm flow, hint conditionnel, disabled states corrects par phase)
  - **Note :** historique des runs + replay context = ajout futur sur la page queue (composants prêts à être branchés sur le `useQueueStore` existant).
- [x] **C.7** — Progressive preview SSE/WS
  - Endpoint backend `GET /preview/stream` (SSE) avec schéma stable `PreviewProgressEvent` (`kind` start/progress/partial/done/error, `sequence` monotonic, `elapsed_ms`, `payload`)
  - Emetteur synthétique pour la démo de bout en bout (placeholder ; refacto du pipeline bitmap pour yielder en parallèle est une PR séparée)
  - Headers `Cache-Control: no-cache` + `X-Accel-Buffering: no` pour défaire la mise en tampon des proxies
  - Composable frontend `useProgressiveStream(eventSourceFactory?)` avec `start`/`lastProgress`/`lastPartial`/`done`/`error`/`active`/`percent` reactives + `open(url)`/`close()` ; `onUnmounted` ferme automatiquement
  - **DoD :** 3 tests backend (kinds émis, payload shape, validation `layer_count`) + 6 tests frontend (start, percent, partial, done à 100% et close, error, re-open ferme l'ancien)
  - **Note :** intégration avec le `convert_file` pipeline pour streamer les vraies couches au lieu d'un emitter synthétique = follow-up. Le contrat SSE est stable, le frontend ne devra pas changer.
- [x] **C.8** — Frontend perf overlay + KPI tracking
  - Pinia store `usePerfStore` : ring buffer 200 samples, `recordTiming(kpi, ms, label?)`, `summary(kpi)` retourne `{count, p50, p95, last}`, compteur `errors`
  - Composable `usePerfTracker` : `time(kpi, label, fn)` sync, `timeAsync(kpi, label, fn)` async, `recordError(label?)`, signal automatique de `slow_interaction` au-delà de 100 ms
  - Composant `PerfOverlay.vue` activé via flag `perf` (URL `?flag.perf=1` ou persisté C.1), table KPI live + clear button
  - **DoD :** 13 tests vitest (store : recordTiming/summary/errors/clear/ring/empty + tracker : sync/async/throw/error + overlay : hidden/visible/rows/clear)
  - **Note :** report serveur des samples + budgets SLO arrivent en D.4 (alerting). Pour l'instant le store reste in-memory, suffisant pour le debug terrain.
- [x] **C.9** — i18n FR/EN + microcopy standardisé + raccourcis clavier
  - Clés i18n `v2.*` ajoutées dans `en.json` et `fr.json` (mode, modal 6 étapes, intent, manifest fallback, perf overlay)
  - Composable `useKeyboardShortcuts([{id, handler}])` avec `SHORTCUTS` registry (6 bindings) ; n'intercepte **pas** les surfaces éditables (input/textarea/contenteditable)
  - Doc `docs/shortcuts.md` (table + convention microcopy action/conséquence/recommandation + workflow i18n FR/EN)
  - **DoD :** 6 tests vitest (registry, Ctrl+K = Cmd+K, ignore sans modifier, n'intercepte pas inputs, unregister à l'unmount)
  - **Note :** toast "persistant si critique" reste un upgrade ciblé du `useToastStore` existant (signal documenté dans shortcuts.md, refacto en follow-up).

---

### Phase D — Extension & optimisation guidée

> Objectif : optimiser sur données réelles, étendre l'architecture vers multi-machine et préparer la marketplace plugins.

- [x] **D.1** — Profiling activable + flamegraphs (py-spy)
  - Script wrapper `backend/scripts/profile.sh record|top` (auto-PID uvicorn ou `OMNIPLOT_PID=<pid>`)
  - Documentation `docs/profiling.md` (table py-spy/OTel/baseline + workflow d'investigation perf en 4 étapes)
  - **DoD :** flamegraphs reproductibles depuis fixtures, doc `docs/profiling.md` complète
  - **Note :** py-spy est sampling (zero-instrumentation), donc l'activation est attache-runtime — pas de feature flag dans le code. OTel spans (B.5) couvrent l'autre angle.
- [x] **D.2** — Rapport d'optimisation basé sur métriques réelles
  - `docs/perf-report.md` : top bottlenecks chiffrés (bitmap convert 71%, optimize 16%, gcode 12% ; vector dominé par optimize 69%), quick wins / medium refactors / long-term distingués
  - Estimation cumulée des quick wins : end-to-end `bitmap_photo` /draft ~640 → ~255 ms (-60%)
  - **DoD :** `docs/perf-report.md` chiffré, prioritisation justifiée, procédure de re-run documentée
- [x] **D.3** — Workspaces sauvegardables + Mode Atelier
  - Pinia store `useWorkspacesStore` : 2 built-ins (`Débutant` : Source/Style/Preview/Plot ; `Pro` : Layer Inspector / Pipeline Inspector / Queue / Machine Telemetry), workspaces custom avec `saveAs`/`rename`/`remove`, persistance localStorage
  - Composant `WorkshopMode.vue` : overlay plein écran avec gros indicateurs (état avec dot animé, nom, progression, hint d'action, Pause/Reprendre géants)
  - **DoD :** 16 tests vitest (store : 11 dont built-ins, switch, saveAs, rename, remove, corruption tolérée + workshop : 5)
  - **Note :** sync serveur des workspaces = V2 (décision arrêtée 2026-05-27 local-first).
- [x] **D.4** — Budgets SLO + alerting
  - `pen_plotter.domain.slo` : 7 budgets par défaut calibrés depuis `docs/perf-report.md` (preview draft 600 ms / standard 1500 / final 4000, upload editable 1500, gcode 400, queue start 2000, stream stall 10s)
  - 3 sévérités (healthy / warning / breach) avec `warn_breach_ratio` configurable, `min_samples` pour éviter alertes sur queue fraîche
  - Endpoints `GET /slo/budgets` (table) + `POST /slo/evaluate` (samples → BudgetReport)
  - Alerting : breach sur `alert_on_breach=True` émet log JSON structuré `slo_breach` (consommable par tout collecteur)
  - **DoD :** 12 tests (5 budget unit + 5 roll-up + 2 HTTP), suite full green
  - **Note :** dashboard Grafana JSON exporté = follow-up déploiement infra (le contrat HTTP est figé, n'importe quel collecteur OTLP peut alimenter l'évaluateur).
- [x] **D.5** — CI contract check + smoke perf gate
  - `backend/scripts/check_contracts.py` : compare backend vs `snapshot.json`, échec si entry drift sans bump de `manifest_version` ou si snapshot/backend désynchronisés
  - `backend/scripts/perf_gate.py` : run fixtures bitmap + vector, p95 vs `REFERENCE_P95`, échec si > `+allowed-regression-pct` (défaut 50%)
  - CI workflow `.github/workflows/ci.yml` étendu avec les deux gates
  - **DoD :** 6 tests unit du contract check (matching/missing/backend-ahead/entry-drift/snapshot-ahead/domain-missing), CI bloque les divergences non versionnées
- [x] **D.6** — Executor service boundary multi-machine (V2)
  - `pen_plotter.deployment` : 5 rôles (`monolith` / `api` / `render` / `executor` / `telemetry`) avec `RoleCapabilities` (serves_http / runs_queue_worker / owns_hardware_transport / ingests_telemetry)
  - Lifespan dans `main.py` honore le rôle : monolith garde v0.1 inchangé, autres rôles n'activent que les subsystems pertinents
  - Doc `docs/deployment.md` : matrice de rôles + 3 topologies exemples (appliance / two-machine workshop / render farm) + limites in-process actuelles
  - **DoD :** 13 tests (5 capabilities + résolution depuis env var, défaut, casing, fallback sur valeur inconnue), SQLite local conservé (Postgres adapter = future work documenté)
  - **Note :** la boundary est **in-process** aujourd'hui (le rôle conditionne quels composants se chargent, pas encore IPC). Le vrai split process avec messaging entre rôles est documenté comme follow-up audit #1 phase 3.
- [x] **D.7** — Tests e2e parcours complets
  - `tests/test_e2e_journeys.py` (TestClient pour bénéficier du lifespan complet) :
    - `test_fast_default_flow_resolves_and_uploads` : POST `/policy/resolve` → GET `/profiles` → POST `/upload` avec algorithm
    - `test_expert_override_flow_replaces_resolver_default` : démontre que `halftone` (override) émet `<circle>` même quand le resolver suggère `scanlines`
    - `test_error_flow_returns_normalized_api_error` : 404 sur `/manifests/<unknown>` retourne l'enveloppe normalisée `{code, path, details}`
    - `test_correlation_id_is_propagated_across_journey` : `X-Request-ID` echo sur 3 endpoints différents
    - `test_validation_error_is_pydantic_422` : payload invalide → 422 avec `detail`
  - **DoD :** 5 tests e2e exercent les 3 parcours canoniques + propagation des correlation IDs + validation pydantic
  - **Note :** suite Playwright pour le modal V2 frontend = follow-up (le modal vit derrière feature flag, branchera au flow prod après stabilisation). Les KPI temps-première-impression sont collectés par `usePerfStore` (C.8) et exposés via dashboard SLO (D.4).
- [x] **D.8** — SDK plugin externe + docs marketplace artefacts
  - Module `pen_plotter.sdk` : surface d'import stable réexportant `RasterAlgorithm`, `Converter`, `ToolChangeStrategyImpl`, `MachineProfile`, `PluginManifest` (alias de `Manifest`), `register_manifest`, etc.
  - Doc `docs/plugin-sdk.md` : 4 exemples concrets (raster algorithm, tool-change strategy, machine profile YAML, manifest domain custom)
  - Stratégie « write now, ne pas réécrire plus tard » : entry-point discovery est annoncée comme follow-up Phase B (mais le contrat reste le même)
  - **DoD :** 6 tests qui n'importent **que** depuis `pen_plotter.sdk` (vérifient surface __all__, subclass RasterAlgorithm, manifest registration custom, ToolChangeStrategyImpl subclassable, MachineProfile valide + capabilities dérivées)
  - **Note :** entry-point discovery (`[project.entry-points."omniplot.algorithms"]`) + marketplace signée arrivent en V2 (audit #1 phase 4).

---

## 4. Questions ouvertes restantes

À trancher en cours de route, non bloquantes :

- Détection bitmap_photo vs bitmap_illustration : seuil exact entropie ?
- Curseur Intent fast/balanced/quality : budget temps preview exact par niveau ?
- Cardinality budget métriques OTel : cap exact sur dimensions (algo × quality × profile × source_kind) ?
- Frontend perf overlay : périmètre exact des KPI affichés ?
- Workspaces : structure JSON exacte ?

---

## 5. Métriques baseline (à remplir après A.2)

> Mesurée sur fixtures de référence avant tout refacto métier.

> Détails complets et procédure de reproduction : `docs/perf-baseline.md`.

| Fixture                          | Phase    | p50 (ms) | p95 (ms) | p99 (ms) |
|----------------------------------|----------|----------|----------|----------|
| bitmap_photo (synthetic 128×128) | convert  |   550.86 |   629.10 |   629.10 |
| bitmap_photo (synthetic 128×128) | optimize |   106.28 |   262.61 |   262.61 |
| bitmap_photo (synthetic 128×128) | gcode    |    67.37 |    73.04 |    73.04 |
| vector_svg (synthetic 100×100)   | convert  |     0.38 |     0.44 |     0.44 |
| vector_svg (synthetic 100×100)   | optimize |     3.61 |     3.86 |     3.86 |
| vector_svg (synthetic 100×100)   | gcode    |     1.17 |     1.26 |     1.26 |

À enrichir au fur et à mesure (sous-phases segmentation/render séparées, fixtures réelles, hardware cible).

---

## 6. Métriques cibles v0.2 (SLO)

> À calibrer après baseline. Cibles indicatives.

| KPI                                       | Budget cible |
|-------------------------------------------|--------------|
| Preview draft p95                         | TBD ms       |
| Preview standard p95                      | TBD ms       |
| Preview final p95                         | TBD ms       |
| Upload → first editable result p95        | TBD s        |
| Generate gcode p95 (cas de référence)     | TBD s        |
| Queue start delay p95 (machine idle)      | TBD s        |
| Streaming stall timeout max               | TBD s        |
| Temps moyen pour première impression      | TBD          |
| Taux d'allers-retours dans le modal       | TBD          |

---

## 7. Journal de progression

> Une ligne par étape complétée. Format : `YYYY-MM-DD · étape · PR/commit · notes`.

| Date       | Étape | Référence  | Notes |
|------------|-------|------------|-------|
| 2026-05-27 | —     | initial    | Création de la roadmap, consolidation 7 audits |
| 2026-05-27 | A.1   | this PR    | Logging JSON + correlation IDs + `RequestContextMiddleware`; 9 tests; doc `docs/observability.md` |
| 2026-05-27 | A.2   | this PR    | OTel tracing opt-in (`OMNIPLOT_OTEL_ENABLED`), spans sur `convert_file`/`optimize_svg`/`generate_gcode`, baseline mesurée dans `docs/perf-baseline.md`, 5 tests |
| 2026-05-27 | A.3   | this PR    | Geometry IR (`SourceAsset`/`SegmentationArtifact`/`GeometryIR`/`PathPlanIR`/`MachineProgram`/`ExecutionRun`) + `artifact_hash` SHA-256 déterministe + adapter SVG→IR opt-in (`OMNIPLOT_IR_ENABLED`), 11 tests |
| 2026-05-27 | A.4   | this PR    | Système manifestes versionnés (`Manifest`/`ManifestEntry`/`Deprecation`), endpoints `/manifests` + `/manifests/{domain}`, erreurs normalisées (`ApiError`), `scripts/generate_openapi.py`, doc `docs/contract_architecture.md`, 7 tests |
| 2026-05-27 | A.5   | this PR    | Capability Model (`ToolingMode`/`CommandSource`/`RecoveryPolicy`/`MachineCapabilities`/`ToolChangeStrategy`), migration YAML additive (champ `capabilities` optionnel dérivé de `tool_change_method`), doc `profile_format.md` mise à jour, 11 tests |
| 2026-05-27 | A.6   | this PR    | Manifeste algorithmes (`/manifests/algorithms`) versionné, enveloppe Manifest standard, legacy `/algorithms` conservé, 7 tests |
| 2026-05-27 | A.7   | this PR    | Frontend zod schemas (`ManifestMeta`/`AlgorithmsManifest`/`ApiErrorBody`), client manifest live→cache→snapshot, `ManifestFallbackBanner.vue`, script `gen:manifests`, 8 tests vitest |
| 2026-05-27 | B.1   | this PR    | `AlgorithmPolicyResolver` (`domain/policy/`): matrice complète audit #4 + hard constraints (mégapixels/mono-pen/palette≤2), 41 tests |
| 2026-05-27 | B.2   | this PR    | `ToolChangeOrchestrator` + 4 stratégies (`FirmwareStrategy`/`HostMacroStrategy`/`ManualStrategy`/`SinglePenStrategy`) avec `SwapPlan`/`SwapContext`/`PauseKind` et substitution placeholders, 16 tests |
| 2026-05-27 | B.3   | this PR    | Recovery layer (`Directive`/`FailureKind`/`JobRecoveryOverride`/`resolve_recovery`) + table totale 3×5 + e2e pause→swap→resume préservant état, 23 tests |
| 2026-05-27 | B.4   | this PR    | Pinia `useAlgorithmsStore` adossé au manifeste versionné (A.4/A.7), bascule des 2 call sites legacy, fallback `source`/`fromFallback` exposés, 4 tests vitest |
| 2026-05-27 | B.5   | this PR    | Spans OTel sub-step sur pipeline bitmap (load/preprocess/fit_within/segment/render_layer/compose_svg), fixture `memory_exporter` mutualisée dans `conftest.py`, 3 tests dédiés |
| 2026-05-27 | B.6   | this PR    | 5 presets bundled (AxiDraw V3 / NextDraw A2 / iDraw A3 GRBL / Custom CoreXY A3 / CoreXY A3 rack avec host_macro complet), doc `docs/presets.md` avec capability matrix, 12 tests d'intégration |
| 2026-05-27 | C.1   | this PR    | `useUiModeStore` (assisted/expert + flags + disclosure level) avec persistance localStorage et override URL `?flag.X=1`, composable `useFeatureFlag`, composant `AssistantModeToggle.vue`, 9 tests vitest |
| 2026-05-27 | C.2   | this PR    | Endpoint backend `/policy/resolve` (wrap resolver B.1), zod schemas frontend, `EditModalV2.vue` 6 étapes (Source/Intent/Algo/Couleurs/Couches/Préflight) avec "Pourquoi ce choix ?" depuis `reasoning[]` et risques depuis `hard_constraints_applied[]`, 3+7 tests |
| 2026-05-27 | C.3   | this PR    | `LayerInspector.vue` (ordre + swap count + longueur agrégée) et `PipelineInspector.vue` (Source→Segmentation→Algo→Fallbacks→Contraintes depuis `PolicyDecision`), 7 tests vitest |
| 2026-05-27 | C.4   | this PR    | zod schemas `MachineCapabilities`, `CapabilityWizard.vue` (3 étapes, UI conditionnelle par mode), `MagazineView.vue` (slots + calibration + simulation highlight), 12 tests vitest |
| 2026-05-27 | C.5   | this PR    | `CompareView.vue` (A/B side-by-side + métriques diff avec winner highlight + overlay toggles `penup_heatmap`/`path_density`/`bounds`/`curvature`), 7 tests vitest |
| 2026-05-27 | C.6   | this PR    | `RunTimeline.vue` (phases + progression + badges terminaux) et `RunActionsPanel.vue` (Pause/Resume/Cancel avec confirm sécurisé + hint d'action), 14 tests vitest |
| 2026-05-27 | C.7   | this PR    | Endpoint SSE `/preview/stream` avec schéma `PreviewProgressEvent` stable + emitter synthétique, composable `useProgressiveStream`, 3+6 tests |
| 2026-05-27 | C.8   | this PR    | `usePerfStore` (ring buffer 200 + summary p50/p95) + `usePerfTracker` (time/timeAsync + slow-interaction auto-detect) + `PerfOverlay.vue` activé via `?flag.perf=1`, 13 tests vitest |
| 2026-05-27 | C.9   | this PR    | i18n FR/EN clés `v2.*`, `useKeyboardShortcuts` + `SHORTCUTS` registry (6 bindings), doc `docs/shortcuts.md`, 6 tests vitest |
| 2026-05-27 | D.1   | this PR    | `scripts/profile.sh record\|top` (py-spy wrapper avec auto-PID uvicorn), `docs/profiling.md` (workflow d'investigation 4 étapes : baseline → OTel → py-spy → delta) |
| 2026-05-27 | D.2   | this PR    | `docs/perf-report.md` : 3 bottlenecks bitmap chiffrés (B1-B3), 4 quick wins prioritisés avec gain estimé ~640→~255 ms sur preview draft, sections medium/long-term reliant à #1 audit |
| 2026-05-27 | D.3   | this PR    | `useWorkspacesStore` (Débutant/Pro built-ins + custom saveAs/rename/remove + persistance localStorage), `WorkshopMode.vue` (overlay plein écran exécution live), 16 tests vitest |
| 2026-05-27 | D.4   | this PR    | `domain/slo/` (7 budgets par défaut + `evaluate_budgets` avec severity healthy/warning/breach) + endpoints `/slo/budgets` et `/slo/evaluate` + structured log `slo_breach`, 12 tests |
| 2026-05-27 | D.5   | this PR    | `scripts/check_contracts.py` + `scripts/perf_gate.py` + workflow CI étendu, 6 tests unit du contract check |
| 2026-05-27 | D.6   | this PR    | `pen_plotter.deployment` (5 process roles avec capabilities), lifespan conditionnel sur le rôle, `docs/deployment.md` (matrice + 3 topologies), 13 tests |
| 2026-05-27 | D.7   | this PR    | `tests/test_e2e_journeys.py` (5 parcours canoniques : fast default, expert override, normalized error, correlation IDs, validation 422) avec TestClient pour exercer la lifespan complète |
| 2026-05-27 | D.8   | this PR    | `pen_plotter.sdk` (réexport stable de RasterAlgorithm / Converter / ToolChangeStrategyImpl / MachineProfile / PluginManifest) + `docs/plugin-sdk.md` (4 exemples concrets), 6 tests qui n'importent que via sdk |
| 2026-05-27 | bugfix | this PR    | « Éditer » un fichier ne le pose plus sur le plan : flag `is_library_draft` sur `Placement` + computed `visiblePlacements`, `editFile()` réutilise un draft existant, bouton « Ajouter au plan » dans `UploadFooter`, i18n FR/EN, 3 tests vitest |

---

## 8. Règles de mise à jour de ce document

1. **À chaque PR** qui complète une étape : cocher la case correspondante, ajouter une ligne au journal §7.
2. **À chaque décision technique** non triviale prise en cours : ajouter dans §2 ou §4.
3. **À chaque mesure baseline** réalisée : remplir §5.
4. **À chaque calibration SLO** : remplir §6.
5. **À chaque nouveau blocage** : marquer `[!]` et expliquer en commentaire dans le PR.
6. Le fichier est **commit dans le même PR que le code livré** pour cette étape.

---

*Document créé le 2026-05-27 — basé sur 7 audits cumulés (architecture, tool-change, algorithm policy, matrice décisionnelle, contrat de données, observabilité, UX opérateur) et décisions techniques arrêtées.*
