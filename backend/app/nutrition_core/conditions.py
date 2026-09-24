"""Condition and drug-interaction overlay.

Applied on top of the base targets. Every rule here is quantitative and sourced
from the guideline research in the design spec.

The engine never resolves a contradiction on the user's behalf: conditions that
give opposite instructions produce a flag for clinician review and leave the
ICMR baseline in place, because silently averaging a 1,500 mg sodium ceiling
with a 6-10 g salt recommendation serves neither condition.
"""

from dataclasses import dataclass, replace

from app.nutrition_core.targets import Target

# Hypertension: sodium tightened from the ICMR 2,000 mg baseline.
HYPERTENSION_SODIUM_MG = 1500.0

# Lipid Association of India / general dyslipidaemia guidance.
HIGH_CHOLESTEROL_SATURATED_FAT_SHARE = 0.07
HIGH_CHOLESTEROL_DIETARY_CHOLESTEROL_MG = 200.0

# RSSDI's absolute band, applied as a floor under the per-calorie figure.
DIABETES_FIBRE_FLOOR_G = 25.0
DIABETES_FREE_SUGAR_CEILING_G = 25.0

KCAL_PER_G_FAT = 9.0

# Pairs whose advice points in opposite directions.
CONFLICTING_CONDITIONS = (
    ("hypertension", "hypotension"),
    ("hypothyroidism", "hyperthyroidism"),
)

CONFLICT_MESSAGES = {
    frozenset({"hypertension", "hypotension"}): (
        "Your profile lists both high and diagnosed symptomatic low blood pressure, which "
        "give opposite sodium advice. Targets have not been averaged — please discuss this "
        "with your clinician."
    ),
    frozenset({"hypothyroidism", "hyperthyroidism"}): (
        "Your profile lists both an under- and an over-active thyroid, which call for "
        "opposite iodine and energy advice. Targets have not been averaged — please discuss "
        "this with your clinician."
    ),
}

"""
Drug classes, matched on the medication name.

Only the interactions the spec verified are encoded: the levothyroxine window
and the potassium caution on renin-angiotensin drugs are both sourced directly
from the guideline research, and warfarin's vitamin K rule is a consistency
requirement rather than a target change. The spec wants these in a
`drug_interaction_rules` table so the list extends without code changes; until
that table exists, adding a name here is the honest interim.
"""
POTASSIUM_SPARING_DRUGS = (
    "ramipril", "enalapril", "lisinopril", "perindopril",  # ACE inhibitors
    "losartan", "telmisartan", "valsartan", "olmesartan",  # ARBs
    "spironolactone", "eplerenone", "amiloride",  # potassium-sparing diuretics
)
VITAMIN_K_CONSISTENCY_DRUGS = ("warfarin", "acenocoumarol")
EMPTY_STOMACH_DRUGS = ("levothyroxine", "thyroxine", "eltroxin")

# Raising potassium is the standard hypertension advice, but only when it is safe.
HYPERTENSION_POTASSIUM_MG = 4000.0


@dataclass(frozen=True)
class Warning:
    # condition-conflict | medication-timing | drug-interaction, from the overlay;
    # calorie-recalibrated | reference-framework | approaching-limit, from resolve_day.
    kind: str
    message: str


@dataclass(frozen=True)
class OverlayResult:
    targets: dict[str, Target]
    warnings: list[Warning]
    # Nutrients whose day-to-day variation must NOT be smoothed by the ledger.
    compensation_disabled: frozenset[str]


def _matches(medications: list[tuple[str, str]], names: tuple[str, ...]) -> bool:
    return any(any(name in drug.lower() for name in names) for drug, _ in medications)


def _retarget(targets: dict[str, Target], code: str, rda: float, kind: str = "target") -> None:
    existing = targets.get(code)
    if existing is None:
        targets[code] = Target(code=code, ear=None, rda=rda, tul=None, kind=kind)
    else:
        targets[code] = replace(existing, rda=rda)


def apply_conditions(
    base: dict[str, Target],
    conditions: list[str],
    medications: list[tuple[str, str]],
) -> OverlayResult:
    targets = dict(base)
    warnings: list[Warning] = []
    compensation_disabled: set[str] = set()
    selected = set(conditions)

    conflicted: set[str] = set()
    for pair in CONFLICTING_CONDITIONS:
        if set(pair) <= selected:
            conflicted.update(pair)
            warnings.append(
                Warning(
                    kind="condition-conflict",
                    message=CONFLICT_MESSAGES[frozenset(pair)],
                )
            )

    energy = base["energy"].rda

    # A condition in conflict contributes no target changes at all — that is what
    # "flagged rather than averaged" means in practice.
    def active(condition: str) -> bool:
        return condition in selected and condition not in conflicted

    if active("hypertension"):
        _retarget(targets, "sodium", HYPERTENSION_SODIUM_MG, kind="ceiling")

        if _matches(medications, POTASSIUM_SPARING_DRUGS):
            warnings.append(
                Warning(
                    kind="drug-interaction",
                    message=(
                        "High blood pressure would normally mean eating more potassium, but "
                        "that is unsafe on your medication, which already raises it. The "
                        "potassium target has been left alone — please review this with your "
                        "clinician."
                    ),
                )
            )
        else:
            _retarget(targets, "potassium", HYPERTENSION_POTASSIUM_MG)

    if active("high_cholesterol"):
        _retarget(
            targets,
            "saturated_fat",
            energy * HIGH_CHOLESTEROL_SATURATED_FAT_SHARE / KCAL_PER_G_FAT,
            kind="ceiling",
        )
        _retarget(
            targets, "cholesterol", HIGH_CHOLESTEROL_DIETARY_CHOLESTEROL_MG, kind="ceiling"
        )

    if active("type2_diabetes") or active("prediabetes"):
        # A floor, never a reduction: the per-calorie figure already clears the
        # ADA's >=14 g per 1,000 kcal, so this only ever raises fibre.
        _retarget(targets, "fibre", max(targets["fibre"].rda, DIABETES_FIBRE_FLOOR_G))
        _retarget(
            targets,
            "free_sugar",
            min(targets["free_sugar"].rda, DIABETES_FREE_SUGAR_CEILING_G),
            kind="ceiling",
        )

    if _matches(medications, VITAMIN_K_CONSISTENCY_DRUGS):
        # The goal on warfarin is steady vitamin K, not a weekly average — so the
        # ledger must not swing it up after a low day.
        compensation_disabled.add("vitamin_k")
        warnings.append(
            Warning(
                kind="drug-interaction",
                message=(
                    "On warfarin, vitamin K should stay steady from day to day rather than "
                    "being averaged out, so it is no longer carried forward."
                ),
            )
        )

    for drug, time in medications:
        if any(name in drug.lower() for name in EMPTY_STOMACH_DRUGS):
            warnings.append(
                Warning(
                    kind="medication-timing",
                    message=(
                        f"{drug} at {time} means the first food or drink of the day — "
                        "including milk coffee — should wait at least 60 minutes, and "
                        "calcium- or iron-rich foods should stay 4 hours clear."
                    ),
                )
            )

    return OverlayResult(
        targets=targets,
        warnings=warnings,
        compensation_disabled=frozenset(compensation_disabled),
    )
