# Audit ergonomique — panneau de droite de l'éditeur expert (2026-06)

Scope : le **panneau de réglages de droite** de l'éditeur expert et l'ensemble de ses
onglets. Concrètement : `components/edit/EditTabs.vue`, les cinq onglets
`components/edit/tabs/{ImageTab,SvgTab,StyleTab,TextTab}.vue`,
`components/LayersSection.vue` + `components/LayerCard.vue`, et tout l'arbre
`components/edit/**` (cartes image / svg / style / render / colors / source / shared).

Objectif : identifier comment rendre le **contrôle de chaque onglet plus propre,
plus facile, plus complet et plus intuitif** — sur l'agencement et l'ergonomie des
contrôles, pas sur le thème de couleurs.

> **Distinction avec l'audit précédent.** `docs/audit_editor_ui.md` (2026-06) traitait
> la **cohérence visuelle clair/sombre** (re-skin slate/emerald de la coquille de la
> modale et des écrans v2). Ce travail est **terminé** : il ne reste aucune surface
> claire hors du papier. Le présent audit est **complémentaire** : il porte sur
> l'**ergonomie/agencement des contrôles** à l'intérieur des onglets, une fois le
> thème uniformisé.

---

## 1. Architecture du panneau

La modale (`components/v2/EditModalV2.vue`) est en deux colonnes : aperçu à gauche,
contrôles à droite. En mode expert (`uiMode.isExpert`), la colonne droite affiche une
barre d'onglets (`EditTabs.vue`) puis le corps de l'onglet actif :

| Onglet | Fichier | Couleur active | Visibilité |
|--------|---------|----------------|------------|
| Image | `tabs/ImageTab.vue` | sky | sources bitmap |
| SVG | `tabs/SvgTab.vue` | amber | sources bitmap |
| Style | `tabs/StyleTab.vue` | violet | bitmap + document |
| Texte | `tabs/TextTab.vue` | rose | typographie / document |
| Calques | `LayersSection.vue` | emerald | toujours (état vide sinon) |

Raccourcis clavier `1`–`5` (badges `<kbd>` dans `EditTabs.vue:126`), `role="tablist"`
+ `aria-selected` — la barre d'onglets elle-même est propre et accessible.

---

## 2. Référence : le système de design en place

Rappel du système (cf. `docs/audit_editor_ui.md`, section « Reference ») :

- **Tailwind only**, toujours sombre (slate surfaces, `border-slate-700`,
  `text-slate-300/400/500`), accents fonctionnels : emerald = primaire/succès,
  amber = avertissement, red = danger, sky = info.
- Primitives partagées dans `src/style.css` (`@layer components`) : `.btn`,
  `.btn-cta`, `.card` (`rounded-lg border border-slate-700 bg-slate-800 p-3`), `.chip`.
- Échelle typo : `text-sm` corps, `text-xs`/`text-[11px]`/`text-[10px]` contrôles,
  `font-mono` pour les mesures. Titres de section :
  `text-xs uppercase tracking-wider text-slate-500`.
- Inputs natifs : `accent-color: emerald.500` forcé via `@layer base` (`style.css:8`).

### Bons patterns déjà présents (à généraliser)

L'audit n'est pas un constat d'échec : plusieurs onglets contiennent déjà les modèles
à étendre au reste du panneau.

- **Clusters d'actions groupés par intention** — `LayersSection.vue:257-336` regroupe
  les boutons en blocs étiquetés (`COULEURS` · `ORDRE` · `VUE`) au lieu d'un mur de
  boutons identiques. Modèle de regroupement de référence.
- **Alertes conditionnelles** — `ColorCountSlider.vue:180-214` affiche des messages
  d'état contextuels (rendu différent, écrêtage par stylos, écrêtage par pool) en
  cartouches amber. Excellent retour de découvrabilité.
- **Unités systématiques** — `TypographyCard.vue:213-349` étiquette ses ~8 champs
  numériques en mm ; `TransformCard.vue:100-150` affiche `(%)`. Modèle de complétude.
- **Accordéons persistants** — les cartes Image (`BasicAdjustmentsCard`, `LevelsCard`,
  `FiltersCard`, `TransformCard`) utilisent `useAccordionPersistence` : l'état
  plié/déplié survit entre sessions.
