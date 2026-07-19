"""Raffinement de l'ordre des chemins après le tri vpype.

Deux améliorations mesurées par ``docs/audit_optimisation_trace_2026-07-19.md``
au-dessus du glouton ``linesort`` de vpype :

- **Rotation de couture** : une boucle fermée peut être entamée à n'importe
  quel sommet — le glouton plus-proche-voisin choisit donc le point d'entrée
  qui minimise le trajet pen-up, au lieu de subir la couture d'origine
  (−19 % de pen-up sur ``circle_pack``).
- **2-opt à budget temps** au niveau des chemins (avec inversion de sens),
  candidats limités aux voisins spatiaux via ``cKDTree`` — même approche que
  :func:`pen_plotter.core.tsp.two_opt_improve`, mais sur des polylignes
  plutôt que des points (−6 à −13 % de pen-up supplémentaires).

Les lignes sont au format vpype : tableaux 1-D de complexes (x + iy). Le
résultat ne peut jamais être pire que l'entrée : chaque étape compare le
pen-up avant/après et conserve le meilleur ordre. Sans scipy, l'entrée est
retournée telle quelle (même dégradation gracieuse que ``core.tsp``).
"""

from __future__ import annotations

import time

import numpy as np
from numpy.typing import NDArray

__all__ = ["improve_order", "pen_up_length"]

ComplexLine = NDArray[np.complex128]

# Une boucle très échantillonnée n'a pas besoin d'exposer chaque sommet
# comme point d'entrée : 64 candidats suffisent pour placer la couture à
# une fraction de périmètre près, et bornent la taille du kd-tree.
_MAX_ENTRIES_PER_LOOP = 64


def pen_up_length(lines: list[ComplexLine]) -> float:
    """Longueur totale des trajets pen-up entre chemins consécutifs."""
    return float(sum(abs(b[0] - a[-1]) for a, b in zip(lines, lines[1:], strict=False)))


def improve_order(
    lines: list[ComplexLine],
    *,
    seam_rotation: bool = True,
    closed_tolerance: float = 0.1,
    two_opt_budget_s: float = 1.5,
) -> list[ComplexLine]:
    """Réordonne ``lines`` pour réduire le pen-up, sans jamais l'augmenter.

    Args:
        lines: Chemins dans l'ordre de tracé actuel (typiquement la sortie
            de ``linesort``).
        seam_rotation: Autorise la rotation de la couture des boucles
            fermées pendant le re-tri glouton. Désactivé, seule
            l'inversion de sens des chemins (déjà permise par vpype)
            est utilisée.
        closed_tolerance: Distance départ/arrivée sous laquelle un chemin
            est considéré fermé (unités utilisateur du SVG).
        two_opt_budget_s: Budget temps du raffinement 2-opt ; ``0``
            désactive la passe.

    Returns:
        Les mêmes chemins (géométrie identique au déplacement de couture
        près), réordonnés et éventuellement inversés/tournés.
    """
    if len(lines) < 3:
        return list(lines)
    try:
        from scipy.spatial import cKDTree  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return list(lines)

    best = list(lines)
    best_up = pen_up_length(best)

    if seam_rotation:
        candidate = _loop_aware_greedy(lines, closed_tolerance)
        candidate_up = pen_up_length(candidate)
        if candidate_up < best_up:
            best, best_up = candidate, candidate_up

    if two_opt_budget_s > 0:
        candidate = _two_opt_paths(best, two_opt_budget_s)
        candidate_up = pen_up_length(candidate)
        if candidate_up < best_up:
            best = candidate

    return best


def _rotate_closed(line: ComplexLine, k: int) -> ComplexLine:
    """Fait démarrer (et refermer) une boucle fermée au sommet ``k``."""
    body = line[:-1]
    return np.concatenate([body[k:], body[:k], body[k : k + 1]])


