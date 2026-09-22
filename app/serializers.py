import asyncio
import re

from beanie import PydanticObjectId

from . import models, schemas


async def generate_unique_username(full_name: str) -> str:
    """Derives a URL-safe username from the person's name and guarantees
    uniqueness by checking Mongo and appending a numeric suffix on
    collision (sam -> sam2 -> sam3 -> ...). Usernames are never chosen
    by the user — they're assigned automatically at registration."""
    base = re.sub(r"[^a-z0-9]", "", full_name.lower())
    if not base:
        base = "cook"
    base = base[:20]

    candidate = base
    suffix = 1
    while await models.User.find_one(models.User.username == candidate):
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def to_object_ids(id_strings: list[str]) -> list[PydanticObjectId]:
    result = []
    for s in id_strings:
        try:
            result.append(PydanticObjectId(s))
        except Exception:
            continue
    return result


async def fetch_authors(author_ids: list[str]) -> dict[str, models.User]:
    unique_ids = list(dict.fromkeys(author_ids))
    if not unique_ids:
        return {}
    users = await models.User.find({"_id": {"$in": to_object_ids(unique_ids)}}).to_list()
    return {str(u.id): u for u in users}


async def fetch_recipes(recipe_ids: list[str]) -> dict[str, models.Recipe]:
    unique_ids = list(dict.fromkeys(recipe_ids))
    if not unique_ids:
        return {}
    recipes = await models.Recipe.find({"_id": {"$in": to_object_ids(unique_ids)}}).to_list()
    return {str(r.id): r for r in recipes}


def author_out(user: models.User | None, fallback_id: str) -> schemas.AuthorOut:
    if user is None:
        return schemas.AuthorOut(id=fallback_id, full_name="Unknown cook", avatar_url=None)
    return schemas.AuthorOut(id=str(user.id), full_name=user.full_name, avatar_url=user.avatar_url)


def recipe_card_out(recipe: models.Recipe, author_map: dict[str, models.User], favorited_ids: set[str]) -> schemas.RecipeCardOut:
    return schemas.RecipeCardOut(
        id=str(recipe.id),
        title=recipe.title,
        image_url=recipe.image_url,
        cook_minutes=recipe.cook_minutes,
        difficulty=recipe.difficulty,
        category=recipe.category,
        rating_avg=recipe.rating_avg,
        rating_count=recipe.rating_count,
        author=author_out(author_map.get(recipe.author_id), recipe.author_id),
        is_favorite=str(recipe.id) in favorited_ids,
    )


def recipe_detail_out(recipe: models.Recipe, author_map: dict[str, models.User], is_favorite: bool) -> schemas.RecipeDetailOut:
    return schemas.RecipeDetailOut(
        id=str(recipe.id),
        title=recipe.title,
        image_url=recipe.image_url,
        cook_minutes=recipe.cook_minutes,
        difficulty=recipe.difficulty,
        category=recipe.category,
        rating_avg=recipe.rating_avg,
        rating_count=recipe.rating_count,
        author=author_out(author_map.get(recipe.author_id), recipe.author_id),
        is_favorite=is_favorite,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
        created_at=recipe.created_at,
    )


def review_with_recipe_out(review: models.Review, recipe: models.Recipe | None) -> schemas.ReviewWithRecipeOut:
    recipe_ref = (
        schemas.RecipeRef(id=str(recipe.id), title=recipe.title, image_url=recipe.image_url)
        if recipe is not None
        else schemas.RecipeRef(id=review.recipe_id, title="Deleted recipe", image_url=None)
    )
    return schemas.ReviewWithRecipeOut(
        id=str(review.id),
        rating=review.rating,
        comment=review.comment,
        recipe=recipe_ref,
        created_at=review.created_at,
    )


def user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        auth_provider=user.auth_provider,
        is_email_verified=user.is_email_verified,
        bio=user.bio,
        location=user.location,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


async def user_card_out(user: models.User, viewer_id: str | None) -> schemas.UserCardOut:
    """Builds the row shown in search results and follower/following
    lists — recipe count, follower count, and whether the *viewer*
    already follows this person. The three DB calls run concurrently
    rather than sequentially."""
    recipe_count_coro = models.Recipe.find(models.Recipe.author_id == str(user.id)).count()
    follower_count_coro = models.Follow.find(models.Follow.followed_id == str(user.id)).count()

    if viewer_id and viewer_id != str(user.id):
        following_coro = models.Follow.find_one(
            models.Follow.follower_id == viewer_id, models.Follow.followed_id == str(user.id)
        )
        recipe_count, follower_count, following_doc = await asyncio.gather(
            recipe_count_coro, follower_count_coro, following_coro
        )
        is_following = following_doc is not None
    else:
        recipe_count, follower_count = await asyncio.gather(recipe_count_coro, follower_count_coro)
        is_following = False

    return schemas.UserCardOut(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        recipe_count=recipe_count,
        follower_count=follower_count,
        is_following=is_following,
    )


async def user_cards_out(users: list[models.User], viewer_id: str | None) -> list[schemas.UserCardOut]:
    return list(await asyncio.gather(*(user_card_out(u, viewer_id) for u in users)))