- **Quick-nav + résumé** — `LayersSection.vue:211-246` (rail de navigation) et
  `:355-365` (résumé chemins/longueur/durée) : navigation et feedback dans un onglet long.

---

## 3. Constats par axe

### Axe 1 — Cohérence des patterns

**1.1 Trois traitements de carte coexistent, sans règle claire.**

| Traitement | Apparence | Exemples |
|------------|-----------|----------|
| A — explicite + accordéon | `rounded-lg border border-slate-700 bg-slate-800` + en-tête repliable | `BasicAdjustmentsCard.vue:19`, `LevelsCard`, `FiltersCard`, `TransformCard`, `SegmentationMethodCard.vue:88` |
| B — `.card` plate | classe `.card`, toujours ouverte | `PostProcessCard.vue:37`, `ColorModeCard.vue:22`, `PaletteCard.vue:132`, sections de `TypographyCard` |
| C — bloc inline sans cadre | simple `space-y-1`, aucun cadre | `MasterStylePicker`, `ColorCountSlider.vue:160`, `DetailPicker.vue:78`, `PenSlotPicker.vue:47` |

Conséquence : à l'intérieur d'un même onglet, certains contrôles sont « encadrés » et
d'autres flottent, sans logique perceptible par l'opérateur.

**1.2 Accordéons incohérents.** Seules les cartes de l'onglet **Image** sont
repliables (`useAccordionPersistence`). Tout le reste est plat. Rien ne signale
pourquoi le pré-traitement photo serait masquable et pas le rendu ou la
segmentation. `LayerCard` a un repli interne (clic sur l'en-tête,
`LayerCard.vue:174`) mais qui n'utilise pas le même mécanisme persistant.

**1.3 Lecture des sliders : cohérente.** Tous les sliders affichent leur valeur en
`font-mono text-[10px]` à droite du label (ex. `BasicAdjustmentsCard.vue:33`,
`SvgTab.vue:84`, `FiltersCard`, `MasterStyleParams.vue:200`). C'est le point le plus
homogène du panneau — à préserver.

### Axe 2 — Réorganisation / regroupement

**2.1 Onglet SVG mixte.** `SvgTab.vue` empile une carte plate `.card` (DetailPicker +
traitements de tracé, `:49-148`) **puis** un accordéon (`SegmentationMethodCard`,
`:151`). Deux conventions de carte dans un seul onglet court.

**2.2 Onglet Texte trop long, sans hiérarchie.** `TypographyCard` empile toutes ses
sections plates « toujours ouvertes » : police/taille (essentiel) au même niveau
visuel que marges/dimensions de page (avancé). Aucun repli des options secondaires.

**2.3 Ordre des contrôles : globalement bon.** À noter comme positif : `StyleTab`
place volontairement le **nombre de couleurs avant le style** (`StyleTab.vue:219-222`)
car le compte contraint les styles pertinents. Logique à documenter comme intention.

### Axe 3 — Complétude des contrôles

**3.1 Aucun slider n'offre de saisie numérique exacte.** Tous les sliders sont en
glisser-seul ; la valeur affichée est en lecture seule. Impossible de taper/coller une
valeur précise ou reproductible. Concerne `BasicAdjustmentsCard`, `LevelsCard`,
`FiltersCard`, `MasterStyleParams`, `ColorCountSlider`, opacité de `LayerCard`.

**3.2 Unités/bornes manquantes sur des champs numériques.**

| Carte | Champ(s) | Problème | Sévérité |
|-------|----------|----------|----------|
| `PostProcessCard.vue:42-84` | `min_region_pixels`, `merge_delta_e`, `background_luminance` | aucune unité, aucune borne visible, aucun hint | Haute |
| `LayerCard.vue:305-323` | vitesse (`drawing_speed_mm_s`), `simplify_tolerance_mm` | unité non affichée ; libellé ne reflète pas l'unité du champ | Moyenne |
| `SegmentationMethodCard` | `num_colors` / `num_bands` / seuils | champs numériques sans unité, seuils en liste inline | Moyenne |

Modèle inverse à généraliser : `TypographyCard` (mm en label) et `TransformCard` (`%`).

