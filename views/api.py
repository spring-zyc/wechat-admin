# coding=utf-8
import os
import glob
from flask import Flask, request, jsonify
from flask.views import MethodView
from flask_sqlalchemy import get_debug_queries
from sqlalchemy import and_
import jwt

import config
import views.errors as errors
from views.utils import ApiResult
from views.exceptions import ApiException
import views.settings as settings
from libs.globals import current_bot, _wx_ctx_stack
import libs.mybot as mybot
from libs.wx import get_logged_in_user
from libs.consts import TYPE_TO_ID_MAP
from ext import db, sse
from .auths import Auth
from models.core import LoginUser
from models.utils import serialize
import time
from loguru import logger

from models.core import User, Group, friendship, group_relationship
from models.messaging import Message, Notification

PER_PAGE = 20
here = os.path.abspath(os.path.dirname(__file__))

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = OSError


class ApiFlask(Flask):

    def make_response(self, rv):
        if isinstance(rv, dict):
            # if 'r' not in rv:
            #     rv['r'] = 0
            rv = ApiResult(rv)
        if isinstance(rv, ApiResult):
            return rv.to_response()
        return Flask.make_response(self, rv)


def check_token(fn):
    def do_check(*args):
        r = Auth.identify(request)
        if r[0] != 0:
            return {'code': 601, 'msg': r[1], 'data': None}
        return fn(*args)
    return do_check


def create_app():
    app = ApiFlask(__name__)
    app.config.from_object(config)
    db.init_app(app)

    app.register_blueprint(settings.bp)

    return app


json_api = create_app()


