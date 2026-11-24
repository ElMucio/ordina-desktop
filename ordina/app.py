"""Finestra principale e ripristino automatico al cambio dei monitor."""
import ctypes
import logging
import logging.handlers
import queue
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import engine, startup
from .desktop_view import init_com
from .monitors import current_monitors
from .planner import match_monitors, signature
from .store import Store, data_dir
from .tray import Tray, ask_running_instance_to_show, claim_single_instance

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "app.ico"
SCRIPT = ROOT / "ordina_desktop.pyw"

POLL_MS = 2000
# Dopo un cambio di monitor Explorer risistema le icone con calma: si ripassa più volte.
AUTO_PASSES_MS = (3000, 5000, 10000)

log = logging.getLogger("ordina")


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def describe(result):
    parts = [f"Ripristino fatto: {_count(result.moved, 'icona spostata', 'icone spostate')}, "
             f"{result.unchanged} già a posto."]
    if result.monitor_missing:
        parts.append(f"{_count(result.monitor_missing, 'icona', 'icone')} su un monitor non collegato: "
                     "torneranno al loro posto quando lo ricolleghi.")
    if result.relocated:
        parts.append(f"{_count(result.relocated, 'icona non salvata spostata', 'icone non salvate spostate')} "
                     "per non restare coperte.")
    elif result.new_icons:
        parts.append(f"{_count(result.new_icons, 'icona nuova lasciata', 'icone nuove lasciate')} dov'era.")
    if result.not_on_desktop:
        parts.append(f"{_count(result.not_on_desktop, 'icona salvata non esiste', 'icone salvate non esistono')} più.")
    if result.auto_arrange_disabled:
        parts.append("Ho disattivato «Disponi icone automaticamente», che impediva di posizionarle.")
    if result.snap_off:
        parts.append("«Allinea icone alla griglia» è spento: con questo monitor principale la griglia sposterebbe le icone.")
    if result.not_exact:
        parts.append(f"{_count(result.not_exact, 'icona spostata', 'icone spostate')} di poco dalla griglia di Windows.")
    return " ".join(parts)


