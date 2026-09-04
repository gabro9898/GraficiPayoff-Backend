# ============================================================
# Percorso: tests/test_tastytrade_errori.py
#
# Cosa esce da _api_request quando TastyTrade risponde male.
#
# Il bug: il ramo `status_code >= 400` sollevava una Exception nuda. FastAPI
# la faceva gestire al ServerErrorMiddleware, che sta FUORI dal CORS
# middleware: il browser riceveva un 500 in testo semplice senza header CORS
# e lo scartava come errore di rete, con `err.response` indefinita. Il motivo
# del rifiuto (buying power, simbolo, prezzo) non arrivava mai all'utente.
#
# Le due cose che questi test sorvegliano:
#   1. l'errore e' una HTTPException con dentro il messaggio vero di TT;
#   2. gli status 401 e 403 NON vengono propagati: diventano 502.
#      Non e' un dettaglio estetico. Un 401 propagato fa scattare
#      l'interceptor del frontend, che rinnova il JWT e RIESEGUE la
#      richiesta: su un ordine significa inviarlo due volte.
#
# Il backend non ha pytest installato. Si esegue direttamente:
#     venv/Scripts/python.exe tests/test_tastytrade_errori.py
# ed e' gia' nella forma che pytest raccoglie, se un giorno verra' aggiunto.
# ============================================================

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.services import tastytrade_service as modulo
from app.services.tastytrade_service import TastyTradeService
from app.utils.exceptions import TastyTradeApiException


# --------------------------- impalcatura ---------------------------

class RispostaFinta:
    """Il minimo di httpx.Response che _api_request tocca."""

    def __init__(self, status_code: int, testo: str = "", json_body=None):
        self.status_code = status_code
        self.text = testo
        self._json = json_body

    def json(self):
        if self._json is None:
            raise ValueError("corpo non JSON")
        return self._json


class ClientFinto:
    """Sostituisce httpx.AsyncClient: restituisce le risposte in sequenza."""

    def __init__(self, risposte):
        self._risposte = list(risposte)
        self.chiamate = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def request(self, method, url, **kwargs):
        self.chiamate.append((method, url))
        return self._risposte.pop(0)


def servizio(token_refresh="tok-nuovo"):
    """Un TastyTradeService senza database: _api_request non ne ha bisogno."""
    s = TastyTradeService.__new__(TastyTradeService)
    s.settings = get_settings()

    async def _token(_user_id):
        return "tok"

    async def _refresh(_user_id):
        return token_refresh

    s.get_valid_token = _token
    s.refresh_access_token = _refresh
    return s


def chiama(risposte, token_refresh="tok-nuovo"):
    """Esegue _api_request con le risposte date, restituendo esito o eccezione."""
    finto = ClientFinto(risposte)
    originale = modulo.httpx.AsyncClient
    modulo.httpx.AsyncClient = lambda **kwargs: finto
    try:
        return asyncio.run(
            servizio(token_refresh)._api_request("u1", "POST", "/accounts/X/orders")
        )
    finally:
        modulo.httpx.AsyncClient = originale


CORPO_TT = {
    "error": {
        "code": "preflight_check_failure",
        "message": "Order execution rejected",
        "errors": [{"message": "Insufficient buying power"}],
    }
}


# --------------------------- i test ---------------------------

def test_errore_400_diventa_httpexception_col_motivo_vero():
    try:
        chiama([RispostaFinta(400, "{}", CORPO_TT)])
    except HTTPException as e:
        assert isinstance(e, TastyTradeApiException)
        assert e.status_code == 400, e.status_code
        assert "Insufficient buying power" in e.detail, e.detail
        assert "Order execution rejected" in e.detail, e.detail
    else:
        raise AssertionError("doveva sollevare")


def test_401_ripetuto_non_viene_propagato_ma_diventa_502():
    # Il primo 401 fa scattare il refresh; il secondo cade nel ramo >= 400.
    # Propagarlo farebbe rieseguire l'ordine dall'interceptor del frontend.
    try:
        chiama([RispostaFinta(401, "no"), RispostaFinta(401, "no")])
    except HTTPException as e:
        assert e.status_code == 502, f"401 propagato: {e.status_code}"
        assert e.upstream_status == 401
        assert "401" in e.detail
    else:
        raise AssertionError("doveva sollevare")


def test_403_non_viene_propagato_ma_diventa_502():
    # Un 403 propagato verrebbe scambiato per "grant TastyTrade revocato"
    # e farebbe riaprire la popup OAuth senza motivo.
    try:
        chiama([RispostaFinta(403, "vietato")])
    except HTTPException as e:
        assert e.status_code == 502, f"403 propagato: {e.status_code}"
        assert e.upstream_status == 403
    else:
        raise AssertionError("doveva sollevare")


def test_429_e_5xx_diventano_502():
    for status_tt in (429, 500, 503):
        try:
            chiama([RispostaFinta(status_tt, "a monte e rotto")])
        except HTTPException as e:
            assert e.status_code == 502, f"{status_tt} -> {e.status_code}"
            assert e.upstream_status == status_tt
        else:
            raise AssertionError("doveva sollevare")


def test_404_e_422_passano_com_erano():
    for status_tt in (404, 422):
        try:
            chiama([RispostaFinta(status_tt, "", {"error": {"message": "non trovato"}})])
        except HTTPException as e:
            assert e.status_code == status_tt, f"{status_tt} -> {e.status_code}"
            assert "non trovato" in e.detail
        else:
            raise AssertionError("doveva sollevare")


def test_corpo_non_json_ripiega_sul_testo_grezzo():
    try:
        chiama([RispostaFinta(400, "<html>Bad Request</html>")])
    except HTTPException as e:
        assert "Bad Request" in e.detail, e.detail
    else:
        raise AssertionError("doveva sollevare")


def test_corpo_vuoto_non_lascia_un_messaggio_muto():
    try:
        chiama([RispostaFinta(400, "")])
    except HTTPException as e:
        assert "nessun dettaglio" in e.detail, e.detail
    else:
        raise AssertionError("doveva sollevare")


def test_il_messaggio_e_troncato():
    try:
        chiama([RispostaFinta(400, "x" * 5000)])
    except HTTPException as e:
        assert len(e.detail) <= 500, len(e.detail)
    else:
        raise AssertionError("doveva sollevare")


def test_risposta_buona_torna_il_json_senza_eccezioni():
    esito = chiama([RispostaFinta(200, "", {"data": {"id": "ORD-1"}})])
    assert esito == {"data": {"id": "ORD-1"}}


def test_401_con_refresh_riuscito_ritenta_e_va_a_buon_fine():
    # Non regressione: il retry dopo il refresh deve continuare a funzionare.
    esito = chiama([RispostaFinta(401, "scaduto"), RispostaFinta(200, "", {"ok": True})])
    assert esito == {"ok": True}


def test_refresh_fallito_resta_un_403_forbidden():
    # Non regressione: quando il refresh non riesce, il comportamento storico
    # (ForbiddenException 403 -> il frontend riapre l'OAuth) non cambia.
    try:
        chiama([RispostaFinta(401, "scaduto")], token_refresh=None)
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
        assert not isinstance(e, TastyTradeApiException)
    else:
        raise AssertionError("doveva sollevare")


if __name__ == "__main__":
    prove = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    falliti = 0
    for nome, prova in prove:
        try:
            prova()
            print(f"  ok   {nome}")
        except Exception as errore:
            falliti += 1
            print(f"  FAIL {nome}: {errore}")
    print(f"\n{len(prove) - falliti}/{len(prove)} passati")
    sys.exit(1 if falliti else 0)
