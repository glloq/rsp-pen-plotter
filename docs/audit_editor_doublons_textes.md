# Audit éditeur expert — doublons, texte en trop, contrôles morts/manquants (2026-06)

Périmètre : l'**interface de l'éditeur expert** (`uiMode.isExpert`) et tout ce
qu'elle affiche : la coquille de la modale (`components/v2/EditModalV2.vue`,
`EditorHeader`, `EditPreviewPane`, `PreviewToolbar`, `EditorInkPanel`,
`SheetPicker`, `EditorPageNav`), la barre d'onglets `EditTabs` + ses cinq
onglets (`tabs/{Image,Svg,Style,Text}Tab.vue`, `LayersSection`/`LayerCard`) et
tout l'arbre `components/edit/**` (cartes image / svg / style / colors / source /
render / shared), plus les textes i18n associés (`locales/fr.json`).

Objectif (demande opérateur) : **chercher les points d'amélioration — texte en
trop, doublons, contrôles inutiles, contrôles manquants** — et proposer des
correctifs **sans ajouter ni retirer de fonctionnalité**. Toutes les pistes
ci-dessous préservent le comportement : suppression de **code mort** (rien de
visible n'est perdu), fusion de **doublons** (l'action reste disponible),
allègement de **texte redondant**, et uniformisation du **vocabulaire**.

> **Position vs audits précédents.** Trois audits ont déjà été livrés et
> **appliqués** :
> - `audit_editor_ui.md` — cohérence visuelle clair/sombre (thème slate/emerald). ✅
> - `audit_editor_panel.md` — ergonomie/agencement des contrôles (slider unifié,
>   carte repliable, unités/bornes, reset par section, hints). ✅
> - `audit_editor_refactor_followup.md` — découpage technique des gros fichiers. ⏳
>
> Le présent audit est **complémentaire** : il ne porte ni sur le thème ni sur
> l'agencement, mais sur la **redondance** (contrôles/textes/concepts en double),
> le **code mort** et la **complétude**. Il signale aussi que les deux audits de
> panneau sont désormais **partiellement périmés** (voir F1).

---

## 0. Synthèse — quick wins d'abord

| # | Constat | Type | Effort | Risque |
|---|---------|------|--------|--------|
| F1 | `ColorCountSlider.vue` n'est plus monté (orphelin) | code mort | faible | nul |
| F2 | `LayersTab.vue` : wrapper jamais importé | code mort | faible | nul |
| F3 | Namespace i18n `editPreview.*` entièrement inutilisé | texte mort | faible | nul |
| F4 | CSS `.view-toggle` orpheline dans `EditPreviewPane` | code mort | faible | nul |
| D1 | `layers.printStyle` == `layers.renderAlgorithm` == « Algorithme du calque » (2× visibles dans la même carte) | doublon libellé | faible | faible |
| D2 | Tooltip `:title` = sous-texte visible (3 cartes) | texte en trop | faible | nul |
| D3 | `MasterStylePicker` affiche 2× la description du style actif | texte en trop | faible | nul |
| T1 | Guidance geste/zoom répétée 3× | texte en trop | faible | nul |
| G1 | Vocabulaire incohérent : stylo/pen/feutre, calque/couche, couleur/encre… | terminologie | moyen | faible |
| D4 | Triple vocabulaire de styles `mono.modes`/`colorStyles`/`printStyles` | doublon structurel | élevé | moyen |

Les lignes F\* et D1–D3, T1 sont des **gains immédiats sans risque**. G1/D4 sont
structurels (à planifier).

---

## 1. Code et contrôles morts / orphelins

> À retirer : aucun n'est rendu à l'écran, donc **aucune fonctionnalité n'est perdue**.

### F1 — `ColorCountSlider.vue` n'est plus monté (et les audits le citent à tort)

`frontend/src/components/edit/render/ColorCountSlider.vue` n'est importé que par
son **propre test** (`ColorCountSlider.test.ts:6`). Aucun onglet ne le rend :
l'onglet Style utilise `ColorReductionCard` (compte M d'encres) au-dessus du
picker multicolore, et le compte N (`num_colors`) vit dans `SegmentationCountCard`
sur l'onglet SVG. Le composant a été **remplacé mais jamais supprimé**.

