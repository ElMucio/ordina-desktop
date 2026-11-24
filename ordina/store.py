"""Disposizioni e impostazioni, in un file JSON in %APPDATA%\\OrdinaDesktop."""
import json
import os
from pathlib import Path


def data_dir():
    return Path(os.environ["APPDATA"]) / "OrdinaDesktop"


DEFAULTS = {
    "default": None,  # nome della disposizione usata da tray, scorciatoia e automatismo
    "auto_restore": True,
    "exact_position": True,
    "snap_off_by_app": False,
    "signature": None,  # ultima configurazione di monitor vista
    "tray_tip_shown": False,
    "layouts": [],
}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.data = dict(DEFAULTS, layouts=[])
        self.recovered_from = None
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as file:
                loaded = json.load(file)
            if not isinstance(loaded, dict) or not isinstance(loaded.get("layouts", []), list):
                raise ValueError("struttura non valida")
            self.data.update(loaded)
        except (ValueError, OSError):
            # Non sovrascrivere un file illeggibile: potrebbe essere recuperabile a mano.
            backup = self.path.with_suffix(".danneggiato.json")
            os.replace(self.path, backup)
            self.recovered_from = backup

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=1)
        os.replace(temp, self.path)

    @property
    def layouts(self):
        return self.data["layouts"]

    def find(self, name):
        return next((layout for layout in self.layouts if layout["name"] == name), None)

    @property
    def default_layout(self):
        return self.find(self.data["default"])

    def put(self, layout):
        for index, existing in enumerate(self.layouts):
            if existing["name"] == layout["name"]:
                self.layouts[index] = layout
                break
        else:
            self.layouts.append(layout)
        if not self.default_layout:
            self.data["default"] = layout["name"]
        self.save()

    def remove(self, name):
        self.data["layouts"] = [layout for layout in self.layouts if layout["name"] != name]
        if self.data["default"] == name:
            self.data["default"] = self.layouts[0]["name"] if self.layouts else None
        self.save()
