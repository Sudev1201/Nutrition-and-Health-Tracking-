from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients


def test_seeding_creates_the_canonical_list(db):
    count = seed_nutrients(db)

    assert count >= 30
    assert db.query(Nutrient).filter_by(code="calcium").one().unit == "mg"
    assert db.query(Nutrient).filter_by(code="energy").one().unit == "kcal"


def test_protein_is_not_compensable(db):
    seed_nutrients(db)

    protein = db.query(Nutrient).filter_by(code="protein").one()

    assert protein.is_compensable is False
    assert protein.compensation_days == 0


def test_vitamin_k_carries_for_one_day_only(db):
    seed_nutrients(db)

    assert db.query(Nutrient).filter_by(code="vitamin_k").one().compensation_days == 1


def test_sodium_is_excess_sensitive_but_never_carried_up(db):
    seed_nutrients(db)

    sodium = db.query(Nutrient).filter_by(code="sodium").one()

    assert sodium.is_compensable is False
    assert sodium.is_excess_sensitive is True


def test_seeding_twice_is_idempotent(db):
    seed_nutrients(db)
    seed_nutrients(db)

    assert db.query(Nutrient).filter_by(code="iron").count() == 1
