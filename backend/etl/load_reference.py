"""Seed the ICMR-NIN 2020 nutrient requirement and upper-limit reference tables.

Every personalised target the app computes is derived from the numbers below, so
transcription accuracy matters more than almost anything else in this codebase.

Sources
-------
- RDA_ROWS (EAR / RDA / AI): ICMR-NIN, "A Brief Note on Nutrient Requirements for
  Indians, the Recommended Dietary Allowances (RDA) and the Estimated Average
  Requirements (EAR), ICMR - NIN, 2020" (the "brief note"), specifically:
    * Table 2a (protein, by sex, EAR/RDA in g/kg/d and g/d)
    * Table 3 (males — calcium, magnesium, iron, zinc, iodine, thiamine,
      riboflavin, niacin, vitamin B6, folate, vitamin B12, vitamin C,
      vitamin A, vitamin D; RDA 2020 and EAR 2020 columns)
    * Table 4 (females — same nutrients as Table 3)
  Retrieved 2026-08-16 from https://www.nin.res.in/rdabook/brief_note.pdf and
  read in full for this verification pass (see "Second verification pass"
  below for exactly what this document does and does not cover).
- UPPER_LIMIT_ROWS: the ICMR upper-limit committee report (2018 Tolerable Upper
  Intake Levels, ICMR-2018-TUL), with IOM (Institute of Medicine) values used
  as an explicit fallback where ICMR has not published a limit (magnesium,
  selenium, copper, manganese, phosphorus) or, for one row, no applicable
  ICMR category exists at all (postmenopausal iron — see below). The TUL
  committee report itself is a gated/paid ICMR publication; it was not
  independently re-fetched in this pass (see caveats below).

Second verification pass (2026-08-16)
--------------------------------------
The brief note PDF above was fetched and read end-to-end and checked against
every RDA_ROWS entry it could possibly cover (the general 18-59 adult, "usual
work"/moderate-activity figures):

  CONFIRMED against Table 2a/3/4, exact match, including the two figures most
  likely to be misremembered from secondary sources — women's zinc RDA is
  13.0 mg (not 13.2, a figure that circulates in some summaries) and vitamin D
  is expressed in the table as 600 IU, i.e. 15 ug, for the general adult band:
    protein (M/F EAR+RDA), calcium (M/F EAR+RDA), magnesium (M/F EAR+RDA),
    iron (M/F EAR+RDA), zinc (M/F EAR+RDA), iodine (M/F EAR+RDA),
    vitamin_a (M/F EAR+RDA), vitamin_d (M/F RDA, 18-59 band only),
    folate (M/F EAR+RDA), vitamin_b12 (M/F EAR+RDA), vitamin_c (M/F EAR+RDA),
    and the "moderate" activity row for thiamine, riboflavin, niacin and
    vitamin_b6 (M/F) — Table 3/4 print exactly one figure per B-vitamin per
    sex, and it matches this file's "moderate" row in every case.

  NOT covered by the brief note, and NOT independently re-confirmed against a
  freely-available primary source in this pass (the underlying ICMR-NIN 2020
  book that would contain them, and the 2018 TUL committee report, are both
  gated/paid ICMR publications — https://www.nin.res.in only exposes the
  6-page brief note for free):
    * The 60+ age-band rise for calcium (1200) and vitamin_d (20 ug / 800 IU) —
      the brief note gives only one adult figure per nutrient, no elderly
      split.
    * Protein's 60+ rows, which reuse the 18-59 figures.
    * sodium / potassium / selenium AI values — absent from the brief note.
    * The sedentary and heavy variants of thiamine/riboflavin/niacin/B6 — only
      a single (moderate) column is printed. As a plausibility check, the
      ratios between the sedentary/moderate/heavy figures given here track the
      sedentary/moderate/heavy energy ratios in the brief note's Table 1a
      (e.g. men's thiamine 1.4 : 1.8 : 2.3 vs. energy 2110 : 2710 : 3470 kcal —
      the same ~0.78 / ~1.28 ratios), which is consistent but not a direct
      table lookup.
    * All of UPPER_LIMIT_ROWS — the ICMR 2018 TUL committee report was not
      accessible in this session.
  These rows are kept exactly as specified (values and source tags
  unchanged), per an explicit product ruling that reviewed this data set and
  the specific gaps in it (elderly figures, the deliberately-absent UL rows
  for thiamine/riboflavin/biotin/vitamin_b12/potassium, magnesium's
  supplemental-only UL, and the IOM fallback for postmenopausal iron) and
  confirmed them as intentional rather than transcription errors. None are
  marked "UNVERIFIED" because that would both contradict the ruling and break
  the tests that assert their exact source tags.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit

ICMR = "ICMR-NIN-2020"
ICMR_TUL = "ICMR-2018-TUL"
IOM = "IOM"

# (nutrient, sex, age_band, activity, ear, rda, ai, source)
# Activity is set only for the four energy-scaled B vitamins. The commonly
# quoted ICMR B-vitamin numbers are the MODERATE column; applying them to a
# sedentary user over-targets by roughly 25%.
RDA_ROWS: list[tuple] = [
    ("protein", "male", "18-59", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "18-59", None, 36.3, 45.7, None, ICMR),
    ("protein", "male", "60+", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "60+", None, 36.3, 45.7, None, ICMR),

    ("calcium", "male", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "female", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "male", "60+", None, 800, 1200, None, ICMR),
    ("calcium", "female", "60+", None, 800, 1200, None, ICMR),

    ("iron", "male", "18-59", None, 11, 19, None, ICMR),
    ("iron", "female", "18-59", None, 15, 29, None, ICMR),
    ("iron", "male", "60+", None, 11, 19, None, ICMR),
    # ICMR publishes no postmenopausal category; the spec requires falling
    # back to the IOM value rather than applying the menstruating figure.
    ("iron", "female", "60+", None, 5, 8, None, IOM),

    ("magnesium", "male", "18-59", None, 370, 440, None, ICMR),
    ("magnesium", "female", "18-59", None, 310, 370, None, ICMR),
    ("zinc", "male", "18-59", None, 14, 17, None, ICMR),
    ("zinc", "female", "18-59", None, 11, 13.0, None, ICMR),
    ("iodine", "male", "18-59", None, 95, 150, None, ICMR),
    ("iodine", "female", "18-59", None, 95, 150, None, ICMR),
    ("sodium", "male", "18-59", None, None, None, 2000, ICMR),
    ("sodium", "female", "18-59", None, None, None, 2000, ICMR),
    ("potassium", "male", "18-59", None, None, None, 3510, ICMR),
    ("potassium", "female", "18-59", None, None, None, 3510, ICMR),
    ("selenium", "male", "18-59", None, None, None, 40, ICMR),
    ("selenium", "female", "18-59", None, None, None, 40, ICMR),

    ("vitamin_a", "male", "18-59", None, 460, 1000, None, ICMR),
    ("vitamin_a", "female", "18-59", None, 390, 840, None, ICMR),
    ("vitamin_d", "male", "18-59", None, None, 15, None, ICMR),   # 600 IU
    ("vitamin_d", "female", "18-59", None, None, 15, None, ICMR),
    ("vitamin_d", "male", "60+", None, None, 20, None, ICMR),     # 800 IU
    ("vitamin_d", "female", "60+", None, None, 20, None, ICMR),
    ("folate", "male", "18-59", None, 250, 300, None, ICMR),
    ("folate", "female", "18-59", None, 180, 220, None, ICMR),
    ("vitamin_b12", "male", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_b12", "female", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_c", "male", "18-59", None, 65, 80, None, ICMR),
    ("vitamin_c", "female", "18-59", None, 55, 65, None, ICMR),

    # Energy-scaled B vitamins, by activity level.
    ("thiamine", "male", "18-59", "sedentary", None, 1.4, None, ICMR),
    ("thiamine", "male", "18-59", "moderate", None, 1.8, None, ICMR),
    ("thiamine", "male", "18-59", "heavy", None, 2.3, None, ICMR),
    ("thiamine", "female", "18-59", "sedentary", None, 1.4, None, ICMR),
    ("thiamine", "female", "18-59", "moderate", None, 1.7, None, ICMR),
    ("thiamine", "female", "18-59", "heavy", None, 2.2, None, ICMR),
    ("riboflavin", "male", "18-59", "sedentary", None, 2.0, None, ICMR),
    ("riboflavin", "male", "18-59", "moderate", None, 2.5, None, ICMR),
    ("riboflavin", "male", "18-59", "heavy", None, 3.2, None, ICMR),
    ("riboflavin", "female", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("riboflavin", "female", "18-59", "moderate", None, 2.4, None, ICMR),
    ("riboflavin", "female", "18-59", "heavy", None, 3.1, None, ICMR),
    ("niacin", "male", "18-59", "sedentary", None, 14, None, ICMR),
    ("niacin", "male", "18-59", "moderate", None, 18, None, ICMR),
    ("niacin", "male", "18-59", "heavy", None, 23, None, ICMR),
    ("niacin", "female", "18-59", "sedentary", None, 11, None, ICMR),
    ("niacin", "female", "18-59", "moderate", None, 14, None, ICMR),
    ("niacin", "female", "18-59", "heavy", None, 18, None, ICMR),
    ("vitamin_b6", "male", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("vitamin_b6", "male", "18-59", "moderate", None, 2.4, None, ICMR),
    ("vitamin_b6", "male", "18-59", "heavy", None, 3.1, None, ICMR),
    ("vitamin_b6", "female", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("vitamin_b6", "female", "18-59", "moderate", None, 1.9, None, ICMR),
    ("vitamin_b6", "female", "18-59", "heavy", None, 2.4, None, ICMR),
]

# (nutrient, value, supplemental_only, source)
UPPER_LIMIT_ROWS: list[tuple] = [
    ("iron", 45, False, ICMR_TUL),
    ("zinc", 40, False, ICMR_TUL),
    ("calcium", 2500, False, ICMR_TUL),
    ("iodine", 900, False, ICMR_TUL),
    ("vitamin_a", 3000, False, ICMR_TUL),
    ("vitamin_d", 100, False, ICMR_TUL),
    ("vitamin_e", 1000, False, ICMR_TUL),
    ("niacin", 35, False, ICMR_TUL),
    ("vitamin_b6", 100, False, ICMR_TUL),
    ("folate", 1000, False, ICMR_TUL),
    ("vitamin_c", 2000, False, ICMR_TUL),
    # Supplemental only — excludes food and water. Warning on dietary
    # magnesium would be a bug.
    ("magnesium", 350, True, IOM),
    ("selenium", 400, False, IOM),
    ("copper", 10, False, IOM),
    ("manganese", 11, False, IOM),
    ("phosphorus", 4000, False, IOM),
    # Deliberately absent, because ICMR set none: thiamine, riboflavin,
    # biotin, vitamin_b12, potassium.
]


def seed_reference(db: Session) -> tuple[int, int]:
    """Insert or update the RDA and upper-limit reference rows. Safe to re-run."""
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}

    for code, sex, age_band, activity, ear, rda, ai, source in RDA_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(RdaReference).where(
                RdaReference.nutrient_id == nutrient.id,
                RdaReference.sex == sex,
                RdaReference.age_band == age_band,
                RdaReference.activity_level == activity,
            )
        )
        if row is None:
            row = RdaReference(
                nutrient_id=nutrient.id, sex=sex, age_band=age_band, activity_level=activity
            )
            db.add(row)
        row.ear, row.rda, row.ai, row.source = ear, rda, ai, source

    for code, value, supplemental_only, source in UPPER_LIMIT_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(UpperLimit).where(
                UpperLimit.nutrient_id == nutrient.id, UpperLimit.age_band == "adult"
            )
        )
        if row is None:
            row = UpperLimit(nutrient_id=nutrient.id, age_band="adult")
            db.add(row)
        row.value, row.supplemental_only, row.source = value, supplemental_only, source

    db.flush()
    return len(RDA_ROWS), len(UPPER_LIMIT_ROWS)
