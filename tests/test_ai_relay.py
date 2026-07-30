# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: tests/test_ai_relay.py
# Prove del relay IA (app/api/routes/ai.py + app/services/ai_relay.py).
#
# ─────────────────── PERCHE `unittest` E NON `pytest` ───────────────────
# Il progetto non aveva alcuna cartella di test e `pytest` NON e installato
# nel venv (`venv/Scripts/python.exe -m pip list` non lo elenca). La regola di
# questo lavoro vieta di aggiungere dipendenze, quindi le prove sono scritte
# con `unittest`, che sta nella libreria standard ed e gia disponibile.
# Nota: pytest raccoglie anche le `unittest.TestCase`, quindi il giorno in cui
# venisse installato questo file funzionerebbe senza modifiche.
#
# COME SI ESEGUE (dalla radice del backend):
#   venv\Scripts\python.exe tests\test_ai_relay.py -v
#   venv\Scripts\python.exe -m unittest discover -s tests -t . -v
#
# ─────────────────── NESSUNA CHIAMATA DI RETE VERA ───────────────────
# Il fornitore e FINTO: si sostituisce `httpx.AsyncClient` dentro
# app/services/ai_relay.py con una fabbrica che inietta un `httpx.MockTransport`.
# Nessun pacchetto lascia questa macchina, nessuna chiave vera viene usata.
#
# ─────────────────── IL DATABASE E IN MEMORIA ───────────────────
# `get_db` viene sostituita con una sessione SQLite in memoria, creata da capo
# a ogni prova. Il database vero (PostgreSQL) non viene mai toccato: gli eventi
# di startup di main.py NON vengono eseguiti, perche il TestClient li avvia solo
# dentro un `with client:` che qui non si usa mai.
#
# ─────────────────── LA MISURA DELLO STREAMING ───────────────────
# Il TestClient di Starlette NON PUO provare la consegna incrementale: il suo
# trasporto scrive tutto in un `io.BytesIO` e restituisce la risposta solo
# quando e completa (starlette/testclient.py:296,342-345,367). Provare il «non
# bufferizza» con il TestClient darebbe sempre un pezzo solo, sia con un relay
# corretto sia con uno rotto: sarebbe una prova che non prova niente.
# Percio lo stream si misura un gradino piu sotto, chiamando l'app ASGI a mano
# e prendendo l'ORA DI ARRIVO di ogni messaggio `http.response.body`.
# ============================================================

import asyncio
import io
import json
import os
import re
import sys
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

# La radice del backend deve stare in sys.path comunque venga lanciato il file
# (`python tests\test_ai_relay.py`, `-m unittest`, o pytest da un'altra cartella).
_RADICE = Path(__file__).resolve().parents[1]
if str(_RADICE) not in sys.path:
    sys.path.insert(0, str(_RADICE))
# Il .env con la configurazione vera sta nella radice del backend: senza questo
# `Settings()` non troverebbe SECRET_KEY e l'import di app.main fallirebbe.
os.chdir(_RADICE)

import httpx  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.main as main_module  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.ai_credential import AiCredentialRepository  # noqa: E402
from app.services import ai_relay  # noqa: E402
from app.utils.rate_limit import limiter  # noqa: E402
from app.utils.security import create_access_token  # noqa: E402

APP = main_module.app

# Chiavi finte, di forma plausibile ma senza alcun valore: servono solo a
# verificare che NON compaiano dove non devono.
CHIAVE_ALICE = "sk-ant-api03-alice-000000001111"
CHIAVE_BRUNO = "sk-ant-api03-bruno-222222223333"


# ─────────────────────────── Fornitore finto ───────────────────────────


class _FlussoFinto(httpx.AsyncByteStream):
    """Corpo di risposta consegnato a pezzi, con una pausa fra l'uno e l'altro.

    La pausa non e un vezzo: senza, tutti i pezzi sarebbero gia pronti e un
    relay che bufferizza risulterebbe indistinguibile da uno che non lo fa.
    """

    def __init__(self, pezzi, pausa: float):
        self._pezzi = list(pezzi)
        self._pausa = pausa

    async def __aiter__(self):
        for pezzo in self._pezzi:
            await asyncio.sleep(self._pausa)
            yield pezzo


