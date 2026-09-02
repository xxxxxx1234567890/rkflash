class RkFlashError(Exception):
    """结构化错误：code 为机器可读标识，action_hint 给用户/Claude 的恢复建议。"""

    def __init__(self, code: str, message: str, action_hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.action_hint = action_hint
