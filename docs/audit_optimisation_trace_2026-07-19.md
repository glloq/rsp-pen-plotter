# Étude — optimisation du tracé avant le passage au G-code

> Périmètre : tout ce qui décide de l'**ordre, du sens et du découpage des
> chemins** entre la sortie d'un style (raster, vecteur, texte) et l'émission
> du G-code — c'est-à-dire ce qui pilote les trajets pen-up et le nombre de
> levées/descentes de stylo, quel que soit le style utilisé. **Hors
> périmètre** : le contenu dessiné par les algorithmes (densité, esthétique),
> l'exécution machine (streamer, flow-control — voir
> `audit_gcode_pipeline.md`).
>
> Méthode : lecture du pipeline + **banc d'essai reproductible**
> (`backend/scripts/toolpath_travel_bench.py`) sur les sorties réelles de six
> algorithmes du dépôt, comparant l'optimiseur actuel à quatre variantes.
>
> État global : **sain**. L'optimiseur actuel capte déjà l'essentiel du gain
> possible (pen-up divisé par 15 à 40 sur les styles denses). Les constats
> ci-dessous sont un vrai trou sur le chemin texte (F1 — ✅ corrigé), deux
> améliorations mesurées mais de second ordre (F2 — ✅ corrigé, F5), un bug
> d'early-exit découvert pendant les correctifs (F7 — ✅ corrigé), et un
> recadrage utile : après tri, ce sont **les levées de stylo qui dominent
> le temps résiduel**, pas les trajets (F4).

---

## 1. Cartographie du pipeline actuel

Le flux nominal (frontend `application/runGeneratePipeline.ts`, déclenché par
« Générer ») est : **optimize → preflight → generate**.

1. **Optimize** — `POST /optimize` par placement →
   `core/toolpath.optimize_svg` : pour chaque calque étiqueté, vpype exécute
   `linemerge --tolerance 0.1` → `linesimplify --tolerance 0.05` →
   `linesort` (`_pipeline`, `core/toolpath.py:83`). `linesort` (vpype 1.15)
   est un **glouton plus-proche-voisin avec inversion de sens** des chemins ;
   les métriques avant/après (pen-up) remontent à l'UI. Réglages par calque :
   `optimize` (défaut `true`), `simplify_tolerance_mm` (défaut 0,05) ; le
   toggle `autoOptimize` du store est aussi `true` par défaut
   (`stores/job.ts:521`).
2. **Preflight / Generate** — le SVG optimisé est recomposé (composite
   multi-placements, coordonnées atelier en mm) puis `core/gcode.py` relit
   les calques via vpype (`_read_layers`) **en préservant l'ordre du
   document** — l'ordre choisi par `linesort` est donc bien celui plotté
   (vérifié). Chaque polyligne émet `pen_up → G0 → pen_down → G1…`
   (`_generate_gcode_impl`, `core/gcode.py:663-691`).

Points confirmés sains au passage :

- early-exit mono-chemin (économise ~100 ms vpype sur les cas triviaux,
  `core/toolpath.py:227-241`) ;
- l'ordre des calques = l'ordre des stylos ; le regroupement pour minimiser
  les changements d'outil existe côté UI (`lib/penorder.ts`) — l'optimiseur
  travaille à raison **par calque**, un changement de stylo coûtant bien plus
  cher qu'un trajet ;
- coût CPU du pipeline actuel : 0,05–1,6 s par calque sur ce banc (machine de
  dev ; compter ×5–10 sur Pi) — compatible avec la cible Pi ;
- `core/tsp.py` (plus-proche-voisin, 2-opt à budget temps, MST+DFS) existe
  déjà mais n'est consommé que par le style `tsp_opt` — pas par l'optimiseur
  de tracé.

---

## 2. Mesures

Banc : masque disque 400×400, modèle de temps du profil `custom_plotter.yaml`
(dessin 60 mm/s, trajet 120 mm/s, levée+descente 2 × 0,15 s par chemin,
1 unité = 1 mm). Variantes : **V0** brut, **V1** pipeline actuel, **V2**
V1 + `linesort --two-opt`, **V3** V1 + tri « loop-aware » (les boucles
fermées peuvent être entamées à n'importe quel sommet — rotation de la
couture), **V4** V3 + two-opt.