class FornitoreFinto:
    """Sostituto del fornitore di modelli. Registra cosa ha ricevuto."""

    def __init__(self, *, status: int = 200, pezzi=None, corpo: bytes = b"",
                 content_type: str = "text/event-stream", pausa: float = 0.0):
        self.status = status
        self.pezzi = list(pezzi) if pezzi is not None else None
        self.corpo = corpo
        self.content_type = content_type
        self.pausa = pausa
        self.richieste: list[httpx.Request] = []

    def _rispondi(self, request: httpx.Request) -> httpx.Response:
        self.richieste.append(request)
        # ★ SEMPRE uno stream, anche per la risposta JSON in un pezzo solo:
        #   con `content=` httpx segnerebbe la risposta come gia letta e il
        #   relay, che apre la connessione con `stream=True`, otterrebbe
        #   `StreamConsumed`. Un fornitore vero risponde comunque a pezzi.
        pezzi = self.pezzi if self.pezzi is not None else ([self.corpo] if self.corpo else [])
        return httpx.Response(
            self.status,
            headers={"content-type": self.content_type},
            stream=_FlussoFinto(pezzi, self.pausa),
        )

    @property
    def ultima_richiesta(self) -> httpx.Request:
        assert self.richieste, "Il fornitore finto non ha ricevuto nessuna richiesta."
        return self.richieste[-1]

    def intestazione(self, nome: str):
        return self.ultima_richiesta.headers.get(nome)

    def corpo_ricevuto(self) -> dict:
        return json.loads(self.ultima_richiesta.content.decode())


_ASYNC_CLIENT_VERO = httpx.AsyncClient


