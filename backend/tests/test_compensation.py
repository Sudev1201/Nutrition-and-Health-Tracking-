"""Invariants of the compensation ledger.

Several of these encode rules a well-meaning change would "fix" in the wrong
direction, so each says why it exists. The policy fields mirror the `nutrients`
table, which is where the spec's research is stored as data rather than code.
"""

import pytest

from app.models.nutrient import Nutrient
from app.nutrition_core.compensation import (
    DEFAULT_CARRY_CAP,
    SURPLUS_CARRY_DAYS,
    NutrientPolicy,
    effective_target,
    plan_carry,
)
from app.nutrition_core.targets import Target
from app.targets.service import _policies


def policy(**overrides) -> NutrientPolicy:
    defaults = {
        "code": "calcium",
        "is_compensable": True,
        "compensation_days": 2,
        "is_excess_sensitive": True,
        "ear": 800.0,
        "tul": 2500.0,
        "carry_cap_fraction": DEFAULT_CARRY_CAP,
    }
    return NutrientPolicy(**{**defaults, **overrides})


PROTEIN = policy(
    code="protein", is_compensable=False, compensation_days=0,
    is_excess_sensitive=False, ear=43.0, tul=None,
)
SODIUM = policy(
    code="sodium", is_compensable=False, compensation_days=0,
    is_excess_sensitive=True, ear=None, tul=2000.0,
)
FIBRE = policy(code="fibre", is_excess_sensitive=False, ear=None, tul=None, carry_cap_fraction=0.25)
VITAMIN_K = policy(code="vitamin_k", compensation_days=1, is_excess_sensitive=False, ear=None, tul=None)
VITAMIN_B12 = policy(code="vitamin_b12", is_excess_sensitive=False, ear=2.0, tul=None)


def test_a_shortfall_is_split_evenly_across_the_next_two_days():
    plan = plan_carry(policy(), consumed=600, effective_target=1000, base_target=1000)

    assert [carry.day_offset for carry in plan.carries] == [1, 2]
    assert [carry.amount for carry in plan.carries] == [200, 200]


def test_nothing_carries_when_the_target_was_met():
    plan = plan_carry(policy(), consumed=1000, effective_target=1000, base_target=1000)

    assert plan.carries == ()
    assert plan.expired == 0


"""
Protein has no storage pool. A 12-day human trial found no catch-up effect for
insufficient amino-acid intake -- excess is oxidised, not banked -- so a protein
deficit expires at midnight and per-meal distribution matters instead.
"""


def test_protein_never_carries_forward():
    plan = plan_carry(PROTEIN, consumed=30, effective_target=54, base_target=54)

    assert plan.carries == ()


def test_an_expired_protein_deficit_is_still_reported():
    """It must show up in the weekly report as uncompensated, not vanish."""
    plan = plan_carry(PROTEIN, consumed=30, effective_target=54, base_target=54)

    assert plan.expired == pytest.approx(24)


# A sodium "deficit" is not a thing to compensate.
def test_a_sodium_shortfall_never_carries_up():
    plan = plan_carry(SODIUM, consumed=900, effective_target=2000, base_target=2000)

    assert plan.carries == ()


def test_a_carry_is_capped_at_thirty_percent_of_the_base_target():
    """A large shortfall cannot be dumped onto the next two days -- eating 1,000
    extra mg of calcium tomorrow is neither realistic nor safe."""
    plan = plan_carry(policy(), consumed=0, effective_target=1000, base_target=1000)

    assert [carry.amount for carry in plan.carries] == [300, 300]


def test_what_the_cap_refuses_to_carry_expires_rather_than_disappearing():
    plan = plan_carry(policy(), consumed=0, effective_target=1000, base_target=1000)

    assert plan.expired == pytest.approx(400)


# Doubling fibre in a day causes GI distress, so its cap is tighter.
def test_fibre_carries_at_a_tighter_cap_than_other_nutrients():
    plan = plan_carry(FIBRE, consumed=0, effective_target=30, base_target=30)

    assert [carry.amount for carry in plan.carries] == [7.5, 7.5]


