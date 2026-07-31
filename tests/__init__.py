# ============================================================
# ★ BACKEND — CARTELLA DI TEST
# Percorso: tests/__init__.py
#
# ATTENZIONE: al momento la cartella e VUOTA di prove. L'unico file che
# conteneva (test_ai_relay.py) e stato rimosso col relay IA: l'app non chiama
# piu i fornitori di modelli, e Claude a chiamare noi tramite il connettore MCP
# del frontend. Il pacchetto resta perche la scoperta dei test funzioni il
# giorno in cui se ne aggiungano di nuovi.
#
# Il file e VUOTO di proposito, ma non e superfluo: senza, `python -m unittest
# discover -s tests -t .` si ferma con «Start directory is not importable»
# (dalla 3.11 unittest non scopre piu i namespace package). Con questo file la
# cartella e un pacchetto e la scoperta funziona.
#
# ESECUZIONE (dalla radice del backend):
#   venv\Scripts\python.exe -m unittest discover -s tests -t . -v
#
# `pytest` NON e installato nel venv e le regole di questo lavoro vietano di
# aggiungere dipendenze: le prove sono scritte con `unittest` della libreria
# standard. Restano comunque raccoglibili da pytest, che raccoglie anche le
# `unittest.TestCase`, il giorno in cui venisse installato.
# ============================================================