@contextmanager
def fornitore(finto: FornitoreFinto):
    """Sostituisce il fornitore vero per la durata del blocco.

    Si sostituisce la CLASSE `httpx.AsyncClient` vista da ai_relay: il relay la
    costruisce da se (`ai_relay.py:553`), quindi non c'e un punto d'iniezione
    piu in alto. La classe vera resta catturata in `_ASYNC_CLIENT_VERO`,
    altrimenti la fabbrica richiamerebbe se stessa all'infinito.
    """

    def fabbrica(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(finto._rispondi)
        return _ASYNC_CLIENT_VERO(*args, **kwargs)

    with mock.patch.object(ai_relay.httpx, "AsyncClient", fabbrica):
        yield finto


# ─────────────────────────── Base comune ───────────────────────────


class BaseRelay(unittest.TestCase):
    """Database in memoria, due utenti veri, chiave di cifratura usa-e-getta."""

    def setUp(self):
        self.motore = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.motore)
        self.Sessione = sessionmaker(bind=self.motore, autoflush=False, autocommit=False)

        def _get_db_di_prova():
            db = self.Sessione()
            try:
                yield db
            finally:
                db.close()

        APP.dependency_overrides[get_db] = _get_db_di_prova

        # Configurazione del relay: si tocca l'oggetto Settings gia in memoria
        # (e `lru_cache`, quindi e lo stesso che vede il codice di produzione).
        # Il .env NON viene mai letto in scrittura ne modificato.
        self.impostazioni = get_settings()
        self._salvate = {
            "AI_ENCRYPTION_KEY": self.impostazioni.AI_ENCRYPTION_KEY,
            "AI_RELAY_ENABLED": self.impostazioni.AI_RELAY_ENABLED,
            "AI_RELAY_RATE_LIMIT": self.impostazioni.AI_RELAY_RATE_LIMIT,
        }
        self.impostazioni.AI_ENCRYPTION_KEY = Fernet.generate_key().decode()
        self.impostazioni.AI_RELAY_ENABLED = True
        # Tetto alto: le prove che non riguardano il tetto non devono inciamparci.
        self.impostazioni.AI_RELAY_RATE_LIMIT = "1000/minute"
        self._azzera_limitatore()

        self.alice = self._crea_utente("alice@esempio.it")
        self.bruno = self._crea_utente("bruno@esempio.it")
        self.token_alice = create_access_token(self.alice)
        self.token_bruno = create_access_token(self.bruno)

        self.client = TestClient(APP)

    def tearDown(self):
        APP.dependency_overrides.pop(get_db, None)
        for nome, valore in self._salvate.items():
            setattr(self.impostazioni, nome, valore)
        self._azzera_limitatore()
        self.motore.dispose()

    # -- attrezzi ---------------------------------------------------------

    @staticmethod
    def _azzera_limitatore():
        """Svuota la memoria del limitatore fra una prova e l'altra.

        Senza, il tetto per IP di `/ai/health` (60/minuto) e quello per utente
        del relay verrebbero ereditati dalla prova precedente e l'esito
        dipenderebbe dall'ORDINE di esecuzione.
        """
        try:
            limiter.reset()
        except Exception:
            pass
        # Le cache interne di ai_relay sono legate alla stringa del tetto: se
        # una prova la cambia e la ripristina, vanno invalidate a mano.
        ai_relay._rate_item = None
        ai_relay._rate_item_source = None

    def _crea_utente(self, email: str) -> str:
        db = self.Sessione()
        try:
            utente = User(
                id=str(uuid.uuid4()),
                email=email,
                hashed_password="non-usata-in-queste-prove",
                first_name="Nome",
                last_name="Cognome",
            )
            db.add(utente)
            db.commit()
            return utente.id
        finally:
            db.close()

    def _registra_chiave(self, user_id: str, chiave: str, provider: str = "anthropic"):
        db = self.Sessione()
        try:
            AiCredentialRepository(db).upsert(
                user_id=user_id,
                provider_id=provider,
                api_key_enc=ai_relay.encrypt_api_key(chiave),
                key_hint=ai_relay.key_hint(chiave),
            )
        finally:
            db.close()

    def _intestazioni(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _busta(self, **extra) -> dict:
        busta = {
            "provider": "anthropic",
            "path": "/v1/messages",
            "stream": True,
            "body": {"model": "claude-x", "messages": []},
        }
        busta.update(extra)
        return busta

    def _chat(self, token: str, **extra):
        return self.client.post(
            "/api/v1/ai/chat", json=self._busta(**extra), headers=self._intestazioni(token)
        )


# ─────────────────── 1. Il relay esiste e si distingue dal suo contrario ───────────────────


class TestSalute(BaseRelay):
    def test_le_rotte_sono_montate_dove_il_frontend_le_cerca(self):
        """`${VITE_API_URL}/ai/chat` con VITE_API_URL = .../api/v1."""
        percorsi = set(APP.openapi()["paths"])
        for atteso in (
            "/api/v1/ai/chat",
            "/api/v1/ai/count-tokens",
            "/api/v1/ai/health",
            "/api/v1/ai/credential",
        ):
            self.assertIn(atteso, percorsi, f"Rotta non montata: {atteso}")

    def test_health_risponde_senza_autenticazione(self):
        """Deve rispondere anche a chi non ha (ancora) un token dell'app.

        Se rispondesse 401, il frontend non potrebbe distinguere «relay assente»
        da «relay presente ma non configurato» proprio quando serve.
        """
        risposta = self.client.get("/api/v1/ai/health")
        self.assertEqual(risposta.status_code, 200)
        dati = risposta.json()
        self.assertTrue(dati["relay"])
        self.assertTrue(dati["enabled"])
        self.assertTrue(dati["encryption_configured"])
        self.assertTrue(dati["providers"], "L'elenco dei fornitori non deve essere vuoto.")
        self.assertIn("anthropic", [p["id"] for p in dati["providers"]])
        self.assertTrue(dati["message"].strip())

    def test_health_distingue_la_cifratura_non_configurata(self):
        """AI_ENCRYPTION_KEY mancante: il relay c'e ma non puo custodire chiavi."""
        self.impostazioni.AI_ENCRYPTION_KEY = ""
        dati = self.client.get("/api/v1/ai/health").json()
        self.assertTrue(dati["relay"])
        self.assertTrue(dati["enabled"])
        self.assertFalse(dati["encryption_configured"])
        self.assertIn("AI_ENCRYPTION_KEY", dati["message"])

    def test_health_distingue_il_relay_spento(self):
        self.impostazioni.AI_RELAY_ENABLED = False
        dati = self.client.get("/api/v1/ai/health").json()
        self.assertTrue(dati["relay"], "Il relay c'e: e spento, non assente.")
        self.assertFalse(dati["enabled"])
        self.assertIn("AI_RELAY_ENABLED", dati["message"])

        self._registra_chiave(self.alice, CHIAVE_ALICE)
        risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 503)
        self.assertIn("spento", risposta.json()["detail"])

    def test_su_un_backend_senza_relay_la_stessa_rotta_e_404(self):
        """Il controllo dell'altro caso: e cosi che si vede un relay ASSENTE.

        Il frontend legge un 404 su questo percorso come «il relay non esiste su
        questo backend» (AI_PROXY_MISSING_MESSAGE). Questa prova fissa la
        differenza: con il router montato e 200, senza e 404 — e nessuna delle
        risposte del relay installato usa mai il 404 (vedi TestCredenziali).
        """
        senza_relay = FastAPI()
        with TestClient(senza_relay) as client_nudo:
            self.assertEqual(client_nudo.get("/api/v1/ai/health").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/ai/health").status_code, 200)

    def test_health_non_espone_nessun_segreto(self):
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        testo = self.client.get("/api/v1/ai/health").text
        self.assertNotIn(CHIAVE_ALICE, testo)
        self.assertNotIn(self.impostazioni.AI_ENCRYPTION_KEY, testo)


# ─────────────────── 2. Credenziali: mancante, mia, di un altro ───────────────────


class TestCredenziali(BaseRelay):
    def test_chat_senza_credenziale_e_412_e_non_404(self):
        """L'errore deve essere DISTINTO da «relay assente».

        412 e non 404: il frontend legge il 404 sul percorso del proxy come
        «il relay non esiste» e manderebbe l'utente a cercare un problema di
        deploy invece della sua chiave mancante. Non e nemmeno 403, che il
        frontend spiega come «chiave rifiutata dal fornitore» — qui una chiave
        non e mai stata registrata.
        """
        risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 412)
        self.assertNotEqual(risposta.status_code, 404, "Un 404 verrebbe letto come «relay assente».")
        dettaglio = risposta.json()["detail"]
        self.assertIn("non registrata", dettaglio)
        self.assertIn("impostazioni", dettaglio)
        # E deve restare distinguibile dal 404 vero di una rotta inesistente.
        self.assertEqual(self.client.get("/api/v1/ai/inesistente").status_code, 404)

    def test_chiave_non_piu_decifrabile_lo_dice_con_altre_parole(self):
        """Chiave di cifratura del server sostituita: la cura e la stessa, la causa no."""
        db = self.Sessione()
        try:
            AiCredentialRepository(db).upsert(
                user_id=self.alice,
                provider_id="anthropic",
                api_key_enc="questo-non-e-un-ciphertext-fernet",
                key_hint="0000",
            )
        finally:
            db.close()
        risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 412)
        self.assertIn("non e piu decifrabile", risposta.json()["detail"])

    def test_la_chiave_non_torna_mai_indietro(self):
        """Ne dalla PUT, ne dalla GET, ne da un errore. Mai."""
        risposta_put = self.client.put(
            "/api/v1/ai/credential",
            json={"provider": "anthropic", "api_key": CHIAVE_ALICE},
            headers=self._intestazioni(self.token_alice),
        )
        self.assertEqual(risposta_put.status_code, 200)
        self.assertNotIn(CHIAVE_ALICE, risposta_put.text)

        risposta_get = self.client.get(
            "/api/v1/ai/credential", headers=self._intestazioni(self.token_alice)
        )
        self.assertEqual(risposta_get.status_code, 200)
        self.assertNotIn(CHIAVE_ALICE, risposta_get.text)

        voci = risposta_get.json()["items"]
        self.assertEqual(len(voci), 1)
        voce = voci[0]
        self.assertEqual(voce["provider"], "anthropic")
        self.assertTrue(voce["configured"])
        self.assertEqual(voce["key_hint"], CHIAVE_ALICE[-4:])
        # L'indizio e solo un indizio: 4 cifre, non un pezzo utile della chiave.
        self.assertEqual(len(voce["key_hint"]), 4)
        self.assertNotIn("api_key", voce)
        self.assertNotIn("api_key_enc", voce)
        self.assertNotIn(CHIAVE_ALICE[:12], risposta_get.text)

    def test_la_chiave_in_chiaro_non_finisce_nel_database(self):
        self.client.put(
            "/api/v1/ai/credential",
            json={"provider": "anthropic", "api_key": CHIAVE_ALICE},
            headers=self._intestazioni(self.token_alice),
        )
        db = self.Sessione()
        try:
            riga = AiCredentialRepository(db).find_by_user_and_provider(self.alice, "anthropic")
            self.assertIsNotNone(riga)
            self.assertNotIn(CHIAVE_ALICE, riga.api_key_enc)
            self.assertEqual(ai_relay.decrypt_api_key(riga.api_key_enc), CHIAVE_ALICE)
        finally:
            db.close()

    def test_senza_chiave_di_cifratura_la_registrazione_e_503(self):
        """Mai un salvataggio in chiaro, mai una cifratura con chiave effimera."""
        self.impostazioni.AI_ENCRYPTION_KEY = ""
        risposta = self.client.put(
            "/api/v1/ai/credential",
            json={"provider": "anthropic", "api_key": CHIAVE_ALICE},
            headers=self._intestazioni(self.token_alice),
        )
        self.assertEqual(risposta.status_code, 503)
        self.assertIn("AI_ENCRYPTION_KEY", risposta.json()["detail"])
        self.assertNotIn(CHIAVE_ALICE, risposta.text)

    def test_revoca_idempotente_e_riporta_a_non_configurato(self):
        """E la cura vera per «l'IA non si collega e non c'e modo di azzerarla»."""
        self._registra_chiave(self.alice, CHIAVE_ALICE)

        prima = self.client.delete(
            "/api/v1/ai/credential?provider=anthropic",
            headers=self._intestazioni(self.token_alice),
        )
        self.assertEqual(prima.status_code, 200)
        self.assertFalse(prima.json()["configured"])

        # Seconda revoca: 200 e non 404. Un 404 qui verrebbe letto dal frontend
        # come «relay assente», e per un azzeramento «non c'era niente» e
        # comunque il risultato voluto.
        seconda = self.client.delete(
            "/api/v1/ai/credential?provider=anthropic",
            headers=self._intestazioni(self.token_alice),
        )
        self.assertEqual(seconda.status_code, 200)
        self.assertFalse(seconda.json()["configured"])

        elenco = self.client.get(
            "/api/v1/ai/credential", headers=self._intestazioni(self.token_alice)
        ).json()
        self.assertEqual(elenco["items"], [])

    def test_le_rotte_delle_credenziali_vogliono_il_token(self):
        for metodo, url, corpo in (
            ("get", "/api/v1/ai/credential", None),
            ("put", "/api/v1/ai/credential", {"provider": "anthropic", "api_key": CHIAVE_ALICE}),
            ("delete", "/api/v1/ai/credential?provider=anthropic", None),
        ):
            with self.subTest(metodo=metodo):
                chiamata = getattr(self.client, metodo)
                risposta = chiamata(url, json=corpo) if corpo else chiamata(url)
                self.assertIn(risposta.status_code, (401, 403))


