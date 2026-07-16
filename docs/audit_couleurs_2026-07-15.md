# Audit — gestion des couleurs : auto-assignation & modification (2026-07-15)

> Objectif : vérifier que l'auto-assignation des couleurs (centroïdes de
> segmentation → encres possédées) et la modification des couleurs par
> l'opérateur sont **propres et intuitives**. Audit mené code + navigateur
> réel (Chromium piloté, backend matériel simulé), avec une image de test
> 5 couleurs (rouge, bleu, vert, jaune, brun sur fond crème) et un
> inventaire de 5 encres nommées.

Périmètre : `color_assignment.py`, `palette_pool.py` (backend) ;
`nearestColor.ts`, `effectivePalette.ts`, `useEditorInkSwatches.ts`,
`AssignedColorPicker.vue`, `EditorInkPanel.vue`, `AvailableColorsPanel.vue`,
stores `job` / `paletteSource` / `availableColors`, `useMagazinePlan.ts`
(frontend) ; pipeline tonal `_style.py` / `_hatch.py` / `render.py`
(déclencheur du défaut n°1).

---

## 1. Verdict d'ensemble

Le socle est **solide et bien conçu** : ΔE 2000 en Lab des deux côtés
(implémentations backend/frontend miroir, testées), règle claire
pens/available/union, overrides manuels préservés par le re-snap
(`color_assignment: "manual"`), re-snap réactif quand le pool change
(source, inventaire, stylos), popover de modification propre (badge
auto/manual, « ↻ auto », pastilles nommées dédupliquées), recoloration
immédiate de l'aperçu, plan de chargement magasin (Belady) qui épingle
les couches en manuel pour résister au re-snap. 104 tests couleur
passaient avant l'audit.

Quatre vrais défauts ont néanmoins été trouvés — dont deux qui font
**disparaître ou dévier des couleurs sans aucun signal** — plus deux
séries de fuites i18n et un piège d'outillage qui a détruit les données
de test pendant l'audit lui-même. Tout est corrigé ci-dessous.

## 2. Défauts corrigés

### 2.1 Des formes entières disparaissaient du tracé (rendu tonal)

**Symptôme observé** (mode assisté par défaut, intent « Balanced » →
crosshatch) : sur l'image de test, le triangle vert et le rectangle
jaune n'étaient **pas dessinés du tout** — pas recolorés : absents du
SVG re-rendu, sans avertissement. Les chips « Inks in use » listaient
pourtant leurs encres.

**Cause** : `tone_darkness` étire la luminance **relativement à la
couche** (percentiles 2–98 de la région), puis la famille de hachures
laisse les pixels sous `TONE_HIGHLIGHT_CUTOFF` (0.08) **vierges**
(« highlights stay paper »). Quand k-means fusionne deux aplats
distincts dans un même cluster (jaune+rouge, ou triangle+trait dans le
cluster vert), la couleur la plus claire du cluster devient le
« highlight » relatif → zéro hachure. Le docstring supposait « les
régions multicouleur partagent une luminance » — faux dès que N est
inférieur au nombre réel de couleurs, c'est-à-dire le cas par défaut.

**Correctif** (`_style.tone_darkness`) : le « highlight qui reste
papier » est désormais **absolu** — seuls les pixels de luminance
≥ `paper_luminance` (0.92, même notion que `background_luminance`)
peuvent rester vierges ; tout pixel qui porte de l'encre réelle est
plafonné à `ink_floor` (0.12, au-dessus des cutoffs de la famille :
crosshatch 0.08, gosper 0.1) et reçoit donc toujours la passe de base.
Le modelé relatif (passes supplémentaires dans les zones sombres) est
conservé. Les 43 tests du contrat tonal passent inchangés — leurs
dégradés 0→1 ont une bande claire réellement quasi blanche. Validé en
navigateur : les 5 formes sont maintenant hachurées en assisté.

### 2.2 Stylos fantômes `#000000` : pool backend ≠ pool frontend

`installed_pen_hexes()` (backend) passait par `effective_pens()`, qui
**synthétise** un `PenSlot` par slot (`color="#000000"`,
`installed=True`) pour un profil dont le magasin n'a jamais été déclaré
(`pens: null` — cas du profil par défaut « Custom CoreXY A3 »). Le pool
backend contenait donc 6 stylos noirs fantômes (les clusters sombres
snappaient dessus au /upload et dans les prompts G-code), tandis que le
frontend lit `pens ?? []` → pool sans stylos. Exactement la divergence
que le module jure d'éviter (« Keeping both implementations in
lock-step matters »).

**Correctif** : `installed_pen_hexes` lit `profile.pens or []` — seuls
les stylos **déclarés** contribuent au pool ; un magasin jamais
configuré n'apporte rien (l'UI route vers l'inventaire / le centroïde
brut, comme le frontend). 2 nouveaux tests
(`test_installed_pen_hexes_ignores_undeclared_magazine`,
`test_resolve_pool_union_with_undeclared_magazine_is_inventory_only`).

### 2.3 Deux chips identiques impossibles à distinguer

Le nearest-match autorise la réutilisation (choix assumé et documenté :
fidélité > étalement des stylos). Conséquence UI : deux clusters
snappés sur la même encre donnaient deux chips **strictement
identiques** (« Rouge Sharpie » ×2) — impossible de savoir laquelle
pilote quelle forme pour la masquer ou la réassigner.

