
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from blockfrost import BlockFrostApi, ApiError, ApiUrls
from pycardano import *
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BLOCKFROST_PROJECT_ID = os.getenv("BLOCKFROST_PROJECT_ID")
api = BlockFrostApi(
    project_id=BLOCKFROST_PROJECT_ID,
    base_url=ApiUrls.preprod.value
)
 
# Load signing key from environment
PAYMENT_SKEY_CBOR = os.getenv("PAYMENT_SKEY_CBOR")
STAKE_SKEY_CBOR = os.getenv("STAKE_SKEY_CBOR")

if not PAYMENT_SKEY_CBOR:
    raise Exception("PAYMENT_SKEY_CBOR not found in .env file!")
if not STAKE_SKEY_CBOR:
    raise Exception("STAKE_SKEY_CBOR not found in .env file!")

# Create signing key objects from CBOR hex
payment_signing_key = PaymentSigningKey.from_cbor(PAYMENT_SKEY_CBOR)
payment_vkey = PaymentVerificationKey.from_signing_key(payment_signing_key)

stake_signing_key = StakeSigningKey.from_cbor(STAKE_SKEY_CBOR)
stake_vkey = StakeVerificationKey.from_signing_key(stake_signing_key)

print(f"✅ Loaded signing keys successfully")
print(f"Payment verification key hash: {payment_vkey.hash()}")
print(f"Stake verification key hash: {stake_vkey.hash()}")

class PayRollItem(BaseModel):
    address: str
    lovelace: int

class PayRollRequest(BaseModel):
    sender_address: str
    payroll: list[PayRollItem]

@app.post("/build_and_submit_tx")
def build_and_submit_transaction(request: PayRollRequest):
    """
    Builds, signs, and submits transaction automatically
    No wallet interaction needed!
    """
    print("Received payroll request:", request.model_dump())
    
    try:
        sender_address = request.sender_address.strip()
        sender = Address.from_primitive(sender_address)
        
        # verifyo that the sender address matches the payment and stake keys
        derived_address = Address(
            payment_part=payment_vkey.hash(),
            staking_part=stake_vkey.hash(),  
            network=Network.TESTNET
        )
        print(f"Sender from request: {sender_address}")
        print(f"Address from your key: {derived_address}")
        
        if str(derived_address) != sender_address:
            raise HTTPException(
                status_code=400,
                detail=f"ADDRESS MISMATCH!\n"
                       f"Your signing key is for: {derived_address}\n"
                       f"But request sender is: {sender_address}\n"
                       f"Either:\n"
                       f"1. Use {derived_address} in the frontend sender field, OR\n"
                       f"2. Fund {derived_address} with testnet ADA from the faucet"
            )
        
        # Fetch UTXOs
        print("Fetching UTXOs...")
        utxos_bf = api.address_utxos(sender_address)
        
        if not utxos_bf:
            raise HTTPException(
                status_code=400,
                detail=f"No UTXOs found for {sender_address}. Fund it at https://docs.cardano.org/cardano-testnet/tools/faucet/"
            )
        
        print(f"Found {len(utxos_bf)} UTXOs")
        
        # Convert to pycardano UTXOs
        utxos = []
        for u in utxos_bf:
            txin = TransactionInput.from_primitive([u.tx_hash, u.output_index])
            lovelace_amount = int(u.amount[0].quantity)
            value = Value(lovelace_amount)
            utxos.append(UTxO(input=txin, output=TransactionOutput(sender, value)))
        
        # Create chain context
        print("Creating transaction...")
        context = BlockFrostChainContext(BLOCKFROST_PROJECT_ID, base_url=ApiUrls.preprod.value)
        
        # Build transaction
        builder = TransactionBuilder(context)
        
        # Add inputs
        for utxo in utxos:
            builder.add_input(utxo)
        
        # Add outputs from payroll
        for p in request.payroll:
            builder.add_output(
                TransactionOutput(
                    Address.from_primitive(p.address),
                    Value(p.lovelace)
                )
            )
        
        # Build and SIGN with BOTH payment and stake keys
        print("Signing transaction...")
        signed_tx = builder.build_and_sign(
            signing_keys=[payment_signing_key, stake_signing_key], 
            change_address=sender
        )
        
        # Submit to blockchain
        print("Submitting to blockchain...")
        tx_hash = context.submit_tx(signed_tx)
        
        print(f"Transaction submitted! Hash: {tx_hash}")
        
        # delay to get block info
        import time
        time.sleep(2)
        
        try:
            tx_info = api.transaction(str(tx_hash))
            block_info = {
                "block": tx_info.block if hasattr(tx_info, 'block') else "pending",
                "block_height": tx_info.block_height if hasattr(tx_info, 'block_height') else None
            }
        except:
            block_info = {"block": "pending", "block_height": None}
        
        return {
            "success": True,
            "tx_hash": str(tx_hash),
            "block": block_info["block"],
            "block_height": block_info["block_height"],
            "explorer_url": f"https://preprod.cardanoscan.io/transaction/{tx_hash}"
        }
        
    except ApiError as e:
        print(f"Blockfrost error: {e}")
        raise HTTPException(status_code=400, detail=f"Blockfrost error: {str(e)}")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/get_tx_info/{tx_hash}")
def get_transaction_info(tx_hash: str):
    """Get transaction block information"""
    try:
        tx_info = api.transaction(tx_hash)
        
        return {
            "tx_hash": tx_hash,
            "block": tx_info.block,
            "block_height": tx_info.block_height,
            "block_time": tx_info.block_time,
            "confirmed": True
        }
    except ApiError as e:
        raise HTTPException(status_code=404, detail="Transaction not found or still pending")