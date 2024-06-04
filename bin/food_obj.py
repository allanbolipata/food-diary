


class Food:
    def __init__(self, data):
        self._load_data(data)

    def _load_data(self, data):
        self.name = data["name"]