**3.3 Reset éparse.** Reset par bande dans `MasterStyleParams.vue:274-277` ; reset
global du pré-traitement dans `ImageTab.vue:42-49`. Aucune autre carte n'offre de
« réinitialiser cette section » — pas de moyen simple de revenir aux défauts ailleurs.

**3.4 Contrôle réservé ambigu.** Le toggle « Curve fitting » est **désactivé avec un
badge TODO** (`SvgTab.vue:126-146`). Un contrôle grisé/TODO visible en permanence
ajoute du bruit : soit le masquer tant qu'il n'est pas livré, soit afficher un libellé
« bientôt disponible » non interactif et discret.

### Axe 4 — Aide & découvrabilité

**4.1 Couverture des hints inégale.** Bien fournis dans les cartes Image/SVG
(`BasicAdjustmentsCard.vue:96`, `LevelsCard`, `FiltersCard`, hints de `SvgTab`),
quasi absents dans `PostProcessCard` (aucun), `ColorModeCard` (aucun),
`PenSlotPicker` (tooltips seulement).

**4.2 Badges et états : présents mais à généraliser.** Bons exemples : badge
« Custom » (`MasterStylePicker`), badge « pinned » sur les bandes surchargées
(`MasterStyleParams.vue:266`), badge « ≈ stylo proche » sévérité-dépendant
(`LayerCard.vue:207-233`), point « non installé » (`PenSlotPicker.vue:71`). Le pattern
d'alertes conditionnelles de `ColorCountSlider`/`PaletteCard` gagnerait à être réutilisé
partout où un réglage a un effet d'écrêtage ou de repli silencieux.

---

## 4. Constats par onglet

### Onglet IMAGE — `tabs/ImageTab.vue`
Le mieux structuré : carte intro + reset global (`:37-54`), puis 4 accordéons
homogènes. Points : reset global présent **ici seulement** ; sliders sans saisie
numérique (axe 3.1). À conserver comme **référence d'agencement** pour les autres onglets.

### Onglet SVG — `tabs/SvgTab.vue`
| Problème | Réf. | Sévérité | Piste |
|----------|------|----------|-------|
| Mélange carte plate + accordéon | `:49-151` | Moyenne | Homogénéiser sur le pattern carte+accordéon |
| Toggle curve-fit désactivé/TODO toujours visible | `:126-146` | Faible | Masquer ou libellé « bientôt » discret |
| Champs segmentation sans unités | `SegmentationMethodCard` | Moyenne | Ajouter unités/bornes (axe 3.2) |

### Onglet STYLE — `tabs/StyleTab.vue`
| Problème | Réf. | Sévérité | Piste |
|----------|------|----------|-------|
| `PostProcessCard` sans unités/bornes/hints | `PostProcessCard.vue:42-84` | Haute | Étiqueter unités + bornes + hints |
| Cartes plates uniquement | `:188-252` | Faible | Accordéon optionnel pour post-process |
| (positif) alertes de `ColorCountSlider` | `ColorCountSlider.vue:180-214` | — | Pattern à étendre |

### Onglet TEXTE — `tabs/TextTab.vue`
| Problème | Réf. | Sévérité | Piste |
|----------|------|----------|-------|
| Onglet long sans repli avancé/essentiel | `TypographyCard.vue:165-349` | Moyenne | Replier marges/page sous accordéon |
| (positif) unités mm systématiques | `:213-349` | — | Modèle de complétude |

### Onglet CALQUES — `LayersSection.vue` / `LayerCard.vue`
Le plus abouti : clusters par intention (`:257-336`), quick-nav (`:211-246`), résumé
(`:355-365`). Points : vitesse/simplify de `LayerCard` sans unités (axe 3.2) ; repli
interne de `LayerCard` ≠ accordéon persistant des cartes Image (axe 1.2).

---

## 5. Plan d'amélioration priorisé

> Recommandations pour une future itération d'implémentation. Aucune n'est appliquée
> dans ce livrable (audit documenté seul).

**P1 — Slider unifié avec saisie numérique (axes 1.3, 3.1).** Extraire un composant
`LabeledSlider` (label + valeur + `<input type="number">` optionnel + unité) et
l'appliquer à tous les sliders du panneau. Conserve la lecture mono déjà cohérente,
ajoute la saisie exacte manquante. Cible : `BasicAdjustmentsCard`, `LevelsCard`,
`FiltersCard`, `MasterStyleParams`, `ColorCountSlider`, opacité `LayerCard`.

