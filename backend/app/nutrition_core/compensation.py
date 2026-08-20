"""The compensation ledger.

The DRI framework states reference intakes are an "average daily intake over 1
or more weeks", which is what makes multi-day compensation valid at all. But the
buffer differs per nutrient, and the per-nutrient policy lives in the `nutrients`
table rather than here — this module is the arithmetic, the database holds the
research.

Everything here is pure and recomputable from the log. The ledger is append-only
by design: a running total that is mutated in place cannot be re-derived, and
cannot be tested for the invariants below.
"""

from dataclasses import dataclass

# A carry may not raise any single day by more than this share of its base
# target. Eating a whole day's missed calcium on top of tomorrow's is neither
# realistic nor safe.
DEFAULT_CARRY_CAP = 0.30

# Fibre is tighter: doubling fibre in a day causes GI distress.
FIBRE_CARRY_CAP = 0.25

CARRY_CAPS = {"fibre": FIBRE_CARRY_CAP}


@dataclass(frozen=True)
class NutrientPolicy:
    """Mirrors a row of `nutrients`, plus the reference bounds for this user."""

    code: str
    is_compensable: bool
    compensation_days: int
    is_excess_sensitive: bool
    ear: float | None
    tul: float | None
    carry_cap_fraction: float = DEFAULT_CARRY_CAP


@dataclass(frozen=True)
class Carry:
    """An adjustment to a future day. Positive raises, negative lowers."""

    day_offset: int
    amount: float


@dataclass(frozen=True)
class CarryPlan:
    carries: tuple[Carry, ...]
    # What could not be carried within the caps. Recorded rather than dropped,
    # so the weekly report can honestly show what was never made up.
    expired: float


def carry_cap_for(code: str) -> float:
    return CARRY_CAPS.get(code, DEFAULT_CARRY_CAP)


def plan_carry(
    policy: NutrientPolicy,
    consumed: float,
    effective_target: float,
    base_target: float,
) -> CarryPlan:
    """Work out what today's outcome hands to the following days."""
    delta = consumed - effective_target

    if delta < 0:
        return _plan_shortfall(policy, deficit=-delta, base_target=base_target)
    if delta > 0:
        return _plan_surplus(policy, surplus=delta, base_target=base_target)
    return CarryPlan(carries=(), expired=0.0)


def _spread(policy: NutrientPolicy, amount: float, base_target: float, sign: int) -> CarryPlan:
    days = policy.compensation_days
    if days <= 0:
        return CarryPlan(carries=(), expired=amount)

    per_day_cap = base_target * policy.carry_cap_fraction
    share = amount / days

    carried = min(share, per_day_cap)
    carries = tuple(Carry(day_offset=offset, amount=sign * carried) for offset in range(1, days + 1))

    # Anything the cap refused is gone: the debt does not roll onward for ever.
    return CarryPlan(carries=carries, expired=amount - carried * days)


def _plan_shortfall(policy: NutrientPolicy, deficit: float, base_target: float) -> CarryPlan:
    """A deficit only carries when the body can actually buffer the nutrient.

    Protein cannot (no storage pool), and a sodium shortfall is not a deficit
    worth making up at all — both fall through to `expired`, which is what the
    weekly report shows as uncompensated.
    """
    if not policy.is_compensable:
        return CarryPlan(carries=(), expired=deficit)
    return _spread(policy, deficit, base_target, sign=1)


def _plan_surplus(policy: NutrientPolicy, surplus: float, base_target: float) -> CarryPlan:
    """Only a storable, harmful surplus is worth rebalancing downward.

    Water-soluble vitamin surpluses are excreted, so there is nothing to
    rebalance and nothing to report — those return an empty plan with no expiry,
    which is different from a shortfall that expired.
    """
    if not policy.is_excess_sensitive:
        return CarryPlan(carries=(), expired=0.0)
    return _spread(policy, surplus, base_target, sign=-1)


def effective_target(policy: NutrientPolicy, base_target: float, carried_in: float) -> float:
    """Today's target after the ledger, clamped to the nutrient's own bounds.

    Two clamps, both required by the spec: an adjusted target may never exceed
    the Tolerable Upper Limit, and a downward adjustment may never take it below
    the EAR adequacy floor. Where ICMR set no limit there is nothing to clamp
    against, so a null TUL is left alone rather than given an invented ceiling.
    """
    target = base_target + carried_in

    if policy.tul is not None:
        target = min(target, policy.tul)
    if policy.ear is not None:
        target = max(target, policy.ear)

    return max(target, 0.0)
