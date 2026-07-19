# Audit exhaustif du projet — 2026-07-19

> Objectif : valider que toutes les sous-parties du projet sont bien
> implémentées et qu'il ne reste pas de grosses erreurs de code ou de
> logique. Périmètre : les deux suites de tests, les 6 gates statiques de
> la CI, l'état réel de la CI GitHub sur `main`, une revue de code
> approfondie de la chaîne critique backend (queue → streamer →
> controller → resume → toolchange → génération G-code) et des stores
> frontend, et un balayage des stubs / TODO restants.

---

## 1. Verdict d'ensemble

Le projet est **complet et sain**. Toutes les sous-parties annoncées
(README, `docs/TODO.md`, roadmap v0.2) sont implémentées et couvertes par
les tests ; aucun stub, `TODO`/`FIXME` ou `NotImplementedError` hors
classes de base abstraites ne subsiste dans le code source. Les seuls
`NotImplementedError` sont les méthodes abstraites de
`converters/base.py` et `converters/algorithms/base.py` — normal.

État des vérifications locales (identiques aux gates CI) :

| Vérification | Résultat |
| --- | --- |
| Backend `ruff check` | ✅ 0 erreur |
| Backend `mypy` strict | ✅ 197 fichiers, 0 erreur |
| Backend `pytest` | ✅ 1138 passés, 1 skipped |
| `check_contracts.py` (D.5) | ✅ contracts OK |
| Drift OpenAPI (`openapi.json`) | ✅ aucun drift |
| Drift snapshot manifests | ❌ **1 ligne** (cf. §2.1) |
| Frontend `eslint` | ✅ 0 erreur, 0 warning |
| Frontend `prettier --check` | ✅ propre |
| Frontend `vue-tsc --noEmit` | ✅ 0 erreur |
| Frontend `vitest` | ✅ 1012 passés (125 fichiers) |
| Drift types TS (`api-types.ts`) | ✅ aucun drift |
| Frontend `vite build` | ✅ build OK (bundle chunké) |

En revanche la **CI GitHub Actions était rouge sur `main`** — tous les
runs récents (du 2026-06-18 au 2026-07-19) sont en échec — pour une seule
cause restée invisible localement (§2.1). Trois anomalies de logique
réelles ont par ailleurs été identifiées et corrigées dans la chaîne de
reprise/recovery (§2.2, §2.3).

## 2. Anomalies trouvées et corrigées

### 2.1 CI `main` rouge : drift du snapshot manifests (0.1.0 → 0.3.0)

**Constat.** Le step « Manifest snapshot drift check » du job backend
échoue sur tous les runs `main` récents (vérifié sur le run du
2026-07-19, sha `7de1832` : c'est l'**unique** step rouge ; le job E2E
Playwright est ensuite « skipped » en cascade, donc la protection de
non-régression opérateur ne tourne plus). Cause : la PR #340 a bumpé
`pen_plotter.__version__` de `0.1.0` à `0.3.0` mais a committé un
`frontend/src/domain/manifests/snapshot.json` généré **avant** le bump —
l'entrée `system` → « Backend version » y est restée `0.1.0`. Toute
régénération produit `0.3.0`, d'où le `git diff --exit-code` rouge.

**Fix.** Snapshot régénéré via `npm run gen:manifests` (1 ligne). La CI
`main` redevient verte au prochain push, ce qui réactive aussi le job E2E.

