from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient

# (code, display_name, unit, category, compensable, days, excess_sensitive)
# Compensability follows the spec's research: protein has no storage pool,
# vitamin K's liver stores last days not weeks, fibre is capped for GI reasons,
# and a sodium shortfall is never something to make up.
NUTRIENTS: list[dict] = [
    {"code": "energy", "display_name": "Energy", "unit": "kcal", "category": "macro",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "protein", "display_name": "Protein", "unit": "g", "category": "macro",
         "is_compensable": False, "compensation_days": 0, "is_excess_sensitive": False},
    {"code": "fat", "display_name": "Total fat", "unit": "g", "category": "macro",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "saturated_fat", "display_name": "Saturated fat", "unit": "g", "category": "macro",
         "is_compensable": False, "compensation_days": 0, "is_excess_sensitive": True},
    {"code": "carbohydrate", "display_name": "Carbohydrate", "unit": "g", "category": "macro",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "free_sugar", "display_name": "Free sugar", "unit": "g", "category": "macro",
         "is_compensable": False, "compensation_days": 0, "is_excess_sensitive": True},
    {"code": "fibre", "display_name": "Dietary fibre", "unit": "g", "category": "macro",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "cholesterol", "display_name": "Cholesterol", "unit": "mg", "category": "macro",
         "is_compensable": False, "compensation_days": 0, "is_excess_sensitive": True},

    {"code": "calcium", "display_name": "Calcium", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "phosphorus", "display_name": "Phosphorus", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "magnesium", "display_name": "Magnesium", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "iron", "display_name": "Iron", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "zinc", "display_name": "Zinc", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "iodine", "display_name": "Iodine", "unit": "ug", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "selenium", "display_name": "Selenium", "unit": "ug", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "copper", "display_name": "Copper", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "manganese", "display_name": "Manganese", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "potassium", "display_name": "Potassium", "unit": "mg", "category": "mineral",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "sodium", "display_name": "Sodium", "unit": "mg", "category": "mineral",
         "is_compensable": False, "compensation_days": 0, "is_excess_sensitive": True},

    {"code": "vitamin_a", "display_name": "Vitamin A", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "vitamin_d", "display_name": "Vitamin D", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "vitamin_e", "display_name": "Vitamin E", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "vitamin_k", "display_name": "Vitamin K", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 1, "is_excess_sensitive": False},
    {"code": "thiamine", "display_name": "Thiamine (B1)", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "riboflavin", "display_name": "Riboflavin (B2)", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "niacin", "display_name": "Niacin (B3)", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "pantothenic_acid", "display_name": "Pantothenic acid (B5)", "unit": "mg",
         "category": "vitamin", "is_compensable": True, "compensation_days": 2,
         "is_excess_sensitive": False},
    {"code": "vitamin_b6", "display_name": "Vitamin B6", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "biotin", "display_name": "Biotin (B7)", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "folate", "display_name": "Folate (B9)", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
    {"code": "vitamin_b12", "display_name": "Vitamin B12", "unit": "ug", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": False},
    {"code": "vitamin_c", "display_name": "Vitamin C", "unit": "mg", "category": "vitamin",
         "is_compensable": True, "compensation_days": 2, "is_excess_sensitive": True},
]


def seed_nutrients(db: Session) -> int:
    """Insert or update the canonical nutrient list. Safe to re-run."""
    existing = {n.code: n for n in db.scalars(select(Nutrient))}

    for spec in NUTRIENTS:
        nutrient = existing.get(spec["code"])
        if nutrient is None:
            db.add(Nutrient(**spec))
        else:
            for key, value in spec.items():
                setattr(nutrient, key, value)

    db.flush()
    return len(NUTRIENTS)
