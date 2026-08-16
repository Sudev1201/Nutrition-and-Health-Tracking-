"""Model registry.

Importing this package registers every model on `Base.metadata`. Alembic and
the test fixtures both import from here rather than from individual modules,
so metadata is always complete no matter which entry point loaded first —
otherwise `create_all`/`drop_all` and autogenerate silently miss tables.
"""

from app.models.base import Base
from app.models.food import (
    Dish,
    DishIngredient,
    DishNutrient,
    Ingredient,
    IngredientNutrient,
    PortionMeasure,
)
from app.models.household import Household, HouseholdInvite, HouseholdMember
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User

__all__ = [
    "Base",
    "Dish",
    "DishIngredient",
    "DishNutrient",
    "Household",
    "HouseholdInvite",
    "HouseholdMember",
    "Ingredient",
    "IngredientNutrient",
    "Nutrient",
    "PortionMeasure",
    "RdaReference",
    "UpperLimit",
    "User",
]
