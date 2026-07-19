# Audit de préparation — implémentation P3 (tolérances en mm réels + doc levées)

> Suite de `audit_optimisation_trace_2026-07-19.md` (F3 + F4, priorité P3).
> Ce document est la spécification d'implémentation ; il a été préparé pour
> être exécuté tel quel, fichier par fichier.

## Rappel du problème (F3)

`optimize_svg` passe `merge_tolerance_mm` / `simplify_tolerance_mm` à vpype
comme nombres nus dans le repère du `viewBox`. Pour un pivot **raster**, ce
repère est en pixels image : sur une image 4 000 px imprimée en 280 mm,
« 0,05 mm » vaut 0,0035 mm réels — simplification et fusion deviennent
inopérantes, silencieusement, selon la résolution du fichier source. Pour un
pivot déjà en mm (texte, composite), le comportement actuel est correct et ne
doit pas changer.

## Conception retenue

Un facteur **`units_per_mm`** (unités utilisateur par millimètre imprimé),
optionnel de bout en bout :

1. fourni par le client (`POST /optimize`) qui connaît la taille d'impression
   (`source_bbox` en unités ÷ `width_mm` du placement) ;
2. sinon auto-détecté depuis la racine SVG quand `width` porte une unité
   physique (`mm`/`cm`/`in`) et qu'un `viewBox` existe :
   `units_per_mm = viewBox_width / width_en_mm` ;
3. sinon `1.0` — comportement strictement identique à aujourd'hui.

Toutes les tolérances sont multipliées par ce facteur avant l'appel vpype :
`merge`, `simplify` (y compris les valeurs par calque), et la
`closed_tolerance` de la rotation de couture. `_QUANTIZATION` reste hors
périmètre (partagé avec la lecture G-code).

## Modifications backend (`backend/pen_plotter/`)

### `core/toolpath.py`

- `optimize_svg(svg, *, layers=None, merge_tolerance_mm=0.1, units_per_mm=None)`
  (idem `optimize_geometry_ir`) — nouveau paramètre `units_per_mm: float | None`,
  transmis à `_optimize_svg`.
- `_optimize_svg` : au début, `scale = units_per_mm or _detect_units_per_mm(root) or 1.0` ;
  dans la boucle par calque, passer `simplify * scale` et
  `merge_tolerance_mm * scale` à `_pipeline`, et
  `closed_tolerance=merge_tolerance_mm * scale` à `_refine_doc_order`.
- Nouveau `_detect_units_per_mm(root: ET.Element) -> float | None` :
  parse `root.get("width")` avec le motif `^([0-9.]+)\s*(mm|cm|in)$`
  (mm=1, cm=10, in=25.4) + `viewBox` présent → `vb_width / width_mm`.
  Retourne `None` pour une largeur sans unité (px) ou absente, une
  valeur non positive, ou sans viewBox.

### `api/optimize.py`

- `OptimizeRequest` : nouveau champ `units_per_mm: float | None = Field(default=None, gt=0)`.
- Le transmettre aux deux chemins (`optimize_svg` et `optimize_geometry_ir`).

### `application/text_render.py`

- Aucun changement : le SVG re-rendu/baké porte `width="…mm"` → l'auto-
  détection rend 1,0 (à couvrir par un test si simple).

## Modifications frontend (`frontend/src/`)

- `api/client.ts` → `optimizeToolpaths(svg, layers, signal?, unitsPerMm?)` :
  ajouter le champ `units_per_mm: unitsPerMm ?? null` au corps
  (attention : `signal` est 3ᵉ paramètre — ajouter `unitsPerMm` en 4ᵉ pour ne
  pas casser les appels existants).
- `stores/job.ts` :
  - petite fonction locale `placementUnitsPerMm(p): number | undefined` =
    `(p.source_bbox.x_max - p.source_bbox.x_min) / p.width_mm` si les deux
    sont > 0, sinon `undefined` ;
  - `optimize()` : la calculer pour le placement sélectionné et la passer ;
  - `generate()` : l'ajouter à chaque entrée de `deps.placements`.
