# gerar_hash.py - ARQUIVO SEPARADO
import hashlib

def gerar_hash_senha():
    senha = input("Digite a senha para gerar hash: ")
    hash_result = hashlib.sha256(senha.encode()).hexdigest()
    print(f"\nSenha: {senha}")
    print(f"Hash SHA-256: {hash_result}")
    print(f"\nPara colar no Google Sheets:\n{hash_result}")

if __name__ == "__main__":
    gerar_hash_senha()