# utils/ui_helpers.py
import logging
from typing import Optional, Union
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from pyrogram.errors import MessageNotModified, RPCError

logger = logging.getLogger(__name__)

async def safe_answer_callback(callback_query: Optional[CallbackQuery], *args, **kwargs):
    """
    Safely answer callback queries. Ignore QUERY_ID_INVALID and benign errors.
    """
    if not callback_query:
        return
    try:
        await callback_query.answer(*args, **kwargs)
    except Exception as e:
        serr = str(e).upper()
        if "QUERY_ID_INVALID" in serr or "MESSAGE_NOT_MODIFIED" in serr:
            logger.debug("Ignored QUERY_ID_INVALID/MESSAGE_NOT_MODIFIED when answering callback query.")
        elif "TIMEOUT" in serr or "FLOOD" in serr:
            logger.debug(f"Ignored callback answer error: {serr}")
        else:
            logger.warning(f"Failed to answer callback query: {e}")

async def safe_edit_or_reply(
    message_or_cb: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    client: Optional[Client] = None
) -> Optional[Message]:
    """
    Safely update a Telegram screen.
    - If CallbackQuery: edits the existing bot message (with media-deletion fallback if needed).
    - If Message: replies to the user's command message.
    - Gracefully passes on MessageNotModified.
    """
    if not message_or_cb:
        return None

    if isinstance(message_or_cb, CallbackQuery):
        msg = message_or_cb.message
        user_id = message_or_cb.from_user.id if message_or_cb.from_user else (msg.chat.id if msg and msg.chat else 0)

        # 1. Edit existing message for CallbackQuery
        if msg and hasattr(msg, "edit_text"):
            try:
                return await msg.edit_text(text, reply_markup=reply_markup)
            except MessageNotModified:
                return msg
            except Exception as e:
                serr = str(e).upper()
                if "MESSAGE_NOT_MODIFIED" in serr:
                    return msg
                logger.debug(f"safe_edit_or_reply: edit_text failed ({e}), attempting fallback.")
                # If editing failed because message is media/document or deleted, try deleting old media message
                try:
                    await msg.delete()
                except Exception:
                    pass

        # 2. Fallback to reply
        if msg and hasattr(msg, "reply_text"):
            try:
                return await msg.reply_text(text, reply_markup=reply_markup)
            except Exception as e:
                logger.debug(f"safe_edit_or_reply: reply_text failed: {e}")

        # 3. Fallback to client.send_message
        if client and user_id:
            try:
                return await client.send_message(user_id, text, reply_markup=reply_markup)
            except Exception as e:
                logger.warning(f"safe_edit_or_reply: send_message failed: {e}")

        return None

    elif isinstance(message_or_cb, Message):
        msg = message_or_cb
        user_id = message_or_cb.from_user.id if message_or_cb.from_user else (message_or_cb.chat.id if message_or_cb.chat else 0)

        # 1. Reply to user's command message
        if msg and hasattr(msg, "reply_text"):
            try:
                return await msg.reply_text(text, reply_markup=reply_markup)
            except Exception as e:
                logger.debug(f"safe_edit_or_reply: reply_text failed: {e}")

        # 2. Fallback to edit_text if message belongs to bot
        if msg and hasattr(msg, "edit_text"):
            try:
                return await msg.edit_text(text, reply_markup=reply_markup)
            except MessageNotModified:
                return msg
            except Exception:
                pass

        # 3. Fallback to client.send_message
        if client and user_id:
            try:
                return await client.send_message(user_id, text, reply_markup=reply_markup)
            except Exception as e:
                logger.warning(f"safe_edit_or_reply: send_message failed: {e}")

        return None