| Style | Pen-up V0 | V1 (actuel) | V2 | V3 | V4 | Temps total V1 → V4 |
|---|---|---|---|---|---|---|
| crosshatch | 22 037 | 481 | 481 | 481 | 481 | 6,6 → 6,6 min |
| dashes | 26 339 | 9 978 | 9 396 | 9 978 | 9 396 | 18,8 → 18,7 min |
| stippling | 134 362 | 7 770 | 6 728 | 7 469 | **6 608** | 6,3 → 6,2 min |
| circle_pack | 249 299 | 11 322 | 9 797 | 9 225 | **8 198** | 17,3 → 16,9 min |
| contours | 323 946 | 8 439 | 7 828 | 7 977 | **7 626** | 15,7 → 15,6 min |
| eulerian_hatch | 908 | 300 | 180 | 300 | 180 | 6,4 → 6,3 min |

Décomposition du temps **après** optimisation actuelle (V1) :

| Style | Dessin | Trajets pen-up | Levées/descentes | Part levées |
|---|---|---|---|---|
| crosshatch (86 chemins) | 368 s | 4 s | 26 s | 7 % |
| dashes (2 987 chemins) | 148 s | 83 s | 896 s | **80 %** |
| stippling (886 chemins) | 50 s | 65 s | 266 s | **70 %** |
| circle_pack (1 607 chemins) | 463 s | 94 s | 482 s | 46 % |
| contours (1 928 chemins) | 291 s | 70 s | 578 s | **62 %** |
| eulerian_hatch (19 chemins) | 374 s | 3 s | 6 s | 2 % |

Lecture :

- **V1 fait déjà l'essentiel** : −94 à −97 % de pen-up vs brut sur les styles
  denses (contours : 324 k → 8,4 k). Le glouton de vpype est un bon choix.
- Les raffinements de tri (V2–V4) gagnent encore **−6 à −28 % de pen-up**
  (le loop-aware bat le two-opt sur les cercles fermés, et les deux se
  cumulent), mais comme le trajet ne pèse plus que 4–9 % du temps total
  après V1, cela ne rend que **0,5 à 2,5 % de temps de plottage**.
- Le poste dominant après V1 est **le cycle levée/descente** (46–80 % sur les
  styles denses) — voir F4.
- Coût CPU des raffinements : two-opt +1–2 s, loop-aware +0,1–0,4 s par
  calque sur ce banc (× 5–10 sur Pi).

---

## 3. Constats

### F1 — **[HAUTE — ✅ corrigé]** Un job texte re-rendu au `/generate` n'est **jamais optimisé**

> **Statut : corrigé** dans ce même lot. `plan_with_rerendered_svg`
> passe désormais le SVG re-rendu par `optimize_svg` **après** le bake de
> la transform de placement, en honorant les réglages `optimize` /
> `simplify_tolerance_mm` portés par les `LayerPlan` du plan, avec repli
> silencieux sur le rendu brut si l'optimiseur échoue (le rerender ne
> bloque jamais la génération). Tests :
> `test_plan_with_rerendered_svg_optimizes_toolpaths` et
> `test_plan_with_rerendered_svg_falls_back_when_optimize_fails`.
> Description d'origine conservée ci-dessous pour traçabilité.

Pour un source `text/plain` / `text/markdown` avec plan typographique,
`run_generate` (et `run_preflight`) remplacent le SVG du plan par un rendu
frais : `plan_with_rerendered_svg` (`application/generate_service.py:113`,
`application/text_render.py:246`). Ce rendu sort **directement du
convertisseur Hershey** et part au G-code tel quel : l'optimisation que le
frontend avait appliquée au placement est **écrasée**, et rien ne ré-optimise
côté backend.

Mesuré (page A4, Hershey 6 mm, ~18 lignes de texte) : pen-up **8 089** unités
en l'état vs **4 380** après le pipeline d'optimisation (−46 %), et 24 chemins
fusionnables par `linemerge`. Soit ~30 s de trajets perdus par page dense —
proportionnel au volume de texte. Le préflight utilisant le même SVG,
l'estimation reste cohérente… avec un plottage sous-optimal.

