from sqlalchemy.ext.hybrid import hybrid_property

from ext import db
from .redis import db as r
from .mixin import BaseMixin
from .core import User, Group, MP
from libs.consts import ID_TO_TYPE_MAP, MP as _MP
from libs.utils import cached_hybrid_property

NOTIFICATION_KEY = 'notification:{receiver_id}'
MY_NOTIFICATION_KEY = 'mynotification:{receiver_id}'


class Notification:
    @staticmethod
    def add(rid, msg_id):
        r.sadd(NOTIFICATION_KEY.format(receiver_id=rid), msg_id)

    @staticmethod
    def count_by_receiver_id(rid):
        return r.scard(NOTIFICATION_KEY.format(receiver_id=rid))

    @staticmethod
    def get_all():
        l = r.keys('notification*')
        ret = {}
        for i in l:
            ret[str(i).split(":")[1][:-1]] = r.scard(i)
        return ret

    @staticmethod
    def clean_by_receiver_id(rid):
        r.delete(NOTIFICATION_KEY.format(receiver_id=rid))


class MyNotification:
    @staticmethod
    def add(rid, msg_id):
        r.sadd(MY_NOTIFICATION_KEY.format(receiver_id=rid), msg_id)

    @staticmethod
    def count_by_receiver_id(rid):
        return r.scard(MY_NOTIFICATION_KEY.format(receiver_id=rid))

    @staticmethod
    def get_all():
        l = r.keys('mynotification*')
        ret = {}
        for i in l:
            ret[str(i).split(":")[1][:-1]] = r.scard(i)
        return ret

    @staticmethod
    def clean_by_receiver_id(rid):
        r.delete(MY_NOTIFICATION_KEY.format(receiver_id=rid))


class Log(db.Model):
    __tablename__ = 'logs'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    operator_id = db.Column(db.Integer)
    operator_type = db.Column(db.SmallInteger)
    payload = db.Column(db.PickleType)

    def __init__(self, operator_id, operator_type, payload):
        self.operator_id = operator_id
        self.operator_type = operator_type
        self.payload = payload

    def __repr__(self):
        return '<Log %r>' % self.id


class Message(BaseMixin, db.Model):
    __tablename__ = 'messages'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.String(20), default=0, index=True)
    sender_id = db.Column(db.String(20), index=True)
    receiver_id = db.Column(db.String(20), index=True)
    content = db.Column(db.String(1024))
    receive_time = db.Column(db.DateTime)
    type = db.Column(db.SmallInteger)
    url = db.Column(db.String(512), default='')
    file_ext = db.Column(db.String(20), default='')

    def __repr__(self):
        return '<Message %r>' % self.id

    @cached_hybrid_property
    def query(self):
        return db.session.query

    @hybrid_property
    def group(self):
        if not self.group_id:
            return {}
        group = self.query(Group).get(self.group_id)
        return group.to_dict() if group else {}

    @hybrid_property
    def sender(self):
        if not self.sender_id:
            return {}
        user = self.query(MP if self.type == _MP else User).get(self.sender_id)
        return user.to_dict() if user else {}

    @cached_hybrid_property
    def msg_type(self):
        return ID_TO_TYPE_MAP.get(self.type, 'Text')

    def to_dict(self):
        dct = super().to_dict()
        for p in ('sender', 'group', 'msg_type'):
            dct[p] = getattr(self, p)
        return dct


class Tag(db.Model, BaseMixin):
    __tablename__ = 'tag'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.Integer, primary_key=True)
    tag_name = db.Column(db.String(1024))
    created_time = db.Column(db.DateTime)
    ref_count = db.Column(db.Integer)
    parent = db.Column(db.Integer, default='')
    level = db.Column(db.Integer, default=0)


tag_message = db.Table(
    'tag_meesage',
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id')),
    db.Column('message_id', db.Integer, db.ForeignKey('message.id')),
    mysql_charset='utf8mb4'
)