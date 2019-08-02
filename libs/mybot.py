from wxpy import Bot
from wxpy.api.messages import MessageConfig
from libs.wx import get_bot

from loguru import logger
import uuid
import os


class MyBot:

    def __init__(self):
        self.bots = {}
        self.uuidMap = {}
        self.botIdMap = {}
        self.default_bot = None

    def get_bot(self, bot_id):
        bot = self.bots[bot_id]
        if bot:
            return bot
        else:
            logger.info("没有指定的bot")
            return None

    def get_bot_by_uuid(self, uuid):
        puid = self.uuidMap[uuid]
        if puid:
            self.get_bot(puid)

    def get_bot_id(self, puid):
        return self.botIdMap[bot_id]

    def create_bot(self, bot_id=None):
        bid = bot_id
        if bot_id is None:
            bid = str(uuid.uuid1())
        bot = get_bot(bot.self.puid)
        self.add_bot(bot.self.puid, bot)
        # 通过puid找到bot_id,然后在调用wx.get_bot找到已经登录的bot
        self.botIdMap[bot.self.puid] = bid
        # 通过uuid找到puid，再找到bot，再对bot操作
        self.uuidMap[bot.core.uuid] = bot.self.puid
        return bid, bot

    def add_bot(self, puid, bot):
        self.bots[puid] = bot
        from .mylistener import init_listener
        init_listener(bot)

    def remove_bot(self, bot_puid):
        del self.bots[bot_puid]

    def remove_bot_by_uuid(self, uuid):
        puid = self.uuidMap[uuid]
        if puid:
            self.remove_bot(puid)

    def do_register(self, func, chats=None, msg_types=None,
                    except_self=True, run_async=True, enabled=True):
        for bid, bot in self.bots:
            bot.registered.append(MessageConfig(bot=bot, func=func, chats=chats, msg_types=msg_types,
                                                except_self=except_self, run_async=run_async, enabled=enabled))

    def get_default_bot(self):
        return self.default_bot


# myBots = MyBot()