# For local test env
@json_api.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add(
        'Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add(
        'Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    for query in get_debug_queries():
        if query.duration >= config.DATABASE_QUERY_TIMEOUT:
            json_api.logger.warning((
                'SLOW QUERY: %s\nParameters: %s\nDuration: %fs'
                '\nContext: %s\n'
            ).format(query.statement, query.parameters, query.duration,
                     query.context))
    return response


@json_api.errorhandler(ApiException)
def api_error_handler(error):
    return error.to_result()


@json_api.errorhandler(403)
@json_api.errorhandler(404)
@json_api.errorhandler(500)
def error_handler(error):
    if hasattr(error, 'name'):
        msg = error.name
        code = error.code
    else:
        msg = error.message
        code = 500
    return ApiResult({'message': msg}, status=code)


# 登录微信，登录成功后跳转主页，不用sse触发
# todo 增加系统用户维度，不同用户可以管理不同的微信,目前系统用户只是为了信息安全
@json_api.route('/login/wx', methods=['get'])
@check_token
def login_wx():
    bot_id, bot = mybot.myBots.create_bot()
    wxuser = get_logged_in_user(bot)
    from wechat.tasks import retrieve_data, listener
    listener.delay(bot)
    retrieve_data.delay(bot)
    return {"code": 600, "msg": "微信登录完成", "data": wxuser}


# 所有登录的微信
@check_token
@json_api.route('/wxes', methods=['get'])
def get_wx():
    r = [get_logged_in_user(bot)
         for bot in mybot.myBots.bots.values()]
    return {'code': 600, 'msg': "bot列表获取成功", 'data': r}


# 系统登录，需要校验用户和密码，返回token
@json_api.route('/login', methods=['post'])
def login_sys():
    j = request.json
    r = Auth.authenticate(j["username"], j["password"])
    if r[0] == 0:
        return {"code": 600, "msg": "登录成功", "data": {"token": "Bearer {}".format(r[1])}}
    else:
        return {"code": 601, "msg": r[1], "data": None }


@json_api.route('/register', methods=['post'])
def register():
    try:
        j = request.json
        user = LoginUser(None, j["userName"], j["passWord"], j['email'])
        if user.add():
            token = Auth.encode_auth_token(user.id, int(time.time()))
            return {'code': 600, 'msg': "注册成功！", 'data': token}
        else:
            return {'code': 601, 'msg': "注册失败！", 'data': None}
    except Exception as e:
        logger.info(e)
        return {'code': 601, 'msg': "注册失败！", 'data': e}


@json_api.route('/userInfo', methods=['post'])
def user_info():
    try:
        user = Auth.identify(request)
        if user[0] == 0:
            return {'code': 600, 'msg': "获取用户信息成功！", 'data': serialize(user[1])}
        else:
            return {'code': 601, 'msg': "获取用户信息失败！", 'data': None}
    except Exception as e:
        logger.info(e)
        return {'code': 601, 'msg': "获取用户信息失败！", 'data': e}


@json_api.route('/logout/wx/<bot_id>', methods=['post'])
def logout(bot_id):
    try:
        # _wx_ctx_stack.pop()
        bot = mybot.myBots.get_bot(bot_id)
        if bot:
            bot.logout()
        mybot.myBots.remove_bot(bot_id)
        for f in glob.glob('{}/bot_{}.pkl'.format(here,bot_id)):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        return {'code': 600, 'msg': "登出成功！", 'data': None}
    except Exception as e:
        logger.info(e)
        return {'code': 601, 'msg': "登出失败！", 'data': e}


class UsersAPI(MethodView):

    def get(self):
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        type = request.args.get('type', 'contact')
        group_id = request.args.get('gid', '')
        if not group_id:
            type = 'contact'
        q = request.args.get('q', '')
        uid = current_bot.self.puid
        query = db.session.query
        if type == 'contact':
            user = query(User).get(uid)
            if user is None:
                return {
                    'total': 0,
                    'group': '',
                    'users': []
                }
            if q:
                users = query(User).outerjoin(
                    friendship, friendship.c.user_id == User.id).filter(and_(
                        User.nick_name.like('%{}%'.format(q)),
                        friendship.c.friend_id == user.id)
                )
            else:
                users = user.friends
            total = users.count()
            if not page:
                users = users.all()
            else:
                users = users.offset(
                    (page - 1) * page_size).limit(page_size).all()
            group = ''
        elif type == 'group':
            group = query(Group).get(group_id)
            if q:
                users = query(User).outerjoin(
                    group_relationship,
                    group_relationship.c.user_id == User.id).filter(and_(
                        User.nick_name.like('%{}%'.format(q)),
                        group_relationship.c.group_id == group.id)
                )
                total = users.count()
                if not page:
                    users = users.all()
                else:
                    users = users.offset((page - 1) * page_size).limit(
                        page_size).all()
            else:
                if not page:
                    users = group.members
                else:
                    users = group.members[
                        (page - 1) * page_size:page * page_size]
                total = group.count
            group = group.to_dict()
        return {
            'total': total,
            'group': group,
            'users': [u.to_dict() for u in users]
        }

    def put(self):
        verify_content = request.args.get('verifyContent', '')
        ids = set(request.args.getlist('wxid[]'))
        users = [u for u in sum([g.members for g in current_bot.groups()], [])
                 if u.puid in ids]
        if users is None:
            raise ApiException(errors.not_found)
        for user in users:
            current_bot.add_friend(user, verify_content)
        unexpected = ids.difference(set([u.id for u in users]))
        if unexpected:
            raise ApiException(
                errors.not_found,
                '如下puid用户未找到: {}'.format(','.join(unexpected)))
        return {}

    def delete(self):
        type = request.args.get('type')
        if type == 'contact':
            raise ApiException(errors.unimplemented_error,
                               'ItChat不支持删除好友')
        elif type == 'group':
            group_id = request.args.get('gid')
            ids = request.args.get('ids')
            group = current_bot.groups().search(puid=group_id)
            if not group:
                raise ApiException(errors.not_found)
            group = group[0]
            for uid in ids:
                group.remove_members(group.members.search(puid=uid))
            return {}


class GroupsAPI(MethodView):

    def get(self):
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        q = request.args.get('q', '')
        uid = current_bot.self.puid
        query = db.session.query
        query = query(Group).filter(Group.owner_id == uid)
        if q:
            groups = query.filter(Group.nick_name.like('%{}%'.format(q)))
            total = groups.count()
        else:
            groups = query
            total = groups.count()
        groups = groups.offset((page - 1) * page_size).limit(page_size).all()
        return {
            'total': total,
            'groups': [group.to_dict() for group in groups]
        }

    def put(self):
        data = request.get_json()
        ids = data['ids'].split(',')
        name = data['name']
        users = [u for u in current_bot.friends() if u.puid in ids]
        group = current_bot.create_group(users, topic=name)
        group.send_msg('创建成功')
        return {}


class UserAPI(MethodView):

    def delete(self, id):
        type = request.args.get('type')
        if type == 'contact':
            raise ApiException(errors.unimplemented_error,
                               'ItChat不支持删除好友')
        elif type == 'group':
            group_id = request.args.get('gid')
            group = current_bot.groups().search(puid=group_id)
            if not group:
                raise ApiException(errors.not_found)
            group = group[0]
            group.remove_members(group.members.search(puid=id))
            return {}

    def put(self, id):
        verify_content = request.args.get('verifyContent', '')
        user = next((u for u in sum(
            [g.members for g in current_bot.groups()], [])
            if u.puid == id), None)
        if user is None:
            raise ApiException(errors.not_found)
        current_bot.add_friend(user, verify_content)
        return {}


@json_api.route('/all_users')
def all_users():
    all_ids = set([u.puid for u in sum(
        [g.members for g in current_bot.groups()], [])])
    friend_ids = set([u.puid for u in current_bot.friends()])
    ids = all_ids.difference(friend_ids)
    users = [u.to_dict() for u in db.session.query(User).filter(
        User.id.in_(ids)).all()]
    return {'users': users}


@json_api.route('/all_groups')
def all_groups():
    uid = current_bot.self.puid
    user = db.session.query(User).filter_by(id=uid).first()
    if not user:
        raise ApiException(errors.not_found)
    groups = [group.to_dict() for group in user.groups]
    return {'groups': groups}


@json_api.route('/send_message', methods=['post'])
def send_message():
    data = request.get_json()
    type = data['type']
    ids = data['ids']
    group_id = data['gid']
    files = data['files']
    content = data['content']
    if type == 'group':
        send_type = data['send_type']
        groups = current_bot.groups()
        if send_type == 'contact':
            group = groups.search(puid=group_id)
            if not group:
                raise ApiException(errors.not_found)
            group = group[0]
            users = group.members
        else:
            users = sum([groups.search(puid=id) for id in ids], [])
    else:
        users = current_bot.friends()
    users = [u for u in users if u.puid in ids]
    for user in users:
        user.send_msg(content)
        for filename in files:
            suffix = filename.partition('.')[-1]
            file = os.path.join(config.UPLOAD_FOLDER, filename)
            if suffix in config.PIC_TYPES:
                user.send_image(file)
            else:
                user.send_file(file)
    unexpected = set(ids).difference(set([u.puid for u in users]))
    if unexpected:
        raise ApiException(
            errors.not_found,
            '如下puid用户未找到: {}，可能消息发送没成功'.format(','.join(unexpected)))
    return {}


@json_api.route('/messages')
def messages():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    type = request.args.get('type', '')
    query = db.session.query
    uid = current_bot.self.puid
    if type:
        if not isinstance(type, int):
            type = TYPE_TO_ID_MAP.get(type, 0)
        ms = query(Message).filter(Message.type == type)
        total = ms.count()
    else:
        ms = query(Message)
        total = ms.count()
    ms = ms.filter(Message.receiver_id == uid).order_by(
        Message.id.desc()).offset((page - 1) * page_size).limit(
            page_size).all()
    return {
        'total': total,
        'messages': [m.to_dict() for m in ms]
    }


@json_api.route('/readall', methods=['post'])
def readall():
    uid = current_bot.self.puid
    Notification.clean_by_receiver_id(uid)
    return {}


@json_api.route('/flush/<bot_id>', methods=['post'])
def flush(bot_id):
    data = request.get_json()
    type = data['type']
    from wechat.tasks import update_contact, update_group
    if type == 'contact':
        update_contact.delay(bot_id, True)
    elif type == 'group':
        update_group.delay(bot_id, True)

    return {}


json_api.add_url_rule('/user/<id>', view_func=UserAPI.as_view('user'))
json_api.add_url_rule('/users', view_func=UsersAPI.as_view('users'))
json_api.add_url_rule('/groups', view_func=GroupsAPI.as_view('groups'))
