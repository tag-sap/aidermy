from .database import save_ingredients as db_save, get_ingredients as db_get

def save_ingredients(product_name: str, ingredients: str):
    db_save(product_name, ingredients)

def get_ingredients(product_name: str) -> str | None:
    return db_get(product_name)