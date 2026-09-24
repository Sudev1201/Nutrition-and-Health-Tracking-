"""Personalised daily targets.

Each nutrient carries three numbers — an EAR adequacy floor, an RDA target shown
to the user, and a TUL ceiling where one exists. ICMR explicitly recommends the
EAR, not the RDA, for planning an individual's diet, which is what gives the
compensation engine a principled lower bound.

Micronutrients are looked up. Energy and the macros are *computed*, because they
depend on the body in front of us rather than on a reference adult.
"""

from dataclasses import dataclass

from app.nutrition_core.energy import Body, energy_target
from app.nutrition_core.recalibration import recalibrated_energy

# ICMR: 0.83 g/kg/day, or 1 g/kg for a cereal-based diet with low-quality
# protein — a rice-dominant diet without adequate pulses and milk.
PROTEIN_G_PER_KG = 0.83
PROTEIN_G_PER_KG_CEREAL_DOMINANT = 1.0
PROTEIN_EAR_G_PER_KG = 0.66

FIBRE_G_PER_2000_KCAL = 30.0

# Percentage-of-energy bands, with ICMR-NIN 2020's carbohydrate floor.
CARBOHYDRATE_ENERGY_SHARE = 0.55
CARBOHYDRATE_FLOOR_G = 130.0
FAT_ENERGY_SHARE = 0.25
SATURATED_FAT_ENERGY_SHARE = 0.10
FREE_SUGAR_ENERGY_SHARE = 0.10

KCAL_PER_G_CARBOHYDRATE = 4.0
KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_FAT = 9.0

# Figures that are limits rather than things to reach. A low-sodium day is not a
# shortfall, and neither is a day with little saturated fat.
CEILING_NUTRIENTS = frozenset({"sodium", "saturated_fat", "free_sugar", "cholesterol"})

# Energy-scaled by ICMR's own method, and stored per activity level. When a
# weight-driven recalibration moves the calorie target these move with it, by the
# same ratio; with no recalibration the ratio is exactly 1.
ENERGY_SCALED_REFERENCES = frozenset({"thiamine", "riboflavin", "niacin", "vitamin_b6"})


@dataclass(frozen=True)
class ReferenceValue:
    """One resolved `rda_reference` row: already filtered by sex, age and activity."""

    ear: float | None
    rda: float | None
    ai: float | None
    # The framework the row comes from ("ICMR-NIN-2020", "IOM", ...). Carried so a
    # target taken from outside ICMR can say so rather than pass as ICMR's.
    source: str | None = None


@dataclass(frozen=True)
class Target:
    code: str
    ear: float | None
    rda: float
    tul: float | None
    kind: str  # target | ceiling


def _kind(code: str) -> str:
    return "ceiling" if code in CEILING_NUTRIENTS else "target"


def build_targets(
    body: Body,
    goal: str,
    pace: str | None,
    cereal_dominant: bool,
    references: dict[str, ReferenceValue],
    upper_limits: dict[str, float],
    *,
    energy_offset_kcal: float = 0.0,
) -> dict[str, Target]:
    """Base targets, before any condition overlay or ledger adjustment.

    `energy_offset_kcal` is the weight-driven recalibration in force, if any. It
    moves the energy target -- bounded and floored in `recalibrated_energy` -- and
    through it the macros, fibre and the energy-scaled B vitamins. Protein does
    not follow it: protein is per kilogram of the weight the body actually has.
    """
    formula = energy_target(body, goal=goal, pace=pace)
    energy = recalibrated_energy(body, formula, energy_offset_kcal)
    energy_scale = energy / formula

    def make(code: str, rda: float, ear: float | None = None) -> Target:
        return Target(
            code=code,
            ear=ear,
            rda=rda,
            tul=upper_limits.get(code),
            kind=_kind(code),
        )

    protein_coefficient = (
        PROTEIN_G_PER_KG_CEREAL_DOMINANT if cereal_dominant else PROTEIN_G_PER_KG
    )

    targets: dict[str, Target] = {
        "energy": make("energy", energy),
        "protein": make(
            "protein",
            body.weight_kg * protein_coefficient,
            ear=body.weight_kg * PROTEIN_EAR_G_PER_KG,
        ),
        "fibre": make("fibre", energy / 2000.0 * FIBRE_G_PER_2000_KCAL),
        "carbohydrate": make(
            "carbohydrate",
            max(
                energy * CARBOHYDRATE_ENERGY_SHARE / KCAL_PER_G_CARBOHYDRATE,
                CARBOHYDRATE_FLOOR_G,
            ),
        ),
        "fat": make("fat", energy * FAT_ENERGY_SHARE / KCAL_PER_G_FAT),
        "saturated_fat": make(
            "saturated_fat", energy * SATURATED_FAT_ENERGY_SHARE / KCAL_PER_G_FAT
        ),
        "free_sugar": make(
            "free_sugar", energy * FREE_SUGAR_ENERGY_SHARE / KCAL_PER_G_CARBOHYDRATE
        ),
    }

    for code, reference in references.items():
        # Computed macros win: the table holds reference-adult figures, while
        # these are derived from this user's weight and energy.
        if code in targets:
            continue

        # ICMR publishes an RDA for most nutrients and an AI for the rest.
        figure = reference.rda if reference.rda is not None else reference.ai
        if figure is None:
            # A row with neither is not a usable target; leaving it out is
            # honest, whereas a zero would read as a shortfall every day.
            continue

        ear = reference.ear
        if code in ENERGY_SCALED_REFERENCES:
            figure *= energy_scale
            ear = ear * energy_scale if ear is not None else None

        targets[code] = make(code, figure, ear=ear)

    return targets
