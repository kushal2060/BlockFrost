from fastapi import FastAPI
from pydantic import BaseModel
from blockfrost import BlockFrostApi, ApiError, ApiUrls
from pycardano import *
import json


app=FastAPI()

BLOCKFROST_PROJECT_ID = "preprodWGej2NMZe9tXwxqPCpmaUtiEOZEvGc9m"


api = BlockFrostApi(project_id=BLOCKFROST_PROJECT_ID)

class PayRollItem(BaseModel):
    address: str
    lovelace: int


class PayRollRequest(BaseModel):
    sender_address: str
    payroll: list[PayRollItem]


@app.post("/build_tx")
def build_transaction(request: PayRollRequest):
    sender_address = request.sender_address
    sender = Address.from_primitive(sender_address) #Address.from_primitive is a pycardano helper that converts a "primitive" address representation (typically a Bech32 string like "addr1..." or a CBOR-decoded structure) into a pycardano Address object you can use in transactions

    #fetcjh UTXOs for the sender address
    try:
        utxos_bf = api.address_utxos(sender_address)
    except ApiError as e:
        return {"error": f"Failed to fetch UTXOs: {str(e)}"}
    
    # convert BlockFrost UTXOs to pycardano UTXOs
    utxos =[]
    for u in utxos_bf:
        txin = TransactionInput(bytes.fromhex(u.tx_hash),u.output_index)
        value = Value.from_primitive({None: u.amount[0].quantity}) #assuming only lovelace for simplicity
        utxos.append(UTxO(input=txin, output=TransactionOutput(sender,value)))

    #protocol parameters
    pp=api.epoch_latest_parameters()

    builder = TransactionBuilder(
        network=Network.TESTNET,
        context=BlockFrostChainContext(BLOCKFROST_PROJECT_ID, base_url=ApiUrls.preprod.value),
        protocol_parameters=pp
    )
    #add inputs
    for utxo in utxos:
        builder.add_input(utxo)

    #add outputs from payroll list
    for p in request.payroll:
        builder.add_output(
            TransactionOutput(
                Address.from_primitive(p.address),
                Value(p.lovelace)
            )
        )

    #build the unsigned transaction    
    unsigned_tx = builder.build(change_address=sender)

    #serialize the transaction to CBOR hex
    cbor_hex = bytes(unsigned_tx.to_cbor())

    return {"unsigned_tx_cbor_hex": cbor_hex.hex()}