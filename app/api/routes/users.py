from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User, VkAccount
from app.schemas import MeResponse

router = APIRouter(prefix="/me", tags=["users"])


@router.get("", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await db.scalar(select(VkAccount).where(VkAccount.user_id == user.id))
    return MeResponse(
        id=user.id,
        vk_user_id=account.vk_user_id,
        email=account.email,
        phone=account.phone,
        first_name=account.first_name,
        last_name=account.last_name,
        avatar_url=account.avatar_url,
    )
