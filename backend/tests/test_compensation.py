"""Invariants of the compensation ledger.

Several of these encode rules a well-meaning change would "fix" in the wrong
direction, so each says why it exists. The policy fields mirror the `nutrients`
table, which is where the spec's research is stored as data rather than code.
"""

import pytest

from app.nutrition_core.compensation import (
    DEFAULT_CARRY_CAP,
    NutrientPolicy,
    effective_target,
    plan_carry,
)


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