def _loop_aware_greedy(lines: list[ComplexLine], closed_tolerance: float) -> list[ComplexLine]:
    """Glouton plus-proche-voisin où les boucles fermées s'entament partout.

    Les chemins ouverts exposent leurs deux extrémités (entrée par la fin =
    sens inversé, comme ``linesort``) ; les fermés exposent jusqu'à
    :data:`_MAX_ENTRIES_PER_LOOP` sommets, la boucle étant réécrite pour
    démarrer au sommet choisi. Démarre du premier chemin de l'ordre reçu,
    comme vpype.
    """
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    n = len(lines)
    entry_pts: list[complex] = []
    entry_path: list[int] = []
    entry_vertex: list[int] = []  # -1 = entrée par la fin (chemin ouvert inversé)
    closed: list[bool] = []
    for i, line in enumerate(lines):
        is_closed = bool(abs(line[0] - line[-1]) < closed_tolerance) and len(line) > 3
        closed.append(is_closed)
        if is_closed:
            body_len = len(line) - 1  # dernier sommet = doublon du premier
            stride = max(1, body_len // _MAX_ENTRIES_PER_LOOP)
            for k in range(0, body_len, stride):
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
    path_ids = np.asarray(entry_path)
    visited = np.zeros(n, dtype=bool)

    order: list[ComplexLine] = [lines[0]]
    visited[0] = True
    pos = complex(lines[0][-1])

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
                    break
                k *= 4
        i = entry_path[chosen]
        v = entry_vertex[chosen]
        line = lines[i]
        if closed[i] and v > 0:
            order.append(_rotate_closed(line, v))
        elif not closed[i] and v == -1:
            order.append(line[::-1])
        else:
            order.append(line)
        visited[i] = True
        pos = complex(order[-1][-1])
    return order


def _two_opt_paths(lines: list[ComplexLine], time_budget_s: float) -> list[ComplexLine]:
    """2-opt sur l'ordre des chemins, inversion de sens comprise.

    Un mouvement retourne la tranche ``[i+1 .. j]`` de la tournée (ordre
    inversé, chaque chemin retourné) : les arêtes pen-up
    ``fin(i)→début(i+1)`` et ``fin(j)→début(j+1)`` deviennent
    ``fin(i)→fin(j)`` et ``début(i+1)→début(j+1)``. ``j == i+1`` dégénère
    en simple inversion d'un chemin. Les candidats ``j`` sont les chemins
    dont une extrémité (orientation d'origine) est proche de ``fin(i)``,
    via un kd-tree statique — même compromis que ``core.tsp``.
    """
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    n = len(lines)
    if n < 3:
        return list(lines)

    order = list(lines)
    starts = np.array([line[0] for line in order])
    ends = np.array([line[-1] for line in order])

    endpoint_pts = np.empty((2 * n, 2))
    endpoint_line = np.empty(2 * n, dtype=np.intp)
    for i, line in enumerate(order):
        endpoint_pts[2 * i] = (line[0].real, line[0].imag)
        endpoint_pts[2 * i + 1] = (line[-1].real, line[-1].imag)
        endpoint_line[2 * i] = i
        endpoint_line[2 * i + 1] = i
    tree = cKDTree(endpoint_pts)
    k = min(16, 2 * n)
    _, neighbour_pts = tree.query(endpoint_pts, k=k)

    # ``pos[id(chemin)]`` = position actuelle dans la tournée ; l'identité
    # d'un chemin est son index d'origine, porté par ``ids``.
    ids = list(range(n))
    pos = list(range(n))

    def apply_reversal(i: int, j: int) -> None:
        order[i + 1 : j + 1] = [line[::-1] for line in order[i + 1 : j + 1]][::-1]
        ids[i + 1 : j + 1] = ids[i + 1 : j + 1][::-1]
        seg_starts = starts[i + 1 : j + 1].copy()
        starts[i + 1 : j + 1] = ends[i + 1 : j + 1][::-1]
        ends[i + 1 : j + 1] = seg_starts[::-1]
        for p in range(i + 1, j + 1):
            pos[ids[p]] = p

    deadline = time.perf_counter() + max(0.0, time_budget_s)
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        for i in range(n - 2):
            if time.perf_counter() >= deadline:
                break
            d_cur = abs(ends[i] - starts[i + 1])
            # Candidats : chemins dont une extrémité d'origine est proche
            # de fin(i). Les deux extrémités du chemin i couvrent les
            # orientations qu'il a pu prendre depuis la construction du
            # kd-tree.
            seen: set[int] = set()
            for p in (2 * ids[i], 2 * ids[i] + 1):
                for q in neighbour_pts[p]:
                    seen.add(int(endpoint_line[q]))
            for cand in seen:
                j = pos[cand]
                if j < i + 1 or j > n - 2:
                    continue
                gain = (
                    d_cur
                    + abs(ends[j] - starts[j + 1])
                    - abs(ends[i] - ends[j])
                    - abs(starts[i + 1] - starts[j + 1])
                )
                if gain > 1e-9:
                    apply_reversal(i, j)
                    improved = True
                    break
    return order
