# Cardano Payroll (dev / testnet)

Lightweight Cardano payroll demo for testing and development.  
For sending batch payments (multiple recipients) from a single company wallet, sign transactions server-side, store transaction history in SQLite, and view history in a minimal frontend.

---

## Features
- Batch payments to multiple recipients in single transaction
- auto server-side transaction construction, signing and submission (pycardano + Blockfrost) wihtout the need to login and sign  and submit transaction from eslint wallet
- SQLite persistence of transactions and outputs (history)
- Frontend UI to manage employees (add/remove), send payroll, and view history


---

## Repo structure
- frontend/
  - index.html — single-file frontend UI
- backend/
  - main.py — FastAPI backend (endpoints, DB, Blockfrost integration)
  - keygenerator.py — derive payment + stake keys from mnemonic (dev only)
  - .env — store secrets (not committed)
- README.md

---

## Security / warnings
- This project uses private keys derived from a mnemonic for local automatic signing. NEVER commit real mnemonics or private keys to git.
- Use dedicated testnet/preprod wallets and Blockfrost project keys for development.
- Treat any `.env` containing keys as sensitive.

---

## Requirements
- macOS (dev machine instructions shown)
- Python 3.11+ (venv recommended)
- Node / static file server or VSCode Live Server for frontend (or `python -m http.server`)

---

## Backend — setup & run (mac)
1. Create and activate venv:
```bash
cd /Users/mac/Desktop/cardano_task/backend
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install fastapi uvicorn pycardano blockfrost-python python-dotenv
```

3. Prepare `.env` (create in backend/). Example:
```
BLOCKFROST_PROJECT_ID=preprodYOURKEY_HERE
PAYMENT_SKEY_CBOR=5820...
STAKE_SKEY_CBOR=5820...
# optional (dev only)
seed_phrase="paddle follow soft ..."
```
- `PAYMENT_SKEY_CBOR` and `STAKE_SKEY_CBOR` come from `keygenerator.py` (run locally).
- have to ensure the Blockfrost token corresponds to the chosen network (preprod/testnet).

4. Start backend:
```bash
uvicorn main:app --reload --port 8000
```

---

## Generate keys (dev)
Run the included script to derive payment & stake keys from a mnemonic. For getting the private keys of the wallet for automatic signing and submitting to blockfrost:
```bash
cd /Users/mac/Desktop/cardano_task/backend
source venv/bin/activate
python keygenerator.py
```
Copied the CBOR hex keys into `.env` as `PAYMENT_SKEY_CBOR` and `STAKE_SKEY_CBOR`.

---

## Frontend — run
Serve the `frontend/index.html` from a static server (recommended: VSCode Live Server or simple Python server).

Example (from repo root):
```bash
cd /Users/mac/Desktop/cardano_task/frontend
# Quick server on port 5500
python3 -m http.server 5500
# Open http://127.0.0.1:5500 in browser
```

---

## API Endpoints
- POST /build_and_submit_tx
  - Request:
    ```json
    {
      "sender_address": "addr_test1...",
      "payroll": [
        {"address": "addr_test1...", "lovelace": 2000000},
        {"address": "addr_test1...", "lovelace": 1000000}
      ]
    }
    ```
  - Response includes `tx_hash`, `explorer_url`.

- GET /transaction_history
  - Returns stored transactions and outputs from SQLite.

- GET /get_tx_info/{tx_hash}
  - Returns stored tx details or falls back to Blockfrost if not in DB.

---

## Example curl (multi-recipient)
```bash
curl -X POST http://localhost:8000/build_and_submit_tx \
  -H "Content-Type: application/json" \
  -d '{
    "sender_address":"<SENDER_ADDR>",
    "payroll":[
      {"address":"<RECIPIENT1>","lovelace":1000000},
      {"address":"<RECIPIENT2>","lovelace":2000000}
    ]
  }'
```

---

## Troubleshooting (common errors)
- CORS blocked: ensure backend has CORSMiddleware enabled (allow origin localhost/dev)
- Blockfrost network mismatch: use project_id matching network; pycardano expects `Network.TESTNET` for preprod/testnet flows in many versions
- MissingVKeyWitnessesUTXOW: signing key was not matching address owning UTXOs so used the address produced by `keygenerator.py` and funded the derived address
- 404 when fetching UTXOs: address has no UTXOs; fund from faucet (Preprod faucet on Cardano docs)


---


## License
MIT
