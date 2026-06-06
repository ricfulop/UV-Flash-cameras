"""Balluffi-style excess expansion and apparent defect swelling calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


DILUTE_WARNING_FRACTION = 0.02


@dataclass(frozen=True)
class BalluffiResult:
    """Computed excess strain and apparent defect fraction."""

    epsilon_macro: float
    epsilon_lattice: float
    epsilon_excess: float
    c_app: float
    c_app_mol_percent: float
    warning: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


DEFECT_LOOKUP_TABLE = [
    {
        "c_app_mol_percent": 5.0,
        "balluffi_excess_linear_strain": 0.016666666666666666,
        "extra_length_48mm_mm": 0.80,
        "extra_diameter_250um_um": 4.2,
        "total_linear_strain_with_0p9pct_pt_cte": 0.025666666666666667,
    },
    {
        "c_app_mol_percent": 10.0,
        "balluffi_excess_linear_strain": 0.03333333333333333,
        "extra_length_48mm_mm": 1.60,
        "extra_diameter_250um_um": 8.3,
        "total_linear_strain_with_0p9pct_pt_cte": 0.042333333333333334,
    },
    {
        "c_app_mol_percent": 15.0,
        "balluffi_excess_linear_strain": 0.05,
        "extra_length_48mm_mm": 2.40,
        "extra_diameter_250um_um": 12.5,
        "total_linear_strain_with_0p9pct_pt_cte": 0.059,
    },
    {
        "c_app_mol_percent": 20.0,
        "balluffi_excess_linear_strain": 0.06666666666666667,
        "extra_length_48mm_mm": 3.20,
        "extra_diameter_250um_um": 16.7,
        "total_linear_strain_with_0p9pct_pt_cte": 0.07566666666666667,
    },
    {
        "c_app_mol_percent": 25.0,
        "balluffi_excess_linear_strain": 0.08333333333333333,
        "extra_length_48mm_mm": 4.00,
        "extra_diameter_250um_um": 20.8,
        "total_linear_strain_with_0p9pct_pt_cte": 0.09233333333333334,
    },
    {
        "c_app_mol_percent": 30.0,
        "balluffi_excess_linear_strain": 0.10,
        "extra_length_48mm_mm": 4.80,
        "extra_diameter_250um_um": 25.0,
        "total_linear_strain_with_0p9pct_pt_cte": 0.109,
    },
]


def constant_cte_strain(alpha_per_k: float, t_initial_k: float, t_final_k: float) -> float:
    """Return linear thermal strain for a constant CTE approximation."""

    return alpha_per_k * (t_final_k - t_initial_k)


def integrate_cte_strain(temperature_k: Iterable[float], alpha_per_k: Iterable[float]) -> float:
    """Integrate alpha(T) dT using a trapezoidal rule."""

    temps = list(temperature_k)
    alphas = list(alpha_per_k)
    if len(temps) != len(alphas):
        raise ValueError("temperature_k and alpha_per_k must have the same length")
    if len(temps) < 2:
        return 0.0

    total = 0.0
    for t0, t1, a0, a1 in zip(temps[:-1], temps[1:], alphas[:-1], alphas[1:]):
        total += 0.5 * (a0 + a1) * (t1 - t0)
    return total


def calculate_balluffi(
    epsilon_macro: float,
    *,
    epsilon_lattice: float | None = None,
    epsilon_cte: float | None = None,
) -> BalluffiResult:
    """Compute apparent defect swelling from macro and lattice/thermal strain.

    If synchronized lattice-parameter data are unavailable, pass ``epsilon_cte``
    and the result should be treated as apparent swelling.
    """

    if epsilon_lattice is None:
        if epsilon_cte is None:
            raise ValueError("Provide epsilon_lattice or epsilon_cte")
        epsilon_lattice = epsilon_cte

    epsilon_excess = epsilon_macro - epsilon_lattice
    c_app = 3.0 * epsilon_excess
    warning = None
    if c_app > DILUTE_WARNING_FRACTION:
        warning = (
            "Apparent defect fraction exceeds dilute Balluffi regime; "
            "report as apparent swelling unless lattice data validate it."
        )
    elif c_app < 0:
        warning = "Negative apparent defect fraction; check temperature/lattice baseline."

    return BalluffiResult(
        epsilon_macro=epsilon_macro,
        epsilon_lattice=epsilon_lattice,
        epsilon_excess=epsilon_excess,
        c_app=c_app,
        c_app_mol_percent=100.0 * c_app,
        warning=warning,
    )


def calculate_from_lengths(
    initial_length_mm: float,
    current_length_mm: float,
    *,
    epsilon_lattice: float | None = None,
    epsilon_cte: float | None = None,
) -> BalluffiResult:
    """Compute Balluffi result from measured 3D arc lengths."""

    if initial_length_mm <= 0:
        raise ValueError("initial_length_mm must be positive")
    epsilon_macro = (current_length_mm - initial_length_mm) / initial_length_mm
    return calculate_balluffi(
        epsilon_macro,
        epsilon_lattice=epsilon_lattice,
        epsilon_cte=epsilon_cte,
    )