**Piste** : appliquer `optimize_svg` (ou au minimum `linemerge → linesort`)
sur le SVG re-rendu dans `plan_with_rerendered_svg` — coût mesuré < 1 s par
page, borné par le même early-exit que `/optimize`. Attention à le faire
**après** `_bake_placement_transform` (le SVG re-rendu porte la transform de
placement sur ses groupes ; l'optimiseur doit voir la géométrie finale) et à
garder preflight/generate alignés (les deux passent par le même helper).

### F2 — **[MOYENNE — ✅ corrigé]** Le tri peut encore gagner −10 à −28 % de pen-up (rotation de couture + 2-opt)

> **Statut : corrigé** dans ce même lot. Nouveau module
> `core/pathsort.py` (`improve_order`) branché dans
> `core/toolpath._optimize_svg` après le pipeline vpype : rotation de
> couture des boucles fermées (glouton loop-aware) puis 2-opt au niveau
> des chemins **à budget temps** (1,5 s/calque, candidats kd-tree — même
> approche que `core/tsp.py`), sans jamais dégrader l'ordre d'entrée.
> Opt-out par calque via `LayerOptimization.seam_rotation` (défaut
> activé), exposé dans l'OpenAPI. Gains mesurés en intégration :
> stippling 7 770 → 6 849, circle_pack 11 322 → 8 539, contours
> 8 439 → 7 694, pour +0,3 à 0,6 s de CPU par calque. Tests :
> `test_pathsort.py`, `test_optimize_rotates_closed_loop_seams`,
> `test_optimize_seam_rotation_keeps_loops_closed`.
> Description d'origine conservée ci-dessous.

Deux limites du `linesort` actuel, mesurées ci-dessus :

1. **Couture figée des boucles fermées.** Un chemin fermé (cercles de
   `circle_pack`, niveaux de `contours`, `rings`, `honeycomb`,
   `voronoi_*`…) n'est abordable que par son point de départ d'origine.
   Autoriser l'entrée à n'importe quel sommet (rotation de la couture) rend
   −19 % de pen-up sur `circle_pack` à coût quasi nul (+0,1–0,4 s). Le
   prototype tient en ~60 lignes (voir `loop_aware_sort` dans le banc).
   Nuance qualité : la couture se déplace là où passe le trajet — sur un
   motif régulier, cela peut créer un alignement de coutures visible
   (c'est la raison d'être de `reloop` chez vpype, qui la **randomise**).
   À exposer en option par calque, défaut activé.
2. **Pas de raffinement local.** `linesort --two-opt` existe déjà dans vpype
   et rend −6 à −13 % de pen-up supplémentaires. Son implémentation est
   bornée en **passes** (250), pas en temps — sur Pi, préférer le
   `two_opt_improve` **à budget temps + kd-tree** déjà présent dans
   `core/tsp.py` (écrit pour ça, jamais branché sur le pipeline), ou gater le
   two-opt vpype sur le nombre de chemins.

À vendre honnêtement : sur le temps total, ces deux améliorations cumulées
rendent **0,5 à 2,5 %** (le trajet ne domine plus après V1). Ça reste le seul
gain générique restant côté tri, il est simple et sans risque de régression
visuelle majeure — mais ce n'est pas lui qui changera la durée d'un plot.

### F3 — **[MOYENNE]** Les tolérances « _mm » s'appliquent en unités utilisateur du SVG

`merge_tolerance_mm` / `simplify_tolerance_mm` sont passées à vpype comme
nombres nus dans le repère du `viewBox` (assumé par le docstring de
`core/toolpath.py:6-8`, mais démenti par les noms d'API et d'UI). Pour un
pivot raster, le `viewBox` est en **pixels image**
(`converters/bitmap/render.py:136`) : sur une image 400 px imprimée en
280 mm, « 0,05 mm » de simplification vaut en réalité 0,035 mm ; sur une
image 4 000 px, 0,0035 mm — la simplification devient inopérante et le
`linemerge` aussi (rien à moins de 0,1 px ne fusionne). L'effet réel des
réglages dépend donc de la résolution du fichier source, silencieusement.

**Piste** : convertir la tolérance mm → unités utilisateur avec l'échelle de
placement avant l'appel vpype (le frontend connaît `bbox` source et taille mm
cible ; sinon ratio `viewBox` / taille physique du SVG), ou a minima renommer
et documenter. Impact surtout sur la **fidélité des réglages**, pas un bug de
correction.

### F4 — **[INFO — le vrai levier restant]** Après tri, les levées dominent — et leur coût réel n'est ni émis ni mesuré

46–80 % du temps modélisé post-V1 part en cycles levée/descente sur les
styles denses. Conséquences pratiques :

- **Le choix du style pèse plus que tout raffinement de tri.** Même
  remplissage : `eulerian_hatch` = 19 chemins, `crosshatch` = 86,
  `dashes` = 2 987. Les styles à tirets/points *sont* des levées par
  conception — aucun optimiseur générique ne les réduira. Le wiki
  « Picking the Right Algorithm » gagnerait à chiffrer ce coût (chemins/cm²).
- **Le nombre de chemins n'est réduit par rien d'autre que `linemerge`**, et
  après tri il ne reste aucun micro-saut fusionnable (histogramme des sauts :
  0 saut < 0,5 unité sur les six styles testés) — le pipeline est déjà au
  taquet à tolérance donnée.
