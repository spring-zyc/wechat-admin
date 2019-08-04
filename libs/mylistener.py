# coding=utf-8
import os
import re
from datetime import datetime

from wxpy import Friend, Group, MP as _MP, sync_message_in_groups
from wxpy.api import consts

from config import PLUGIN_PATHS, PLUGINS, GROUP_MEMBERS_LIMIT
from libs.consts import *  # noqa
import libs.mybot as b
from models.setting import GroupSettings
from models.redis import db as r
from models.core import User
from models.messaging import Message, Notification, db
from loguru import logger

class SettingWrapper:

    def __init__(self, bot):
        self.bot = bot
        self.uid = bot.self.puid

    def __getattr__(self, item):
        settings = GroupSettings.get(self.uid)
        return getattr(settings, item, None)

    @property
    def pattern_map(self):
        return {p: tmpl for p, tmpl in settings.group_patterns}


new_member_regex = re.compile(r'^"(.+)"通过|邀请"(.+)"加入')
kick_member_regex = re.compile(r'^(移出|移除|踢出|T)(\s*)@(.+?)(?:\u2005?\s*$)')
all_types = [k.capitalize()
             for k in dir(consts) if k.isupper() and k != 'SYSTEM']
here = os.path.abspath(os.path.dirname(__file__))
UPLOAD_PATH = os.path.join(here, '../static/img/uploads')
if not os.path.exists(UPLOAD_PATH):
    os.mkdir(UPLOAD_PATH)
KICK_KEY = 'kick:members'
KICK_SENDER_KEY = 'kick:senders'


def get_creators(settings, bot):
    creator_ids = settings.creators
    try:
        creators = list(map(lambda x: bot.friends().search(puid=x)[0],
                            creator_ids))
    except IndexError:
        from views.api import json_api
        with json_api.app_context():
            users = [u.to_dict() for u in db.session.query(User).filter(
                User.id.in_(creator_ids)).all()]
            creators = list(map(lambda u: bot.friends().search(
                u['nick_name'], Sex=u['sex'], Signature=u['signature'])[0],
                users))
    return creators


def get_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def invite(user, bot, pattern):
    groups = sorted(bot.groups(update=True).search(pattern),
                    key=lambda x: x.name)
    if len(groups) > 0:
        for group in groups:
            if len(group.members) == GROUP_MEMBERS_LIMIT:
                continue
            if user in group:
                content = "您已经加入了{} [微笑]".format(group.nick_name)
                user.send(content)
            else:
                group.add_members(user, use_invitation=True)
            return
        else:
            next_topic = settings.pattern_map[pattern].format(
                re.search(r'\d+', s).group() + 1)
            new_group = bot.create_group(get_creators(), topic=next_topic)
            new_group.add_members(user, use_invitation=True)
            new_group.send_msg('创建 [{}] 成功'.format(next_topic))
    else:
        next_topic = settings.pattern_map[pattern].format(1)
        new_group = bot.create_group(get_creators(), topic=next_topic)
        new_group.add_members(user, use_invitation=True)
        new_group.send_msg('创建 [{}] 成功'.format(next_topic))


def init_listener(bot):
    settings = SettingWrapper(bot)
    groups = [g for g in bot.groups() if g.is_owner]

    @bot.register(msg_types=FRIENDS)
    def new_friends(msg):
        user = msg.card.accept()
        pattern = next(
            (p for p in settings.pattern_map if p in msg.text.lower()), None)
        if pattern is not None:
            invite(user, pattern)
        else:
            user.send(settings.invite_text)

    @bot.register(Friend, msg_types=TEXT)
    def exist_friends(msg):
        if msg.sender.name.find('黑名单') != -1:
            return '拉黑了，放弃吧 ╮（﹀＿﹀）╭'
        pattern = next(
            (p for p in settings.pattern_map if p in msg.text.lower()), None)
        if pattern is not None:
            invite(msg.sender, bot, pattern)

    @bot.register(groups, NOTE)
    def welcome(msg):
        match = new_member_regex.search(msg.text)
        if match:
            text = list(filter(lambda x: x, match.groups()))
            if text:
                return settings.welcome_text.format(text[0])

    @bot.register(groups, TEXT, except_self=False)
    def kick(msg):
        match = kick_member_regex.search(msg.text)
        if not match:
            return

        name = match.group(3)
        to_kick = msg.chat.members.search(name=name, nick_name=name)
        if not to_kick:
            return '没找到对应用户，请联系群主😯'
        to_kick = to_kick[0]
        receiver_id = to_kick.puid
        if receiver_id == uid:
            return '群主不能被移出哦😯'
        rs = r.sadd(KICK_SENDER_KEY, msg.member.puid)
        if not rs:
            return
        current = r.hincrby(KICK_KEY, receiver_id, 1)

        if current < settings.kick_quorum_n:
            period = settings.kick_period * 60
            if current == 1:
                for key in (KICK_SENDER_KEY, KICK_KEY):
                    r.expire(key, period)
            return settings.kick_text.format(
                current=current, member=to_kick.nick_name,
                total=settings.kick_quorum_n, period=period)
        to_kick.set_remark_name('[黑名单]-' + get_time())
        msg.chat.remove_members([to_kick])
        return '成功移出 @{}'.format(to_kick.nick_name)

    @bot.register(msg_types=all_types, except_self=True)
    def send_msg(m):
        # wxpy还不支持未命名的群聊消息
        # 先忽略腾讯新闻之类发的信息
        logger.info("收到消息")
        if m.receiver.name is None or m.sender is None:
            return
        msg_type = TYPE_TO_ID_MAP.get(m.type, 0)
        if isinstance(m.sender, Group):
            sender_id = m.member.puid
            group_id = m.chat.puid
        elif isinstance(m.sender, _MP):
            sender_id = m.sender.puid
            group_id = 0
            msg_type = TYPE_TO_ID_MAP.get('MP')
        else:
            sender_id = m.sender.puid
            group_id = 0
        receiver_id = m.receiver.puid
        from views.api import json_api as app
        with app.app_context():
            msg = Message.create(sender_id=sender_id, receiver_id=receiver_id,
                                 content=m.text, url=m.url, type=msg_type,
                                 receive_time=m.receive_time, group_id=group_id)
            if m.type in (PICTURE, RECORDING, ATTACHMENT, VIDEO):
                _, ext = os.path.splitext(m.file_name)
                m.get_file(os.path.join(UPLOAD_PATH, '{}{}'.format(msg.id, ext)))
                msg.file_ext = ext
                db.session.commit()
            Notification.add(receiver_id, msg.id)

            if isinstance(m.sender, _MP):
                for mp_id, ids in settings.mp_forward:
                    if m.sender.puid == mp_id:
                        groups = map(lambda x: bot.groups().search(puid=x)[0], ids)
                        sync_message_in_groups(m, groups)
                        return



