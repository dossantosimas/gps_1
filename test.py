import socket
import time

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('10.25.157.133', 5023))
print("✅ Conectado al servidor")

# Trama login GT06
login = bytes.fromhex('7878110103' + '353535353535353535353535' + '0001' + '0d0a')
client.send(login)
print("📤 Login enviado")
time.sleep(2)

while True:
    # Trama ubicación simple
    ubicacion = bytes.fromhex('78782200' + '1a050a0a0000' + '0109685000' + '0074781300' + '00' + '0000' + '000000' + '0001' + '0d0a')
    client.send(ubicacion)
    print("📍 Ubicación enviada")
    time.sleep(5)