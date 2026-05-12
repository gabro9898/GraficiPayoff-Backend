-- ============================================================
-- Migrazione manuale: normalizzazione email utenti in lowercase
-- ============================================================
--
-- Contesto: il bug "molti utenti devono resettare la password" era
-- causato da find_by_email case-sensitive sul DB. Confermato dal caso
-- Antonio: registrato come ANTONIOGIAMMARIA@gmail.com, login con
-- antoniogiammaria@gmail.com → 401 InvalidCredentials.
--
-- Con il fix applicato:
--   - gli schemas Pydantic normalizzano l'email in lowercase IN ENTRATA
--   - il repository fa find_by_email case-insensitive (func.lower)
--
-- Il fix è già funzionante senza questo script (la query lower-vs-lower
-- tollera record storici con case misto). Questo script è IGIENE:
-- rende il DB consistente, permette in futuro di mettere un check
-- constraint, e velocizza la query con un index funzionale.
--
-- ⚠ ATTENZIONE: prima di lanciare lo STEP 2 esegui sempre lo STEP 1.
--   Se restituisce righe, NON LANCIARE l'UPDATE — risolvi i duplicati
--   a mano (vedi STEP 1b) altrimenti UNIQUE(email) si rifiuta di
--   accettare l'UPDATE.
--
-- Tutto è in transazione: se qualcosa va storto, ROLLBACK lascia il DB
-- intatto.
-- ============================================================


-- ─── STEP 1: VERIFICA DUPLICATI (READ-ONLY) ───────────────────
-- Cerca casi tipo: "mario@x.com" e "Mario@X.com" registrati come
-- account separati. La UNIQUE(email) attuale non li blocca perché
-- è case-sensitive, ma l'UPDATE successivo li farebbe collidere.

SELECT
    LOWER(email) AS normalized_email,
    COUNT(*)    AS account_count,
    ARRAY_AGG(email ORDER BY created_at) AS variants,
    ARRAY_AGG(id    ORDER BY created_at) AS user_ids
FROM users
GROUP BY LOWER(email)
HAVING COUNT(*) > 1
ORDER BY account_count DESC;

-- Se la query sopra restituisce 0 righe → procedi allo STEP 2.
-- Se restituisce righe → fermati. Per ogni gruppo devi decidere quale
-- account tenere (di solito il più vecchio o quello con sub attiva)
-- e cosa fare degli altri (cancellare? riassegnare strategie?).
-- Vedi STEP 1b per una checklist.


-- ─── STEP 1b: (solo se STEP 1 ha trovato duplicati) ───────────
-- Per ogni gruppo duplicato, prima di cancellare gli account "duplicati"
-- controlla cosa hanno collegato. Sostituisci :dup_id con l'id da
-- rimuovere e lancia uno alla volta:
--
-- SELECT COUNT(*) FROM accounts                 WHERE user_id = :dup_id;
-- SELECT COUNT(*) FROM strategies               WHERE user_id = :dup_id;
-- SELECT COUNT(*) FROM password_reset_codes     WHERE user_id = :dup_id;
-- SELECT COUNT(*) FROM email_verification_tokens WHERE user_id = :dup_id;
--
-- Se l'account duplicato ha dati: riassegnali all'account "canonico"
-- (UPDATE ... SET user_id = :canonical_id WHERE user_id = :dup_id)
-- prima di cancellarlo. Se è vuoto, cancellalo direttamente.
-- NB: i nomi tabella esatti dipendono dallo schema attuale — verifica
-- con \d nei vari modelli prima.


-- ─── STEP 2: NORMALIZZAZIONE (DESTRUCTIVE) ────────────────────
-- Esegui SOLO se STEP 1 non ha trovato duplicati.
-- Tutto in una transazione: se l'UPDATE viola UNIQUE, ROLLBACK.

BEGIN;

-- Backup di sicurezza (tabella temporanea con la mappa vecchio→nuovo).
-- Resta nel DB finché non fai DROP; comoda per audit/rollback manuale.
CREATE TABLE IF NOT EXISTS users_email_normalize_backup AS
SELECT id, email AS old_email, LOWER(email) AS new_email, NOW() AS migrated_at
FROM users
WHERE email <> LOWER(email);

-- Normalizzazione vera e propria.
UPDATE users
SET email = LOWER(email)
WHERE email <> LOWER(email);

-- Verifica post-update: deve essere 0.
SELECT COUNT(*) AS rows_still_with_mixed_case
FROM users
WHERE email <> LOWER(email);

-- Se tutto OK:
COMMIT;
-- Se qualcosa non torna:
-- ROLLBACK;


-- ─── STEP 3: INDICE FUNZIONALE (OTTIMIZZAZIONE) ───────────────
-- Dopo la normalizzazione, l'indice UNIQUE(email) di base è già
-- sufficiente perché tutto è lowercase. Questo indice extra serve solo
-- se vuoi mantenere la query func.lower(...) performante anche se
-- in futuro venissero reinseriti record con case misto (es. da import).
-- Opzionale.

-- CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower
-- ON users (LOWER(email));