- **Aucun dwell n'est émis** après `pen_up`/`pen_down` (`pen_up.j2` =
  la commande du profil, seule). Le coût réel d'une levée est donc ce que le
  firmware veut bien attendre : si le firmware n'attend pas le servo, le
  temps est moindre… mais le trait peut démarrer pendant le transit du stylo
  (qualité) ; si le profil embarque un `G4`, ce dwell **est** le poste
  dominant et sa calibration (`pen_lift_time_ms`, angles/hauteur servo)
  vaut plus que tout le reste de cette étude. À mesurer sur machine réelle
  avant d'investir davantage dans le tri.

### F5 — **[BASSE]** Chaînage côté émetteur : non rentable seul, marginal avec F2

Idée récurrente : sauter le cycle `pen_up → G0 → pen_down` quand le saut est
plus court que la largeur du trait (dessiner à travers). Mesure : après V1 il
n'existe **aucun** saut < 0,5 unité (le `linemerge` amont les a déjà
fusionnés). La rotation de couture (F2) en fait toutefois apparaître :
175 sauts < 2 unités sur `contours` (~50 s de levées économisables), 13–18
sur les styles à cercles. À ne considérer que comme complément de F2, seuil
borné à la largeur du stylo du calque, jamais par défaut sur un SVG importé
(un saut peut être un blanc voulu).

### F7 — **[HAUTE — ✅ corrigée]** L'early-exit sautait l'optimisation des calques faits de cercles

> Découverte **pendant l'implémentation des correctifs** (le test de
> rotation de couture sur trois `<circle>` retournait des métriques à
> zéro), corrigée dans ce même lot.

Le raccourci « mono-calque, un seul chemin » de `_optimize_svg`
(`_path_count`) ne comptait que `path` / `polyline` / `polygon` /
`line`. Un dessin **mono-calque composé de `<circle>`** — exactement ce
qu'émettent `stippling`, `halftone`, `voronoi_stipple` et `circle_pack`,
c'est-à-dire un portrait pointillisme mono-stylo typique — comptait
« 0 chemin » et repartait **tel quel, en ordre brut de génération, avec
des métriques à zéro**. Vu les mesures du §2 (pen-up brut ×17 à ×22 sur
ces styles), c'est le pire cas possible passé sous le radar : le seul
garde-fou restant était le tri « écriture » naturel de l'algorithme.
Correctif : `_path_count` compte désormais aussi `circle` / `ellipse` /
`rect`. Test : `test_optimize_does_not_early_exit_on_circle_only_layer`.

### F6 — **[BASSE]** Divers

- `linesort` démarre du premier chemin du calque, pas de la position de
  repos : le premier trajet (home → premier chemin) et l'ordre inter-calques
  ne sont pas optimisés. Négligeable (un trajet par calque), noté pour
  mémoire.
- `_QUANTIZATION = 0.5` unité utilisateur à la relecture vpype : sur un pivot
  déjà en mm c'est 0,5 mm d'échantillonnage des courbes — correct pour le
  tracé (les arcs sont re-lissés par `fit_arcs` en aval), mais c'est la même
  dépendance d'unités que F3.

---

## 4. Synthèse et plan d'action proposé

| # | Constat | Gain | Effort | Priorité |
|---|---------|------|--------|----------|
| F1 | SVG texte re-rendu jamais optimisé | −46 % de pen-up sur les jobs texte (~30 s/page dense) | Faible (brancher `optimize_svg` dans `text_render`) | **P1 — ✅ corrigé** |
| F7 | Early-exit : calques de `<circle>` jamais optimisés (stippling/halftone mono-calque) | Pen-up brut ×17–22 évité sur le cas touché | Trivial (`_path_count`) | **découverte — ✅ corrigée** |
| F2 | Rotation de couture + 2-opt à budget | −10 à −28 % de pen-up ; 0,5–2,5 % du temps total | Moyen (`core/pathsort.py`, option par calque) | **P2 — ✅ corrigé** |
| F3 | Tolérances en unités utilisateur, pas en mm | Fidélité des réglages (dépend de la résolution source) | Faible-moyen (conversion via l'échelle de placement) | **P3** |
| F4 | Levées = poste dominant post-tri | Documentation + calibration profil (`pen_lift_time_ms`, dwell) | Doc + mesure machine | **P3** |
| F5 | Chaînage émetteur | ~50 s sur `contours`, sinon nul | Ne vaut le coup qu'avec F2 | P4 |
| F6 | Divers (départ du tri, quantization) | Négligeable | — | mémoire |

Reproduction des chiffres : `cd backend && .venv/bin/python
scripts/toolpath_travel_bench.py` (la sortie du banc donne, par style, les
lignes V0→V4 et la décomposition dessin/trajet/levées du §2).
