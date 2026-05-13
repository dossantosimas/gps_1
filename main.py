import socket
import datetime

# Configuración
HOST = '0.0.0.0'  # Escucha en todas las interfaces
PORT = 80       # Puerto GT06

def parse_gt06(data):
    """Parsea la trama GT06 básica"""
    try:
        hex_data = data.hex()
        print(f"Trama recibida (hex): {hex_data}")
        return hex_data
    except:
        return data.decode('utf-8', errors='ignore')

def guardar_txt(imei, trama_hex):
    """Guarda los datos en archivo txt"""
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"{fecha} | IMEI: {imei} | TRAMA: {trama_hex}\n"
    
    with open("datos_gps.txt", "a") as f:
        f.write(linea)
    print(f"Guardado: {linea}")

# Servidor TCP
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(10)

print(f"✅ Servidor escuchando en puerto {PORT}...")
print(f"📁 Guardando datos en: datos_gps.txt")

while True:
    try:
        conn, addr = server.accept()
        print(f"\n📡 Conexión de: {addr}")
        
        while True:
            data = conn.recv(1024)
            if not data:
                break
                
            trama_hex = parse_gt06(data)
            imei = addr[0]  # Usamos IP como identificador temporal
            guardar_txt(imei, trama_hex)
            
            # Respuesta de login GT06 (necesaria para que el GPS siga enviando)
            if data[3:4] == b'\x01':  # Paquete de login
                respuesta = bytes.fromhex('787801010d0a')
                conn.send(respuesta)
                print("✅ Login confirmado al GPS")
                
    except Exception as e:
        print(f"Error: {e}")
        conn.close()