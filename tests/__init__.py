# ============================================================
# ★ BACKEND — NUOVA CARTELLA
# Percorso: tests/__init__.py
# Il progetto non aveva una cartella di test: questa e la prima.
#
# Il file e VUOTO di proposito, ma non e superfluo: senza, `python -m unittest
# discover -s tests -t .` si ferma con «Start directory is not importable»
# (dalla 3.11 unittest non scopre piu i namespace package). Con questo file la
# cartella e un pacchetto e la scoperta funziona.
#
# ESECUZIONE (dalla radice del backend):
#   venv\Scripts\python.exe -m unittest discover -s tests -t . -v
#   venv\Scripts\python.exe tests\test_ai_relay.py -v
#
# `pytest` NON e installato nel venv e le regole di questo lavoro vietano di
# aggiungere dipendenze: le prove sono scritte con `unittest` della libreria
# standard. Restano comunque raccoglibili da pytest, che raccoglie anche le
# `unittest.TestCase`, il giorno in cui venisse installato.
# ============================================================
