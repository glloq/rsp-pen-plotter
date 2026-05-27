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
- [ ] **A.4** — Système de manifestes versionnés + génération types frontend
  - Modèle générique `PluginManifest` (algorithms, profiles, presets, plans…)
  - Endpoints `/manifests/{domain}` versionnés (`manifest_version: int`)
  - Metadata : `manifest_version`, `generated_at`, `deprecations`, `feature_flags`
  - Erreurs normalisées RFC 7807-like (`code`, `message`, `details`, `path`)
  - OpenAPI → `openapi-typescript` en CI
  - Snapshot build-time pour fallback frontend
  - **DoD :** types TS générés en CI, snapshot embarqué, tests de contrat
- [ ] **A.5** — Capability Model dans profil machine + migration YAML additive
  - Enums : `ToolingMode`, `CommandSource`, `RecoveryPolicy`
  - Schéma `capabilities` + `tool_change_strategy` séparés de `tool_change_method`
  - Migration additive : anciens profils restent valides, mapping vers nouveau modèle
  - Validation Pydantic stricte avec erreurs explicites
  - Doc `docs/profile_format.md` mise à jour
  - **DoD :** tous les profils existants chargent sans warning, nouveaux champs validés, tests parsing
- [ ] **A.6** — Manifeste algorithmes versionné (consommateur du système A.4)
  - Manifestes par algo : id, version, kind, complexity, params + bornes + defaults, presets recommandés
  - Suppression progressive des `_ALGORITHMS`/`_KINDS`/`_COMPLEXITY` hardcodés
  - Registry dynamique (chargement depuis manifestes)
  - `cost_estimate(inputStats)` exposé
  - **DoD :** `/algorithms` retourne des manifests, plus aucun default critique dupliqué front/back
- [ ] **A.7** — Validation runtime frontend (zod) + erreurs normalisées + fallback
  - Schémas zod pour payloads API critiques (algorithms, profiles, jobs, runs)
  - Indicateur UI quand fallback manifeste actif (snapshot build-time ou cache localStorage)
  - Mapping erreurs backend → toasts actionnables
  - **DoD :** parsing strict des manifestes en frontend, UI affiche cause + action en cas de mismatch

---

### Phase B — Logique métier

> Objectif : consommer les fondations Phase A pour livrer les briques métier (resolver, orchestrator, recovery).
> Découpage PR : 1 PR par module métier.

