# Audit — pipeline d'envoi G-code, changement de couleur & suivi d'impression

> Périmètre : chaîne d'exécution machine uniquement (envoi série, flow-control,
> changement d'outil manuel/automatique via magasin, checkpoint / reprise,
> suivi de progression). **Hors périmètre volontaire** : les algorithmes de
> tracé (segmentation, raster, TSP, assignation perceptuelle des couleurs) —
> ils ne sont pas remis en cause ici.
>
> État global : **sain**. L'architecture est propre, découplée et testée
> (111 tests ciblés + 54 tests streamer/swap au vert lors de l'audit). Les
> points ci-dessous sont des correctifs ciblés, pas une refonte.

---

## 1. Envoi du G-code — « les cartes exécutent les messages reçus au bon moment »

**Conception : correcte et sûre.** `GcodeStreamer` (`hardware/streamer.py`)
applique le handshake standard « une ligne → attente de `ok` → ligne suivante »
(`_send_line` puis `_wait_ok`). C'est le protocole *simple send-response* :

- GRBL / Marlin / Klipper acquittent une ligne dès qu'elle entre dans le
  *planner buffer* (pas à la fin du mouvement physique), donc l'hôte continue
  d'alimenter la carte et le buffer reste plein → mouvement fluide, pas de
  famine ni de débordement. C'est le bon compromis sûreté/débit.
- `_wait_ok` boucle jusqu'à voir `ok`, en ignorant les lignes intermédiaires
  (`echo:`, `busy: processing`, températures Marlin). Chaque `read_line`
  ré-arme le timeout, donc un `busy:` périodique n'entraîne pas de faux
  timeout. **Bien vu.**
- `error` / `alarm` / `!!` → `StreamError` remonté et géré par la politique de
  récupération. `abort()` et le dwell `wait_ms` préemptable via
  `asyncio.wait_for(self._abort.wait(), …)` : un abort coupe court à un dwell
  au lieu d'attendre sa fin. **Bien vu.**
- `emergency_stop` envoie le payload temps-réel par dialecte (GRBL `0x18`,
  Marlin/Klipper `M112`, EBB `ES`) **hors file de lignes** puis annule la tâche
  — le seul moyen d'interrompre un `G1` déjà en cours d'exécution. **Correct.**
- Le `_send_lock` sérialise commandes manuelles et démarrage du streamer
  (double-check sous verrou pour la fenêtre TOCTOU `_require_idle` → écriture).
  **Correct.**

### Observations (robustesse, priorité moyenne/basse)

1. **[Moyen] Timeout d'ack pour un `M6` firmware bloquant.** En mode
   `tool_change_method` firmware, le déclencheur (`M6`) est envoyé comme une
   ligne normale et attend `ok` sous `ack_timeout_s = 30 s`. Si le firmware
   n'acquitte le `M6` qu'une fois le changement physique terminé (opérateur qui
   agit à la machine), un swap de plus de 30 s lève un `StreamError` parasite.
   Les modes `busy:` de Marlin atténuent le cas côté Marlin ; à documenter /
   rendre configurable par profil pour les firmwares qui restent muets pendant
   un M6.

2. **[Bas] Pas de numérotation de ligne + checksum Marlin (`Nxx …*ck`).** Le
   streamer ne gère pas les demandes de renvoi (`Resend: N`) : une ligne
   `Resend:` serait ignorée et le streamer attendrait un `ok` qui ne vient pas,
   jusqu'au timeout. Sans impact en USB court/propre ; à considérer pour les
   liaisons longues/bruitées.

3. **[Bas] Dwell `host_timed` mesuré depuis l'ack, pas depuis la fin du
   mouvement.** Pour un swap rack/host, `wait_ms` démarre à la réception du
   `ok` (ligne *mise en file*), pas à la fin physique du déplacement. Un
   `move_to_slot` suivi d'un `grab` peut donc déclencher la préhension avant que
   la tête soit arrivée. Mitigation actuelle : c'est à l'auteur du profil
   d'insérer un `M400`/`G4` de synchro. À rendre explicite (doc profil, ou
   insérer un sync buffer avant les étapes de préhension compilées par
   `HostMacroStrategy._compile_swap`).

---

## 2. Changement de couleur manuel & automatique via magasin

