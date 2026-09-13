from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, status, Query

from .. import models, schemas
from ..dependencies import get_current_user, get_current_user_optional, PageParams, pagination_params
from ..serializers import fetch_authors, recipe_card_out, recipe_detail_out, author_out

router = APIRouter(prefix="/recipes", tags=["recipes"])


# ---------- helpers ----------

async def _get_recipe_or_404(recipe_id: str) -> models.Recipe:
    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    recipe = await models.Recipe.get(oid)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return recipe


async def _get_owned_recipe_or_404(recipe_id: str, user: models.User) -> models.Recipe:
    recipe = await _get_recipe_or_404(recipe_id)
    if recipe.author_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this recipe")
    return recipe


async def _favorited_ids(user: models.User | None, recipe_ids: list[str]) -> set[str]:
    if user is None or not recipe_ids:
        return set()
    favs = await models.Favorite.find(
        models.Favorite.user_id == str(user.id), In(models.Favorite.recipe_id, recipe_ids)
    ).to_list()
    return {f.recipe_id for f in favs}


# ---------- listing / search (paginated) ----------

@router.get("", response_model=schemas.Page[schemas.RecipeCardOut])
async def list_recipes(
    category: models.Category | None = Query(default=None),
    search: str | None = Query(default=None, description="Matches title, author name, or username"),
    sort: schemas.RecipeSort = Query(default=schemas.RecipeSort.newest),
    max_cook_minutes: int | None = Query(default=None, gt=0, description="e.g. 30 for an 'Under 30 min' filter"),
    pg: PageParams = Depends(pagination_params),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    filter_query: dict = {}
    if category is not None:
        filter_query["category"] = category.value
    if max_cook_minutes is not None:
        filter_query["cook_minutes"] = {"$lte": max_cook_minutes}
    if search:
        regex = {"$regex": search, "$options": "i"}
        matching_authors = await models.User.find({"$or": [{"full_name": regex}, {"username": regex}]}).to_list()
        author_ids = [str(u.id) for u in matching_authors]
        filter_query["$or"] = [
            {"title": regex},
            {"author_id": {"$in": author_ids}},
        ]

    query = models.Recipe.find(filter_query) if filter_query else models.Recipe.find_all()
    total = await query.count()

    sort_fields = ["-rating_avg", "-rating_count"] if sort == schemas.RecipeSort.popular else ["-created_at"]
    recipes = await query.sort(*sort_fields).skip(pg.offset).limit(pg.page_size).to_list()

    author_map = await fetch_authors([r.author_id for r in recipes])
    favorited = await _favorited_ids(current_user, [str(r.id) for r in recipes])
    items = [recipe_card_out(r, author_map, favorited) for r in recipes]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.get("/mine", response_model=schemas.Page[schemas.RecipeCardOut])
async def list_my_recipes(
    pg: PageParams = Depends(pagination_params),
    current_user: models.User = Depends(get_current_user),
):
    query = models.Recipe.find(models.Recipe.author_id == str(current_user.id))
    total = await query.count()
    recipes = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    favorited = await _favorited_ids(current_user, [str(r.id) for r in recipes])
    author_map = {str(current_user.id): current_user}
    items = [recipe_card_out(r, author_map, favorited) for r in recipes]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.get("/saved", response_model=schemas.Page[schemas.RecipeCardOut])
async def list_saved_recipes(
    pg: PageParams = Depends(pagination_params),
    current_user: models.User = Depends(get_current_user),
):
    fav_query = models.Favorite.find(models.Favorite.user_id == str(current_user.id))
    total = await fav_query.count()
    favs = await fav_query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    recipe_ids = [f.recipe_id for f in favs]
    recipes = await models.Recipe.find({"_id": {"$in": [PydanticObjectId(rid) for rid in recipe_ids]}}).to_list()
    recipes_by_id = {str(r.id): r for r in recipes}
    ordered = [recipes_by_id[rid] for rid in recipe_ids if rid in recipes_by_id]

    author_map = await fetch_authors([r.author_id for r in ordered])
    items = [recipe_card_out(r, author_map, set(recipe_ids)) for r in ordered]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


# ---------- single recipe ----------

@router.get("/{recipe_id}", response_model=schemas.RecipeDetailOut)
async def get_recipe(
    recipe_id: str,
    current_user: models.User | None = Depends(get_current_user_optional),
):
    recipe = await _get_recipe_or_404(recipe_id)
    author_map = await fetch_authors([recipe.author_id])
    favorited = await _favorited_ids(current_user, [recipe_id])
    return recipe_detail_out(recipe, author_map, recipe_id in favorited)


@router.post("", response_model=schemas.RecipeDetailOut, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload: schemas.RecipeCreate,
    current_user: models.User = Depends(get_current_user),
):
    recipe = models.Recipe(
        title=payload.title,
        image_url=payload.image_url,
        cook_minutes=payload.cook_minutes,
        difficulty=payload.difficulty,
        category=payload.category,
        author_id=str(current_user.id),
        ingredients=payload.ingredients,
        steps=payload.steps,
    )
    await recipe.insert()
    return recipe_detail_out(recipe, {str(current_user.id): current_user}, False)


@router.put("/{recipe_id}", response_model=schemas.RecipeDetailOut)
async def update_recipe(
    recipe_id: str,
    payload: schemas.RecipeUpdate,
    current_user: models.User = Depends(get_current_user),
):
    recipe = await _get_owned_recipe_or_404(recipe_id, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)
    await recipe.save()

    favorited = await _favorited_ids(current_user, [recipe_id])
    return recipe_detail_out(recipe, {str(current_user.id): current_user}, recipe_id in favorited)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: str,
    current_user: models.User = Depends(get_current_user),
):
    recipe = await _get_owned_recipe_or_404(recipe_id, current_user)
    await recipe.delete()


