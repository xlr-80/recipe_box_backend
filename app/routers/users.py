from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import models, schemas
from ..dependencies import get_current_user, get_current_user_optional, PageParams, pagination_params
from ..serializers import user_out, user_cards_out, fetch_authors, fetch_recipes, recipe_card_out, review_with_recipe_out
from .. import notifications

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user_or_404(user_id: str) -> models.User:
    try:
        oid = PydanticObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = await models.User.get(oid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# NOTE: declared before GET /{user_id} — otherwise FastAPI would match
# "/users/search" as /{user_id} with user_id="search".
@router.get("/search", response_model=schemas.Page[schemas.UserCardOut])
async def search_users(
    q: str = Query(min_length=1, description="Matches full name or username"),
    pg: PageParams = Depends(pagination_params),
    viewer: models.User | None = Depends(get_current_user_optional),
):
    regex = {"$regex": q, "$options": "i"}
    filter_query = {"$or": [{"full_name": regex}, {"username": regex}]}

    query = models.User.find(filter_query)
    total = await query.count()
    users = await query.skip(pg.offset).limit(pg.page_size).to_list()

    viewer_id = str(viewer.id) if viewer else None
    items = await user_cards_out(users, viewer_id)
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.get("/{user_id}", response_model=schemas.UserProfile)
async def get_profile(user_id: str, viewer: models.User | None = Depends(get_current_user_optional)):
    user = await _get_user_or_404(user_id)

    recipe_count = await models.Recipe.find(models.Recipe.author_id == user_id).count()
    follower_count = await models.Follow.find(models.Follow.followed_id == user_id).count()
    following_count = await models.Follow.find(models.Follow.follower_id == user_id).count()

    is_following = False
    if viewer is not None and str(viewer.id) != user_id:
        is_following = (
            await models.Follow.find_one(
                models.Follow.follower_id == str(viewer.id), models.Follow.followed_id == user_id
            )
            is not None
        )

    base = user_out(user)
    return schemas.UserProfile(
        **base.model_dump(),
        recipe_count=recipe_count,
        follower_count=follower_count,
        following_count=following_count,
        is_following=is_following,
    )


# ---------- THE MISSING PIECE: public profile tabs ----------
# These power the "Recipes" and "Reviews" tabs when viewing someone
# else's profile — previously there was no way to fetch either.

@router.get("/{user_id}/recipes", response_model=schemas.Page[schemas.RecipeCardOut])
async def list_user_recipes(
    user_id: str,
    pg: PageParams = Depends(pagination_params),
    viewer: models.User | None = Depends(get_current_user_optional),
):
    await _get_user_or_404(user_id)  # 404 if the profile itself doesn't exist

    query = models.Recipe.find(models.Recipe.author_id == user_id)
    total = await query.count()
    recipes = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    author_map = await fetch_authors([user_id])
    favorited = set()
    if viewer is not None:
        from ..routers.recipes import _favorited_ids  # local import avoids a circular import at module load time
        favorited = await _favorited_ids(viewer, [str(r.id) for r in recipes])

    items = [recipe_card_out(r, author_map, favorited) for r in recipes]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.get("/{user_id}/reviews", response_model=schemas.Page[schemas.ReviewWithRecipeOut])
async def list_user_reviews(user_id: str, pg: PageParams = Depends(pagination_params)):
    """All reviews *written by* this person, across every recipe — the
    Reviews tab on a profile, distinct from GET /recipes/{id}/reviews
    (reviews *on* one recipe, written by anyone)."""
    await _get_user_or_404(user_id)

    query = models.Review.find(models.Review.author_id == user_id)
    total = await query.count()
    reviews = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    recipe_map = await fetch_recipes([r.recipe_id for r in reviews])
    items = [review_with_recipe_out(r, recipe_map.get(r.recipe_id)) for r in reviews]
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.put("/me", response_model=schemas.UserOut)
async def update_me(payload: schemas.UserUpdate, current_user: models.User = Depends(get_current_user)):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await current_user.save()
    return user_out(current_user)


@router.post("/{user_id}/follow")
async def follow_user(user_id: str, current_user: models.User = Depends(get_current_user)):
    if user_id == str(current_user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself")

    await _get_user_or_404(user_id)

    existing = await models.Follow.find_one(
        models.Follow.follower_id == str(current_user.id), models.Follow.followed_id == user_id
    )
    if existing:
        await existing.delete()
        return {"is_following": False}

    await models.Follow(follower_id=str(current_user.id), followed_id=user_id).insert()

    await notifications.send_to_user(
        user_id,
        title="New follower",
        body=f"{current_user.full_name} started following you",
        data={"type": "new_follower", "follower_id": str(current_user.id)},
    )

    return {"is_following": True}


@router.get("/{user_id}/followers", response_model=schemas.Page[schemas.UserCardOut])
async def list_followers(
    user_id: str,
    pg: PageParams = Depends(pagination_params),
    viewer: models.User | None = Depends(get_current_user_optional),
):
    query = models.Follow.find(models.Follow.followed_id == user_id)
    total = await query.count()
    follows = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    follower_ids = [f.follower_id for f in follows]
    users = await models.User.find({"_id": {"$in": [PydanticObjectId(fid) for fid in follower_ids]}}).to_list()
    users_by_id = {str(u.id): u for u in users}
    ordered = [users_by_id[fid] for fid in follower_ids if fid in users_by_id]

    viewer_id = str(viewer.id) if viewer else None
    items = await user_cards_out(ordered, viewer_id)
    return schemas.Page.build(items, total, pg.page, pg.page_size)


@router.get("/{user_id}/following", response_model=schemas.Page[schemas.UserCardOut])
async def list_following(
    user_id: str,
    pg: PageParams = Depends(pagination_params),
    viewer: models.User | None = Depends(get_current_user_optional),
):
    query = models.Follow.find(models.Follow.follower_id == user_id)
    total = await query.count()
    follows = await query.sort("-created_at").skip(pg.offset).limit(pg.page_size).to_list()

    followed_ids = [f.followed_id for f in follows]
    users = await models.User.find({"_id": {"$in": [PydanticObjectId(fid) for fid in followed_ids]}}).to_list()
    users_by_id = {str(u.id): u for u in users}
    ordered = [users_by_id[fid] for fid in followed_ids if fid in users_by_id]

    viewer_id = str(viewer.id) if viewer else None
    items = await user_cards_out(ordered, viewer_id)
    return schemas.Page.build(items, total, pg.page, pg.page_size)
