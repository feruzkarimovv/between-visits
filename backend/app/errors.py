class ApiError(Exception):
    """Raised by routers/services; rendered as {"error": {"code", "message"}} with the given status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
