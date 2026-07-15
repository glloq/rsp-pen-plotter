# Audit projet — 2026-07-15

> Objectif : auditer le projet dans sa totalité et chercher des points à
> améliorer ou à finir d'implémenter. Périmètre : état de la CI, suites de
> tests backend/frontend, hygiène de types, dépendances (vulnérabilités),
> dettes UX documentées dans `docs/TODO.md`, stubs restants.

---

## 1. Verdict d'ensemble

Le projet est **fonctionnellement sain** : 1120 tests backend et 1001 tests
frontend passaient localement avant cet audit, lint `ruff`/`eslint` propres,
`vue-tsc` propre. En revanche la **CI GitHub Actions était rouge sur `main`
depuis le 2026-06-17** (aucun des runs récents n'était vert), pour deux causes
précises restées sous le radar parce que les suites de tests, elles,
passaient :

1. **Backend — gate « Mypy strict »** : 8 erreurs dans
   `pen_plotter/vision/tip_detect.py` (narrowing perdu dans `average_tips`)
   et `pen_plotter/api/tip_calibration.py` (pin GPIO `int | None` non
   rétréci), introduites avec la calibration caméra et déjà signalées
   « préexistantes » par l'audit offset-camera de juillet.
2. **Frontend — gate « Prettier check »** : `OffsetCameraSettings.test.ts`
   (depuis mi-juin) puis `TipDetectionTuner.vue` non formatés.

Conséquence : le job e2e (Playwright), qui dépend des deux premiers, ne
s'exécutait plus du tout — la protection de non-régression opérateur était
effectivement désactivée depuis un mois.

À cela s'ajoutaient **6 vulnérabilités npm** (2 high : `form-data`,
`vite` imbriqué sous vitest ; 3 moderate : `dompurify` ×8 advisories,
`js-yaml` ; 1 low : `esbuild`) et un `.nvmrc` à 20 alors que
`vue-i18n@11` exige Node ≥ 22 (warnings `EBADENGINE` à chaque `npm ci`,
et divergence avec `bootstrap.sh` qui installe Node 22).

## 2. Correctifs appliqués

### 2.1 CI remise au vert

- **mypy 8→0** : `average_tips` construit désormais les listes de points
  `tip_px`/`tip_mm` en une passe avec narrowing explicite (`is not None`),
  et en profite pour réutiliser les distances déjà calculées au lieu de
  refaire un `min(...)` avec `np.hypot` ; l'endpoint measure calcule un
  `light_pin: int | None` unique, rétréci une fois, utilisé pour l'allumage
  **et** l'extinction dans le `finally`. Aucun changement de comportement —
  les 84 tests tip_calibration / pen_offset / bitmap passent inchangés.
- **Prettier** : les deux fichiers reformatés (`npx prettier --write`) ;
  `format:check` repasse sur tout `src/`.
- **`.nvmrc` 20 → 22** : aligne CI et contributeurs sur l'exigence
  `engines` de `vue-i18n@11`/`@intlify` et sur ce que `bootstrap.sh`
  installe réellement en production.

### 2.2 Dépendances — 6 vulnérabilités → 0

- `npm audit fix` : `dompurify` ^3.4.12, `form-data`, `js-yaml`,
  `esbuild` top-level.
- Le `vite@8.0.14` imbriqué sous `vitest` (advisories high, corrigées en
  8.0.16) ne se résolvait pas par `npm audit fix` ; un `npm dedupe` a
  supprimé la copie imbriquée — vitest consomme désormais le `vite@7.3.6`
  hoisté (sa contrainte accepte `^6 || ^7 || ^8`). `npm audit` : **0
  vulnérabilité**.

### 2.3 DOMPurify ≥ 3.4.11 × happy-dom : 10 tests réparés sans perdre le patch

La montée `dompurify` 3.4.10 → 3.4.12 a cassé 10 tests (sanitizeSvg,
SafeSvgHtml, EditPreviewPane, useFileManager ×3) : sous **happy-dom**, le
durcissement cross-realm des versions patchées mutile la sortie SVG
(racine `<svg>` supprimée, attributs namespacés conservés à tort).
**Vérification dans le vrai Chromium** (Playwright, bundle
`purify.min.js` 3.4.12) : le comportement navigateur est correct — racine
conservée, `inkscape:label` retiré par défaut et conservé via `ADD_ATTR`.
C'est donc un artefact d'environnement de test, pas un bug produit ; un
retour à 3.4.10 aurait réintroduit les 8 advisories.

Correctif : les 6 fichiers de test concernés basculent sur **jsdom**
(pragma `@vitest-environment jsdom` + commentaire expliquant pourquoi,
`jsdom` ajouté en devDependency). jsdom reproduit le comportement
Chromium vérifié. Le reste de la suite reste sous happy-dom.

### 2.4 Fin de `window.prompt` (dette TODO 1.4) et dialogue unifié

Nouveau couple `composables/prompt.ts` + `PromptDialog.vue`, jumeau texte
du singleton `confirmAction`/`ConfirmDialog` existant (mêmes règles :
résolution du prompt concurrent en « annulé », backdrop = annuler, Échap
= annuler, Entrée = valider, autofocus + sélection du texte initial).
Trois appels natifs remplacés :

- `PlotterSettingsModal.onWizardConfirm` — nom du profil créé par le
  CapabilityWizard (le « Reste éventuel » explicite de TODO 1.4) ;
- `FilesPane.onFolderChange` — création de dossier de bibliothèque ;
- `FilesPane.moveFile` — déplacement vers un dossier.

`window.prompt` bloquait la boucle d'événements et est inutilisable sur
tablette/kiosque — surface visée par le mode Workshop. 7 tests neufs
(`PromptDialog.test.ts`) calqués sur `ConfirmDialog.test.ts`.