**Note de fond.** C'est la deuxième fois qu'un audit trouve la CI `main`
rouge de longue date (cf. `audit_projet_2026-07-15.md`, causes
différentes) sans que personne ne s'en aperçoive, parce que les suites de
tests, elles, passent. Une protection de branche « required status
checks » sur `main` (ou au minimum une notification d'échec) éviterait la
récidive — décision à prendre côté repo GitHub, pas dans le code.

### 2.2 Reprise en plein trait : la plume restait levée (perte d'encre)

**Constat.** Promesse du README : « *a power blip resumes from the last
stroke, not from the start* ». Or `core/resume.py::build_resume_program`
rejouait les unités, le mode absolu/relatif et la position XY — mais
**pas l'état plume levée/baissée**. Le préambule de reprise lève la
plume (`goto_command`), revient à la dernière position… et enchaîne
directement sur les lignes restantes. Si le checkpoint tombe **au milieu
d'une polyline** (cas majoritaire : le générateur émet
`pen_up → travel → pen_down → G1 × n` par polyline, et les polylines
longues — remplissages, flowfield, chemins TSP — font des centaines de
points), tout le reste de la polyline interrompue était « dessiné » en
l'air jusqu'au `pen_down` de la polyline suivante. Perte d'encre
silencieuse, aggravée par le throttle de checkpoint (~50 lignes) qui rend
la reprise mid-stroke quasi systématique après une coupure.

**Fix.** `_replay` piste désormais l'état plume en reconnaissant les
lignes `pen_up_command`/`pen_down_command` du profil **et** les overrides
par slot (`PenSlot.pen_up_command`/`pen_down_command`, comparaison
verbatim — l'override par slot est ré-émis tel quel). Quand le
checkpoint laisse la plume baissée et que le programme restant s'ouvre
sur un mouvement de tracé (`G1`/`G2`/`G3`), le préambule ré-abaisse la
plume après le retour en position. Garde-fou : si le restant s'ouvre sur
un `pen_up`/travel (frontière de polyline), on ne ré-abaisse pas — sinon
on tamponnerait un point parasite au point de reprise. Deux tests ajoutés
(`test_resume_mid_stroke_relowers_the_pen`,
`test_resume_at_polyline_boundary_keeps_pen_up`) ; les 4 tests existants
passent inchangés.

### 2.3 `skip_layer` : le badge nommait le numéro de slot, pas l'encre

**Constat.** `queue._next_layer_boundary` retournait comme label « le
premier groupe non vide » de la regex de frontière. Pour un commentaire
`; Change to pen slot 2 (Red)`, le premier groupe est `2` (numéro de
slot), pas `Red`. Conséquence : `skipped_layers` — qui alimente le toast
critique `queue.skipNotice` et le badge « ⚠ N sautée(s) » du cockpit —
affichait « 2 » là où l'opérateur attend « Red ». Le test
`test_next_layer_boundary_finds_change_comment` assertait ce comportement
(`(4, "1")`), en contradiction avec l'intention documentée (TODO 2.4 :
« ajoute le label »).

**Fix.** Regex passée en groupes nommés + helper `_boundary_label` qui
préfère label de plume / couleur / nom de calque, avec repli sur le
numéro de slot (label vide) puis `"layer"`. Test mis à jour
(`(4, "Blue")`).

## 3. Revue des sous-systèmes — rien d'autre à signaler

### 3.1 Backend

- **Queue durable (`queue.py`)** : checkpoints throttlés (50 lignes / 2 s
  + flush sur chaque bascule d'état), remap des indices de swap au
  resume, recovery par politique (`abort` / `pause_and_prompt` /
  `skip_layer`), re-queue sur course RuntimeError (busy/disconnect),
  `recover_interrupted` au boot (jamais d'auto-resume — position
  physique inconnue). Utilisation systématique du checkpoint **live**
  (`latest_acked`) et non du snapshot de ligne — les pièges classiques
  sont explicitement traités et testés.
- **Streamer (`hardware/streamer.py`)** : flow-control par `ok`,
  `SwapAction` 4 modes (operator_confirm / firmware / host_timed / none),
  dwell préemptable par abort, `needs_operator` distingue swap automatisé
  et pause opérateur. Cohérent avec la consommation côté queue.
- **Controller (`hardware/controller.py`)** : verrou `_send_lock` avec
  re-check anti-TOCTOU (commande manuelle vs job), broadcast borné
  drop-oldest, e-stop par dialecte (0x18 GRBL / M112 Marlin-Klipper / ES
  EBB) qui bypass la file, distinction cancel interne vs externe dans
  `stream()`. Solide.
- **Génération G-code (`core/gcode.py`)** : contrat de templates vérifié
  au boot, logique de pause unifiée (`core/pause_logic.py`) partagée avec
  le preflight (aucun drift possible du compte `pen_changes`), re-ink /
  promotion L7 / repli « load » quand l'encre n'est pas dans le magasin,
  offsets par plume opt-in avec enveloppe dans le check de débordement.
- **Tool change (`core/toolchange.py` + domain/toolchange)** :
  l'orchestrateur est bien la source de vérité (TODO 2.2 fermée) ; le
  repli manuel quand un profil rack/carousel n'a pas de séquence
  authorée évite le 500 opaque.
- **API / sécurité** : API-key opt-in en comparaison temps constant
  (`auth.py`), rate-limit, garde CSRF/Origin testée
  (`test_csrf_origin.py`), audit trail sur les actions sensibles, 409 sur
  la suppression d'un run en cours de streaming.
- **Persistence** : migrations additives (`_add_missing_columns`),
  `schema_version` stampé, engine injectable partout pour les tests.
- **Converters** : 56 algorithmes raster enregistrés et couverts par les
  manifests + snapshots d'options (le README annonce « 47 » — chiffre
  périmé *en dessous* de la réalité ; cosmétique).

