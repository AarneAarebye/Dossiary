# Migration von Mariner Paperless

*Teil von [Dossiary](README.de.md) — alles andere finden Sie im Haupt-README.
[Read this in English](MIGRATION.md).*

Wenn Sie von der eingestellten App Mariner Paperless kommen, konvertieren
Sie zunächst Ihre Bibliothek mit einem der Werkzeuge aus dem
Schwesterprojekt
[LibraryLifeboat](https://github.com/AarneAarebye/LibraryLifeboat)
— eine einmalige Konvertierung, die eine `.paperless`-Bibliothek liest
und daraus einen `library.sqlite` + `files/`-Ordner in dem Schema
erzeugt, das Dossiary erwartet. Zeigen Sie Dossiary anschließend auf
diesen Ausgabeordner.

- **[`migrate_to_new_library.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_to_new_librarypy-migration-to-dossiary)**
  — das eigentliche Skript, aus dem Terminal ausgeführt. Das ist die
  einzige verbindliche Quelle für die eigentliche Migrationslogik; beide
  grafischen Oberflächen unten sind nur dünne Hüllen um genau dieses
  Skript, keine eigenständigen Implementierungen.
- **[`migrate_gui.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_guipy-desktop-app)**
  — eine kleine native Desktop-App (tkinter), falls Sie lieber nicht das
  Terminal nutzen möchten: den Ordner wählen, in dem Ihre Bibliotheken
  liegen, auswählen, welche migriert werden sollen, einen Ausgabeordner
  wählen, auf Migrate klicken. (Diese App hat außerdem einen Export-Modus
  für einen separaten, verlustfreien Kopier-Anwendungsfall — siehe deren
  eigenes Repository — aber für Dossiary ist Migrate das Richtige.)
- **[`migrate_web.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_webpy-browser-based-alternative)**
  — dasselbe, einschließlich derselben Migrate-/Export-Modus-Wahl, als
  lokale Webseite statt als natives Fenster, für alle, die lieber einen
  Browser-Tab benutzen.

Wenn Sie mehrere Bibliotheken zu migrieren haben, ist eine der beiden
grafischen Oberflächen vermutlich bequemer, als das Skript einmal pro
Bibliothek von Hand aufzurufen.