class TestIsolamentoFraUtenti(BaseRelay):
    def test_un_utente_non_vede_la_credenziale_di_un_altro(self):
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        elenco_bruno = self.client.get(
            "/api/v1/ai/credential", headers=self._intestazioni(self.token_bruno)
        )
        self.assertEqual(elenco_bruno.status_code, 200)
        self.assertEqual(elenco_bruno.json()["items"], [])
        self.assertNotIn(CHIAVE_ALICE[-4:], elenco_bruno.text)

    def test_un_utente_non_puo_usare_la_credenziale_di_un_altro(self):
        """Non esiste una chiave di riserva: senza la PROPRIA non si parte."""
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            risposta_bruno = self._chat(self.token_bruno)
        self.assertEqual(risposta_bruno.status_code, 412)
        self.assertEqual(
            finto.richieste, [], "Nessuna richiesta doveva partire verso il fornitore."
        )

    def test_ognuno_inoltra_con_la_propria_chiave(self):
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        self._registra_chiave(self.bruno, CHIAVE_BRUNO)
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            self.assertEqual(self._chat(self.token_alice).status_code, 200)
            self.assertEqual(finto.intestazione("x-api-key"), CHIAVE_ALICE)
            self.assertEqual(self._chat(self.token_bruno).status_code, 200)
            self.assertEqual(finto.intestazione("x-api-key"), CHIAVE_BRUNO)

    def test_la_revoca_di_uno_non_tocca_l_altro(self):
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        self._registra_chiave(self.bruno, CHIAVE_BRUNO)
        self.client.delete(
            "/api/v1/ai/credential?provider=anthropic",
            headers=self._intestazioni(self.token_bruno),
        )
        elenco_alice = self.client.get(
            "/api/v1/ai/credential", headers=self._intestazioni(self.token_alice)
        ).json()
        self.assertEqual(len(elenco_alice["items"]), 1)
        self.assertTrue(elenco_alice["items"][0]["configured"])


