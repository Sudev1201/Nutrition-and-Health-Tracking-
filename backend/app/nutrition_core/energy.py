"""Energy requirement, by ICMR-NIN 2020's own methodology.

    TEE = BMR(FAO/WHO/UNU 2004, age + sex + weight) x 0.90 (men) / 0.91 (women) x PAL

ICMR does **not** use the Henry equations. It applies a cumulative 10% downward
correction to FAO/WHO/UNU because Indian body composition carries relatively
more fat for a given weight. Reproduced against all six of ICMR's published
reference figures in `tests/test_energy.py`; every one lands within 0.32%.

The equations are weight-based and take no height. That is deliberate: the spec
found ICMR's published reference *heights* could not be verified against any
primary source, so nothing here may depend on one.
"""

from dataclasses import dataclass

# Physical activity levels, ICMR-NIN 2020.
PAL = {"sedentary": 1.40, "moderate": 1.80, "heavy": 2.30}

# Indian body-composition correction, applied to the FAO/WHO/UNU BMR.
BODY_COMPOSITION_CORRECTION = {"male": 0.90, "female": 0.91}

# FAO/WHO/UNU 2004 weight-based BMR, as (slope, intercept) per age band.
# The bands are genuinely discontinuous — a 29-year-old and a 31-year-old of the
# same weight get different equations, which is the published method, not a bug.
BMR_COEFFICIENTS = {
    "male": {30: (15.057, 692.2), 60: (11.472, 873.1), None: (11.711, 587.7)},
    "female": {30: (14.818, 486.6), 60: (8.126, 845.6), None: (9.082, 658.5)},
}

# 1 kg of body fat is about 7,700 kcal, so a 0.25 kg/week change is ~275 kcal/day.
KCAL_PER_KG_BODY_FAT = 7700.0
PACE_KG_PER_WEEK = {"gentle": 0.25, "steady": 0.5}

# The conventional floor for calorie restriction without medical supervision.
SAFE_FLOOR_KCAL = {"female": 1200.0, "male": 1500.0}


@dataclass(frozen=True)
class Body:
    sex: str
    age: int
    weight_kg: float
    activity: str


def _coefficients(sex: str, age: int) -> tuple[float, float]:
    try:
        bands = BMR_COEFFICIENTS[sex]
    except KeyError as exc:
        raise ValueError(f"unknown sex {sex!r}") from exc

    for upper_bound, coefficients in bands.items():
        if upper_bound is not None and age < upper_bound:
            return coefficients
    return bands[None]


def basal_metabolic_rate(body: Body) -> float:
    """Resting energy expenditure in kcal/day, before the activity multiplier."""
    slope, intercept = _coefficients(body.sex, body.age)
    return slope * body.weight_kg + intercept


def total_energy_expenditure(body: Body) -> float:
    """BMR, corrected for Indian body composition, scaled by activity."""
    if body.activity not in PAL:
        raise ValueError(
            f"unknown activity level {body.activity!r}; expected one of {sorted(PAL)}"
        )

    correction = BODY_COMPOSITION_CORRECTION[body.sex]
    return basal_metabolic_rate(body) * correction * PAL[body.activity]


def energy_target(body: Body, goal: str, pace: str | None) -> float:
    """The daily energy target for a goal, never below BMR or, for a loss, the safe floor.

    An unclamped deficit on a small, sedentary, older person lands under resting
    expenditure, which is not a diet. The clamp is the floor the spec requires;
    weight-driven recalibration later moves the target by bounded steps within it.
    """
    maintenance = total_energy_expenditure(body)

    if goal == "maintain":
        return maintenance

    if pace not in PACE_KG_PER_WEEK:
        raise ValueError(f"goal {goal!r} needs a pace, got {pace!r}")

    daily_change = PACE_KG_PER_WEEK[pace] * KCAL_PER_KG_BODY_FAT / 7.0

    if goal == "lose":
        # Never below BMR, and never below the safe floor -- unless maintenance itself
        # is lower, since a loss goal must never ask for more than maintenance.
        floor = max(basal_metabolic_rate(body), min(maintenance, SAFE_FLOOR_KCAL[body.sex]))
        return max(maintenance - daily_change, floor)
    if goal == "gain":
        return maintenance + daily_change

    raise ValueError(f"unknown goal {goal!r}")
