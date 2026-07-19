# Chantiers v2 — implémentation du 2026-07-19

> Suite de l'audit exhaustif du même jour
> (`audit_exhaustif_2026-07-19.md`) : les 8 chantiers v2 identifiés ont
> été traités dans la foulée. État final ci-dessous, avec ce qui reste
> à la main de l'opérateur.

## Livré dans cette série de commits

| # | Chantier | État | Où |
| --- | --- | --- | --- |
| 1 | Protection de branche `main` | **Documenté** (l'activation est un clic admin GitHub, pas du code) | `docs/repo_settings.md` |
| 2 | Queue temps réel WebSocket | **Livré** — `/ws/queue` pousse la liste de runs à chaque mutation ; le polling 3 s devient un heartbeat lent de repli | `queue.py` (pub/sub), `api/queue.py` (WS), `stores/queue.ts` |
| 3 | Prompts de swap i18n | **Livré** — champs structurés `swap_color` / `swap_label` / `swap_reason` de `SwapAction` jusqu'au run et au WS ; le modal compose le texte FR/EN, fallback anglais pour les runs antérieurs | `streamer.py`, `toolchange.py`, `SwapPromptModal.vue`, locales |
| 4 | Per-layer riche dans Modal V2 + suppression v1 | **Déjà livré par le refactor éditeur** (constat) : v1 supprimé du code, per-layer/per-pass via `LayersSection` dans l'onglet Couches du panneau expert ; dette lint soldée par policy scoped documentée. TODO 1.1 / 6.1 mis à jour | `docs/TODO.md` |
| 5 | Pipeline IR direct | **Livré** — consommateur vpype direct (`_doc_from_ir_layer`) + émetteur G-code direct (`_layers_from_geometry_ir`), équivalence stricte testée. Mesure container : gcode −69 à −85 %, optimize −8 à −48 % | `toolpath.py`, `gcode.py`, `test_ir.py` |
| 6 | Audit perf Pi | **Partie automatisable livrée** — banc `perf_ir_compare.py` + procédure complète. Les mesures sur matériel restent à faire | `backend/scripts/perf_ir_compare.py`, `docs/perf_pi_procedure.md` |
| 7 | Overlays penup/densité | **Livré, recadré** — la surface Compare drawer n'existait plus ; les overlays atterrissent sur le simulateur G-code (toggles 🔥 heatmap pen-up et ▦ densité) | `SimCanvas.vue`, `SimControls.vue`, `Simulator.vue` |
| 8 | Suite Playwright étoffée | **Livré** — parcours queue+swap en 3 tests (API structuré, frames `/ws/queue`, modal UI → Resume → completed) ; 14/14 e2e verts en local | `frontend/e2e/queue-swap-parcours.spec.ts` |

## Ce qui reste à la main de l'opérateur

1. **Activer la protection de branche** — 2 minutes dans
   GitHub → Settings → Branches, configuration exacte dans
   `docs/repo_settings.md`. C'est le seul rempart durable contre les
   drifts de snapshot silencieux (deux récidives à ce jour).
2. **Dérouler `docs/perf_pi_procedure.md` sur un Pi réel** (~30 min).
   Si le banc confirme la parité IR (attendu, l'avantage container est
   net), basculer `OMNIPLOT_IR_ENABLED` à on par défaut dans
   `domain/ir/adapter.py` — dernier reste de TODO 2.1.
3. **`curvature`** (3e overlay historique) reste non implémenté —
   demande une géométrie que le parseur G-code frontend ne calcule
   pas ; à re-scoper seulement si un besoin opérateur concret émerge.

## Vérifications finales

Backend : ruff 0, mypy strict 0, pytest complet vert. Frontend :
eslint 0/0, vue-tsc 0, vitest complet vert, build OK. E2E : 14/14 en
local (fake hardware). Drift checks OpenAPI / types TS / manifests : 0.