**P2 — Règle unique de carte (axes 1.1, 1.2, 2.1, 2.2).** Une seule convention :
`.card` + en-tête accordéon optionnel via `useAccordionPersistence`. Convertir les
blocs inline (C) et plats (B) sur ce modèle, et homogénéiser SVG/Style/Texte. Replier
par défaut les sections avancées (marges/page du Texte, post-process du Style).

**P3 — Unités, bornes et reset par section (axes 3.2, 3.3).** Étiqueter toutes les
unités/bornes manquantes (`PostProcessCard`, `LayerCard`, `SegmentationMethodCard`) sur
le modèle de `TypographyCard`/`TransformCard`. Ajouter un bouton « réinitialiser cette
section » par carte, sur le modèle du reset par bande de `MasterStyleParams`.

**P4 — Hints et alertes homogènes (axe 4).** Combler les hints absents
(`PostProcessCard`, `ColorModeCard`, `PenSlotPicker`) et réutiliser le pattern
d'alertes conditionnelles de `ColorCountSlider`/`PaletteCard` partout où un réglage
écrête ou se replie silencieusement.

**P5 — Clarifier les contrôles réservés (axe 3.4).** Décider du sort du toggle
curve-fit (`SvgTab.vue:126-146`) : masquer ou afficher un état « bientôt » discret et
non interactif, plutôt qu'un contrôle grisé permanent.

Ordre conseillé : P1 et P3 apportent le gain de complétude le plus visible ; P2 est
structurel (préalable utile à P1/P3) ; P4–P5 sont du polissage.

---

## 6. Effort & vérification

Chaque constat cite un fichier (et une ligne quand pertinent) vérifiable, et chaque
recommandation Pn renvoie aux fichiers concernés et à un axe.

---

## 7. Statut : implémenté (2026-06)

Les P1–P5 sont appliqués dans la même branche que cet audit.

Deux primitives partagées ont été ajoutées sous `components/edit/shared/` :

- **`LabeledSlider.vue`** — slider unifié : libellé (texte ou slot `#label`),
  saisie numérique éditable + unité à droite (ou lecture seule via `formatValue`),
  et hint optionnel. (P1)
- **`CollapsibleCard.vue`** — carte slate unique avec en-tête repliable persistant
  (`useAccordionPersistence`) et bouton **reset par section** optionnel
  (`resettable` / `canReset`). (P2 + P3)

Migrations :

- **P1 (saisie numérique)** — `BasicAdjustmentsCard`, `LevelsCard`, `FiltersCard`
  (via `LabeledSlider`) ; le rendu déclaratif des knobs `MasterStyleKnobs` (sliders
  `range` non-`percent`) ; `MasterStyleParams` (bandes + seuil) ; `ColorCountSlider`
  (nombre de couleurs) ; sliders `min-branch` et simplification de `SvgTab`.
- **P2 (carte unique + repli)** — les 4 cartes Image, `SegmentationMethodCard` et
  `PostProcessCard` passent par `CollapsibleCard` ; les sections avancées
  *Mise en page* et *Page* de `TypographyCard` deviennent repliables (repliées par
  défaut), les essentiels *Police* restent à plat.
- **P3 (unités/bornes + reset)** — unités sur `PostProcessCard` (px, ΔE, 0–1) et
  `LayerCard` (mm/s, mm) ; reset par section sur les 4 cartes Image et
  `PostProcessCard` (en plus du reset global de l'onglet Image).
- **P4 (aide)** — hints ajoutés à `ColorModeCard` (`printMode.modeHint`),
  `PenSlotPicker` (`mono.penHint`) et aux champs de `PostProcessCard`
  (`convert.minRegionHint` / `mergeDeltaEHint` / `bgLuminanceHint`). Le pattern
  d'alertes conditionnelles de `ColorCountSlider` reste la référence.
- **P5 (contrôle réservé)** — le toggle curve-fit désactivé de `SvgTab` est remplacé
  par une note discrète non interactive avec tag « bientôt ».

Vérifié : `vue-tsc --noEmit` ✓, `vitest run` (657 tests) ✓, `vite build` ✓, lint ✓.