# Liver stores of vitamin K fall to about 25% in three days.
def test_vitamin_k_carries_for_one_day_only():
    plan = plan_carry(VITAMIN_K, consumed=0, effective_target=120, base_target=120)

    assert [carry.day_offset for carry in plan.carries] == [1]


def test_a_harmful_surplus_lowers_the_following_days():
    plan = plan_carry(policy(), consumed=1400, effective_target=1000, base_target=1000)

    assert [carry.amount for carry in plan.carries] == [-200, -200]


"""
Water-soluble vitamin surpluses are excreted. There is nothing to rebalance, so
a large B12 intake must produce no downward adjustment at all.
"""


def test_a_surplus_of_a_nutrient_that_is_simply_excreted_changes_nothing():
    plan = plan_carry(VITAMIN_B12, consumed=8, effective_target=2.2, base_target=2.2)

    assert plan.carries == ()
    assert plan.expired == 0


def test_an_effective_target_is_the_base_plus_what_was_carried_in():
    assert effective_target(policy(), base_target=1000, carried_in=180) == 1180


def test_an_adjusted_target_is_never_pushed_past_the_upper_limit():
    """The spec is explicit: never let an adjusted target exceed the TUL."""
    assert effective_target(policy(), base_target=2400, carried_in=400) == 2500


def test_a_nutrient_with_no_upper_limit_is_not_clamped():
    """ICMR deliberately set no limit for B12, so there is no ceiling to apply."""
    assert effective_target(VITAMIN_B12, base_target=2.2, carried_in=50) == pytest.approx(52.2)


def test_a_reduced_target_never_falls_below_the_adequacy_floor():
    """Compensating a surplus downward must not push intake under the EAR."""
    assert effective_target(policy(), base_target=900, carried_in=-300) == 800


def test_a_reduction_is_allowed_when_it_stays_above_the_floor():
    assert effective_target(policy(), base_target=1200, carried_in=-200) == 1000


def test_a_nutrient_with_no_floor_can_still_be_reduced():
    assert effective_target(SODIUM, base_target=2000, carried_in=-400) == 1600


def test_a_target_never_goes_negative_even_without_a_floor():
    assert effective_target(SODIUM, base_target=300, carried_in=-900) == 0


# --- a harmful surplus of a ceiling -------------------------------------------
#
# Sodium carries no shortfall, so its policy has no compensation days -- and until
# a surplus had days of its own, a 4,000 mg day lowered nothing at all. The spec
# lowers the next two days after any excess-sensitive surplus (manual step 5).

# Sodium as `_policies` builds it: no shortfall carry, no EAR, and no ICMR upper
# limit -- its 2,000 mg figure is itself the ceiling.
SALT = policy(
    code="sodium", is_compensable=False, compensation_days=0,
    is_excess_sensitive=True, ear=None, tul=None, surplus_days=SURPLUS_CARRY_DAYS,
)


def test_a_salty_day_lowers_the_next_two_days():
    """A 2,000 mg surplus halves to 1,000 mg a day, past the 30% cap of 600 mg."""
    plan = plan_carry(SALT, consumed=4000, effective_target=2000, base_target=2000)

    assert [carry.day_offset for carry in plan.carries] == [1, 2]
    assert [carry.amount for carry in plan.carries] == [-600, -600]


def test_what_the_cap_refuses_of_a_salty_day_expires():
    plan = plan_carry(SALT, consumed=4000, effective_target=2000, base_target=2000)

    assert plan.expired == pytest.approx(800)


def test_a_modest_sodium_surplus_is_split_evenly():
    plan = plan_carry(SALT, consumed=2600, effective_target=2000, base_target=2000)

    assert [carry.amount for carry in plan.carries] == [-300, -300]
    assert plan.expired == 0


def test_a_sodium_shortfall_still_never_carries_up():
    """Surplus days are for a surplus. A low-salt day is not a debt."""
    plan = plan_carry(SALT, consumed=900, effective_target=2000, base_target=2000)

    assert plan.carries == ()


