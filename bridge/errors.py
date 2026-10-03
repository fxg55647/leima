class BridgeError(Exception):
    """An error with a stable code from docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md (protocol or bridge)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