Conséquence documentaire : `audit_editor_panel.md` cite `ColorCountSlider` comme
**bon pattern vivant** (lignes 86, 121, 177, 201, 251 — « alertes
conditionnelles », cible de la saisie numérique P1). Ces références sont
**périmées** : le pattern d'alertes (écrêtage stylos/pool, rendu différent) n'est
**plus visible** par l'opérateur. À décider : (a) supprimer le composant + son
test ; ou (b) si l'on tient au pattern d'alertes, le **remonter** dans
`ColorReductionCard`/`SegmentationCountCard` (là, ce serait un *ajout* — hors
périmètre « sans ajout »). Recommandation minimale : **(a)**, et corriger les
docs.

### F2 — `LayersTab.vue` : wrapper jamais importé

`frontend/src/components/edit/tabs/LayersTab.vue` est un wrapper de 12 lignes
autour de `LayersSection`. Mais `EditorExpertPanel.vue:19` importe
**`LayersSection` directement**. Aucun composant n'importe `LayersTab`
(seule référence : un commentaire dans `useFileManager.ts:11`). → supprimable.

### F3 — Namespace i18n `editPreview.*` entièrement inutilisé

Recherche `editPreview.` dans tout `frontend/src` : **0 occurrence** (ni `.vue`
ni `.ts`). La barre d'aperçu actuelle (`PreviewToolbar.vue`) utilise
`v2.modal.viewPlot` / `viewOriginal` / `viewCompare`. Le namespace `editPreview`
(≈ 25 clés : `source`, `split`, `vector`, `modeSource`, `modeSplit`, `modeAuto`,
`live`, `quality*`, `resetView`…, `fr.json:441-475`) est un **vestige complet
d'une version antérieure de la toolbar** — il porte même deux jeux parallèles
(`source`/`split`/`vector` **et** `modeSource`/`modeSplit`/`modeAuto`, valeurs
identiques). À supprimer du `fr.json` **et** du `en.json`.

### F4 — CSS `.view-toggle` orpheline

`EditPreviewPane.vue:560-581` définit `.view-toggle`, `.view-toggle:hover`,
`.view-toggle.is-original`, `.view-toggle:focus-visible` — **aucun élément du
template ne porte cette classe** (l'ancien bouton de bascule a migré vers
`PreviewToolbar`). Bloc `<style scoped>` mort, supprimable.

### F5 — Contrôle réservé « curve fit » (rappel)

`SvgTab.vue:118-130` affiche une note non interactive « Lissage de courbe —
Bientôt » (`svg.curveFit*`). L'audit panneau l'avait déjà dégradée de toggle
désactivé → note discrète. Tant que la fonction n'existe pas côté backend, on
peut **masquer entièrement** la note (et geler `svg.curveFit*`) pour retirer ce
bruit résiduel. Décision produit, faible enjeu.

---

## 2. Doublons de contrôles et de libellés

### D1 — Libellé « Algorithme du calque » affiché deux fois dans `LayerCard`

`fr.json` : `layers.renderAlgorithm` (l. 914) **et** `layers.printStyle` (l. 916)
valent tous deux **« Algorithme du calque »**. Les deux sont rendus dans le
**même composant** :
- `LayerCard.vue:400` — `printStyle` = en-tête de la section *Rendu* (au-dessus de
  la grille de tuiles `PrintStylePicker`) ;
- `LayerCard.vue:446` — `renderAlgorithm` = label du menu déroulant « Avancé ».

Donc l'en-tête de section **et** le menu interne portent la même phrase. Piste :
donner à l'en-tête de section un libellé qui parle de **style/preset** (le
contenu réel : une grille de presets), et réserver « Algorithme du calque » au
menu avancé. Zéro changement de comportement.

### D2 — Le tooltip `:title` répète le sous-texte déjà visible

