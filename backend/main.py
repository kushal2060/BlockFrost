from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from blockfrost import BlockFrostApi, ApiError, ApiUrls
from pycardano import *
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # use specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BLOCKFROST_PROJECT_ID = os.getenv("BLOCKFROST_PROJECT_ID")
api = BlockFrostApi(
    project_id=BLOCKFROST_PROJECT_ID,
    base_url=ApiUrls.preprod.value  # Changed from testnet to preprod
)

class PayRollItem(BaseModel):
    address: str
    lovelace: int

class PayRollRequest(BaseModel):
    sender_address: str
    payroll: list[PayRollItem]

@app.post("/build_tx")
def build_transaction(request: PayRollRequest):
    print("Received request:", request.model_dump())
    
    # Strip whitespace from sender address
    sender_address = request.sender_address.strip()
    sender = Address.from_primitive(sender_address)
    
    # Fetch UTXOs for the sender address
    try:
        utxos_bf = api.address_utxos(sender_address)
    except ApiError as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch UTXOs: {e}")
    
    # Convert BlockFrost UTXOs to pycardano UTXOs
    utxos = []
    for u in utxos_bf:
        tx_in = TransactionInput.from_primitive([u.tx_hash, u.output_index])
        
        # parse amounts from Blockfrost
        lovelace = 0
        for amt in u.amount:
            if amt.unit == "lovelace":
                lovelace = int(amt.quantity)
        
        tx_out = TransactionOutput(sender, Value(lovelace))
        utxos.append(UTxO(tx_in, tx_out))
    
    if not utxos:
        raise HTTPException(status_code=400, detail="No UTXOs found for sender address")
    
    # Get protocol parameters
    pp_response = api.epoch_latest_parameters()
    
    # Create chain context
    context = BlockFrostChainContext(BLOCKFROST_PROJECT_ID, base_url=ApiUrls.preprod.value)
    
    # Build transaction
    builder = TransactionBuilder(context)
    
    # Add inputs
    for utxo in utxos:
        builder.add_input(utxo)
    
    # Add outputs from payroll list
    for p in request.payroll:
        recipient = Address.from_primitive(p.address.strip())
        builder.add_output(TransactionOutput(recipient, Value(p.lovelace)))
    
    # Build the unsigned transaction    
    unsigned_tx = builder.build_and_sign([], change_address=sender)
    
    # Serialize the transaction to CBOR hex
    cbor_hex = unsigned_tx.to_cbor_hex()
    
    return {"cbor_hex": cbor_hex}