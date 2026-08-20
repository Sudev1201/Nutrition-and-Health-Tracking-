"""Model registry.

Importing this package registers every model on `Base.metadata`. Alembic and
the test fixtures both import from here rather than from individual modules,
so metadata is always complete no matter which entry point loaded first —
otherwise `create_all`/`drop_all` and autogenerate silently miss tables.
"""

from app.models.base import Base
from app.models.diary import MealLog
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
from app.models.profile import (
    AvoidedFood,
    FavouriteIngredient,
    HealthCondition,
    MealSlotTime,
    Medication,
    ObservanceRule,
    Profile,
    UsualIntakeItem,
)
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User

__all__ = [
    "AvoidedFood",
    "Base",
    "Dish",
    "DishIngredient",
    "DishNutrient",
    "FavouriteIngredient",
    "HealthCondition",
    "Household",
    "HouseholdInvite",
    "HouseholdMember",
    "Ingredient",
    "IngredientNutrient",
    "MealLog",
    "MealSlotTime",
    "Medication",
    "Nutrient",
    "ObservanceRule",
    "PortionMeasure",
    "Profile",
    "RdaReference",
    "UpperLimit",
    "User",
    "UsualIntakeItem",
]
