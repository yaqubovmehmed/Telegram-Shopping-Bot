"""Channel membership updates (no DB side effects for random channel users)."""

from aiogram import Router
from aiogram.types import ChatMemberUpdated

from bot.config import settings
from bot.middlewares.subscription import MEMBER_STATUSES, invalidate_user

router = Router(name="channel")


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated) -> None:
    if not settings.required_channel_id:
        return
    if event.chat.id != settings.required_channel_id:
        return
    if event.new_chat_member.status in MEMBER_STATUSES:
        invalidate_user(event.new_chat_member.user.id)