**Correctif** (`useEditorInkSwatches`) : quand plusieurs chips partagent
une encre, chacune suffixe son centroïde source —
« Rouge Sharpie · #c62828 » / « Rouge Sharpie · #ad6863 ». Les chips
uniques gardent leur nom propre. Test dédié + validation navigateur.

### 2.4 « Éditer » échouait en silence sur une conversion disparue

Quand le SVG stocké d'un fichier de bibliothèque manque sur disque
(410 « Stored SVG is missing on disk » — stockage nettoyé, déplacé…),
le clic « ✎ Éditer » ne faisait **rien du tout** : `ensureDetail`
rangeait l'erreur dans `library.error`… que la FilesPane n'affiche pas,
et `editFile` retournait silencieusement. (Le scan d'intégrité au boot
répond d'ailleurs « issues: [] » sur ce cas — voir recommandations.)

**Correctif** : `ensureDetail` émet désormais un `toasts.error()` avec
le détail backend. Test store dédié + validation navigateur (le toast
apparaît, l'opérateur sait quoi rétablir).

### 2.5 `pytest` effaçait la bibliothèque réelle du développeur

Découvert pendant l'audit (les uploads de la session disparaissaient à
chaque run de la suite backend) : `conftest.py` isole la DB, les
profils et les macros, **mais pas `OMNIPLOT_FILES_DIR`**. La fixture
autouse de `test_files_endpoint.py` fait `shutil.rmtree(FILES_DIR)`
entre chaque test → chaque `pytest` détruisait le **vrai**
`backend/data/files/` (en y laissant les résidus de fixtures
`placed-*`, `txt-*`), pendant que les lignes SQLite survivaient — d'où
des 410 sur toute la bibliothèque, en combinaison directe avec le 2.4.

**Correctif** : `OMNIPLOT_FILES_DIR` isolé vers un répertoire temporaire
dans `conftest.py` (même mécanique que `OMNIPLOT_DB`). Vérifié : la
suite complète ne touche plus `backend/data/files/`.

### 2.6 Fuites de clés i18n brutes + garde-fou

Le rail de mise en page affichait littéralement « PLANRAIL.TITLE » ;
un scan systématique a trouvé **14 clés statiques manquantes** dans les
deux locales : `planRail.title/expand/collapse`, `simRail.title`, les
8 clés de la carte `blockMap.*` (PDF) et `plotter.running`. Toutes
ajoutées (FR/EN). Nouveau test `src/locales/i18n-coverage.test.ts` :
parité EN/FR stricte + toute clé statique `t('…')` du code doit exister
— la classe de bug entière est désormais bloquée en CI.

## 3. Constats sains (parcours vérifiés en navigateur)

- **Auto-assignation** : image 5 couleurs + inventaire nommé → chips
  « Bleu nuit / Vert prairie / Rouge Sharpie / Jaune soleil » correctes
  (à N suffisant), noms d'inventaire affichés partout (chips, popover,
  plan magasin, prompts de swap).
- **Modification** : 🎨 → popover avec badge auto/manual, pastilles
  magasin ∪ inventaire (indépendant du pool d'auto-snap — choix
  documenté), pick → recoloration immédiate de l'aperçu + badge manual,
  « ↻ auto » → retour au snap. Overrides préservés par tous les
  re-snaps et bakés au Generate (`applyClusterOverridesToLayers`).
- **Réactivité du pool** : bascule pens/available/union et édition de
  l'inventaire re-snappent les couches `auto` seulement, avec garde
  « fidèle à l'image » (kmeans sans ink_pool jamais écrasé).
- **Magasin** : plan Belady par placement, application = épingle
  slot+encre en manuel + déclare le chargement dans le profil ;
  garde-fous single-slot, multi-placements, tool_change `none`.

## 4. Recommandations (non bloquants)

1. **« N couleurs » compte le fond supprimé** : demander 6 couches avec
   `drop_background` actif en dessine 5. Décaler l'étiquette (« couches
   dessinées ») ou compenser le cluster fond éviterait la surprise.
2. **Badge « Layers 3 » vs aperçu live** : en expert, le badge de
   l'onglet Layers compte les couches *committées* pendant que l'aperçu
   montre la segmentation *courante* (5 clusters) — source de confusion
   avant le premier Apply.
3. **Scan d'intégrité incomplet** : `integrity_scan()` répond
   « issues: [] » alors que chaque fichier 410 sur son détail (SVG
   manquant sur des lignes non re-renderables). Étendre le scan pour
   que l'`IntegrityBanner` prévienne avant le clic.
4. **Toast 410 dupliqué** : deux `ensureDetail` séquentiels (aperçu +
   édition) émettent chacun leur toast ; dédup par message possible
   dans le store toasts.
5. **Mode « pens » sans magasin déclaré** : depuis 2.2 le pool est vide
   (fallback centroïdes bruts, honnête). Un hint UI « déclarez vos
   stylos dans Couleurs » rendrait le vide actionnable.

## 5. Validation

- Backend : suite complète **1122 passed, 1 skipped** (dont 43 tonal,
  9 palette_pool, 26 color_assignment), `ruff` / `mypy` propres,
  `data/files` réel intact après pytest. Aucun changement de schéma
  API (pas de drift openapi/api-types).
- Frontend : suite complète verte (dont i18n-coverage, ink swatches,
  library.cache), `eslint` / `prettier` / `vue-tsc` propres, build OK.
- Navigateur (Chromium + backend simulé) : les 5 formes hachurées en
  assisté ; chips dédupliquées à N=6 ; toast sur Edit périmé ; pick /
  reset / recoloration vérifiés visuellement.
