"""Calcolo delle posizioni: nessun accesso a Windows, così si può provare a tavolino.

Ogni icona è salvata rispetto all'angolo del suo monitor. Quando cambia il primario
cambiano le coordinate di tutto il desktop, ma non la posizione dentro il monitor.
"""
from dataclasses import dataclass, field
from typing import NamedTuple


class Rect(NamedTuple):
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    def contains(self, x, y):
        return self.left <= x < self.right and self.top <= y < self.bottom

    def distance_to(self, x, y):
        dx = max(self.left - x, 0, x - self.right + 1)
        dy = max(self.top - y, 0, y - self.bottom + 1)
        return dx * dx + dy * dy


@dataclass(frozen=True)
class Monitor:
    id: str  # percorso del dispositivo, non cambia con il primario
    hardware: str  # marca e modello, es. "GSM5B09"
    device: str  # \\.\DISPLAY1: può cambiare, serve solo da mostrare
    bounds: Rect
    work: Rect
    primary: bool = False


@dataclass(frozen=True)
class Item:
    id: str  # percorso completo, o ::{CLSID} per Cestino e simili
    name: str
    x: int  # coordinate nel desktop, relative a origin
    y: int


@dataclass
class Plan:
    moves: dict = field(default_factory=dict)  # id icona -> (x, y)
    unchanged: int = 0
    monitor_missing: int = 0  # icone salvate su un monitor che ora non c'è
    not_on_desktop: int = 0  # icone salvate che non esistono più
    new_icons: int = 0  # icone non presenti nel salvataggio
    relocated: int = 0  # icone non salvate spostate perché coperte


def hardware_of(path):
    parts = (path or "").split("#")
    return parts[1] if len(parts) > 1 else (path or "")


def signature(monitors):
    """Cambia se cambiano i monitor collegati, il primario o la loro disposizione."""
    return "|".join(sorted(
        f"{m.id}@{m.bounds.left},{m.bounds.top},{m.bounds.width}x{m.bounds.height}{'*' if m.primary else ''}"
        for m in monitors
    ))


def _monitor_at(monitors, x, y):
    for index, monitor in enumerate(monitors):
        if monitor.bounds.contains(x, y):
            return index
    return min(range(len(monitors)), key=lambda i: monitors[i].bounds.distance_to(x, y))


def capture(name, monitors, items, origin, saved_at):
    if not monitors:
        raise ValueError("Nessun monitor rilevato.")
    icons = []
    for item in items:
        sx, sy = item.x + origin[0], item.y + origin[1]
        index = _monitor_at(monitors, sx, sy)
        bounds = monitors[index].bounds
        icons.append({"id": item.id, "name": item.name, "monitor": index,
                      "x": sx - bounds.left, "y": sy - bounds.top})
    return {
        "name": name,
        "saved_at": saved_at,
        "monitors": [{"id": m.id, "hardware": m.hardware, "width": m.bounds.width,
                      "height": m.bounds.height, "primary": m.primary} for m in monitors],
        "icons": icons,
    }


def match_monitors(saved, monitors):
    """Associa i monitor salvati a quelli attuali: prima lo stesso dispositivo, poi
    lo stesso modello (se il cavo è passato a un'altra porta il percorso cambia)."""
    matches = {}
    free = list(monitors)
    for index, entry in enumerate(saved):
        for monitor in free:
            if monitor.id == entry["id"]:
                matches[index] = monitor
                free.remove(monitor)
                break
    for index, entry in enumerate(saved):
        if index in matches:
            continue
        for monitor in free:
            if monitor.hardware == entry["hardware"]:
                matches[index] = monitor
                free.remove(monitor)
                break
    return matches


def _target(icon, entry, monitor, origin, cell):
    bounds = monitor.bounds
    x, y = icon["x"], icon["y"]
    # Stessa risoluzione: posizione esatta. Altrimenti in proporzione.
    if entry["width"] != bounds.width:
        x = round(x * bounds.width / entry["width"])
    if entry["height"] != bounds.height:
        y = round(y * bounds.height / entry["height"])
    x = max(0, min(x, bounds.width - cell[0]))
    y = max(0, min(y, bounds.height - cell[1]))
    return bounds.left + x - origin[0], bounds.top + y - origin[1]


def _overlaps(a, b, cell, ratio):
    return abs(a[0] - b[0]) < cell[0] * ratio and abs(a[1] - b[1]) < cell[1] * ratio


def _free_cell(work, occupied, origin, cell):
    x = work.left
    while x + cell[0] <= work.right:
        y = work.top
        while y + cell[1] <= work.bottom:
            spot = (x - origin[0], y - origin[1])
            if not any(_overlaps(spot, other, cell, 1) for other in occupied):
                return spot
            y += cell[1]
        x += cell[0]
    return None


def plan_restore(layout, monitors, items, origin, cell):
    plan = Plan()
    if not monitors:
        return plan
    matches = match_monitors(layout["monitors"], monitors)
    current = {item.id: item for item in items}
    targets = {}

    for icon in layout["icons"]:
        item = current.get(icon["id"])
        if item is None:
            plan.not_on_desktop += 1
            continue
        monitor = matches.get(icon["monitor"])
        if monitor is None:
            plan.monitor_missing += 1
            continue
        target = _target(icon, layout["monitors"][icon["monitor"]], monitor, origin, cell)
        targets[item.id] = target
        if (item.x, item.y) == target:
            plan.unchanged += 1
        else:
            plan.moves[item.id] = target

    saved_ids = {icon["id"] for icon in layout["icons"]}
    others = [item for item in items if item.id not in targets]
    plan.new_icons = sum(1 for item in others if item.id not in saved_ids)

    # Un'icona non ripristinata non deve restare nascosta sotto una ripristinata.
    occupied = list(targets.values()) + [(item.x, item.y) for item in others]
    for item in others:
        spot = (item.x, item.y)
        if not any(_overlaps(spot, target, cell, 0.5) for target in targets.values()):
            continue
        monitor = monitors[_monitor_at(monitors, item.x + origin[0], item.y + origin[1])]
        occupied.remove(spot)
        free = _free_cell(monitor.work, occupied, origin, cell)
        if free is None:
            occupied.append(spot)
            continue
        occupied.append(free)
        plan.moves[item.id] = free
        plan.relocated += 1
    return plan