Sur plusieurs cartes « tuile sélectionnable », le `:title` (infobulle) affiche
**exactement** le sous-texte déjà rendu sous le libellé. L'infobulle n'apporte
rien et double la maintenance de la traduction :

| Carte | `:title` | Sous-texte visible |
|-------|----------|--------------------|
| `SegmentationMethodCard.vue` | `:89` `convert.seg_${method}_hint` | `:92-95` même clé |
| `MasterStylePicker.vue` | `:149` `t(style.descriptionKey)` | `:157-159` même clé |
| `PrintStylePicker.vue` | `:92` `t(style.descriptionKey)` | `:96-98` même clé |

Piste : retirer le `:title` quand la description est déjà visible (le garder
uniquement là où le texte est tronqué/masqué, ex. tuiles compactes sans
sous-texte).

### D3 — `MasterStylePicker` : description du style actif rendue 2×

`MasterStylePicker.vue` :
- chaque tuile montre sa description en sous-texte (`:157-159`) — donc la tuile
  **sélectionnée** l'affiche déjà ;
- le **pied de carte** (`:163-165`) ré-affiche la description du **style actif**.

Quand un style est sélectionné, sa description apparaît **deux fois** (tuile + pied).
De plus, l'état « personnalisé » est expliqué par une **paire** redondante :
`render.customisedHint` (infobulle, `:131`) + `render.customisedExplain` (texte,
`:135-137`) disent la même chose. Piste : garder le pied **ou** le sous-texte,
pas les deux ; fusionner la paire `customisedHint`/`customisedExplain`.

### D4 — Triple traduction du vocabulaire de styles (structurel)

Le même algorithme est décrit **2 à 3 fois** dans trois namespaces parallèles :
`mono.modes.*` (~115 clés, monochrome), `colorStyles.*` (~70, multicolore),
`printStyles.*` (~60, par calque). Exemples vérifiés (même concept, libellés et
descriptions re-traduits) : « Fil tendu » (`mono.modes.stringThread` /
`colorStyles.stringArt` / `printStyles.stringArt`), « Veines organiques », « Nid
d'abeille », « Harmonographe », « Touches picturales », « L-système »… (~30
algorithmes concernés). C'est la **racine** d'une grande partie des doublons de
texte et de la dérive de vocabulaire (G1). Piste (gros chantier) : une **source
unique** de label+description par algorithme, projetée vers les trois familles.

### D5 — Visibilité de calque : deux contrôles pour la même action

- `EditorInkPanel.vue:65-86` — pastille d'encre sous l'aperçu, œil 👁/⊘
  (`toggle`) ;
- `LayerCardSummary.vue:44-49` — case à cocher dans la liste des calques.

Les deux pilotent `store.isVisible`. C'est une redondance *assumée* (proximité de
l'aperçu vs liste), mais à **documenter comme intentionnelle** pour ne pas être
re-signalée, et à garder synchronisées visuellement.

### D6 — Affectation d'encre par calque exposée à deux endroits

Le même composant `AssignedColorPicker` est monté :
- dans `LayerCard.vue:288-294` (onglet Calques) ;
- dans `EditorInkPanel.vue:112-118` via le bouton 🎨 sous l'aperçu.

Là encore, redondance volontaire (deux contextes). À conserver, mais à mentionner
dans les commentaires des deux hôtes pour éviter une divergence de comportement.

### D7 — Table des formats de feuille dupliquée

`SheetPicker.vue:39-46` maintient à la main une copie de la liste de presets
(A6…Letter + dimensions) « identique à `LayoutSection.vue` » (commentaire l.
37-38). Deux copies à synchroniser manuellement. Piste : extraire une **constante
partagée** (ex. `data/sheetPresets.ts`) consommée par les deux.

---

## 3. Texte en trop / verbeux

### T1 — Guidance geste/zoom répétée 3× (textes vivants)

