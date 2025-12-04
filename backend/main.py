from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from blockfrost import BlockFrostApi, ApiError, ApiUrls
from pycardano import *
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from datetime import datetime
import sqlite3
from typing import List

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

#intialize databse 
def init_database():
    connection = sqlite3.connect('payrolls.db')
    c = connection.cursor() #for executing commands
    c.execute('''
        CREATE TABLE IF NOT EXISTS payrolls (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tx_hash TEXT UNIQUE NOT NULL,
              sender_address TEXT NOT NULL,
              total_amount INTEGER NOT NULL,
              receipient_count INTEGER NOT NULL,
              block_hash TEXT,
              block_height  INTEGER,
              status TEXT DEFAULT 'pending',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              confirmed_at TIMESTAMP
              )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transaction_output(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tx_hash TEXT NOT NULL,
              receiver_address TEXT NOT NULL,
              amount INTEGER NOT NULL,
              FOREIGN KEY (tx_hash) REFERENCES payrolls(tx_hash)
              )
    ''')
    connection.commit()
    connection.close()

#start db
init_database()


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

print(f"Loaded signing keys successfully")
print(f"Payment verification key hash: {payment_vkey.hash()}")
print(f"Stake verification key hash: {stake_vkey.hash()}")

class PayRollItem(BaseModel):
    address: str
    lovelace: int

class PayRollRequest(BaseModel):
    sender_address: str
    payroll: list[PayRollItem]


def save_transaction(tx_hash:str, sender:str, payroll: List[PayRollItem],block_hash:str=None,block_height:int=None):
    connection = sqlite3.connect('payrolls.db')
    c=connection.cursor()

    total_amount=sum(p.lovelace for p in payroll)
    reciever_count=len(payroll)

    try:
        #inserting in database:
        c.execute('''
            INSERT INTO payrolls (
                  tx_hash,sender_address,total_amount,receipient_count,block_hash,
                  block_height,status,confirmed_at)
            VALUES (?,?,?,?,?,?,?,?)      
        ''',(tx_hash,sender,total_amount,reciever_count,block_hash,block_height,
            'confirmed' if block_hash else 'pending',
            datetime.utcnow() if block_hash else None))
        #insert outputs
        for p in payroll:
            c.execute('''
                INSERT INTO transaction_output(tx_hash,receiver_address,amount)
                VALUES (?,?,?)
            ''', (tx_hash,p.address,p.lovelace))
        connection.commit()    
        print("Transaction saved in database")
    except sqlite3.IntegrityError:
        print("Transaction already exists")
    finally:
        connection.close()        


@app.post("/build_and_submit_tx")
def build_and_submit_transaction(request: PayRollRequest):
    """
    Builds, signs, and submits transaction automatically
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
                detail=f"No UTXOs found for {sender_address}. Fund  at https://docs.cardano.org/cardano-testnet/tools/faucet/"
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
        # Save to database 
        save_transaction(str(tx_hash), sender_address, request.payroll)
        
        # Wait for confirmation and update status
        import time
        time.sleep(3)  # increased from 2 to 3 seconds
        
        # try:
        #     tx_info = api.transaction(str(tx_hash))
        #     block_hash = tx_info.block if hasattr(tx_info, 'block') else None
        #     block_height = tx_info.block_height if hasattr(tx_info, 'block_height') else None
            
        #     # UPDATE the database with block info
        #     if block_hash:
        #         connection = sqlite3.connect('payrolls.db')
        #         c = connection.cursor()
        #         c.execute('''
        #             UPDATE payrolls 
        #             SET block_hash = ?, block_height = ?, status = 'confirmed', confirmed_at = ?
        #             WHERE tx_hash = ?
        #         ''', (block_hash, block_height, datetime.utcnow(), str(tx_hash)))
        #         connection.commit()
        #         connection.close()
        #         print(f"Transaction confirmed in block {block_height}")
        # except Exception as e:
        #     print(f"Could not fetch block info yet: {e}")
        #     block_hash = None
        #     block_height = None
        
        return {
            "success": True,
            "tx_hash": str(tx_hash),
            "explorer_url": f"https://preprod.cardanoscan.io/transaction/{tx_hash}"
        }
        
    except ApiError as e:
        print(f"Blockfrost error: {e}")
        raise HTTPException(status_code=400, detail=f"Blockfrost error: {str(e)}")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/transaction_history")
def get_transaction_history():
    '''get the transactions from sqlite'''
    connection = sqlite3.connect('payrolls.db')
    connection.row_factory = sqlite3.Row
    c= connection.cursor()

    c.execute('''
        SELECT * FROM payrolls 
        ORDER BY created_at DESC
    ''')

    transactions = []
    for row in c.fetchall():
        tx_hash =row['tx_hash']
        c.execute('''
            SELECT receiver_address , amount FROM transaction_output WHERE tx_hash =?
        ''',(tx_hash,))

        outputs = [{"address": o['receiver_address'],"lovelace":o['amount']}
                  for o in c.fetchall()]
        transactions.append({
            "tx_hash": tx_hash,
            "sender_address": row['sender_address'],
            "total_amount": row['total_amount'],
            "recipient_count": row['receipient_count'],
            "outputs": outputs,
            "block_hash": row['block_hash'],
            "block_height": row['block_height'],
            "status": row['status'],
            "created_at": row['created_at'],
            "confirmed_at": row['confirmed_at'],
            "explorer_url": f"https://preprod.cardanoscan.io/transaction/{tx_hash}"
        })     
    connection.close()         
    return {"transactions": transactions}



@app.get("/get_tx_info/{tx_hash}")
def get_transaction_info(tx_hash: str):
    """Get transaction block information"""
    conn=sqlite3.connect('payrolls.db')
    conn.row_factory=sqlite3.Row
    c=conn.cursor()

    c.execute('SELECT * FROM payrolls WHERE tx_hash =?',(tx_hash))
    row = c.fetchone() #just one row

    if not row:
        #not in db fetch from blockfrost
        try:
            tx_info = api.transaction(tx_hash)
            conn.close()        
            return {
            "tx_hash": tx_hash,
            "block": tx_info.block,
            "block_height": tx_info.block_height,
            "block_time": tx_info.block_time,
            "confirmed": True,
            "source":"blockfrost"
            }
        except ApiError as e:
            raise HTTPException(status_code=404, detail="Transaction not found or still pending")

    c.execute('SELECT * FROM transaction_output WHERE tx_hash = ?', (tx_hash,))
    outputs = [{"address": o['receiver_address'], "lovelace": o['amount']} 
              for o in c.fetchall()]
    
    conn.close()
    
    return {
        "tx_hash": tx_hash,
        "sender_address": row['sender_address'],
        "outputs": outputs,
        "total_amount": row['total_amount'],
        "block": row['block_hash'],
        "block_height": row['block_height'],
        "status": row['status'],
        "created_at": row['created_at'],
        "confirmed_at": row['confirmed_at'],
        "confirmed": row['status'] == 'confirmed',
        "source": "database"
    }