- [ ] **B.1** — `AlgorithmPolicyResolver` avec matrice décisionnelle (audit #4)
  - Entrées : `source_kind`, `goal`, `palette_mode`, `available_colors_count`, `image_megapixels`, `layer_count_estimate`, `machine_profile`
  - Sorties : `segmentation_method`, `default_algorithm`, `default_options`, `quality_tier`, `fallback_chain`, `reasoning`, `hard_constraints_applied`
  - Implémentation des matrices A/B/C/D/E de l'audit #4
  - Hard constraints perf (mégapixels, mono-pen, palette ≤2)
  - **DoD :** tests unitaires sur toutes les branches de la matrice, snapshot des reasoning
- [ ] **B.2** — `ToolChangeOrchestrator` + 4 stratégies
  - Stratégies : `FirmwareStrategy`, `HostMacroStrategy` (YAML), `ManualStrategy`, `SinglePenStrategy`
  - Capability resolver dérive le plan opératoire depuis profil + job
  - Sélection auto via Capability Model
  - **DoD :** tests E2E sur les 4 modes, génération prompts manuels, fallback de mode
- [ ] **B.3** — Pipeline pause/resume robuste + RecoveryPolicy
  - Politique appliquée : profil par défaut, override par job
  - Reprise après pause/changement avec checkpoint
  - **DoD :** test scenario pause → swap → resume sans perte d'état
- [ ] **B.4** — Frontend : consommation dynamique des manifestes
  - Suppression des defaults/options hardcodés critiques
  - Formulaires algo générés depuis JSON Schema
  - Conservation fallback minimal (snapshot build-time)
  - **DoD :** un nouvel algo backend devient exploitable frontend sans patch type/schema
- [ ] **B.5** — Instrumentation détaillée par phase pipeline
  - Spans OTel sur sous-étapes : parse/upload, preprocess, segmentation, render (par couche/pass), optimize, gcode
  - Métriques cache (hit/miss/eviction), workers (spawn, queue wait, active), queue (delay, duration, abort)
  - **DoD :** dashboard Grafana "Pipeline" complet, cardinality budget respecté
- [ ] **B.6** — Presets plotters marché (≥4) + docs capability matrix
  - Profils : AxiDraw, NextDraw, iDraw/EleksDraw (GRBL), custom CoreXY
  - Documentation `docs/presets/` avec capability matrix par preset
  - **DoD :** 4 profils chargent et passent les tests d'intégration, doc disponible

---

### Phase C — UX opérateur

> Objectif : livrer l'expérience opérateur cible (modes Assisté/Expert, modal V2, vues avancées, queue UX pro).
> Découpage PR : 1 PR par vue majeure.

- [ ] **C.1** — Architecture 2 modes (Assisté / Expert) + feature flags + mémorisation user
  - Toggle par tâche dans modal, persisté en localStorage
  - **DoD :** mode mémorisé entre sessions, switch sans perte de contexte
- [ ] **C.2** — Modal V2 refondu en 6 étapes
  - Étapes : Source Prep → Intent → Algo recommandé → Couleurs/Pens → Couches/Passes → Préflight
  - « Pourquoi ce choix ? » généré dynamique depuis `reasoning` du resolver
  - ETA visible en continu
  - Indicateurs de risque (couches, swaps, bounds, coût algo)
  - **DoD :** parcours fast-default e2e < N étapes, override expert accessible
- [ ] **C.3** — Layer Inspector + Pipeline Inspector
  - Layer Inspector : ordre réel, coût par couche, pauses/swaps attendus
  - Pipeline Inspector : segmentation, algo/passes par couche, optimisations appliquées
  - **DoD :** consomme IR + spans OTel, lisible non-techniciens
- [ ] **C.4** — Wizard capability + vue magazine améliorée
  - Wizard configuration "capacité plotter"
  - UI conditionnelle selon mode tool-change
  - Vue magazine : slots, calibration, install state, simulation
  - **DoD :** un opérateur novice configure un nouveau plotter sans aide
- [ ] **C.5** — Compare Mode A/B + overlays debug
  - A/B visuel 2 presets/algos avec métriques (temps, travel, swaps)
  - Overlays : pen-up heatmap, path density, bounds/margins warnings, curvature stress
  - **DoD :** comparaison side-by-side, métriques côte à côte
- [ ] **C.6** — Queue UX pro avec timeline + checkpoints + actions sécurisées
  - Timeline : queued → running → pause → resume → done/fail
  - Détails run : checkpoint actuel, raison pause, prochaine action
  - Actions sécurisées : confirm pause/abort, reprise guidée
  - Historique : jobs récents, erreurs, replay context
  - **DoD :** opérateur comprend l'état d'un run sans lire de logs
- [ ] **C.7** — Progressive preview SSE/WS
  - Stream partial layers + métriques pendant calcul
  - **DoD :** preview heavy ne bloque plus l'UI, progression visible
- [ ] **C.8** — Frontend perf overlay + KPI tracking
  - Overlay activable `?perf=1` + feature flag serveur
  - KPI : time-to-first-preview, preview-refresh latency, interactions lentes (>100ms), frame drops, erreurs réseau
  - **DoD :** overlay accessible en prod sous flag, KPI remontés en métriques
- [ ] **C.9** — i18n FR/EN + microcopy standardisé + raccourcis clavier
  - Standardisation textes (action / conséquence / recommandation)
  - Toasts non intrusifs + persistants si critique
  - Raccourcis clavier documentés
  - **DoD :** parcours complet en FR et EN, raccourcis dans `docs/shortcuts.md`

---

### Phase D — Extension & optimisation guidée

> Objectif : optimiser sur données réelles, étendre l'architecture vers multi-machine et préparer la marketplace plugins.

- [ ] **D.1** — Profiling activable + flamegraphs (py-spy)
  - Feature flag profiling, profils ciblés (tsp, voronoi, flowfield, segmentation, preview HQ)
  - **DoD :** flamegraphs reproductibles depuis fixtures, doc `docs/profiling.md`
- [ ] **D.2** — Rapport d'optimisation basé sur métriques réelles
  - Top 10 bottlenecks mesurés, quick wins, medium refactors, long-term
  - **DoD :** `docs/perf-report.md` chiffré, prioritisation justifiée
- [ ] **D.3** — Workspaces sauvegardables + Mode Atelier
  - Workspaces local (localStorage) avec layouts Beginner / Pro
  - Mode Atelier : UI simplifiée en exécution live
  - **DoD :** layouts persistés, mode atelier accessible en 1 clic
- [ ] **D.4** — Budgets SLO + alerting
  - Budgets : preview draft/standard/final, upload → editable, gcode gen, queue start delay, stream stall
  - Alertes sur dépassements répétés
  - **DoD :** dashboard "SLO" actif, alertes testées
- [ ] **D.5** — CI contract check + smoke perf gate
  - Diff snapshots manifestes bloque merge sans bump version
  - Smoke perf gate (régression > seuil vs baseline)
  - **DoD :** CI bloque les divergences non versionnées, perf gate documenté
- [ ] **D.6** — Executor service boundary multi-machine (V2)
  - Split process : API Gateway / Render Worker / Executor / Telemetry
  - SQLite local conservé, adaptateur Postgres optionnel
  - **DoD :** mode mono-process et multi-process testés
- [ ] **D.7** — Tests e2e parcours complets
  - Fast default flow, override expert flow, erreur + recovery flow
  - KPI mesurables : temps première impression, réduction erreurs config
  - **DoD :** suite e2e dans CI, KPI trackés
- [ ] **D.8** — SDK plugin externe + docs marketplace artefacts
  - Documentation interface plugin (algorithms, converters, machines)
  - **DoD :** un dev tiers peut écrire un plugin sans toucher au cœur

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