# ─────────────────── 3. Inoltro: cosa esce, cosa entra ───────────────────


class TestInoltro(BaseRelay):
    def setUp(self):
        super().setUp()
        self._registra_chiave(self.alice, CHIAVE_ALICE)

    def test_verso_il_fornitore_esce_solo_il_minimo(self):
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 200)

        richiesta = finto.ultima_richiesta
        self.assertEqual(str(richiesta.url), "https://api.anthropic.com/v1/messages")
        self.assertEqual(richiesta.headers.get("x-api-key"), CHIAVE_ALICE)
        self.assertEqual(richiesta.headers.get("anthropic-version"), "2023-06-01")
        # Senza `identity` httpx negozierebbe gzip e i byte andrebbero
        # decompressi prima di poter essere ripassati: fine della consegna
        # incrementale.
        self.assertEqual(richiesta.headers.get("accept-encoding"), "identity")
        # ★ Il JWT dell'app NON deve uscire verso un terzo.
        self.assertIsNone(richiesta.headers.get("authorization"))
        self.assertNotIn(self.token_alice, str(dict(richiesta.headers)))
        # Il corpo nativo del fornitore attraversa INALTERATO.
        self.assertEqual(
            finto.corpo_ricevuto(), {"model": "claude-x", "messages": []}
        )

    def test_stream_false_ritorna_il_json_del_fornitore(self):
        finto = FornitoreFinto(
            corpo=b'{"id":"msg_1","content":[{"type":"text","text":"ciao"}]}',
            content_type="application/json",
        )
        with fornitore(finto):
            risposta = self._chat(self.token_alice, stream=False)
        self.assertEqual(risposta.status_code, 200)
        self.assertEqual(risposta.json()["id"], "msg_1")
        self.assertEqual(finto.intestazione("accept"), "application/json")

    def test_count_tokens_usa_lo_stesso_inoltro(self):
        finto = FornitoreFinto(corpo=b'{"input_tokens":1234}', content_type="application/json")
        with fornitore(finto):
            risposta = self.client.post(
                "/api/v1/ai/count-tokens",
                json=self._busta(path="/v1/messages/count_tokens", stream=False),
                headers=self._intestazioni(self.token_alice),
            )
        self.assertEqual(risposta.status_code, 200)
        self.assertEqual(risposta.json()["input_tokens"], 1234)
        self.assertEqual(
            str(finto.ultima_richiesta.url),
            "https://api.anthropic.com/v1/messages/count_tokens",
        )

    def test_percorso_fuori_elenco_rifiutato_prima_di_uscire(self):
        finto = FornitoreFinto(pezzi=[b"x"])
        with fornitore(finto):
            risposta = self._chat(self.token_alice, path="/v1/models")
        self.assertEqual(risposta.status_code, 400)
        self.assertIn("Percorso non ammesso", risposta.json()["detail"])
        self.assertEqual(finto.richieste, [])

    def test_percorsi_ostili_respinti_dalla_validazione(self):
        for percorso in ("/v1/../../etc/passwd", "https://malevolo.example/v1/messages",
                         "//malevolo.example/v1/messages", "/v1/messages@malevolo.example"):
            with self.subTest(percorso=percorso):
                risposta = self._chat(self.token_alice, path=percorso)
                self.assertEqual(risposta.status_code, 422)

    def test_fornitori_locali_e_sconosciuti_hanno_messaggi_diversi(self):
        locale = self._chat(self.token_alice, provider="ollama")
        self.assertEqual(locale.status_code, 400)
        self.assertIn("gira sul tuo PC", locale.json()["detail"])

        ignoto = self._chat(self.token_alice, provider="fornitore-che-non-esiste")
        self.assertEqual(ignoto.status_code, 400)
        self.assertIn("non riconosciuto", ignoto.json()["detail"])
        # L'elenco degli ammessi dev'esserci: e cio che rende l'errore azionabile.
        self.assertIn("anthropic", ignoto.json()["detail"])


