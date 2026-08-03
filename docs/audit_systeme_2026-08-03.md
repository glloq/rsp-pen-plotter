# Audit système exhaustif — 2026-08-03

Passe d'audit complète du projet (backend ~35 k LOC Python, frontend ~77 k LOC
Vue/TS) visant à **renforcer** le code sans ajouter de fonctionnalité : valider
que chaque sous-système fonctionne comme prévu et corriger les défauts réels.

## Méthode

1. **Base de référence** — l'intégralité des gates CI passent au départ :
   `ruff`, `mypy --strict`, `eslint`, `prettier`, `vue-tsc`, pytest
   (1238 tests), vitest (1037 tests), et tous les contrôles de drift
   (OpenAPI, types TS, manifests, contrats). Le système démarre et sert
   réellement (79 routes, 56 algorithmes, profils). Codebase déjà très
   auditée (voir les autres `docs/audit_*.md`).
2. **Découverte** — chasse de bugs ciblée sur sept sous-systèmes à risque
   (hardware, core gcode/queue/resume, converters, API/auth, domain/
   application, infra transversale, frontend), chaque finding exigeant
   `fichier:ligne` + scénario d'échec concret.
3. **Vérification** — chaque finding relu dans le code réel avant action ;
   deux ont été écartés (voir plus bas).
4. **Correction + test** — chaque correctif s'accompagne d'un test de
   régression. Suite finale : **pytest 1249**, **vitest 1040**, lint/type/
   build verts, drift en phase.

## Corrigé (backend — commit `fix(audit): …`)

### Sécurité machine / hardware
- **`goto` non borné** (`hardware/controller.py`) — un `goto` absolu ne
  validait pas la cible contre le workspace : une faute de frappe
  (`x_mm=2000` sur une machine 300 mm) envoyait la tête dans le châssis à
  vitesse de déplacement. Rejet 422 hors-workspace.
- **Reconnexion sur job actif** (`hardware/controller.py`) — `open_serial`
  écrasait le transport sans annuler la tâche de streaming ni fermer
  l'ancien lien (tâche orpheline pilotant la machine + fuite de handle).
  Refus si un job tourne ; fermeture propre d'une connexion inactive.
- **Jog plume baissée** (`hardware/commands.py`) — après un abort mi-trait la
  plume reste baissée ; un jog X/Y la traînait sur la feuille. Le jog X/Y
  relève désormais la plume d'abord (le jog Z explicite est respecté).

