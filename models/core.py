from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from werkzeug.security import generate_password_hash, check_password_hash

from ext import db
from config import avatar_tmpl
from .mixin import BaseMixin


friendship = db.Table(
    'friends',
    db.Column('user_id', db.String(20), db.ForeignKey('users.id')),
    db.Column('friend_id', db.String(20), db.ForeignKey('users.id')),
    mysql_charset='utf8mb4'
)


group_relationship = db.Table(
    'group_relationship',
    db.Column('group_id', db.String(20), db.ForeignKey('groups.id'),
              nullable=False),
    db.Column('user_id', db.String(20), db.ForeignKey('users.id'),
              nullable=False),
    mysql_charset='utf8mb4'
)

mp_relationship = db.Table(
    'mp_relationship',
    db.Column('mp_id', db.String(20), db.ForeignKey('mps.id'),
              nullable=False),
    db.Column('user_id', db.String(20), db.ForeignKey('users.id'),
              nullable=False),
    mysql_charset='utf8mb4'
)


class CoreMixin(BaseMixin):

    @property
    def avatar(self):
        return avatar_tmpl.format(self.id)

    def to_dict(self):
        rs = super().to_dict()
        rs['avatar'] = self.avatar
        return rs


class User(CoreMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.String(20), primary_key=True)  # puid
    sex = db.Column(db.SmallInteger, default=2)
    nick_name = db.Column(db.String(60), index=True)
    signature = db.Column(db.String(512), default='')
    province = db.Column(db.String(20), default='')
    city = db.Column(db.String(20), default='')
    name = db.Column(db.String(20), default='') # name mobile userId_in_order 来自定单系统
    mobile = db.Column(db.String(20), default='')
    userId_in_order = db.Column(db.Integer)
    groups = db.relationship('Group', secondary=group_relationship,
                             backref='members')
    mps = db.relationship('MP', secondary=mp_relationship,
                          backref='users')
    friends = db.relationship('User',
                              secondary=friendship,
                              primaryjoin=(friendship.c.user_id == id),
                              secondaryjoin = (friendship.c.friend_id == id),
                              lazy = 'dynamic'
                              )

    def __repr__(self):
        return '<User %r>' % self.nick_name

    @hybrid_method
    def add_friend(self, user):
        if not self.is_friend(user):
            self.friends.append(user)
            user.friends.append(self)
            return self

    @hybrid_method
    def del_friend(self, user):
        if self.is_friend(user):
            self.friends.remove(user)
            user.friends.remove(self)
            return self

    @hybrid_method
    def is_friend(self, user):
        return self.friends.filter(
            friendship.c.friend_id == user.id).count() > 0

    @hybrid_method
    def add_group(self, group):
        if not self.is_in_group(group):
            self.groups.append(group)

    @hybrid_method
    def del_group(self, group):
        if self.is_in_group(group):
            self.groups.remove(group)

    @hybrid_method
    def is_in_group(self, group):
        return group in self.groups


class Group(CoreMixin, db.Model):
    __tablename__ = 'groups'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.String(20), primary_key=True)  # puid
    owner_id = db.Column(db.String(20), index=True)
    nick_name = db.Column(db.String(60), index=True)

    def __repr__(self):
        return '<Group %r>' % self.nick_name

    @hybrid_method
    def is_member(self, user):
        return user in self.members

    @hybrid_method
    def add_member(self, user):
        if not self.is_member(user):
            self.members.append(user)

    @hybrid_method
    def del_member(self, user):
        if self.is_member(user):
            self.members.remove(user)

    @hybrid_property
    def count(self):
        return len(self.members)

    def to_dict(self):
        rs = super().to_dict()
        rs['count'] = self.count
        return rs


class MP(CoreMixin, db.Model):
    __tablename__ = 'mps'
    __table_args__ = {'mysql_charset': 'utf8mb4'}
    id = db.Column(db.String(20), primary_key=True)  # puid
    city = db.Column(db.String(20), default='')
    province = db.Column(db.String(20), default='')
    nick_name = db.Column(db.String(60), index=True)
    signature = db.Column(db.String(255), default='')

    def __repr__(self):
        return '<MP %r>' % self.nick_name


class LoginUser(db.Model):
    __tablename__ = 'login_user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250),  unique=True, nullable=False)
    username = db.Column(db.String(250),  unique=True, nullable=False)
    password = db.Column(db.String(250))
    login_time = db.Column(db.Integer)

    def __init__(self, id, username, password, email):
        self.id = id
        self.username = username
        self.password = password
        self.email = email

    def __str__(self):
        return "Users(id='%s')" % self.id

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, hash, password):
        return check_password_hash(hash, password)

    def get(self, username):
        return self.query.filter_by(username=username).first()

    def add(self):
        db.session.add(self)
        return session_commit()


def session_commit():
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        reason = str(e)
        return reason