class TestErroriDelFornitore(BaseRelay):
    """La traduzione dei codici e VOLUTA: due messaggi del frontend sarebbero
    FALSI se il codice del fornitore passasse cosi com'e."""

    def setUp(self):
        super().setUp()
        self._registra_chiave(self.alice, CHIAVE_ALICE)

    def _errore(self, status: int, corpo: bytes = b'{"error":"boom"}'):
        finto = FornitoreFinto(status=status, corpo=corpo, content_type="application/json")
        with fornitore(finto):
            return self._chat(self.token_alice)

    def test_404_del_fornitore_diventa_400(self):
        """Se restasse 404, il frontend direbbe «il relay non esiste»: falso."""
        risposta = self._errore(404)
        self.assertEqual(risposta.status_code, 400)
        self.assertNotEqual(risposta.status_code, 404)
        self.assertIn("non conosce il percorso", risposta.json()["detail"])

    def test_401_del_fornitore_diventa_403(self):
        """Se restasse 401, il frontend direbbe «esci e rientra nell'app»: falso."""
        risposta = self._errore(401)
        self.assertEqual(risposta.status_code, 403)
        self.assertNotEqual(risposta.status_code, 401)
        self.assertIn("rifiutato la chiave", risposta.json()["detail"])

    def test_403_del_fornitore_resta_403(self):
        self.assertEqual(self._errore(403).status_code, 403)

    def test_429_e_5xx_passano_invariati(self):
        for codice in (429, 500, 502, 529):
            with self.subTest(codice=codice):
                self.assertEqual(self._errore(codice).status_code, codice)

    def test_il_dettaglio_del_fornitore_arriva_ma_senza_la_chiave(self):
        """Un errore del fornitore puo contenere la chiave: non deve arrivare."""
        corpo = json.dumps(
            {"error": {"message": f"invalid x-api-key: {CHIAVE_ALICE} rifiutata"}}
        ).encode()
        risposta = self._errore(401, corpo)
        self.assertEqual(risposta.status_code, 403)
        dettaglio = risposta.json()["detail"]
        self.assertNotIn(CHIAVE_ALICE, dettaglio)
        self.assertNotIn(CHIAVE_ALICE, risposta.text)
        self.assertIn("[credenziale-rimossa]", dettaglio)
        # Il dettaglio c'e comunque: senza, l'utente non saprebbe cosa e successo.
        self.assertIn("Dettaglio dal fornitore", dettaglio)

    def test_fornitore_irraggiungibile_e_502(self):
        def esplode(request):
            raise httpx.ConnectError("connessione rifiutata", request=request)

        def fabbrica(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(esplode)
            return _ASYNC_CLIENT_VERO(*args, **kwargs)

        with mock.patch.object(ai_relay.httpx, "AsyncClient", fabbrica):
            risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 502)
        self.assertIn("non e raggiungibile", risposta.json()["detail"])

    def test_fornitore_lento_oltre_il_tempo_massimo_e_504(self):
        def scade(request):
            raise httpx.ReadTimeout("troppo lento", request=request)

        def fabbrica(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(scade)
            return _ASYNC_CLIENT_VERO(*args, **kwargs)

        with mock.patch.object(ai_relay.httpx, "AsyncClient", fabbrica):
            risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.status_code, 504)
        self.assertIn("tempo massimo", risposta.json()["detail"])


# ─────────────────── 4. Lo stream arriva a pezzi (misurato) ───────────────────


