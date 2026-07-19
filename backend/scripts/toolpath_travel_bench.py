"""Banc d'essai : optimisation du tracé avant G-code (trajets pen-up et levées).

Compare, sur des sorties réelles des algorithmes raster du dépôt, plusieurs
stratégies d'ordonnancement des chemins et chiffre leur effet sur le temps de
plottage modélisé. Source des mesures du rapport
``docs/audit_optimisation_trace_2026-07-19.md``.

Variantes mesurées :

- ``V0 brut``       : ordre de génération (aucune optimisation) ;
- ``V1 actuel``     : pipeline de ``core.toolpath.optimize_svg``
  (``linemerge 0.1 → linesimplify 0.05 → linesort``) ;
- ``V2 +two-opt``   : V1 avec ``linesort --two-opt`` (250 passes, défaut vpype) ;
- ``V3 loop-aware`` : V1 puis re-tri glouton où une boucle fermée peut être
  entamée à n'importe quel sommet (rotation de la couture) ;
- ``V4 V3+2opt``    : V3 raffiné par le two-opt de vpype.

Modèle de temps (profil ``custom_plotter.yaml``, 1 unité utilisateur = 1 mm) :
dessin 60 mm/s, trajet 120 mm/s, levée + descente 2 × 0,15 s par chemin.
Les valeurs absolues dépendent de ce modèle ; les écarts relatifs entre
variantes n'en dépendent pas (mêmes géométries, mêmes vitesses).

Usage::

    cd backend && .venv/bin/python scripts/toolpath_travel_bench.py
"""

from __future__ import annotations

import time

import numpy as np
import vpype as vp
import vpype_cli

import pen_plotter.converters  # noqa: F401  — casse le cycle d'import core ↔ converters
from pen_plotter.core.toolpath import _doc_from_svg

SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://www.inkscape.org/namespaces/inkscape"

DRAW_MM_S = 60.0
TRAVEL_MM_S = 120.0
LIFT_S = 0.15  # par mouvement servo ; un chemin = levée + descente

MASK_SIZE = 400


def make_mask(size: int = MASK_SIZE) -> np.ndarray:
    """Retourne un masque disque (``True`` à l'intérieur) de ``size``²."""
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - size / 2, yy - size / 2)
    result: np.ndarray = r <= size * 0.42
    return result


def wrap_svg(group: str, size: int = MASK_SIZE) -> str:
    """Enveloppe un ``<g>`` de calque dans un SVG pivot autonome."""
    return (
        f'<svg xmlns="{SVG_NS}" xmlns:inkscape="{INK_NS}" '
        f'viewBox="0 0 {size} {size}" width="{size}" height="{size}">{group}</svg>'
    )


def doc_lines(doc: vp.Document) -> list[np.ndarray]:
    """Aplati les lignes (complexes vpype) d'un document en une liste ordonnée."""
    out: list[np.ndarray] = []
    for layer in doc.layers.values():
        for line in layer:
            if len(line) >= 2:
                out.append(np.asarray(line))
    return out


def lines_to_doc(lines: list[np.ndarray]) -> vp.Document:
    """Reconstruit un document vpype mono-calque depuis une liste de lignes."""
    lc = vp.LineCollection()
    for line in lines:
        lc.append(line)
    doc = vp.Document()
    doc.add(lc, 1)
    return doc


def pen_up_of(lines: list[np.ndarray]) -> float:
    """Longueur totale des trajets pen-up entre chemins consécutifs."""
    return float(sum(abs(b[0] - a[-1]) for a, b in zip(lines, lines[1:], strict=False)))


def pen_down_of(lines: list[np.ndarray]) -> float:
    """Longueur totale dessinée."""
    return float(sum(np.abs(np.diff(line)).sum() for line in lines))


def gap_histogram(lines: list[np.ndarray]) -> dict[str, int]:
    """Compte les trajets inter-chemins plus courts que quelques seuils.

    Chiffre l'opportunité d'un « chaînage » côté émetteur G-code (dessiner à
    travers un micro-saut plutôt que lever/reposer le stylo).
    """
    gaps = [abs(b[0] - a[-1]) for a, b in zip(lines, lines[1:], strict=False)]
    return {
        "<0.5": sum(1 for g in gaps if g < 0.5),
        "<1": sum(1 for g in gaps if g < 1.0),
        "<2": sum(1 for g in gaps if g < 2.0),
        "total": len(gaps),
    }