La même consigne « molette = zoom · glisser = déplacer · double-clic = recadrer »
existe en trois clés affichées simultanément/successivement :
`v2.modal.gestureHint` (l. 1757, sous l'aperçu), `v2.modal.resetView` (l. 1751,
infobulle du bouton zoom), `v2.modal.tourStep1Body` (l. 1777, visite guidée). +
une 4ᵉ copie **morte** dans `editPreview.resetView` (l. 448, cf. F3). Piste :
garder la visite + l'infobulle, retirer le `gestureHint` permanent (ou
l'inverse).

### T2 — Hints à raccourcir (échantillon vérifié)

Plusieurs hints tiennent en deux phrases là où une suffit (réécritures
proposées) :

- `svg.minBranchDesc` (l. 168) → *« Ignore les branches du squelette plus
  courtes que ce seuil. 1-2 px conserve les détails fins ; 4-5 px si le scan est
  bruité. »*
- `mono.detailHint` (l. 260) → *« Détail élevé = plus de finesse (petit texte,
  grilles, schémas denses) mais conversion plus lente. »*
- `mono.shadesHint` (l. 251) → *« 1 = un calque, un stylo, sans ombrage. Plus de
  nuances = plus de bandes de gris (un calque par bande). »*
- `layers.convertSyncHint` (l. 864) → *« Le style global de l'onglet Style
  s'applique à chaque calque à la conversion. Les réglages par calque ci-dessous
  priment et sont conservés. »*
- `magazine.hintManual` (l. 1571), `availableColors.odometerTitle` (l. 1538),
  `mono.spiralTonalHint` (l. 427) : même registre, à trimmer.

### T3 — Trois avertissements « nombre de couleurs » qui se chevauchent

`colorStyles.numColorsCapped` (l. 541), `numColorsRendered` (l. 542),
`numColorsPoolCapped` (l. 543) disent des variantes du même message et finissent
toutes par le **même appel à l'action** « Ajoute des couleurs dans Traceur ▸
Couleurs… ». *Note : ces trois clés ne sont consommées que par `ColorCountSlider`
(cf. F1) — donc actuellement invisibles.* Si le composant est supprimé, ces clés
deviennent mortes ; s'il est ré-intégré, fusionner les trois messages.

### T4 — Étiquettes d'encre ambiguës

Deux libellés proches coexistent : `v2.modal.paletteLabel` = **« Encres »**
(`EditorAssistedPanel` — sélecteur de source) et `v2.modal.inksLabel` = **« Encres
utilisées »** (`EditorInkPanel`, affiché sous l'aperçu dans les deux modes).
Piste : désambiguïser, ex. « Source des encres » vs « Encres utilisées ».

---

## 4. Vocabulaire incohérent (G1)

Le même objet porte plusieurs noms selon le namespace. C'est le défaut le plus
**diffus** et il alourdit la lecture. Uniformiser ne change aucune fonction.

| Concept | Termes trouvés | Cible proposée |
|---------|----------------|----------------|
| Stylo | **stylo** (`mono.pen`, `paletteSource.pens`…), **pen** (non traduit : `palette.followPens` « Suivre les pens », `palette.noPensInstalled` « Aucun pen », `layers.mergeToOnePen` « Tous sur un pen », `layers.nearestPenHint` « Pen #{slot} »), **feutre** (`availableColors.hint/empty`, `assignedColor.emptyPool`) | **stylo** |
| Emplacement | **emplacement** (`layers.penSlot`, `magazine.slotCount`) vs **slot** (`mono.penNotInstalled`, `palette.slotTooltip`, `magazine.posX`) | **emplacement** |
| Calque | **calque** (`editModal.tabLayers`, tout `layers.*`) vs **couche** (**tout le namespace `v2.modal`** : `stepLayers`, `layerCount`, `layerHide`, `render.multicolorHint`…) | **calque** |
| Couleur / encre | **couleur** (`assignedColor.title` « Couleur du calque », `footer.penChanges`) vs **encre** (`v2.modal.*`) — parfois **mélangées dans une même phrase** (`colorStyles.numColorsPoolCapped`, `svg.layerCountHint`) | choisir un terme |
| Magasin | **magasin** vs **rack** (`v2.capability.modeHostMacro*`) | **magasin** |
| Tramage | « Tramage »/« Trame » désigne **3 algorithmes distincts** : dither Floyd-Steinberg (`preprocess.filters.dither`), halftone (`mono.modes.halftone`, `convert.algoHalftone`), tramé ordonné (`printStyles.dither`, `v2.style.halftone`) | désambiguïser |

Autres : **fuites d'anglais** dans des chaînes FR (« Squiggle », « Flow field »,
« Streamlines », « hand-drawn »), **centerline** tantôt label, tantôt
parenthèse, tantôt « Mode trait » ; **tu/vous** mélangés (majorité en *tu* ;
*vous* dans `mono.penHint`, `printMode.modeHint`, `convert.specificColorsHint`,
`layers.generateHint`…). Cible : **tutoiement** partout.

> ⚠️ « pens » et « couche » ne sont pas des choix stylistiques mais des **fuites
> du nouvel éditeur v2** (le `en.json` dit bien `"pen"`/`"layer"`). À traiter en
> priorité dans G1.

---

## 5. Contrôles manquants / incomplets

> Ici on distingue ce qui relève d'un **manque de clarté** (corrigeable sans
> nouvelle fonction) de ce qui serait un **vrai ajout** (signalé, hors périmètre).

