"""Agent-owned errors, independent from Backend HTTP/business modules."""


class BusinessError(Exception):
    def __init__(self, code: int, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