### 3.2 Frontend

- **Stores** : `queue.ts` (single-flight, cadence adaptative 3 s/30 s,
  backoff exponentiel plafonné, détection des nouveaux skips par delta,
  purge du bookkeeping), `plotter.ts` (WS propriétaire du statut, les
  snapshots REST n'écrasent jamais un flux live ; reconnexion auto ;
  watcher deviceLost pendant un run), gardes anti double-clic
  (`busyIds`, `movementBusy`, `enqueuing`). Aucune anomalie.
- **Contrats** : `api-types.ts` généré depuis `openapi.json` et
  `snapshot.json` depuis le registre backend, tous deux gated en CI —
  après le fix §2.1, les trois drift checks sont verts.

### 3.3 Dette documentée (intentionnelle, pas des oublis)

`docs/TODO.md` est à jour et honnête : les seuls chantiers ouverts sont
explicitement reportés v2.0 (IPC inter-rôles 2.5, overlays Compare 3.1,
audit perf sur matériel 3.2, suite Playwright étoffée 3.4, consommateurs
IR directs 2.1-reste). Chacun est annoté avec sa raison (dépendance
matériel ou infra). Rien de « silencieusement manquant » n'a été trouvé
en croisant TODO.md, la roadmap et le code.

## 4. Points d'attention non bloquants (non corrigés ici)

1. **Protection de branche** : activer les « required status checks » sur
   `main` pour que le prochain drift de snapshot bloque la merge au lieu
   de pourrir silencieusement (§2.1, récidive).
2. **README « 47 algorithmes »** : le registre en expose 56 ; à
   rafraîchir à l'occasion.
3. **Reprise EBB** : `_replay` ne recouvre pas la position depuis les
   moves `SM` relatifs d'un programme EBB natif (pas de X/Y absolus à
   rejouer). Le préambule reste minimal (`G90`) — comportement inchangé,
   documenté ici pour mémoire.
4. **Labels i18n des prompts de swap** : les prompts générés côté backend
   (`Load X into magazine slot N…`) sont en anglais uniquement ; le
   frontend est bilingue FR/EN. Cohérent avec le choix « le G-code reste
   portable », mais à garder en tête si l'i18n des prompts devient une
   demande opérateur.

## 5. Fichiers modifiés par cet audit

- `frontend/src/domain/manifests/snapshot.json` — régénéré (Backend
  version 0.1.0 → 0.3.0) ; remet la CI `main` au vert.
- `backend/pen_plotter/core/resume.py` — rejeu de l'état plume +
  ré-abaissement mid-stroke avec garde-fou frontière de polyline.
- `backend/pen_plotter/queue.py` — label humain pour les frontières de
  couche (`_boundary_label`, groupes nommés).
- `backend/tests/test_resume.py` — 2 tests ajoutés.
- `backend/tests/test_queue.py` — assertion de label mise à jour.