class TestStreamNonBufferizzato(BaseRelay):
    """★ La prova che il testo comparira parola per parola invece che in blocco.

    Il TestClient non serve a niente qui (bufferizza per costruzione, vedi la
    nota in testa al file): si chiama l'app ASGI a mano e si prende l'ORA DI
    ARRIVO di ogni messaggio `http.response.body`.
    """

    PAUSA = 0.2
    PEZZI = [b"data: {\"t\":\"pri\"}\n\n", b"data: {\"t\":\"sec\"}\n\n", b"data: {\"t\":\"ter\"}\n\n"]

    def setUp(self):
        super().setUp()
        self._registra_chiave(self.alice, CHIAVE_ALICE)

    async def _guida_asgi(self, corpo: dict, token: str):
        payload = json.dumps(corpo).encode()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/ai/chat",
            "raw_path": b"/api/v1/ai/chat",
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                (b"authorization", f"Bearer {token}".encode()),
            ],
            "client": ("127.0.0.1", 5000),
            "server": ("testserver", 80),
        }
        gia_inviato = [False]

        async def receive():
            if not gia_inviato[0]:
                gia_inviato[0] = True
                return {"type": "http.request", "body": payload, "more_body": False}
            # Il client resta in ascolto: non si disconnette da solo.
            await asyncio.sleep(3600)

        partenza = time.monotonic()
        eventi = []

        async def send(message):
            eventi.append((time.monotonic() - partenza, message))

        await APP(scope, receive, send)
        return eventi

    def test_i_pezzi_arrivano_distanziati_nel_tempo(self):
        finto = FornitoreFinto(pezzi=self.PEZZI, pausa=self.PAUSA)
        with fornitore(finto):
            eventi = asyncio.run(self._guida_asgi(self._busta(), self.token_alice))

        inizio = [(t, m) for t, m in eventi if m["type"] == "http.response.start"]
        corpi = [(t, m["body"]) for t, m in eventi if m["type"] == "http.response.body" and m.get("body")]

        self.assertEqual(len(inizio), 1)
        self.assertEqual(inizio[0][1]["status"], 200)

        # (a) I pezzi restano pezzi: nessuna riunificazione in un corpo solo.
        self.assertEqual([c for _, c in corpi], self.PEZZI)

        # (b) Le intestazioni partono PRIMA che il corpo sia finito: e questo
        #     che permette al pannello di aprire la risposta subito.
        arrivo_ultimo = corpi[-1][0]
        self.assertLess(
            inizio[0][0], arrivo_ultimo - self.PAUSA,
            "Le intestazioni sono uscite solo alla fine: il relay sta bufferizzando.",
        )

        # (c) Ogni pezzo arriva DOPO il precedente, distanziato quanto il
        #     fornitore lo ha prodotto. Se il relay accumulasse, i tre tempi
        #     sarebbero praticamente identici e questo confronto fallirebbe.
        tempi = [t for t, _ in corpi]
        for precedente, successivo in zip(tempi, tempi[1:]):
            self.assertGreaterEqual(
                successivo - precedente, self.PAUSA * 0.5,
                f"Pezzi troppo vicini ({tempi}): sono stati consegnati tutti insieme.",
            )

    def test_le_intestazioni_scoraggiano_i_proxy_che_accumulano(self):
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            risposta = self._chat(self.token_alice)
        self.assertEqual(risposta.headers.get("x-accel-buffering"), "no")
        self.assertIn("no-cache", risposta.headers.get("cache-control", ""))
        self.assertIn("text/event-stream", risposta.headers.get("content-type", ""))

    def test_se_il_client_si_stacca_lo_stream_verso_il_fornitore_si_chiude(self):
        """«Ferma» deve fermare anche la spesa: la connessione va chiusa davvero."""
        chiuso = {"valore": False}

        class FlussoTracciato(_FlussoFinto):
            async def aclose(self):
                chiuso["valore"] = True

        finto = FornitoreFinto(pezzi=self.PEZZI, pausa=self.PAUSA)

        def rispondi_tracciando(request):
            finto.richieste.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=FlussoTracciato(self.PEZZI, self.PAUSA),
            )

        def fabbrica(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(rispondi_tracciando)
            return _ASYNC_CLIENT_VERO(*args, **kwargs)

        async def stacca_a_meta():
            with mock.patch.object(ai_relay.httpx, "AsyncClient", fabbrica):
                eventi = await self._guida_asgi_interrotto(self._busta(), self.token_alice)
            return eventi

        eventi = asyncio.run(stacca_a_meta())
        # Il client ha chiuso dopo il primo pezzo: il generatore del relay deve
        # essere finito (e con lui il `finally` che chiude verso il fornitore).
        corpi = [m for _, m in eventi if m["type"] == "http.response.body" and m.get("body")]
        self.assertLessEqual(len(corpi), len(self.PEZZI) - 1)
        self.assertTrue(chiuso["valore"], "La connessione verso il fornitore non e stata chiusa.")

    async def _guida_asgi_interrotto(self, corpo: dict, token: str):
        """Come `_guida_asgi`, ma il client se ne va dopo il primo pezzo."""
        payload = json.dumps(corpo).encode()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/ai/chat",
            "raw_path": b"/api/v1/ai/chat",
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                (b"authorization", f"Bearer {token}".encode()),
            ],
            "client": ("127.0.0.1", 5000),
            "server": ("testserver", 80),
        }
        eventi = []
        stato = {"corpo_inviato": False, "pezzi_visti": 0}

        async def receive():
            if not stato["corpo_inviato"]:
                stato["corpo_inviato"] = True
                return {"type": "http.request", "body": payload, "more_body": False}
            # Appena il primo pezzo e uscito, il client si stacca.
            while stato["pezzi_visti"] < 1:
                await asyncio.sleep(0.01)
            return {"type": "http.disconnect"}

        async def send(message):
            eventi.append((time.monotonic(), message))
            if message["type"] == "http.response.body" and message.get("body"):
                stato["pezzi_visti"] += 1

        await APP(scope, receive, send)
        return eventi


