import bcrypt

senha = "1154"

hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt())

print(hash.decode())