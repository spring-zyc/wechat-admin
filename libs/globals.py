from werkzeug.local import LocalStack, LocalProxy


def _find_bot():
    from .wx import get_bot
    top = _wx_ctx_stack.top
    if top is None:
        top = get_bot()
        _wx_ctx_stack.push(top)
    return top


_wx_ctx_stack = LocalStack()
# current_bot = LocalProxy(_find_bot)


def _get_my_bots():
    from .mybot import MyBot
    top = _wx_ctx_stack.top
    if top is None:
        top = MyBot()
        _wx_ctx_stack.push(top)
    return top


current_bots = LocalProxy(_get_my_bots)