- `application/runGeneratePipeline.ts` : `PipelinePlacement` gagne
  `unitsPerMm?: number` ; le passer à `optimizeToolpaths`.

## Tests

### Backend (`tests/test_toolpath.py`)

1. `test_units_per_mm_scales_merge_tolerance` : SVG `viewBox="0 0 400 400"`
   sans unité, un calque avec deux segments colinéaires séparés d'un trou de
   0,3 unité (ex. `M0 0 L10 0` puis `M10.3 0 L20 0`, plus un 3ᵉ chemin
   éloigné pour éviter l'early-exit). Avec `units_per_mm=4` (400 px = 100 mm),
   la tolérance de fusion 0,1 mm → 0,4 unité : les deux segments fusionnent
   (pen_up_after < pen_up sans le paramètre, ou nombre de chemins réduit —
   vérifier via `_doc_from_svg(result.svg)`). Sans le paramètre : pas de
   fusion.
2. `test_units_per_mm_autodetected_from_physical_width` : même géométrie avec
   `width="100mm" height="100mm" viewBox="0 0 400 400"` et **sans** le
   paramètre → même fusion (auto-détection).
3. `test_units_per_mm_default_keeps_mm_svgs_unchanged` : sur `TWO_LAYERS`
   existant, résultat identique avec et sans `units_per_mm=1.0`.

### Backend (`tests/test_api.py` ou fichier du routeur optimize)

- Requête `/optimize` avec `units_per_mm` invalide (0 ou négatif) → 422.
  (Chercher les tests existants de `/optimize` et s'aligner sur leur style.)

### Frontend

- Adapter les tests existants qui moquent `optimizeToolpaths` si la nouvelle
  signature les casse (paramètre optionnel : normalement non). Ajouter un
  assert simple dans un test existant du store si peu coûteux, sinon s'en
  tenir à la compilation `vue-tsc` + tests existants verts.

## F4 — documentation du coût des levées

Dans `wiki/Picking-the-Right-Algorithm.md`, ajouter une courte section
« Pen lifts are the hidden cost » (suivre la langue du fichier) : après
optimisation des trajets, 46–80 % du temps résiduel des styles denses part
en cycles levée/descente ; même remplissage : `eulerian_hatch` ≈ 19 chemins,
`crosshatch` ≈ 86, `dashes` ≈ 2 987 ; conseils : préférer les styles
« serpentine » pour les grands aplats, calibrer `pen_lift_time_ms` et le
dwell servo du profil. Référencer `docs/audit_optimisation_trace_2026-07-19.md`.

## Clôture de l'audit principal

Dans `docs/audit_optimisation_trace_2026-07-19.md` : annoter F3
« ✅ corrigé » (note de statut au-dessus du texte d'origine, comme F1/F2) et
F4 « ✅ doc ajoutée », mettre à jour la ligne P3 du tableau de synthèse.

## Mécanique CI (obligatoire, dans cet ordre)

```bash
cd /home/user/rsp-pen-plotter/backend
.venv/bin/ruff check pen_plotter tests
.venv/bin/python -m mypy pen_plotter
.venv/bin/python -m pytest tests/test_toolpath.py tests/test_text_render.py tests/test_pathsort.py -q
.venv/bin/python scripts/generate_openapi.py > openapi.json   # OptimizeRequest change
.venv/bin/python -m pytest -q                                  # suite complète
cd /home/user/rsp-pen-plotter/frontend
npm run gen:types            # régénère src/domain/api-types.ts
npx vue-tsc --noEmit
npm test
npx prettier --check "src/**/*.{ts,vue,json,css}"
npx eslint --ext .ts,.vue src
```

Commit unique en français (convention du dépôt), poussé sur
`claude/optimisation-trace-gcode-4xemoj`. **Pas de pull request.**
