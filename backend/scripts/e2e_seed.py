"""Seed the minimum the end-to-end walk needs, without touching the network.

The full ETL downloads IFCT, INDB and USDA, which is far too slow and too
network-dependent for CI. But three of its loaders need no downloads at all:

  * `seed_nutrients`  -- the nutrient vocabulary and its compensation policy
  * `seed_reference`  -- the ICMR-NIN RDA and TUL rows, transcribed as Python
  * `seed_manual_ingredients` -- iodised salt, curd, sugar, coffee and tea

Between them that is enough for targets to compute and for food search to return
something real to log. These are genuine app rows, not synthetic test fixtures,
so the walk exercises the same code paths a seeded database does.

Idempotent: every loader is insert-or-update on a natural key, so running this
against an already-seeded development database changes nothing.

Usage:
    uv run python -m scripts.e2e_seed
"""

import sys

from app.db import SessionLocal
from etl.load_manual_ingredients import seed_manual_ingredients
from etl.load_nutrients import seed_nutrients
from etl.load_reference import seed_reference


def main() -> int:
    with SessionLocal() as db:
        nutrients = seed_nutrients(db)
        reference = seed_reference(db)
        ingredients = seed_manual_ingredients(db)
        db.commit()

    print(f"nutrients: {nutrients}")
    print(f"reference: {reference}")
    print(f"manual ingredients: {ingredients}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
