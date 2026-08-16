"""Seed the food and reference database. Idempotent: safe to re-run.

Step order is dependency-driven, not alphabetical or file-creation order:

1. seed_nutrients       -- every other step looks nutrient codes up by name.
2. seed_reference       -- only needs nutrients.
3. load_ifct            -- needs nutrients; the bulk of ingredients.
4. seed_manual_ingredients -- needs nutrients; the five IFCT can't supply
   (salt, curd, sugar, brewed coffee, brewed tea). Must run before recipes:
   57 of the 72 authored dishes reference salt, and load_recipes raises
   RecipeIngredientMissing on any unknown ingredient code.
5. the USDA gap-fill    -- attaches B12/iodine onto ingredients created in
   steps 3 and 4, so it has to run after both.
6. load_recipes         -- needs every ingredient created above, manual five
   included.
7. load_indb            -- independent reference dishes; only needs nutrients,
   so its position is flexible, but it runs last here.

One commit at the end: a failure partway through should leave the previous
run's data untouched rather than a half-loaded database.
"""

import zipfile
from pathlib import Path

from app.db import SessionLocal
from etl.common import cached_download
from etl.load_ifct import IFCT_URL, load_ifct
from etl.load_indb import INDB_URL, load_indb
from etl.load_manual_ingredients import seed_manual_ingredients
from etl.load_nutrients import seed_nutrients
from etl.load_recipes import load_recipes
from etl.load_reference import seed_reference
from etl.load_usda import USDA_URL, load_usda_gapfill
from etl.recipes.south_indian import RECIPES

USDA_CSV_DIRNAME = "FoodData_Central_foundation_food_csv_2025-04-24"


def _usda_csv_paths() -> tuple[Path, Path, Path]:
    """Download (if needed) and extract (if needed) the USDA Foundation Foods
    release, returning the three CSVs load_usda_gapfill reads.

    Extraction is skipped once the target directory exists, so a second run
    doesn't re-unzip a ~50 MB archive it already expanded.
    """
    zip_path = cached_download(USDA_URL, "usda_foundation_food.zip")
    extract_root = zip_path.parent / "usda_foundation_food"
    csv_dir = extract_root / USDA_CSV_DIRNAME

    if not csv_dir.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_root)

    return csv_dir / "food.csv", csv_dir / "nutrient.csv", csv_dir / "food_nutrient.csv"


def main() -> None:
    db = SessionLocal()
    try:
        print("nutrients:", seed_nutrients(db))

        rda_rows, upper_limit_rows = seed_reference(db)
        print(f"reference rows: {rda_rows} RDA, {upper_limit_rows} upper limits")

        ifct_csv = cached_download(IFCT_URL, "ifct_compositions.csv")
        print("ingredients (IFCT):", load_ifct(db, ifct_csv))

        print("ingredients (manual):", seed_manual_ingredients(db))

        food_csv, nutrient_csv, food_nutrient_csv = _usda_csv_paths()
        print(
            "USDA gap-fill rows:",
            load_usda_gapfill(db, food_csv, nutrient_csv, food_nutrient_csv),
        )

        print("recipes (authored dishes):", load_recipes(db, RECIPES))

        indb_xlsx = cached_download(INDB_URL, "indb.xlsx")
        print("reference dishes (INDB):", load_indb(db, indb_xlsx))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
