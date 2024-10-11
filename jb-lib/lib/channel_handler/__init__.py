from typing import Dict
from .channel_handler import ChannelHandler, ChannelData, User
from .pinnacle_whatsapp_handler import PinnacleWhatsappHandler
from .telegram_handler import TelegramHandler
from .cunnekt_whatsapp_handler import CunnektWhatsappHandler
import os


WA_CHANNEL_NAME = os.getenv("WA_CHANNEL_NAME")
if WA_CHANNEL_NAME == "cunnekt_whatsapp":
    channel_map: Dict[str, type[ChannelHandler]] = {
        CunnektWhatsappHandler.get_channel_name(): CunnektWhatsappHandler,
        TelegramHandler.get_channel_name(): TelegramHandler,
    }

if WA_CHANNEL_NAME == "pinnacle_whatsapp":
    channel_map: Dict[str, type[ChannelHandler]] = {
        PinnacleWhatsappHandler.get_channel_name(): PinnacleWhatsappHandler,
        TelegramHandler.get_channel_name(): TelegramHandler,
    }
