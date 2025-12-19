#extracting the private key from eslint wallte by using the mnemonic phrase
import string
from pycardano import (
    HDWallet, 
    Network, 
    PaymentSigningKey, 
    PaymentVerificationKey,
    StakeSigningKey,
    StakeVerificationKey,
    Address
)
import os
from dotenv import load_dotenv

load_dotenv()

seed_phrase = os.getenv("seed_phrase")

def generate_keys(seed: str):
    try:
        hdwallet = HDWallet.from_mnemonic(seed)
        
        # payment key
        payment_hdwallet = hdwallet.derive_from_path("m/1852'/1815'/0'/0/0")
        payment_private_key = payment_hdwallet.xprivate_key[:32].hex()
        payment_public_key = payment_hdwallet.public_key.hex()
        
        # stake key
        stake_hdwallet = hdwallet.derive_from_path("m/1852'/1815'/0'/2/0")
        stake_private_key = stake_hdwallet.xprivate_key[:32].hex()
        stake_public_key = stake_hdwallet.public_key.hex()
        
        # payment signing and verification keys
        payment_skey = PaymentSigningKey(bytes.fromhex(payment_private_key))
        payment_vkey = PaymentVerificationKey(bytes.fromhex(payment_public_key))
        
        # stake signing and verification keys
        stake_skey = StakeSigningKey(bytes.fromhex(stake_private_key))
        stake_vkey = StakeVerificationKey(bytes.fromhex(stake_public_key))
        
        # address with both payment and staking parts
        payment_address = Address(
            payment_part=payment_vkey.hash(),
            staking_part=stake_vkey.hash(),
            network=Network.TESTNET
        )
        
        # bor hex for storage
        payment_skey_cbor_hex = payment_skey.to_cbor_hex()
        stake_skey_cbor_hex = stake_skey.to_cbor_hex()
        
        print("Payment Signing Key CBOR Hex:", payment_skey_cbor_hex)
        print("\nStake Signing Key CBOR Hex:", stake_skey_cbor_hex)
        print("\nPayment Address:", payment_address)
        print("\nPayment Public Key:", payment_public_key)
        print("\nStake Public Key:", stake_public_key)
        print("\nSave these in .env")
        print(f"PAYMENT_SKEY_CBOR={payment_skey_cbor_hex}")
        print(f"STAKE_SKEY_CBOR={stake_skey_cbor_hex}")
        print(f"SENDER_ADDRESS={payment_address}")
        
        # save to files
        # payment_skey.save(f"{payment_address}_payment.skey")
        # payment_vkey.save(f"{payment_address}_payment.vkey")
        # stake_skey.save(f"{payment_address}_stake.skey")
        # stake_vkey.save(f"{payment_address}_stake.vkey")
        
    except Exception as e:
        print("An error occurred:", e)
        import traceback
        traceback.print_exc()

generate_keys(seed_phrase)




