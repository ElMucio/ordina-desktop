"""Le due operazioni dell'app: fotografare il desktop e rimetterlo a posto."""
import time
from dataclasses import dataclass
from datetime import datetime

from .desktop_view import DesktopView
from .monitors import current_monitors
from .planner import capture, plan_restore

# La griglia riallinea le icone con un attimo di ritardo: rileggendo subito
# la posizione sembrerebbe giusta anche quando poi l'icona slitta.
GRID_SETTLE_SECONDS = 0.5


@dataclass
class RestoreResult:
    moved: int = 0
    unchanged: int = 0
    monitor_missing: int = 0
    not_on_desktop: int = 0
    new_icons: int = 0
    relocated: int = 0
    not_exact: int = 0  # icone che la griglia di Windows ha tenuto altrove
    auto_arrange_disabled: bool = False
    snap_off: bool = False  # "Allinea alla griglia" è spento per opera dell'app
    before: dict = None  # posizioni prima del ripristino, per annullare


def _now():
    return datetime.now().isoformat(timespec="seconds")


def snapshot(name):
    """Restituisce le posizioni attuali e se è attiva la disposizione automatica."""
    monitors = current_monitors()
    with DesktopView() as view:
        layout = capture(name, monitors, view.read_items(), view.origin(), _now())
        return layout, view.auto_arrange


def restore(layout, exact=True, snap_off=False):
    """Rimette le icone secondo layout.

    La griglia di Windows è ancorata al monitor principale: se questo cambia, le
    posizioni salvate possono non cadere più su una cella. Con exact=True in quel caso
    si spegne "Allinea alla griglia"; snap_off ricorda di averlo fatto, così il
    ripristino successivo lo riaccende e lo rispegne solo se serve ancora.
    """
    monitors = current_monitors()
    with DesktopView() as view:
        origin, cell = view.origin(), view.cell()
        items = view.read_items()
        result = RestoreResult(snap_off=snap_off, before=capture("prima", monitors, items, origin, _now()))
        plan = plan_restore(layout, monitors, items, origin, cell)

        if view.auto_arrange:
            view.auto_arrange = False
            result.auto_arrange_disabled = True
            items = view.read_items()
            plan = plan_restore(layout, monitors, items, origin, cell)

        if plan.moves:
            if snap_off:
                view.snap_to_grid = True
                result.snap_off = False
                time.sleep(GRID_SETTLE_SECONDS)
                items = view.read_items()
                plan = plan_restore(layout, monitors, items, origin, cell)

            view.move(plan.moves)
            if view.snap_to_grid:
                time.sleep(GRID_SETTLE_SECONDS)
            drift = _drift(view, plan.moves)
            if drift and exact and view.snap_to_grid:
                view.snap_to_grid = False
                result.snap_off = True
                view.move(drift)
                drift = _drift(view, plan.moves)
            result.not_exact = len(drift)

        result.moved = len(plan.moves) - plan.relocated
        result.unchanged = plan.unchanged
        result.monitor_missing = plan.monitor_missing
        result.not_on_desktop = plan.not_on_desktop
        result.new_icons = plan.new_icons
        result.relocated = plan.relocated
        return result


def _drift(view, targets):
    actual = {item.id: (item.x, item.y) for item in view.read_items()}
    return {item_id: target for item_id, target in targets.items() if actual.get(item_id) != target}
