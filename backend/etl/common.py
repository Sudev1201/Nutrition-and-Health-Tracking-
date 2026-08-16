from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).parent / ".cache"

KCAL_PER_KJ = 1 / 4.184

# Multiplier to convert a source unit into a canonical unit.
_CONVERSIONS: dict[tuple[str, str], float] = {
    ("g", "g"): 1.0,
    ("g", "mg"): 1_000.0,
    ("g", "ug"): 1_000_000.0,
    ("mg", "mg"): 1.0,
    ("mg", "ug"): 1_000.0,
    ("mg", "g"): 0.001,
    ("ug", "ug"): 1.0,
    ("ug", "mg"): 0.001,
    ("kj", "kcal"): KCAL_PER_KJ,
    ("kcal", "kcal"): 1.0,
}


def to_canonical(value: float, source_unit: str, target_unit: str) -> float:
    """Convert a source value into the nutrient's canonical unit.

    IFCT's machine-readable mirror stores everything in SI base units — a
    calcium value of 0.121 means 121 mg — while the printed book uses mg and
    ug. Every load path goes through here so that difference is handled once.
    """
    try:
        factor = _CONVERSIONS[(source_unit.lower(), target_unit.lower())]
    except KeyError as exc:
        raise ValueError(f"No conversion from {source_unit} to {target_unit}") from exc
    return value * factor


class ColumnMapUnresolved(Exception):
    """A loader's column map names something that is not actually there.

    Deliberately fatal rather than skipped, for the same reason
    etl.load_recipes.RecipeIngredientMissing is: both column maps and the
    nutrient list are static, so a typo drops one nutrient across every row of
    the source at once, and the result still looks like a complete load. That
    is exactly how `free_sugar` stayed missing from all 542 IFCT foods for a
    whole plan while the ETL reported success on every run. Loud beats silent.
    """


def require_column_map(
    map_name: str,
    column_map: dict[str, tuple[str, str]],
    nutrient_codes: set[str],
    source_columns: set[str],
) -> None:
    """Check a loader's column map against reality before loading a single row.

    Two failure modes, both silent before this existed and both invisible in a
    successful-looking run:

    * a nutrient code in the map that no seeded nutrient answers to (a typo, or
      a nutrient renamed in etl/load_nutrients.py);
    * a source column in the map that the file being read does not publish (a
      typo, or an upstream release that renamed or dropped a column).
    """
    missing_nutrients = sorted(
        code for _, (code, _) in column_map.items() if code not in nutrient_codes
    )
    missing_columns = sorted(set(column_map) - source_columns)

    problems = []
    if missing_nutrients:
        problems.append(f"unseeded nutrient codes {missing_nutrients}")
    if missing_columns:
        problems.append(f"columns absent from the source {missing_columns}")
    if problems:
        raise ColumnMapUnresolved(f"{map_name}: " + "; ".join(problems))


def cached_download(url: str, filename: str) -> Path:
    """Download once into etl/.cache and reuse it on later runs."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / filename

    if not target.exists():
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    return target