# ─────────────────── 5. Il tetto di consumo ───────────────────


class TestTettoDiConsumo(BaseRelay):
    def setUp(self):
        super().setUp()
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        self._registra_chiave(self.bruno, CHIAVE_BRUNO)
        self.impostazioni.AI_RELAY_RATE_LIMIT = "2/minute"
        self._azzera_limitatore()

    def test_il_tetto_scatta_e_dice_quanto_manca(self):
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            self.assertEqual(self._chat(self.token_alice).status_code, 200)
            self.assertEqual(self._chat(self.token_alice).status_code, 200)
            terza = self._chat(self.token_alice)

        self.assertEqual(terza.status_code, 429)
        dettaglio = terza.json()["detail"]
        # ★ Deve dire QUANTO MANCA, non solo «troppe richieste».
        self.assertIn("riparte fra", dettaglio)
        self.assertRegex(dettaglio, r"\d+\s+(second|minut)")
        self.assertIn("non ti e stato addebitato nulla", dettaglio)
        # L'attesa e leggibile anche a macchina: l'header c'e ed e un numero.
        attesa = terza.headers.get("retry-after")
        self.assertIsNotNone(attesa, "Manca l'header Retry-After.")
        self.assertTrue(attesa.isdigit())
        self.assertGreater(int(attesa), 0)
        self.assertLessEqual(int(attesa), 60)
        # E la terza richiesta NON e uscita verso il fornitore.
        self.assertEqual(len(finto.richieste), 2)

    def test_il_tetto_e_per_utente_e_non_per_indirizzo(self):
        """Due utenti dietro lo stesso ufficio non si consumano il tetto a vicenda."""
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            self._chat(self.token_alice)
            self._chat(self.token_alice)
            self.assertEqual(self._chat(self.token_alice).status_code, 429)
            # Stesso indirizzo IP (il TestClient e uno solo), utente diverso.
            self.assertEqual(self._chat(self.token_bruno).status_code, 200)

    def test_senza_tetto_configurato_non_si_limita_nulla(self):
        self.impostazioni.AI_RELAY_RATE_LIMIT = ""
        self._azzera_limitatore()
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        with fornitore(finto):
            for _ in range(5):
                self.assertEqual(self._chat(self.token_alice).status_code, 200)


# ─────────────────── 6. Divieto di registrazione ───────────────────


class TestNessunLog(BaseRelay):
    """Da queste rotte passano il portafoglio dell'utente e la sua chiave.

    Il divieto e scritto in testa ai due file; questa prova lo rende
    verificabile invece che affidato alla buona volonta di chi li modifica.
    """

    FILE_DEL_RELAY = (
        "app/api/routes/ai.py",
        "app/services/ai_relay.py",
        "app/schemas/ai.py",
        "app/models/ai_credential.py",
        "app/repositories/ai_credential.py",
    )

    def test_nessun_print_e_nessun_logging_nei_file_del_relay(self):
        sospetti = re.compile(r"^\s*(print\s*\(|import\s+logging|from\s+logging\s|logger\s*\.)")
        for relativo in self.FILE_DEL_RELAY:
            percorso = _RADICE / relativo
            with self.subTest(file=relativo):
                self.assertTrue(percorso.exists(), f"File mancante: {relativo}")
                righe = percorso.read_text(encoding="utf-8").splitlines()
                colpevoli = [
                    f"{relativo}:{n}: {r.strip()}"
                    for n, r in enumerate(righe, start=1)
                    if sospetti.match(r)
                ]
                self.assertEqual(colpevoli, [], f"Registrazione vietata: {colpevoli}")

    def test_il_corpo_del_turno_non_finisce_su_stdout(self):
        """Spia vera: si cattura stdout durante un inoltro completo."""
        self._registra_chiave(self.alice, CHIAVE_ALICE)
        segreto_nel_corpo = "PORTAFOGLIO-RISERVATO-9137"
        finto = FornitoreFinto(pezzi=[b"data: ok\n\n"])
        cattura = io.StringIO()
        vero_stdout = sys.stdout
        sys.stdout = cattura
        try:
            with fornitore(finto):
                risposta = self._chat(
                    self.token_alice,
                    body={"model": "claude-x", "messages": [{"role": "user", "content": segreto_nel_corpo}]},
                )
        finally:
            sys.stdout = vero_stdout
        self.assertEqual(risposta.status_code, 200)
        stampato = cattura.getvalue()
        self.assertNotIn(segreto_nel_corpo, stampato)
        self.assertNotIn(CHIAVE_ALICE, stampato)


if __name__ == "__main__":
    unittest.main(verbosity=2)