**Conception : complète et cohérente.** Le flux
génération → parsing → orchestration → streamer est bien découplé :

- Les templates (`tool_change.j2`, `pen_color_change.j2`, `pen_load.j2`)
  émettent des commentaires machine-lisibles qui **correspondent exactement**
  aux regex du parseur (`core/toolchange.py` : `_CHANGE_RE`, `_COLOR_RE`,
  `_LOAD_RE`). Vérifié un à un.
- `ToolChangeOrchestrator` + les 4 stratégies (firmware / host_macro / manual /
  single_pen) produisent un `SwapPlan` uniforme, converti en `SwapAction` de
  fil (`kind`, `prompt`, `commands`, `slot`).
- **Garde-fou magasin bien pensé** (`gcode.py` L528-573) : pour un magasin
  automatisé (`carousel`/`rack`), si la couleur requise n'est **pas
  physiquement présente** (slot non installé) **ou** s'il s'agit d'un **re-ink**
  (le slot porte encore une autre couleur), on **retombe sur une pause de
  chargement opérateur** (`pen_load.j2` → `M0`) au lieu de déclencher la
  séquence automatique — qui dessinerait sinon silencieusement avec l'ancienne
  encre. **Excellent.**
- Le suivi `slot_inks` par slot permet à un plan d'utiliser **plus de couleurs
  que de slots** (re-ink mid-print), avec un prompt qui nomme l'encre *voulue*
  et non le stylo sortant. **Correct.**