def loop_aware_sort(lines: list[np.ndarray], closed_tol: float = 0.11) -> list[np.ndarray]:
    """Tri glouton plus-proche-voisin où les boucles fermées s'entament n'importe où.

    Les chemins ouverts exposent leurs deux extrémités (avec inversion de sens
    comme ``linesort``) ; les chemins fermés (départ ≈ arrivée sous
    ``closed_tol``) exposent chaque sommet comme point d'entrée, la boucle
    étant réécrite pour démarrer — et se refermer — au sommet choisi.
    """
    from scipy.spatial import cKDTree

    n = len(lines)
    if n < 2:
        return list(lines)

    entry_pts: list[complex] = []
    entry_path: list[int] = []
    entry_vertex: list[int] = []  # -1 = entrée par la fin (chemin ouvert inversé)
    closed: list[bool] = []
    for i, line in enumerate(lines):
        is_closed = bool(abs(line[0] - line[-1]) < closed_tol) and len(line) > 3
        closed.append(is_closed)
        if is_closed:
            for k in range(len(line) - 1):  # dernier sommet = doublon du premier
                entry_pts.append(complex(line[k]))
                entry_path.append(i)
                entry_vertex.append(k)
        else:
            entry_pts.append(complex(line[0]))
            entry_path.append(i)
            entry_vertex.append(0)
            entry_pts.append(complex(line[-1]))
            entry_path.append(i)
            entry_vertex.append(-1)

    pts = np.column_stack([np.real(entry_pts), np.imag(entry_pts)])
    tree = cKDTree(pts)
    visited = np.zeros(n, dtype=bool)
    path_ids = np.asarray(entry_path)

    order: list[np.ndarray] = [lines[0]]
    visited[0] = True
    pos = lines[0][-1]

    for _ in range(n - 1):
        k = 8
        chosen: int | None = None
        while chosen is None:
            _, idx = tree.query([pos.real, pos.imag], k=min(k, len(pts)))
            for j in np.atleast_1d(idx):
                if not visited[path_ids[j]]:
                    chosen = int(j)
                    break
            if chosen is None:
                if k >= len(pts):
                    chosen = next(j for j in range(len(pts)) if not visited[path_ids[j]])
                k *= 4
        i = entry_path[chosen]
        v = entry_vertex[chosen]
        line = lines[i]
        if closed[i]:
            body = line[:-1]
            order.append(np.concatenate([body[v:], body[:v], body[v : v + 1]]))
        else:
            order.append(line if v == 0 else line[::-1])
        visited[i] = True
        pos = order[-1][-1]
    return order


def stats(tag: str, lines: list[np.ndarray], wall_s: float | None = None) -> dict[str, object]:
    """Assemble les métriques d'une variante (distances, temps modélisé, CPU)."""
    down = pen_down_of(lines)
    up = pen_up_of(lines)
    t_draw = down / DRAW_MM_S
    t_travel = up / TRAVEL_MM_S
    t_lift = len(lines) * 2 * LIFT_S
    return {
        "tag": tag,
        "paths": len(lines),
        "down": down,
        "up": up,
        "time_s": t_draw + t_travel + t_lift,
        "t_draw": t_draw,
        "t_travel": t_travel,
        "t_lift": t_lift,
        "wall_s": wall_s,
    }


def run_case(name: str, group_svg: str) -> None:
    """Mesure toutes les variantes sur un calque SVG et imprime le tableau."""
    svg = wrap_svg(group_svg)

    rows = [stats("V0 brut", doc_lines(_doc_from_svg(svg)))]

    t0 = time.perf_counter()
    doc1 = vpype_cli.execute(
        "linemerge --tolerance 0.1 linesimplify --tolerance 0.05 linesort",
        document=_doc_from_svg(svg),
    )
    w1 = time.perf_counter() - t0
    l1 = doc_lines(doc1)
    rows.append(stats("V1 actuel", l1, w1))

    t0 = time.perf_counter()
    doc2 = vpype_cli.execute(
        "linemerge --tolerance 0.1 linesimplify --tolerance 0.05 linesort --two-opt",
        document=_doc_from_svg(svg),
    )
    rows.append(stats("V2 +two-opt", doc_lines(doc2), time.perf_counter() - t0))

    t0 = time.perf_counter()
    l3 = loop_aware_sort(l1)
    w3 = time.perf_counter() - t0
    rows.append(stats("V3 loop-aware", l3, w1 + w3))

    t0 = time.perf_counter()
    doc4 = vpype_cli.execute("linesort --two-opt", document=lines_to_doc(l3))
    rows.append(stats("V4 V3+2opt", doc_lines(doc4), w1 + w3 + (time.perf_counter() - t0)))

    print(f"\n=== {name} ===")
    for r in rows:
        wall = f"  opt={r['wall_s']:.2f}s" if r["wall_s"] is not None else ""
        print(
            f"{r['tag']:>14}: chemins={r['paths']:5d}  dessin={r['down']:8.0f}  "
            f"pen-up={r['up']:8.0f}  temps~{r['time_s'] / 60:6.1f} min "
            f"[dessin {r['t_draw']:5.0f}s | trajet {r['t_travel']:4.0f}s | "
            f"levees {r['t_lift']:4.0f}s]{wall}"
        )
    print(f"  sauts V1: {gap_histogram(l1)}   sauts V3: {gap_histogram(l3)}")


def main() -> None:
    """Rend chaque style de test sur un masque disque et mesure les variantes."""
    from pen_plotter.converters.algorithms.circle_pack import CirclePackAlgorithm
    from pen_plotter.converters.algorithms.contours import ContoursAlgorithm
    from pen_plotter.converters.algorithms.crosshatch import CrosshatchAlgorithm
    from pen_plotter.converters.algorithms.dashes import DashesAlgorithm
    from pen_plotter.converters.algorithms.eulerian_hatch import EulerianHatchAlgorithm
    from pen_plotter.converters.algorithms.stippling import StipplingAlgorithm

    mask = make_mask()
    cases = [
        ("crosshatch (hachures croisées)", CrosshatchAlgorithm(), {}),
        ("dashes (tirets)", DashesAlgorithm(), {}),
        ("stippling (pointillisme)", StipplingAlgorithm(), {"density": 0.01}),
        ("circle_pack (cercles fermés)", CirclePackAlgorithm(), {}),
        ("contours (niveaux fermés)", ContoursAlgorithm(), {}),
        ("eulerian_hatch (référence auto-optimisée)", EulerianHatchAlgorithm(), {}),
    ]
    for name, algo, opts in cases:
        group = algo.render_layer(mask, "#000000", "Layer", options=opts)
        run_case(name, group)


if __name__ == "__main__":
    main()