### M1 — Deux curseurs « nombre de couleurs » sans lien visible (clarté)

L'éditeur expose deux compteurs sur **deux onglets** :
- onglet SVG → `SegmentationCountCard` : **N** = `num_colors` (= nb de calques),
  titre `svg.layerCountTitle` ;
- onglet Style (multicolore) → `ColorReductionCard` : **M** = `color_count`
  (= nb d'encres distinctes, écrêté à N), titre `style.colorCountTitle`.

Les deux montrent un `LayerCountBadge`. Rien à l'écran n'explique la relation N≥M
ni pourquoi « nombre de couleurs » apparaît sur deux onglets. **Sans ajouter de
contrôle**, piste : libellés explicites (« Calques / segments (N) » vs « Encres
distinctes (M) ») + un court hint croisé. Réduit la confusion la plus citée.

### M2 — Migration « slider numérique » incomplète sur l'opacité de calque

L'audit panneau (P1) listait « opacité `LayerCard` » comme cible du slider unifié
`LabeledSlider`. Or `LayerCard.vue:344-361` utilise encore un `<input
type="range">` **brut** avec lecture seule `{{ opacity_percent }}%` — pas de
saisie numérique, contrairement à vitesse/simplify (qui sont des `type=number`).
Incohérence résiduelle : aligner l'opacité sur `LabeledSlider` (cohérence, pas
nouvelle fonction).

### M3 — Simplify global (SVG) vs simplify par calque : relation non signalée

`SvgTab.vue:37-45` (`onSimplifyChange`) propage la tolérance de simplification à
**tous** les calques ; `LayerCard.vue:320-330` permet l'override **par calque**.
Le curseur global ne dit pas qu'il s'agit d'un **défaut** réécrit à chaque
modification (et écrasé par les overrides). Piste : un hint « valeur par défaut,
modifiable par calque » sur le curseur SVG.

### M4 — (Vrai ajout, hors périmètre) saut de page direct

`EditorPageNav` ne propose que des chevrons ‹ › (pas de saisie de n° de page).
Acceptable pour un éditeur grand public ; **ajouter** un champ serait une
fonctionnalité → à décider séparément, hors de cet audit « sans ajout ».

---

## 6. Détails mineurs (à grouper avec ce qui précède)

- **`CollapsibleCard`** (`shared`) : l'en-tête a **deux** déclencheurs du même
  pliage (le titre cliquable **et** le bouton `+`/`−`). Acceptable (a11y), à
  noter.
- **`EditorPageNav`** emprunte `upload.pageOf` alors que ses autres clés sont en
  `v2.modal.*` — incohérence de namespace mineure.
