import unittest

from ordina.planner import Item, Monitor, Rect, capture, match_monitors, plan_restore, signature

CELL = (76, 86)


def monitor(mid, left, top, width, height, primary=False, taskbar=48):
    return Monitor(
        id=f"\\\\?\\DISPLAY#{mid}#uid#{{guid}}",
        hardware=mid,
        device="\\\\.\\DISPLAY1",
        bounds=Rect(left, top, left + width, top + height),
        work=Rect(left, top, left + width, top + height - taskbar),
        primary=primary,
    )


# Configurazione reale: portatile a sinistra e più in alto, HP primario, Acer a destra.
BEFORE = [
    monitor("BOE", -2560, -300, 2560, 1600),
    monitor("HPN", 0, 0, 1920, 1080, primary=True),
    monitor("ACR", 1920, 9, 1920, 1080),
]
BEFORE_ORIGIN = (-2560, -300)

# Stessi monitor, ma ora il primario è l'Acer: cambiano tutte le coordinate.
AFTER = [
    monitor("BOE", -4480, -309, 2560, 1600),
    monitor("HPN", -1920, -9, 1920, 1080),
    monitor("ACR", 0, 0, 1920, 1080, primary=True),
]
AFTER_ORIGIN = (-4480, -309)


def client(screen_x, screen_y, origin):
    return screen_x - origin[0], screen_y - origin[1]


def saved_layout():
    # Un'icona per monitor, a posizioni note sullo schermo.
    items = [
        Item("laptop", "Laptop", *client(-2500, -200, BEFORE_ORIGIN)),
        Item("hp", "HP", *client(100, 200, BEFORE_ORIGIN)),
        Item("acer", "Acer", *client(2000, 309, BEFORE_ORIGIN)),
    ]
    return capture("prova", BEFORE, items, BEFORE_ORIGIN, "2026-11-03T17:00:00")


def screen_after(plan, item_id, items, origin):
    x, y = plan.moves.get(item_id) or next((i.x, i.y) for i in items if i.id == item_id)
    return x + origin[0], y + origin[1]


class CaptureTest(unittest.TestCase):
    def test_saves_position_relative_to_own_monitor(self):
        icons = {icon["id"]: icon for icon in saved_layout()["icons"]}
        self.assertEqual((icons["laptop"]["monitor"], icons["laptop"]["x"], icons["laptop"]["y"]), (0, 60, 100))
        self.assertEqual((icons["hp"]["monitor"], icons["hp"]["x"], icons["hp"]["y"]), (1, 100, 200))
        self.assertEqual((icons["acer"]["monitor"], icons["acer"]["x"], icons["acer"]["y"]), (2, 80, 300))

    def test_icon_off_screen_goes_to_nearest_monitor(self):
        items = [Item("fuori", "Fuori", *client(5000, 300, BEFORE_ORIGIN))]
        layout = capture("x", BEFORE, items, BEFORE_ORIGIN, "t")
        self.assertEqual(layout["icons"][0]["monitor"], 2)


class PrimaryChangeTest(unittest.TestCase):
    def test_icons_return_to_same_place_on_each_monitor(self):
        # Windows le ha ammucchiate tutte sul nuovo primario.
        shuffled = [Item(i, i, 76 * n + 2000, 2000) for n, i in enumerate(["laptop", "hp", "acer"])]
        plan = plan_restore(saved_layout(), AFTER, shuffled, AFTER_ORIGIN, CELL)
        self.assertEqual(screen_after(plan, "laptop", shuffled, AFTER_ORIGIN), (-4480 + 60, -309 + 100))
        self.assertEqual(screen_after(plan, "hp", shuffled, AFTER_ORIGIN), (-1920 + 100, -9 + 200))
        self.assertEqual(screen_after(plan, "acer", shuffled, AFTER_ORIGIN), (0 + 80, 0 + 300))

    def test_second_restore_moves_nothing(self):
        layout = saved_layout()
        shuffled = [Item(i, i, 0, 0) for i in ["laptop", "hp", "acer"]]
        plan = plan_restore(layout, AFTER, shuffled, AFTER_ORIGIN, CELL)
        settled = [Item(i.id, i.name, *plan.moves[i.id]) for i in shuffled]
        again = plan_restore(layout, AFTER, settled, AFTER_ORIGIN, CELL)
        self.assertEqual(again.moves, {})
        self.assertEqual(again.unchanged, 3)

    def test_signature_changes_with_primary(self):
        self.assertNotEqual(signature(BEFORE), signature(AFTER))
        self.assertEqual(signature(BEFORE), signature(list(reversed(BEFORE))))


