"""业务异常类型。"""

from app.core.api_response import ApiCode


class BizError(Exception):
    """业务错误，由全局 advice 统一转为 ApiResponse（默认 code=FAIL）。"""

    def __init__(self, message: str, code: int = ApiCode.FAIL):
        super().__init__(message)
        self.message = message
        self.code = code


class AuthError(Exception):
    """认证/鉴权错误（code=NO_LOGIN）。"""

    def __init__(self, message: str = "未登录或登录已过期"):
        super().__init__(message)
        self.message = message
