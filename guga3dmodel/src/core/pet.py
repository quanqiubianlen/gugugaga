"""Desktop pet model wrapper."""

import time

class DesktopPet:
    def __init__(self, model) -> None:
        self.model = model
        self.state = "idle"

    def set_state(self, state: str) -> None:
        self.state = state