class MissingMonitorTest(unittest.TestCase):
    def test_icons_of_disconnected_monitor_stay_put(self):
        only_two = [AFTER[1], AFTER[2]]
        items = [Item("laptop", "Laptop", 300, 300), Item("hp", "HP", 700, 700), Item("acer", "Acer", 900, 900)]
        plan = plan_restore(saved_layout(), only_two, items, (-1920, -9), CELL)
        self.assertNotIn("laptop", plan.moves)
        self.assertEqual(plan.monitor_missing, 1)

    def test_same_model_on_other_port_is_recognised(self):
        saved = [{"id": "\\\\?\\DISPLAY#ACR#porta1#{g}", "hardware": "ACR"}]
        current = [monitor("HPN", 0, 0, 1920, 1080), Monitor("\\\\?\\DISPLAY#ACR#porta2#{g}", "ACR", "d",
                                                             Rect(0, 0, 1, 1), Rect(0, 0, 1, 1))]
        self.assertEqual(match_monitors(saved, current)[0].hardware, "ACR")

    def test_identical_monitors_are_not_mixed_up(self):
        first = Monitor("a#ACR#1", "ACR", "d", Rect(0, 0, 10, 10), Rect(0, 0, 10, 10))
        second = Monitor("a#ACR#2", "ACR", "d", Rect(10, 0, 20, 10), Rect(10, 0, 20, 10))
        saved = [{"id": "a#ACR#2", "hardware": "ACR"}, {"id": "a#ACR#1", "hardware": "ACR"}]
        matches = match_monitors(saved, [first, second])
        self.assertIs(matches[0], second)
        self.assertIs(matches[1], first)


class ResolutionTest(unittest.TestCase):
    def test_position_scales_and_stays_on_screen(self):
        smaller = [
            monitor("BOE", -2560, -300, 2560, 1600),
            monitor("HPN", 0, 0, 960, 540, primary=True),
            monitor("ACR", 960, 0, 1920, 1080),
        ]
        items = [Item("hp", "HP", 0, 0)]
        layout = capture("x", BEFORE, [Item("hp", "HP", *client(1900, 1000, BEFORE_ORIGIN))], BEFORE_ORIGIN, "t")
        plan = plan_restore(layout, smaller, items, BEFORE_ORIGIN, CELL)
        x, y = screen_after(plan, "hp", items, BEFORE_ORIGIN)
        self.assertEqual((x, y), (960 - CELL[0], 540 - CELL[1]))


class NewIconsTest(unittest.TestCase):
    def setUp(self):
        self.origin = (0, 0)
        self.monitors = [monitor("HPN", 0, 0, 1920, 1080, primary=True)]
        self.layout = capture("x", self.monitors, [Item("a", "A", 20, 2)], self.origin, "t")

    def test_new_icon_far_away_is_left_alone(self):
        items = [Item("a", "A", 20, 2), Item("nuova", "Nuova", 900, 500)]
        plan = plan_restore(self.layout, self.monitors, items, self.origin, CELL)
        self.assertEqual(plan.moves, {})
        self.assertEqual(plan.new_icons, 1)

    def test_new_icon_under_a_restored_one_is_moved_to_free_cell(self):
        items = [Item("a", "A", 500, 500), Item("nuova", "Nuova", 22, 4)]
        plan = plan_restore(self.layout, self.monitors, items, self.origin, CELL)
        self.assertEqual(plan.relocated, 1)
        x, y = plan.moves["nuova"]
        self.assertTrue(abs(x - 20) >= CELL[0] or abs(y - 2) >= CELL[1])

    def test_deleted_icon_is_counted(self):
        plan = plan_restore(self.layout, self.monitors, [], self.origin, CELL)
        self.assertEqual(plan.not_on_desktop, 1)


if __name__ == "__main__":
    unittest.main()
