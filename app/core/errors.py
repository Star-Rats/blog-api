"""业务异常与全局错误处理。"""


class BizError(Exception):
    """业务错误，HTTP 400 返回。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthError(Exception):
    """认证/鉴权错误，HTTP 401 返回。"""

    def __init__(self, message: str = "未登录或登录已过期"):
        super().__init__(message)
        self.message = message
