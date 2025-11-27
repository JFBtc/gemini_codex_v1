#!/usr/bin/env python3
# engine/vbp_core.py – v1.0.0
# Core logique VBP (sans UI) : calcul de zones en Ticks et en % contiguë.

from __future__ import annotations
from typing import Dict, Tuple, Optional


def compute_zone_ticks_exact(
    vbp: Dict[float, float],
    tick_size: float,
    zone_width_lines: int,
) -> Tuple[Optional[Tuple[float, float]], float, int]:
    """
    Zone en TICKS (largeur EXACTE) :
      - vbp : dict {price -> volume}
      - tick_size : taille de tick
      - zone_width_lines : nb de niveaux de prix (lignes) EXACT à couvrir.
    Retour:
      - zone : (lo, hi) ou None
      - share : part du volume total (0..1)
      - width_eff : largeur effective en lignes
    """
    if not vbp or zone_width_lines <= 0:
        return None, 0.0, 0

    levels = sorted(vbp.items(), key=lambda kv: kv[0])
    total = sum(v for _, v in levels)
    if total <= 0:
        return None, 0.0, 0

    tick = float(tick_size)
    max_span = (zone_width_lines - 1) * tick

    best_sum = 0.0
    best_lo: Optional[float] = None
    best_hi: Optional[float] = None

    n = len(levels)
    j = 0
    running = 0.0

    for i in range(n):
        p_i, v_i = levels[i]
        # Étend la fenêtre tant qu'on respecte la largeur max
        while j < n:
            p_j, v_j = levels[j]
            if (p_j - p_i) <= max_span + 1e-9:
                running += v_j
                j += 1
            else:
                break

        lo_i = levels[i][0]
        hi_i = levels[j - 1][0] if j > i else levels[i][0]

        if running > best_sum:
            best_sum = running
            best_lo, best_hi = lo_i, hi_i

        # Retire le niveau i de la somme courante
        running -= v_i

    if best_lo is None or best_hi is None or best_sum <= 0.0:
        return None, 0.0, 0

    width_lines_eff = int(round((best_hi - best_lo) / tick)) + 1
    if width_lines_eff < zone_width_lines:
        # On n'a pas réussi à respecter la largeur demandée
        return None, 0.0, width_lines_eff

    share = best_sum / total
    return (best_lo, best_hi), share, width_lines_eff


def compute_zone_pct_contiguous(
    vbp: Dict[float, float],
    tick_size: float,
    pct_target: float,
) -> Tuple[Optional[Tuple[float, float]], float, int]:
    """
    Zone en POURCENTAGE (% contiguë minimale) :
      - vbp : dict {price -> volume}
      - tick_size : taille de tick
      - pct_target : % du volume total à couvrir (0..100)
    Retour:
      - zone : (lo, hi) ou meilleure zone trouvée si aucune n'atteint la cible
      - share : part du volume total couverte (0..1)
      - width_lines : largeur en lignes
    """
    if not vbp:
        return None, 0.0, 0

    levels = sorted(vbp.items(), key=lambda kv: kv[0])
    total = sum(v for _, v in levels)
    if total <= 0:
        return None, 0.0, 0

    target = max(0.0, min(100.0, pct_target)) / 100.0
    tick = float(tick_size)

    best_zone: Optional[Tuple[float, float]] = None
    best_share = 0.0
    best_width = 0

    j = 0
    running = 0.0
    n = len(levels)

    for i in range(n):
        p_i, v_i = levels[i]
        # Étend la fenêtre jusqu'à atteindre la cible (ou épuiser les niveaux)
        while j < n and (running / total) < target:
            running += levels[j][1]
            j += 1

        if running > 0.0:
            lo = levels[i][0]
            hi = levels[j - 1][0]
            width_lines = int(round((hi - lo) / tick)) + 1
            share = running / total

            if share >= target:
                # On garde la zone la plus étroite, et à largeur égale celle qui a le plus de volume
                if (best_zone is None) or (width_lines < best_width) or (
                    width_lines == best_width and share > best_share
                ):
                    best_zone = (lo, hi)
                    best_share = share
                    best_width = width_lines
            else:
                # Si aucune zone n'atteint la cible, on conservera la meilleure atteinte
                if (best_zone is None) and (share > best_share):
                    best_zone = (lo, hi)
                    best_share = share
                    best_width = width_lines

        # On rétrécit la fenêtre en retirant le niveau i
        running -= v_i

    if best_zone is None:
        return None, 0.0, 0

    return best_zone, best_share, best_width