### Fiabilité
- **Reprise conservative traversant un tool change** (`core/resume.py`) —
  bug HIGH : le rembobinage vers la dernière plume levée pouvait franchir un
  `M0` déjà confirmé, redessinant la couche précédente avec la **mauvaise
  plume** et ré-émettant le `M0` en pause firmware brute (la queue filtrant
  les pauses guidées sur l'ancien checkpoint). Le scan arrière s'arrête
  désormais à la frontière de changement d'outil. La reprise conservative
  est le mode **par défaut**.
- **Self-update vs queue** (`api/system.py`, `queue.py`) — la garde
  « machine occupée » n'était évaluée qu'au démarrage de l'update ; pendant
  le rebuild (minutes, `await`) le worker pouvait réclamer un run et le
  streamer dans le redémarrage imminent. Le worker est mis en pause pour
  toute la durée de l'update.
- **Génération en pouces** (`core/gcode.py`) — un profil `units: inch`
  émettait `G20` mais les feedrates restaient en mm/min → tête ~25,4× trop
  rapide (+ effondrement du mode `fit`). La génération refuse désormais les
  profils pouces (mm-only, message clair) au lieu d'un overspeed silencieux.

### Robustesse aux entrées non fiables (l'app accepte des fichiers uploadés)
- **`<use>` SVG cyclique → OOM** (`core/pdf_postprocess.py`) — un SVG de
  204 octets avec `<use>` auto-référentiel (ou fan-out exponentiel type
  « billion laughs ») faisait exploser l'arbre. Plafond d'expansions +
  suppression des `<use>` restants.
- **HTML → WeasyPrint : SSRF + lecture fichier** (`converters/html.py`,
  `application/preview_raster.py`) — le HTML uploadé était rendu avec le
  fetcher par défaut, résolvant `http(s)://` / `file://` côté serveur.
  Fetcher restrictif (seul `data:` autorisé).
- **EPS ghostscript sans timeout** (`converters/eps.py`) — un PostScript en
  boucle infinie bloquait le worker indéfiniment. Timeout ajouté.
- **Options d'algorithme non bornées** (`contours`, `dither`) — `spacing_px`
  / `cell_px` fabriqués provoquaient un hang multi-secondes (érosion pleine
  toile) ou une allocation multi-Go. Self-clamp + early-out.
- **Couleur non-hex → 500** (`application/color_assignment.py`) — un SVG
  Inkscape avec `stroke="red"` / `hsl(...)` sur un groupe faisait planter
  l'attribution couleur (`int('rr', 16)`). Parse tolérant → « pas de snap ».
- **Clé API non-ASCII → 500** (`auth.py`) — `secrets.compare_digest` sur des
  `str` non-ASCII lève `TypeError`. Comparaison sur octets UTF-8 → 401 propre.
- **Buffer SLO non borné** (`domain/slo/runtime.py`) — `POST /slo/evaluate`
  acceptait des noms de métrique libres, créant une deque par nom sans
  éviction. Whitelist sur la table de budgets.

### Correction / durabilité
- **Calibration d'échelle** (`vision/tip_detect.py`) — l'extent bornait *tous*
  les pixels sombres ; une poussière déflate `mm/px` et dérègle tout le
  magasin. Utilise le plus grand composant connexe + garde de saturation.
- **Slot de changement d'outil** (`domain/toolchange/strategies.py`) —
  `current_slot` n'était mis à jour que pour un slot calibré ; un slot non
  calibré laissait la tête aller au slot précédent. Suivi inconditionnel.
- **`meta.json` timelapse** (`timelapse.py`) — écriture non atomique : une
  coupure/disque plein laissait un meta tronqué → frames orphelines
  invisibles. Écriture tempfile + `os.replace`.
- **Audit best-effort** (`audit.py`) — un échec d'écriture d'audit (disque
  plein, verrou SQLite) après une action physique renvoyait 500 → un retry
  ré-envoyait les commandes. L'audit n'échoue plus le caller (log seulement).
- **Tolérance de simplification 0.0** (`application/text_render.py`) — `or
  0.05` traitait un « 0.0 explicite » (simplification désactivée) comme non
  défini. Corrigé en `is not None`.

## Corrigé (frontend — commit `fix(ui): …`)

- **Statut plotter non réhydraté** — au reload la page repartait
  « déconnectée » (cockpit désactivé, progression figée) alors que le backend
  garde la liaison série. `plotter.hydrate()` au montage récupère
  `/plotter/status` et rouvre le flux WS si connecté.
- **REST écrasant le WS (queue)** — un poll REST lent pouvait faire régresser
  l'état poussé par `/ws/queue`. Garde `socketLive()` (comme le store plotter).
- **Gate magasin multi-placement** — le compte d'encres n'utilisait que le
  placement sélectionné alors que le G-code composite tous les placements
  visibles → le plan de chargement pouvait être sauté. Agrégation sur
  `visiblePlacements`.
- **Auto-timelapse print très court** — `autoActive` posé après `await
  start()` : un print terminé avant la résolution n'était jamais arrêté.
  Re-vérification post-await.

## Écarté après vérification (pas de correctif)

- **Tâche streamer « orpheline » à l'arrêt** (`controller.stream`) — signalé
  comme fuite mais **faux positif** : annuler la tâche externe propage
  l'annulation à la tâche interne attendue (`fut_waiter.cancel()`), qui suit
  déjà le chemin ABORTED. Vérifié empiriquement. Code d'origine conservé.

## Différé (risque/périmètre — à traiter séparément)

- **DNS-rebinding en mode ouvert** (`main.py`) — une allow-list de `Host`
  stricte fermerait l'attaque mais **casse le déploiement reverse-proxy
  supporté** (le backend voit alors `Host: plotter.local`, non-loopback, en
  mode ouvert). Une défense correcte demande une liste de hosts de confiance
  *configurable* (nouvelle fonctionnalité). Risque réel limité : le mode
  ouvert n'est autorisé que sur loopback.
- **SSRF caméra TOCTOU** — `validate_camera_url` résout puis `urllib`
  re-résout à la connexion (rebinding). Le correctif propre (épingler l'IP
  validée) est non trivial avec `urllib` ; il existe déjà une revalidation
  par redirection. Les URLs caméra sont usuellement des IP directes.
- **Origin WS en mode ouvert** — lecture cross-origin des frames
  status/queue. LOW ; partage la logique risquée ci-dessus.
- **Flattener IR incomplet** (`domain/ir/adapter.py`) — `S`/`T`/`A` ignorés,
  `C`/`Q` réduits à des cordes → perte de géométrie **silencieuse**. Concerne
  uniquement le chemin opt-in `OMNIPLOT_IR_ENABLED=1` (désactivé par défaut).
- **Quota librairie check-then-write** (`application/file_library.py`) — deux
  uploads concurrents peuvent dépasser légèrement le quota (soft, pas de
  corruption).
- **Timeout ack fixe 30 s** (`hardware/streamer.py`) — un tracé unique lent
  et long (> 30 s) pourrait expirer à tort ; changer le timeout de sécurité
  demande une validation sur matériel réel.

## État final

- Backend : ruff ✓, mypy strict ✓, **pytest 1249 passés / 1 skip**, drift ✓.
- Frontend : eslint ✓, prettier ✓, vue-tsc ✓, **vitest 1040 passés**, build ✓.