# ---------- favorites ----------

@router.post("/{recipe_id}/favorite")
async def toggle_favorite(
    recipe_id: str,
    current_user: models.User = Depends(get_current_user),
):
    await _get_recipe_or_404(recipe_id)  # 404 if the recipe doesn't exist

    existing = await models.Favorite.find_one(
        models.Favorite.user_id == str(current_user.id), models.Favorite.recipe_id == recipe_id
    )
    if existing:
        await existing.delete()
        return {"is_favorite": False}

    await models.Favorite(user_id=str(current_user.id), recipe_id=recipe_id).insert()
    return {"is_favorite": True}


# ---------- reviews (paginated) ----------

@router.get("/{recipe_id}/reviews", response_model=schemas.Page[schemas.ReviewOut])
async def list_reviews(recipe_id: str, pg: PageParams = Depends(pagination_params)):
    await _get_recipe_or_404(recipe_id)

    query = models.Review.find(models.Review.recipe_id == recipe_id)
    total = await query.count()
    reviews = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    author_map = await fetch_authors([r.author_id for r in reviews])
    items = [
        schemas.ReviewOut(
            id=str(r.id),
            rating=r.rating,
            comment=r.comment,
            author=author_out(author_map.get(r.author_id), r.author_id),
            created_at=r.created_at,
        )
        for r in reviews
    ]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.post("/{recipe_id}/reviews", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
async def create_review(
    recipe_id: str,
    payload: schemas.ReviewCreate,
    current_user: models.User = Depends(get_current_user),
):
    recipe = await _get_recipe_or_404(recipe_id)

    existing = await models.Review.find_one(
        models.Review.recipe_id == recipe_id, models.Review.author_id == str(current_user.id)
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already reviewed this recipe")

    review = models.Review(recipe_id=recipe_id, author_id=str(current_user.id), rating=payload.rating, comment=payload.comment)
    await review.insert()

    new_count = recipe.rating_count + 1
    recipe.rating_avg = round(((recipe.rating_avg * recipe.rating_count) + payload.rating) / new_count, 2)
    recipe.rating_count = new_count
    await recipe.save()

    return schemas.ReviewOut(
        id=str(review.id),
        rating=review.rating,
        comment=review.comment,
        author=schemas.AuthorOut(id=str(current_user.id), full_name=current_user.full_name, avatar_url=current_user.avatar_url),
        created_at=review.created_at,
    )