Au passage, `AvailableColorsPanel.removeColor` — dernière suppression
passant par `window.confirm` alors que GcodeFilesPanel / MacroPanel /
ProfileEditor / FilesPane utilisent tous `confirmAction` — adopte le
dialogue maison (variante `danger`). Seul `EditModalV2` garde
volontairement `window.confirm` (contrat synchrone du close-guard) ; son
commentaire, qui justifiait le choix par « même affordance que le panneau
couleurs », est mis à jour pour refléter la vraie raison.

i18n : nouvelle section `prompt.ok` (FR/EN) ; annuler réutilise
`confirm.cancel`.

### 2.5 Suite e2e : dérive silencieuse pendant le mois de CI rouge

Conséquence directe du §1 : rejouée localement (Chromium préinstallé +
backend `OMNIPLOT_FAKE_HARDWARE=1`, même protocole que le job CI), la
suite échouait à **3/10**. Deux dérives distinctes, aucune détectable
tant que le job ne tournait pas :

1. **Visite guidée non couverte.** La visite « Welcome to the editor »
   (overlay `modal-v2-tour`, corps du modal `inert`) a été ajoutée sans
   mise à jour du spec : elle interceptait tous les clics des deux
   parcours éditeur, et le test « Escape ferme l'éditeur » échouait parce
   qu'Escape dissipe d'abord la visite (comportement produit correct et
   testé unitairement — simplement jamais reflété dans le spec).
2. **Parcours expert jamais validé.** Le commit d'origine du spec
   (2026-06-15) notait explicitement « not executed here — validate in a
   browser+backend run before treating it as a gate » ; la CI est passée
   au rouge deux jours après, donc ce parcours n'a **jamais** tourné.
   Vérifié en navigateur réel : le bouton « Save style » expert commet le
   draft via un re-upload, et `uploadSelected` demande d'abord
   « Re-convert file — Overwrite? » (ConfirmDialog) que le spec
   n'acquittait pas.

Correctifs : `editor-parcours.spec.ts` seed le flag
`omniplot.onboarding.editorV2.v1` en `addInitScript` (les parcours
pilotent l'éditeur en opérateur qui revient) ; **nouveau test premier
lancement** — la visite apparaît, Escape la dissipe sans fermer l'éditeur
— qui aurait attrapé la dérive n°1 ; le parcours expert acquitte le
dialogue d'écrasement, désormais adressable via des ancres
`data-test="confirm-dialog-confirm/-cancel"` ajoutées à
`ConfirmDialog.vue`. Résultat local : **11/11 e2e verts** (modal-v2,
operator-parcours, editor-parcours).

### 2.6 Hygiène

- `tests/test_bitmap.py` : deux asserts passent de `getdata()` (déprécié,
  suppression Pillow 14 / 2027) à `tobytes()` — équivalent octet à octet
  en mode L ; la suite ne log plus de `DeprecationWarning` Pillow.

## 3. Constats sains (échantillon)

- Les clés i18n `offsetCamera.next.zone` / `next.light` signalées
  « inatteignables » par l'audit offset-camera ont déjà été nettoyées.
- Pas de `TODO`/`FIXME`/stub non documenté dans `pen_plotter/` ; les
  `NotImplementedError` restants sont les contrats abstraits attendus
  (`converters/base.py`, `algorithms/base.py`).
- `docs/TODO.md` est fidèle : tous les chantiers ouverts restants sont
  bien des reports v2.0 assumés (IPC inter-rôles, overlays Compare,
  Playwright étoffé, perf Pi, consommation IR directe).

## 4. Recommandations (non bloquants, suivis v2.0)

1. **Actions GitHub épinglées sur Node 20** : `actions/checkout@v4`,
   `setup-node@v4`, `upload-artifact@v4`, `astral-sh/setup-uv@v3` déclenchent
   l'avertissement de dépréciation Node 20 des runners (forcés en Node 24
   aujourd'hui). Monter les majeures à l'occasion d'un passage CI.
2. **EditModalV2** : basculer `useEditorCloseGuard.confirmDiscard` vers un
   contrat `() => boolean | Promise<boolean>` pour finir la migration vers
   `confirmAction` (3 blocs de tests à adapter).
3. **Surveiller happy-dom × DOMPurify** : si happy-dom corrige la
   compatibilité avec les checks cross-realm (>20.10.6), les 6 fichiers
   jsdom peuvent revenir à happy-dom et la devDependency `jsdom` partir.
4. **Queue polling → SSE/WebSocket** (TODO 1.2 « reste éventuel ») :
   toujours pertinent pour réduire le trafic LAN, non bloquant.
5. **Double dialogue au Generate expert** : sur une session experte
   fraîche (draft « dirty » par défaut), « Save style » enchaîne le clic
   Generate puis le dialogue « Re-convert file — Overwrite? ». Le
   commentaire de `uploadSelected` considère déjà qu'une action de plus
   haut niveau confirmée rend ce re-prompt redondant (`skipConfirm` du
   chemin non-rerenderable) ; appliquer la même logique au commit expert
   éviterait un clic. Décision produit à trancher — le spec e2e documente
   le comportement actuel.

## 5. Validation

- Backend : `pytest` **1120 passed, 1 skipped** (0 warning Pillow),
  `ruff check` / `ruff format --check` propres, `mypy pen_plotter`
  **0 erreur** (196 fichiers), `check_contracts.py` OK, `openapi.json`
  sans drift (aucun changement de schéma).
- Frontend : `vitest` **1008 passed** (1001 + 7 PromptDialog),
  `eslint` 0 erreur, `prettier --check` propre, `vue-tsc --noEmit`
  propre, `npm audit` 0 vulnérabilité, `npm run build` OK,
  `api-types.ts` sans drift.