- **`PreviewToolbar`** : tout le groupe Résultat/Original/Comparer est masqué
  (`v-if="canShowOriginal"`) quand il n'y a pas d'image source — même le bouton
  « Résultat » (toujours valide) disparaît. À vérifier : préférer désactiver
  « Comparer » seul plutôt que masquer le groupe.

---

## 7. Plan proposé (priorité)

**Lot A — nettoyage sans risque (recommandé en premier).**
Supprimer `ColorCountSlider.vue` (+ test) [F1], `LayersTab.vue` [F2], le
namespace `editPreview.*` dans `fr.json`/`en.json` [F3], la CSS `.view-toggle`
[F4] ; corriger les références périmées dans `audit_editor_panel.md`. Retirer les
`:title` redondants [D2] et la 2ᵉ description du style actif [D3] ; dédupliquer
le libellé « Algorithme du calque » [D1] ; dégonfler la guidance geste/zoom [T1]
et les hints listés [T2].

**Lot B — terminologie (G1).**
Une passe `fr.json` : **stylo / emplacement / calque** uniformisés, tutoiement
partout, fuites d'anglais traduites, alignement du namespace `v2.modal` (« couche
» → « calque », « pens » → « stylos »). Mécanique, testable par diff i18n.

**Lot C — clarté (M1–M3).**
Libellés N/M explicites + hints croisés ; opacité `LayerCard` sur `LabeledSlider`
; hint « défaut par calque » sur le simplify global.

**Lot D — structurel (D4, D7).**
Source unique de label/description de styles (fusion `mono.modes`/`colorStyles`/
`printStyles`) ; constante partagée des presets de feuille. Gros chantiers, à
planifier.

---

## 8. À préserver (déjà bon)

Pour mémoire, l'éditeur a beaucoup de points forts à **ne pas casser** : clusters
d'actions par intention (`LayersSection`), quick-nav + résumé de calques, slider
unifié `LabeledSlider` avec saisie numérique, cartes repliables persistantes
`CollapsibleCard` + reset par section, badges d'état (Custom, ≈ stylo proche,
pinned), normalisation hex de `PaletteCard`, état vide `TabEmptyState`, et le
plan magasin (`MagazinePlanPanel`). Ces acquis (issus des deux audits panneau)
restent valides ; le présent audit ne les remet pas en cause.

---

## 9. Vérification

Chaque constat cite un fichier (et une ligne quand pertinent). Constats
**vérifiés par recherche** dans cette passe : F1 (`ColorCountSlider` importé
seulement par son test), F2 (`LayersTab` non importé), F3 (`editPreview.` : 0
occurrence dans `frontend/src`), F4 (`.view-toggle` absent du template), D1
(`fr.json:914`==`:916`, rendus en `LayerCard.vue:400`/`:446`), D2/D3 (titres ==
sous-textes), T1 (3 clés vivantes + 1 morte).

---

## 10. Statut : Lot A appliqué (2026-06)

Premier incrément « nettoyage sans risque » livré dans cette branche :

- **F1** — `ColorCountSlider.vue` + son test supprimés ; clés i18n orphelines
  `colorStyles.numColors*` (et `numColorsLocked`) retirées de `fr.json`/`en.json` ;
  entrée morte retirée de `eslint.config.js` ; commentaires de `PaletteCard` et
  `MultiColorMasterStyleParams` corrigés (ils pointaient vers le fichier supprimé) ;
  références historiques signalées dans `audit_editor_panel.md`.
- **F2** — `LayersTab.vue` (wrapper jamais importé) supprimé.
- **F3** — namespace i18n `editPreview.*` (~25 clés, inutilisé) retiré des deux locales.
- **F4** — CSS `.view-toggle` morte retirée de `EditPreviewPane.vue`.
- **D1** — `layers.printStyle` renommé « Style de rendu » / « Render style » ; le
  menu avancé conserve « Algorithme du calque ». Plus de libellé en double dans
  `LayerCard`.
- **D2** — `:title` redondant retiré sur `SegmentationMethodCard` et
  `PrintStylePicker` (le sous-texte, non tronqué, dit déjà la même chose).