class App:
    def __init__(self, store, start_hidden=False, use_tray=True):
        self.store = store
        self.undo_layout = None
        self.auto_jobs = []
        self.events = queue.Queue()
        self.layout_ids = {}

        self.root = tk.Tk()
        self.root.title("Ordina Desktop")
        self.root.report_callback_exception = self._on_callback_error
        if ICON.exists():
            self.root.iconbitmap(default=str(ICON))
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        if start_hidden:
            self.root.withdraw()

        self._build_ui()

        self.tray = None
        if use_tray:
            self.tray = Tray(ICON, "Ordina Desktop", self.events)
            self.tray.start()
            self.tray.ready.wait(5)

        self.refresh()
        if store.recovered_from:
            self.set_status(f"Il file dei salvataggi era danneggiato: l'ho messo da parte in {store.recovered_from}.")
        elif self.tray and not self.tray.hotkey_ok:
            self.set_status("La scorciatoia Ctrl+Alt+R è già usata da un altro programma: usa il pulsante o l'icona.")

        self._check_monitors()
        self.root.after(100, self._drain_events)

    def _build_ui(self):
        self.scale = self.root.winfo_fpixels("1i") / 96
        style = ttk.Style(self.root)
        style.configure("Treeview", rowheight=int(26 * self.scale))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 15))
        style.configure("Sub.TLabel", foreground="#5f6368")
        style.configure("Big.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
        style.configure("TButton", padding=(10, 5))

        self.root.geometry(f"{int(700 * self.scale)}x{int(500 * self.scale)}")
        self.root.minsize(int(620 * self.scale), int(440 * self.scale))
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="Ordina Desktop", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.summary = ttk.Label(frame, style="Sub.TLabel")
        self.summary.grid(row=1, column=0, sticky="w", pady=(0, 12))

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.restore_button = ttk.Button(actions, text="Ripristina icone", style="Big.TButton", command=self.restore_selected)
        self.restore_button.pack(side="left")
        ttk.Button(actions, text="Salva posizioni attuali…", style="Big.TButton", command=self.save_new).pack(side="left", padx=8)
        self.undo_button = ttk.Button(actions, text="Annulla ripristino", style="Big.TButton", command=self.undo)
        self.undo_button.pack(side="left")

        table = ttk.Frame(frame)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = {"name": ("Disposizione", 260), "date": ("Salvata il", 140), "icons": ("Icone", 60), "monitors": ("Monitor", 130)}
        self.tree = ttk.Treeview(table, columns=list(columns), show="headings", selectmode="browse")
        for key, (title, width) in columns.items():
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=int(width * self.scale), stretch=key == "name", anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._update_buttons())
        self.tree.bind("<Double-1>", lambda _event: self.restore_selected())

        manage = ttk.Frame(frame)
        manage.grid(row=4, column=0, sticky="ew", pady=(8, 12))
        self.overwrite_button = ttk.Button(manage, text="Aggiorna con le posizioni attuali", command=self.overwrite)
        self.overwrite_button.pack(side="left")
        self.default_button = ttk.Button(manage, text="Imposta come predefinita", command=self.make_default)
        self.default_button.pack(side="left", padx=8)
        self.delete_button = ttk.Button(manage, text="Elimina", command=self.delete)
        self.delete_button.pack(side="left")

        self.auto_var = tk.BooleanVar(value=self.store.data["auto_restore"])
        self.exact_var = tk.BooleanVar(value=self.store.data["exact_position"])
        self.startup_var = tk.BooleanVar(value=startup.is_enabled())
        ttk.Checkbutton(frame, text="Ripristina da solo la predefinita quando cambiano i monitor o il principale",
                        variable=self.auto_var, command=self._save_options).grid(row=5, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Posizione esatta al pixel (se serve, spegne «Allinea icone alla griglia»)",
                        variable=self.exact_var, command=self._save_options).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Avvia con Windows, nascosta vicino all'orologio",
                        variable=self.startup_var, command=self._toggle_startup).grid(row=7, column=0, sticky="w")

        self.status = ttk.Label(frame, anchor="w", justify="left")
        self.status.grid(row=8, column=0, sticky="ew", pady=(12, 0))
        self.status.bind("<Configure>", lambda event: self.status.configure(wraplength=event.width))

    # --- stato mostrato

    def refresh(self, select=None):
        selected = select or self._selected_name() or self.store.data["default"]
        self.tree.delete(*self.tree.get_children())
        self.layout_ids = {}
        monitors = current_monitors()
        for index, layout in enumerate(self.store.layouts):
            iid = f"layout{index}"
            self.layout_ids[iid] = layout["name"]
            star = "★ " if layout["name"] == self.store.data["default"] else ""
            total = len(layout["monitors"])
            connected = len(match_monitors(layout["monitors"], monitors))
            self.tree.insert("", "end", iid=iid, values=(
                star + layout["name"],
                datetime.fromisoformat(layout["saved_at"]).strftime("%d/%m/%Y %H:%M"),
                len(layout["icons"]),
                f"{total}" if connected == total else f"{connected} di {total} collegati",
            ))
            if layout["name"] == selected:
                self.tree.selection_set(iid)
        primary = next((m for m in monitors if m.primary), None)
        self.summary.configure(text=f"Monitor collegati: {len(monitors)}"
                                    + (f", principale {primary.hardware}" if primary else "")
                                    + "  ·  scorciatoia Ctrl+Alt+R")
        self._update_buttons()
        if not self.store.layouts:
            self.set_status("Sistema le icone come le vuoi, poi premi «Salva posizioni attuali».")

    def _selected_name(self):
        selection = self.tree.selection()
        return self.layout_ids.get(selection[0]) if selection else None

    def _update_buttons(self):
        has_selection = "normal" if self._selected_name() else "disabled"
        for button in (self.restore_button, self.overwrite_button, self.default_button, self.delete_button):
            button.configure(state=has_selection)
        self.undo_button.configure(state="normal" if self.undo_layout else "disabled")

    def set_status(self, text):
        self.status.configure(text=text)

    def _report_error(self, action, error):
        log.exception("%s", action)
        self.set_status(f"{action}: {error}")
        if self.tray and not self.root.winfo_viewable():
            self.tray.notify("Ordina Desktop", f"{action}: {error}")

    def _on_callback_error(self, exc_type, exc, tb):
        log.error("Errore nell'interfaccia", exc_info=(exc_type, exc, tb))
        self.set_status(f"Errore imprevisto: {exc}")

    # --- azioni

    def _ask_name(self):
        suggestion = "Principale" if not self.store.layouts else ""
        name = simpledialog.askstring("Salva posizioni", "Nome della disposizione:", parent=self.root, initialvalue=suggestion)
        return name.strip() if name else None

    def _capture_and_store(self, name):
        try:
            layout, auto_arrange = engine.snapshot(name)
            self.store.put(layout)
        except OSError as error:
            self._report_error("Salvataggio non riuscito", error)
            return
        self.refresh(select=name)
        text = f"Salvata «{name}»: {_count(len(layout['icons']), 'icona', 'icone')} su {_count(len(layout['monitors']), 'monitor', 'monitor')}."
        if auto_arrange:
            text += " Attenzione: «Disponi icone automaticamente» è attivo, verrà disattivato al ripristino."
        self.set_status(text)

    def save_new(self):
        name = self._ask_name()
        if not name:
            return
        if self.store.find(name) and not messagebox.askyesno(
                "Sovrascrivere?", f"Esiste già «{name}». Vuoi sostituirla con le posizioni attuali?", parent=self.root):
            return
        self._capture_and_store(name)

    def overwrite(self):
        name = self._selected_name()
        if not name:
            return
        layout = self.store.find(name)
        question = f"Sostituire «{name}» con le posizioni attuali?"
        connected = len(match_monitors(layout["monitors"], current_monitors()))
        if connected < len(layout["monitors"]):
            question += (f"\n\nQuesta disposizione usa {len(layout['monitors'])} monitor e ora ne risultano collegati "
                         f"{connected}: le posizioni sui monitor mancanti andrebbero perse.")
        if messagebox.askyesno("Sovrascrivere?", question, parent=self.root):
            self._capture_and_store(name)

    def make_default(self):
        name = self._selected_name()
        if name:
            self.store.data["default"] = name
            self.store.save()
            self.refresh(select=name)
            self.set_status(f"«{name}» è la disposizione usata da scorciatoia, icona e ripristino automatico.")

    def delete(self):
        name = self._selected_name()
        if name and messagebox.askyesno("Eliminare?", f"Eliminare la disposizione «{name}»?", parent=self.root):
            self.store.remove(name)
            self.refresh()
            self.set_status(f"«{name}» eliminata.")

    def _apply(self, layout, keep_undo=True):
        result = engine.restore(layout, exact=self.store.data["exact_position"],
                                snap_off=self.store.data["snap_off_by_app"])
        if result.snap_off != self.store.data["snap_off_by_app"]:
            self.store.data["snap_off_by_app"] = result.snap_off
            self.store.save()
        if keep_undo:
            self.undo_layout = result.before
        self._update_buttons()
        return result

    def _restore(self, layout):
        try:
            self.set_status(describe(self._apply(layout)))
        except OSError as error:
            self._report_error("Ripristino non riuscito", error)

    def restore_selected(self):
        name = self._selected_name()
        if name:
            self._restore(self.store.find(name))

    def restore_default(self):
        layout = self.store.default_layout
        if layout:
            self._restore(layout)
        elif self.tray:
            self.tray.notify("Ordina Desktop", "Non hai ancora salvato una disposizione.")
            self.show()

    def undo(self):
        layout, self.undo_layout = self.undo_layout, None
        if layout:
            try:
                self._apply(layout, keep_undo=False)
                self.set_status("Ultimo ripristino annullato.")
            except OSError as error:
                self._report_error("Annullamento non riuscito", error)
            self._update_buttons()

    def _save_options(self):
        self.store.data["auto_restore"] = self.auto_var.get()
        self.store.data["exact_position"] = self.exact_var.get()
        self.store.save()

    def _toggle_startup(self):
        try:
            startup.set_enabled(self.startup_var.get(), SCRIPT)
        except OSError as error:
            self.startup_var.set(startup.is_enabled())
            self._report_error("Impostazione non riuscita", error)

    # --- monitor che cambiano

    def _check_monitors(self):
        try:
            monitors = current_monitors()
            current = signature(monitors)
            if monitors and current != self.store.data["signature"]:
                changed = self.store.data["signature"] is not None
                self.store.data["signature"] = current
                self.store.save()
                if changed:
                    self.refresh()
                    self._schedule_auto_restore()
        except OSError:
            log.exception("Controllo monitor")
        self.root.after(POLL_MS, self._check_monitors)

    def _schedule_auto_restore(self):
        for job in self.auto_jobs:
            self.root.after_cancel(job)
        self.auto_jobs = []
        if not self.store.data["auto_restore"] or not self.store.default_layout:
            return
        delay = 0
        for index, wait in enumerate(AUTO_PASSES_MS):
            delay += wait
            self.auto_jobs.append(self.root.after(delay, self._auto_restore, index == 0))

    def _auto_restore(self, first_pass):
        layout = self.store.default_layout
        if not layout or not self.store.data["auto_restore"]:
            return
        try:
            # L'annullamento deve riportare allo stato prima del primo passaggio.
            result = self._apply(layout, keep_undo=first_pass)
            if first_pass or result.moved or result.relocated:
                self.set_status("Monitor cambiati. " + describe(result))
        except OSError:
            log.exception("Ripristino automatico")  # Explorer può non essere pronto: riprova al passaggio dopo

    # --- finestra e tray

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event == "open":
                    self.show()
                elif event == "restore":
                    self.restore_default()
                elif event == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def show(self):
        self.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        if not self.tray:
            self.quit()
            return
        self.root.withdraw()
        if not self.store.data["tray_tip_shown"]:
            self.tray.notify("Ordina Desktop è ancora attiva",
                             "Resta vicino all'orologio per ripristinare le icone. Per chiuderla: tasto destro, Esci.")
            self.store.data["tray_tip_shown"] = True
            self.store.save()

    def quit(self):
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _setup_logging():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(folder / "errori.log", maxBytes=200_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)


def prepare_process():
    # Interfaccia nitida. Il motore passa ai pixel reali solo quando serve (physical_pixels).
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    # Così la barra delle applicazioni mostra l'icona dell'app e non quella di Python.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OrdinaDesktop")
    init_com()


def main():
    start_hidden = "--tray" in sys.argv
    if not claim_single_instance():
        if not start_hidden:
            ask_running_instance_to_show()
        return
    _setup_logging()
    prepare_process()
    App(Store(data_dir() / "dati.json"), start_hidden=start_hidden).run()
