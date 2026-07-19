# Audit perf sur Raspberry Pi — procédure (v2, TODO 3.2 + 2.1c)

> La moitié automatisable de l'audit perf « sur matériel » est prête :
> scripts déterministes, critères de décision, gabarit de rapport. Ce
> document est la marche à suivre le jour où un Pi 4/5 de production
> est disponible. Durée totale estimée : ~30 minutes.

## Pré-requis

- Raspberry Pi 4 (4 Go+) ou Pi 5, Raspberry Pi OS 64-bit à jour.
- OmniPlot installé par `bootstrap.sh` (l'install standard — pas un
  venv de dev x86 copié).
- Alimentation officielle et refroidissement passif au minimum : le
  throttling thermique fausse les p95. Vérifier avant ET après chaque
  série : `vcgencmd get_throttled` doit rester `throttled=0x0`.
- Aucune impression en cours, service `omniplot` arrêté pendant les
  mesures (`sudo systemctl stop omniplot`) pour que le worker de la
  queue ne vole pas de CPU.

## Étape 1 — Baseline générale

```sh
cd ~/omniplot/rsp-pen-plotter/backend
.venv/bin/python scripts/perf_baseline.py --runs 7 --warmup 2
```

Copier la table de sortie dans `docs/perf-baseline.md` sous un titre
« Snapshot Pi <modèle> <date> » (ne pas écraser le snapshot container —
les deux formes se comparent). Les chiffres attendus sont ~3-5× le
container CI ; ce qui compte est **la forme** (convert dominant sur
bitmap, optimize dominant sur vecteur dense).

## Étape 2 — Décision IR : `perf_ir_compare.py`

C'est la mesure qui gate la bascule de `OMNIPLOT_IR_ENABLED` à on par
défaut (TODO 2.1c) :

```sh
.venv/bin/python scripts/perf_ir_compare.py --runs 9 --warmup 2
```

**Règle de décision** : basculer le défaut uniquement si la colonne
`ir/svg p95` est ≤ 1.00 sur **toutes** les lignes. Point de référence
container (2026-07-19, à re-mesurer sur Pi) :

| fixture | phase | ir/svg p95 |
| --- | --- | ---: |
| simple (2 paths, 1 layer) | optimize | 0.52 |
| simple | gcode | 0.31 |
| dense (1200 strokes, 3 layers) | optimize | 0.92 |
| dense | gcode | 0.15 |

Si le Pi confirme (attendu : l'avantage IR *grandit* sur un CPU lent,
le round-trip SVG étant du parse XML pur), la bascule se fait dans
`domain/ir/adapter.py::is_ir_enabled` (défaut `"1"`), avec le résultat
du banc collé dans la PR.

## Étape 3 — Gate CI recalibré

Le smoke gate CI (`scripts/perf_gate.py`) tourne avec une tolérance de
50 % pensée pour un runner GitHub. Après la baseline Pi, vérifier que
les constantes `REFERENCE_P95` restent pertinentes ; elles ne changent
que si la CI elle-même migre de runner.

## Étape 4 — SLO targets (roadmap §6)

Remplir la section « SLO targets » de `docs/ROADMAP_V0.2.md` avec les
p95 Pi mesurés (arrondis à la dizaine de ms supérieure), qui deviennent
les objectifs de l'évaluateur SLO (`OMNIPLOT_SLO_EVAL_ENABLED=1`).

## Étape 5 — Charge réaliste (manuel, ~10 min)

Avec le service relancé et l'UI ouverte depuis un autre appareil :

1. Importer une photo A4 dense, algorithme `flowfield`, 4 couleurs —
   noter le temps upload→preview affiché par l'UI (PerfOverlay via le
   flag `perf`).
2. Générer + envoyer dans la queue avec le profil réel de la machine,
   noter la latence de prévisualisation du simulateur.
3. Pendant le plot (fake hardware accepté :
   `OMNIPLOT_FAKE_HARDWARE=1`), vérifier que le cockpit reste fluide
   et que `/ws/queue` pousse bien les frames (pas de retour au polling
   3 s dans l'onglet Réseau).

Consigner l'ensemble dans `docs/perf-report.md` (section « Pi »).
