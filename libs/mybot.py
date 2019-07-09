from wxpy import Bot
from wxpy.api.messages import MessageConfig

from loguru import logger
import uuid
import os



class MyBot:

    def __init__(self):
        self.bots = {}
        self.default_bot = None

    def get_bot(self,uuid):
        bot = self.bots[uuid]
        if bot:
            return bot
        else:
            logger.info("没有指定的bot")
            return None

    def create_bot(self):
        bid = uuid.uuid1()
        here = os.path.abspath(os.path.dirname(__file__))
        bot = Bot('bot_{}.pkl'.format(bid), qr_path=os.path.join(
            here, '../static/img/qr_code_{}.png'.format(bid)), console_qr=None)
        bot.enable_puid()
        bot.messages.max_history = 0
        self.bots[bid] = bot
        if self.default_bot is None:
            self.default_bot = bot
        from .mylistener import init_listener
        init_listener(bot)
        return bid, bot

    def do_register(self, func, chats=None, msg_types=None,
                    except_self=True, run_async=True, enabled=True):
        for bid, bot in self.bots:
            bot.registered.append(MessageConfig(bot=bot, func=func, chats=chats, msg_types=msg_types,
                                                except_self=except_self, run_async=run_async, enabled=enabled))

    def get_default_bot(self):
        return self.default_bot


myBots = MyBot()
