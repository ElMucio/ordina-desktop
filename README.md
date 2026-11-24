# Ordina Desktop

> **EN** — Windows tray app that saves your desktop icon layout and restores it with one key,
> even after changing the primary monitor. Monitors are matched by hardware ID and icons are moved
> through the official Shell API (`IFolderView`). Pure Python standard library, no dependencies.

Salva la posizione delle icone del desktop e le rimette a posto con un tasto,
anche dopo aver cambiato il monitor principale. Solo per Windows.

## Avvio

Serve Python 3 (installato da [python.org](https://www.python.org/downloads/), con tkinter);
non ci sono altre dipendenze.

- Doppio clic su **`ordina_desktop.pyw`**, oppure
- doppio clic su **`crea_collegamento.bat`**: crea `Ordina Desktop.lnk` con l'icona dell'app,
  da usare o da copiare dove preferisci.

Se chiudi la finestra l'app resta attiva vicino all'orologio: per chiuderla davvero,
tasto destro sull'icona e **Esci**.

Se usi DesktopOK, chiudilo: due programmi che spostano le icone si danno fastidio.

## Uso

1. Sistema le icone come le vuoi.
2. Premi **Salva posizioni attuali** e dai un nome. La prima disposizione diventa la predefinita (★).
3. Per rimetterle a posto: **Ripristina icone**, `Ctrl+Alt+R`, o tasto destro sull'icona vicino all'orologio.

Se le risistemi e vuoi tenere il nuovo ordine, usa **Aggiorna con le posizioni attuali**:
il ripristino, anche quello automatico, riporta sempre all'ultima versione salvata.

| Opzione | Effetto |
|---|---|
| Ripristina da solo | Quando cambiano i monitor o il principale ripristina la predefinita, anche se il cambio è avvenuto ad app chiusa. |
| Posizione esatta al pixel | Vedi sotto. |
| Avvia con Windows | Parte nascosta all'accesso. Se sposti questa cartella, toglila e rimettila. |

## Cosa succede in casi particolari

- **Monitor non collegato:** le sue icone restano dove le ha messe Windows e tornano al loro posto quando lo ricolleghi.
- **Risoluzione diversa da quella salvata:** la posizione viene riportata in proporzione.
- **Icona nuova:** non viene toccata, salvo che finisca sotto una ripristinata: allora va nel primo spazio libero del suo monitor.
- **File rinominato o spostato:** conta come icona nuova, perché le icone sono riconosciute dal percorso completo.
- **«Disponi icone automaticamente» attivo:** viene disattivato al ripristino, perché impedisce di posizionarle.
- **«Allinea icone alla griglia»:** la griglia di Windows parte dal monitor principale, quindi cambiandolo le posizioni
  salvate possono non cadere più su una cella e le icone slitterebbero fino a mezza cella. Con *Posizione esatta*
  l'app spegne l'allineamento solo in quel caso e lo riaccende al primo ripristino in cui non serve più.
  Senza l'opzione l'allineamento resta attivo e le icone si spostano di poco.

## Come funziona

Ogni icona è salvata rispetto all'angolo del suo monitor, e i monitor sono riconosciuti dal
loro identificativo hardware, non dal numero DISPLAY né dal fatto di essere il principale.
Le icone si leggono e si spostano con l'API ufficiale di Windows (`IFolderView`), senza scrivere
nella memoria di Explorer.

L'app è in Python e non in un `.exe` perché Smart App Control blocca gli eseguibili senza una
firma attendibile; Python invece è già firmato. Per lo stesso motivo usa solo la libreria standard.

| Percorso | Contenuto |
|---|---|
| `ordina/planner.py` | Calcolo delle posizioni, senza accesso a Windows |
| `ordina/desktop_view.py` | Lettura e spostamento delle icone |
| `ordina/monitors.py` | Elenco dei monitor |
| `ordina/engine.py` | Salvataggio e ripristino |
| `ordina/app.py` | Finestra e ripristino automatico |
| `ordina/tray.py` | Icona vicino all'orologio e scorciatoia |
| `%APPDATA%\OrdinaDesktop\` | Dati (`dati.json`) ed errori (`errori.log`) |

Per i test, che non toccano il desktop:

```bash
python -m unittest tests.test_planner
```

L'icona `assets/app.ico` si rigenera con `python tools/make_icon.py`.

---

Sviluppato da [Luca Sonno](https://lucasonno.com) con l'assistenza di Claude Code. Licenza [MIT](LICENSE).