- Dégradation gracieuse : si un profil déclare un magasin automatisé mais sans
  séquence de swap exploitable, `guided_swap_actions` rattrape le `ValueError`
  et **retombe sur une pause manuelle** (au lieu d'un 500). **Bien vu.**
- `SwapAction.slot` est porté structurellement jusqu'à `PrintRun.swap_slot`,
  donc l'UI affiche le badge de slot sans reparser le texte localisé.

### Constat principal (voir §3, finding A) — priorité **haute**

Le seul défaut réel de cette section concerne le **suivi** d'un swap
*automatisé* : il est momentanément présenté comme une pause opérateur. Détaillé
ci-dessous.

---

## 3. Suivi de l'impression (progression, pause/reprise, checkpoint)

**Conception : solide.**

- Checkpoint SQLite *throttlé* (50 lignes / 2 s / à chaque bascule d'état) pour
  ne pas mettre un `fsync` synchrone sur la boucle asyncio à chaque `ok`, tout
  en gardant chaque frontière de récupération durable. **Bon compromis.**
- `build_resume_program` rejoue l'état modal (unités, G90/G91, dernière
  position) et émet un préambule (relève stylo + trajet retour) avant les lignes
  restantes → reprise sûre après coupure. **Correct.**
- `recover_interrupted` repasse en `paused` (jamais auto-`resume`) les runs
  laissés `running` par un crash — la position tête est inconnue après un arrêt
  sale. **Bonne décision de sûreté.**
- Le calcul du checkpoint absolu tient compte de la longueur du préambule sur
  un run repris (`latest_acked` live vs snapshot figé) — piège classique évité,
  avec commentaire à l'appui. **Bien vu.**
- Diffusion progression via `_broadcast` en `put_nowait` drop-oldest sur file
  bornée : un client WebSocket lent ne bloque jamais le streamer. **Correct.**

### Finding A — **[HAUTE — CORRIGÉ]** Un swap automatisé (magasin rack/host) s'affichait comme une pause opérateur

> **Statut : corrigé** dans ce même lot. Ajout d'un discriminant
> `StreamProgress.needs_operator` (True uniquement pour un swap
> `operator_confirm`). La queue ne repasse plus le run en `PAUSED` que
> pour ces swaps ; les swaps inline automatiques (`firmware`/`host_timed`)
> transitent toujours par `WAITING` (le run reste « occupé ») mais sans
> `swap_prompt`, donc le `SwapPromptModal` ne s'ouvre plus. Le flag est aussi
> propagé sur `/plotter/status` + `/ws/plotter` et le
> `PlotterSettingsModal` (chemin direct `/plotter/run`) gate désormais son
> encart « tool change — Continue » sur `needs_operator`. Tests ajoutés :
> `test_needs_operator_flag_distinguishes_swap_kinds` (streamer) et
> `test_automated_swap_does_not_surface_as_operator_pause` (queue).
> Description d'origine conservée ci-dessous pour traçabilité.

**Reproduit** (script `scratchpad/repro.py` pendant l'audit) :

```
WAITING emitted -> message='swap (host_timed)' slot=None
  (la queue traduit -> state=PAUSED, swap_prompt='swap (host_timed)')
```

Chaîne du défaut :

1. `GcodeStreamer._handle_swap` passe l'état à `WAITING` avec
   `message = f"swap ({action.kind})"` pour **toute** action inline non vide
   (`firmware` / `host_timed`), le temps d'émettre les commandes et leurs dwells
   (`streamer.py` L313-316).
2. `PrintQueue.checkpoint` traite **tout** `WAITING` de manière identique :
   `state → PAUSED`, `swap_prompt = message` (`queue.py` L414-423). Aucun
   discriminant entre pause opérateur et swap automatique.
3. `SwapPromptModal.vue` s'affiche dès que `state === 'paused' && swap_prompt`
   (L29). Il présente donc « ✋ Changez le stylo — J'ai changé, Reprendre »
   **pendant un swap entièrement automatisé**.

**Impact.** Pas de casse de correction (le swap se termine seul : le chemin
inline ne `clear()` jamais `_resume`, et « Reprendre » est un no-op). Mais :

- Sur une machine **rack/host avec dwells de plusieurs secondes**, la fenêtre
  `WAITING` dure toute la séquence — assez longtemps pour que le polling queue
  (3 s) attrape l'état et **fasse apparaître le modal opérateur à tort**.
- Le prompt affiché est le texte technique `swap (host_timed)`, sans slot ni
  swatch (`progress.slot` n'est pas renseigné pour le chemin inline, d'où
  `slot=None`).
- Si l'opérateur clique **Annuler**, le run est **avorté en plein swap**.
- Le run clignote `PAUSED → RUNNING` et pollue la vue file.

**Piste de correctif** (au choix) :
- Ne pas repasser un swap inline en `PAUSED` côté queue : ne traiter comme pause
  opérateur que `WAITING` issu d'un `kind == operator_confirm`. Pour cela,
  transporter le `kind` (ou un booléen `needs_operator`) sur `StreamProgress`
  (aujourd'hui absent), ou ne pas émettre `WAITING` du tout pour le chemin
  inline (garder `RUNNING` avec un `message` informatif).
- Corollaire : renseigner `progress.slot` aussi pour le chemin inline pour que
  le badge de slot soit correct si l'on choisit d'afficher un indicateur
  « swap automatique en cours » distinct (non bloquant).

### Finding B — **[BASSE]** Le WebSocket `/ws/plotter` n'expose pas `slot`

Le payload WS (`api/plotter.py` L250-259) envoie
`total/sent/acked/state/message` mais **pas** `StreamProgress.slot`. Sans
conséquence fonctionnelle : `SwapPromptModal` lit `swap_slot` depuis le run
polé (`GET /queue`), pas depuis le WS. À harmoniser pour cohérence si un jour
l'UI temps-réel veut le slot sans attendre le prochain poll (~jusqu'à 3 s de
latence pour l'apparition du modal après le park).

---

## Synthèse

| # | Axe | Constat | Priorité |
|---|-----|---------|----------|
| A | Suivi / couleur auto | Swap automatisé (rack/host) surfacé comme pause opérateur → modal parasite, Annuler avorte le swap | **Haute — ✅ corrigé** |
| 1 | Envoi G-code | `M6` firmware bloquant peut dépasser `ack_timeout_s` (30 s) | Moyenne |
| 3 | Envoi G-code | Dwell `host_timed` compté depuis l'ack, pas depuis la fin de mouvement (sync `M400` à la charge du profil) | Basse |
| 2 | Envoi G-code | Pas de checksum/renvoi Marlin (liaisons bruitées) | Basse |
| B | Suivi | WS `/ws/plotter` n'expose pas `slot` | Basse |

Tout le reste des trois axes est **correctement construit et adapté au besoin** :
flow-control sûr, garde-fou magasin (pas de dessin avec la mauvaise encre),
re-ink multi-couleurs, reprise après crash, checkpoint durable, arrêt d'urgence
par dialecte. Le seul correctif à traiter en priorité est le **Finding A**.
