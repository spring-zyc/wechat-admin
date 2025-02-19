import jwt
import datetime
import time
from models.core import LoginUser
import config


class Auth:
    @staticmethod
    def encode_auth_token(user_id, login_time):
        """
        生成认证Token
        :param user_id: int
        :param login_time: int(timestamp)
        :return: string
        """
        try:
            payload = {
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=0, seconds=10),
                'iat': datetime.datetime.utcnow(),
                'iss': 'ken',
                'data': {
                    'id': user_id,
                    'login_time': login_time
                }
            }
            return jwt.encode(
                payload,
                config.SECRET_KEY,
                algorithm='HS256'
            )
        except Exception as e:
            return e

    @staticmethod
    def decode_auth_token(auth_token):
        """
        验证Token
        :param auth_token:
        :return: integer|string
        """
        try:
            # payload = jwt.decode(auth_token, app.config.get('SECRET_KEY'), leeway=datetime.timedelta(seconds=10))
            # 取消过期时间验证
            payload = jwt.decode(auth_token, config.SECRET_KEY, options={'verify_exp': False})
            if 'data' in payload and 'id' in payload['data']:
                return payload
            else:
                raise jwt.InvalidTokenError
        except jwt.ExpiredSignatureError:
            return 'Token过期'
        except jwt.InvalidTokenError:
            return '无效Token'

    @staticmethod
    def authenticate(username, password):
        """
        用户登录，登录成功返回token，写将登录时间写入数据库；登录失败返回失败原因
        :param password:
        :return: json
        """
        userInfo = LoginUser.query.filter_by(username=username).first()
        if userInfo is None:
            return -1, '找不到用户'
        else:
            if userInfo.check_password(password):
                login_time = int(time.time())
                userInfo.login_time = login_time
                if not userInfo.update():
                    return -6, "登录时间更新失败"
                token = Auth.encode_auth_token(userInfo.id, login_time)
                return 0, token.decode()
            else:
                return -2, '密码不正确'

    @staticmethod
    def identify(request):
        """
        用户鉴权
        :return: list
        """
        auth_header = request.headers.get('Authorization')
        if auth_header:
            auth_tokenArr = auth_header.split(" ")
            if not auth_tokenArr or auth_tokenArr[0] != 'Bearer' or len(auth_tokenArr) != 2:
                result = -1, '请传递正确的验证头信息'
            else:
                auth_token = auth_tokenArr[1]
                payload = Auth.decode_auth_token(auth_token)
                if not isinstance(payload, str):
                    user = LoginUser.query.filter_by(id=payload['data']['id']).first()
                    if user is None:
                        result = -2, '找不到该用户信息'
                    else:
                        if user.login_time == payload['data']['login_time']:
                            result = 0, user  # '请求成功'
                        else:
                            result = -3, 'Token已更改，请重新登录获取'
                else:
                    result = -4, payload
        else:
            result = -5, '没有提供认证token'
        return result