- **T3** — les trois avertissements `numColorsCapped`/`Rendered`/`PoolCapped`
  disparaissent avec leur unique consommateur (`ColorCountSlider`).

**Révision d'un constat initial :** `MasterStylePicker` (D3) est finalement
**laissé tel quel**. Ses tuiles **tronquent** label et description
(`truncate`), donc l'infobulle de tuile et le pied de carte (description complète
du style actif) ne sont pas de purs doublons — les retirer perdrait l'accès au
texte complet. À revoir seulement si les tuiles cessent de tronquer.

Vérifié : `vue-tsc --noEmit` ✓ · `vite build` ✓ · `vitest run` (844 tests) ✓ ·
`eslint` ✓.

**Reste à faire (lots suivants).** T1 (guidance geste/zoom — touche
`EditPreviewPane.test.ts`), T2 (réécriture des hints verbeux), **Lot B**
(terminologie : stylo/emplacement/calque/encre, tutoiement, fuites d'anglais,
alignement du namespace `v2.modal`), **Lot C** (clarté N/M, opacité `LayerCard`
→ `LabeledSlider`, hint « défaut par calque » sur le simplify global), **Lot D**
(source unique de styles `mono.modes`/`colorStyles`/`printStyles`, presets de
feuille partagés).

---

## 11. Statut : Lots B, C, T1, T2 et D7 appliqués (2026-06)

Suite directe du Lot A, dans la même branche :

- **Lot C (clarté)** — opacité par calque migrée sur `LabeledSlider` (saisie
  numérique) ; `layerCountHint` renvoie au réglage du nombre de couleurs de
  l'onglet Style ; `simplifyDesc` précise « défaut modifiable par calque ».
- **T1** — hint geste/zoom permanent retiré (doublon de l'infobulle + de la
  visite guidée) : élément, CSS `.gesture-hint` et clé `v2.modal.gestureHint`.
- **T2** — 7 hints verbeux raccourcis (minBranch, detail, shades, spiralTonal,
  convertSync, odometer, hintManual).
- **Lot B (terminologie, valeurs FR uniquement)** — unifié : `pens`/`feutre`
  → **stylo**, `slot` → **emplacement** (variables `{slot}`/`{slots}`
  préservées), `couche` → **calque**, `encre` → **couleur** (élisions gérées) ;
  vouvoiement → tutoiement ; noms de style anglais traduits (Squiggle →
  Gribouillis, Flow field → Champ de flux, Streamlines → Lignes de flux,
  hand-drawn → façon croquis). `en.json` laissé tel quel (déjà cohérent).
  **« rack » conservé** : c'est un type de changeur d'outil distinct
  (« Rack à pince »), pas le magasin ; **« pen up/down » conservé** (terme
  firmware).
- **D7** — table de presets de feuille extraite dans `data/sheetPresets.ts`,
  consommée par `SheetPicker` **et** `LayoutSection` (fin de la double copie
  maintenue à la main).

Révision d'un constat : **D2** n'a été appliqué que sur `SegmentationMethodCard`
et `PrintStylePicker` (sous-texte non tronqué) ; `MasterStylePicker` est
conservé (ses tuiles **tronquent** label et description → l'infobulle de tuile
et le pied de carte restent utiles, ce n'est pas un pur doublon).

Vérifié à chaque incrément : `vue-tsc --noEmit` ✓ · `vite build` ✓ ·
`vitest run` (844 tests) ✓ · `eslint` ✓.

### Non fait — **D4** (refonte structurelle), volontairement différé

La fusion des trois vocabulaires de styles (`mono.modes` / `colorStyles` /
`printStyles`) en une source unique touche `printRegistry.ts`, `styleKnobs.ts`
et les sélecteurs : elle change la **résolution/affichage des styles** et
**risque de modifier le rendu**. Ce n'est pas un nettoyage « sans risque » mais
un vrai refactor à concevoir et tester séparément (mapping des ids legacy,
parité des presets, snapshots de rendu). Laissé pour une itération dédiée
plutôt que fait à l'aveugle.