def test_a_lowered_ceiling_has_no_floor_to_stop_it():
    """Two salty days in a row add up, and nothing props the ceiling back up:
    less sodium is never a shortfall."""
    assert effective_target(SALT, base_target=2000, carried_in=-600) == 1400
    assert effective_target(SALT, base_target=2000, carried_in=-1200) == 800


def test_surplus_days_default_to_the_compensation_days():
    """Unset, a surplus spreads exactly as it did before surplus days existed."""
    plan = plan_carry(
        policy(compensation_days=1), consumed=1400, effective_target=1000, base_target=1000
    )

    assert [carry.day_offset for carry in plan.carries] == [1]
    assert [carry.amount for carry in plan.carries] == [-300]


def test_surplus_days_leave_a_shortfall_to_the_compensation_days():
    plan = plan_carry(
        policy(compensation_days=1, surplus_days=2),
        consumed=600, effective_target=1000, base_target=1000,
    )

    assert [carry.day_offset for carry in plan.carries] == [1]


def test_no_surplus_days_lets_the_whole_surplus_expire():
    """What a nutrient held steady gets: it is smoothed in neither direction."""
    plan = plan_carry(
        policy(surplus_days=0), consumed=1400, effective_target=1000, base_target=1000
    )

    assert plan.carries == ()
    assert plan.expired == pytest.approx(400)


# --- how the targets service builds each policy ---------------------------------


def nutrient_row(code: str, compensable: bool, days: int, excess_sensitive: bool) -> Nutrient:
    """A `nutrients` row, never saved: `_policies` reads only its policy columns."""
    return Nutrient(
        code=code, display_name=code, unit="mg", category="mineral",
        is_compensable=compensable, compensation_days=days,
        is_excess_sensitive=excess_sensitive,
    )


# The policy columns as the seed has them (etl/load_nutrients.py).
ROWS = {
    "sodium": nutrient_row("sodium", compensable=False, days=0, excess_sensitive=True),
    "calcium": nutrient_row("calcium", compensable=True, days=2, excess_sensitive=True),
    "vitamin_k": nutrient_row("vitamin_k", compensable=True, days=1, excess_sensitive=False),
    "protein": nutrient_row("protein", compensable=False, days=0, excess_sensitive=False),
}
TARGETS = {
    "sodium": Target("sodium", ear=None, rda=2000.0, tul=None, kind="ceiling"),
    "calcium": Target("calcium", ear=800.0, rda=1000.0, tul=2500.0, kind="target"),
    "vitamin_k": Target("vitamin_k", ear=None, rda=55.0, tul=None, kind="target"),
    "protein": Target("protein", ear=42.9, rda=53.95, tul=None, kind="target"),
}


def test_a_ceiling_spreads_a_surplus_over_two_days_and_carries_no_shortfall():
    sodium = _policies(TARGETS, ROWS, disabled=frozenset())["sodium"]

    assert sodium.surplus_days == SURPLUS_CARRY_DAYS
    assert sodium.is_compensable is False
    assert sodium.compensation_days == 0


def test_a_compensable_nutrient_spreads_a_surplus_as_it_always_has():
    policies = _policies(TARGETS, ROWS, disabled=frozenset())

    assert policies["calcium"].surplus_days == 2
    assert policies["vitamin_k"].surplus_days == 1


def test_a_nutrient_that_is_not_excess_sensitive_has_no_surplus_days():
    assert _policies(TARGETS, ROWS, disabled=frozenset())["protein"].surplus_days == 0


def test_a_nutrient_held_steady_is_not_lowered_after_a_surplus():
    """Only vitamin K is held steady today, on warfarin. Whatever is held steady
    next -- a ceiling included -- is smoothed in neither direction."""
    policies = _policies(TARGETS, ROWS, disabled=frozenset({"vitamin_k", "sodium"}))

    assert policies["vitamin_k"].surplus_days == 0
    assert policies["sodium"].surplus_days == 0
