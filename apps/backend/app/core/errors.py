INTERNAL_ERROR_CODE = 20004
INTERNAL_ERROR_MESSAGE = '服务暂时不可用，请稍后重试'


class BusinessError(Exception):
    def __init__(self, code: int, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
