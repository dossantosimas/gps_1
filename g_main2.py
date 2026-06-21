import asyncio
import os
import sys
from datetime import datetime
from pprint import pformat

from db import close_database, init_database, registrar_trama

# Desactivar buffering para que Railway vea los logs inmediatamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Puerto dinámico asignado por Railway
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

# Almacena dispositivos conectados {direccion: imei}
dispositivos = {}

# Conexión compartida a la base de datos
db_pool = None

def parsear_gt06(datos):
    """
    Parsea paquetes del protocolo GT06/GNXIS
    Retorna dict con la información extraída
    """
    resultado = {
        'tipo': 'desconocido',
        'raw_hex': datos.hex().upper()
    }
    
    # Verificar header GT06 (0x78 0x78) o (0x79 0x79 para paquetes largos)
    if not (datos.startswith(b'\x78\x78') or datos.startswith(b'\x79\x79')):
        resultado['tipo'] = 'no_gt06'
        return resultado
    
    # Longitud y protocolo
    if datos.startswith(b'\x78\x78'):
        longitud = datos[2]
        protocolo = datos[3]
    else:  # 0x79 0x79 - paquete largo
        longitud = (datos[2] << 8) | datos[3]
        protocolo = datos[4]
    
    resultado['protocolo_id'] = hex(protocolo)
    
    # 0x01 - Login (contiene IMEI)
    if protocolo == 0x01:
        resultado['tipo'] = 'login'
        # IMEI está en bytes 4-11 (8 bytes, formato BCD)
        imei_bytes = datos[4:12]
        imei = ''.join(f'{b:02X}' for b in imei_bytes)
        resultado['imei'] = imei.lstrip('0')
        
    # 0x12 - Datos de ubicación GPS
    elif protocolo == 0x12:
        resultado['tipo'] = 'ubicacion'
        resultado.update(parsear_ubicacion(datos))
        
    # 0x13 - Heartbeat/Status
    elif protocolo == 0x13:
        resultado['tipo'] = 'heartbeat'
        
    # 0x16 - Alarma GPS
    elif protocolo == 0x16:
        resultado['tipo'] = 'alarma'
        resultado.update(parsear_ubicacion(datos))
        
    # 0x1A - Datos GPS con LBS
    elif protocolo == 0x1A:
        resultado['tipo'] = 'gps_lbs'
        resultado.update(parsear_ubicacion(datos))
        
    # 0x19 - Múltiples datos LBS
    elif protocolo == 0x19:
        resultado['tipo'] = 'lbs_multiple'
        
    return resultado

def parsear_ubicacion(datos):
    """Extrae coordenadas GPS de un paquete de ubicación"""
    info = {}
    try:
        # Offset depende del tipo de paquete
        offset = 4
        
        # Fecha y hora (6 bytes): YY MM DD HH MM SS
        info['fecha'] = f"20{datos[offset]:02d}-{datos[offset+1]:02d}-{datos[offset+2]:02d}"
        info['hora'] = f"{datos[offset+3]:02d}:{datos[offset+4]:02d}:{datos[offset+5]:02d}"
        
        # Cantidad de satélites y GPS fijo
        gps_info = datos[offset + 6]
        info['satelites'] = gps_info & 0x0F
        info['gps_fijo'] = (gps_info >> 4) > 0
        
        # Latitud (4 bytes, formato: grados * 30000 * 60)
        lat_raw = (datos[offset+7] << 24) | (datos[offset+8] << 16) | (datos[offset+9] << 8) | datos[offset+10]
        info['latitud'] = lat_raw / 1800000.0
        
        # Longitud (4 bytes)
        lon_raw = (datos[offset+11] << 24) | (datos[offset+12] << 16) | (datos[offset+13] << 8) | datos[offset+14]
        info['longitud'] = lon_raw / 1800000.0
        
        # Velocidad (1 byte, km/h)
        info['velocidad'] = datos[offset + 15]
        
        # Curso/dirección (2 bytes)
        curso_status = (datos[offset+16] << 8) | datos[offset+17]
        info['curso'] = curso_status & 0x03FF
        
        # Ajustar signo de coordenadas basado en flags
        if not (curso_status & 0x0400):  # bit 10 = latitud sur
            info['latitud'] = -info['latitud']
        if curso_status & 0x0800:  # bit 11 = longitud oeste
            info['longitud'] = -info['longitud']
            
    except (IndexError, Exception) as e:
        info['error_parsing'] = str(e)
    
    return info

def generar_respuesta_gt06(datos, protocolo):
    """Genera respuesta de confirmación para GT06"""
    # Header + longitud + protocolo + serial + checksum + footer
    serial = datos[len(datos)-6:len(datos)-4]  # Serial está antes del checksum
    
    if protocolo == 0x01:  # Login response
        respuesta = b'\x78\x78\x05\x01' + serial
    else:  # Response genérica
        respuesta = b'\x78\x78\x05' + bytes([protocolo]) + serial
    
    # Calcular checksum CRC-ITU
    crc = calcular_crc(respuesta[2:])
    respuesta += crc.to_bytes(2, 'big')
    respuesta += b'\x0D\x0A'
    
    return respuesta

def calcular_crc(data):
    """Calcula CRC-ITU para GT06"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

async def manejar_trafico_mixto(reader, writer):
    """
    Detecta si la conexión es un Health Check de Railway (HTTP) 
    o datos reales de un rastreador GPS (TCP).
    """
    direccion = writer.get_extra_info('peername')
    print(f"[+] Nueva conexión desde: {direccion}", flush=True)
    
    try:
        # Leer con timeout para no bloquear
        try:
            datos = await asyncio.wait_for(reader.read(1024), timeout=30.0)
        except asyncio.TimeoutError:
            print(f"[!] Timeout esperando datos de {direccion}", flush=True)
            return
            
        if not datos:
            print(f"[-] Conexión vacía de {direccion}", flush=True)
            return

        # === IMPRIMIR TRAMA RECIBIDA ===
        print(f"\n{'='*60}", flush=True)
        print(f"[TRAMA] Datos recibidos de {direccion}", flush=True)
        print(f"[TRAMA] HEX: {datos.hex().upper()}", flush=True)
        print(f"[TRAMA] Bytes: {list(datos)}", flush=True)
        print(f"[TRAMA] Longitud: {len(datos)} bytes", flush=True)
        print(f"[TRAMA] ASCII (printable): {datos.decode('ascii', errors='replace')}", flush=True)
        print(f"{'='*60}", flush=True)

        # 1. SI ES TRAFICO HTTP (Railway Health Check o Navegador)
        if datos.startswith(b'GET') or datos.startswith(b'HEAD') or b'HTTP/' in datos:
            print(f"[HTTP] Health check recibido de {direccion}", flush=True)
            respuesta_http = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 2\r\n"
                "Connection: close\r\n\r\n"
                "OK"
            )
            writer.write(respuesta_http.encode('utf-8'))
            await writer.drain()
            return

        # 2. SI ES TRAFICO TCP (Rastreador GPS GNXIS/GT06)
        print(f"[GPS] Conexión GPS establecida desde: {direccion}", flush=True)
        
        imei_dispositivo = None
        
        while True:
            if datos:
                print(f"\n{'='*50}", flush=True)
                print(f"[GPS] Datos recibidos de {direccion}", flush=True)
                print(f"[GPS] Raw HEX: {datos.hex().upper()}", flush=True)
                print(f"[GPS] Longitud: {len(datos)} bytes", flush=True)
                
                # Parsear datos GT06
                info = parsear_gt06(datos)
                if imei_dispositivo:
                    info_db = {**info, 'imei': imei_dispositivo}
                else:
                    info_db = dict(info)
                if info.get('tipo') != 'no_gt06' and db_pool:
                    try:
                        await registrar_trama(db_pool, direccion, datos, info_db)
                    except Exception as err:
                        print(f"[DB] No se pudo registrar la trama: {err}", flush=True)
                
                print(f"[INFO] Datos parseados:\n{pformat(info)}", flush=True)
                if info['tipo'] == 'login':
                    imei_dispositivo = info.get('imei', 'desconocido')
                    dispositivos[direccion] = imei_dispositivo
                    print(f"[GPS] >>> LOGIN - IMEI: {imei_dispositivo}", flush=True)
                    
                elif info['tipo'] == 'ubicacion' or info['tipo'] == 'alarma' or info['tipo'] == 'gps_lbs':
                    print(f"[GPS] >>> UBICACIÓN ({info['tipo'].upper()})", flush=True)
                    if 'fecha' in info:
                        print(f"[GPS]     Fecha/Hora: {info['fecha']} {info['hora']}", flush=True)
                    if 'latitud' in info and 'longitud' in info:
                        print(f"[GPS]     Coordenadas: {info['latitud']:.6f}, {info['longitud']:.6f}", flush=True)
                        print(f"[GPS]     Google Maps: https://maps.google.com/?q={info['latitud']},{info['longitud']}", flush=True)
                    if 'velocidad' in info:
                        print(f"[GPS]     Velocidad: {info['velocidad']} km/h", flush=True)
                    if 'satelites' in info:
                        print(f"[GPS]     Satélites: {info['satelites']}", flush=True)
                        
                elif info['tipo'] == 'heartbeat':
                    print(f"[GPS] >>> HEARTBEAT del dispositivo", flush=True)
                    
                else:
                    print(f"[GPS] >>> Tipo: {info['tipo']} | Protocolo: {info.get('protocolo_id', 'N/A')}", flush=True)
                
                # Enviar confirmación para paquetes GT06
                if datos.startswith(b'\x78\x78') and len(datos) > 4:
                    protocolo = datos[3]
                    try:
                        respuesta = generar_respuesta_gt06(datos, protocolo)
                        writer.write(respuesta)
                        await writer.drain()
                        print(f"[GPS] Confirmación enviada: {respuesta.hex().upper()}", flush=True)
                    except Exception as e:
                        # Respuesta simplificada si falla
                        confirmacion = b'\x78\x78\x05' + bytes([protocolo]) + datos[len(datos)-6:len(datos)-4] + b'\x00\x01\x0D\x0A'
                        writer.write(confirmacion)
                        await writer.drain()

            # Leer siguientes paquetes
            try:
                datos = await asyncio.wait_for(reader.read(1024), timeout=300.0)
            except asyncio.TimeoutError:
                print(f"[!] GPS {direccion} sin actividad por 5 min", flush=True)
                break
            
            # === IMPRIMIR TRAMA RECIBIDA ===
            if datos:
                print(f"\n{'='*60}", flush=True)
                print(f"[TRAMA] Nueva trama de {direccion}", flush=True)
                print(f"[TRAMA] HEX: {datos.hex().upper()}", flush=True)
                print(f"[TRAMA] Bytes: {list(datos)}", flush=True)
                print(f"[TRAMA] Longitud: {len(datos)} bytes", flush=True)
                print(f"{'='*60}", flush=True)
                
            if not datos:
                print(f"[-] GPS {direccion} desconectado.", flush=True)
                if direccion in dispositivos:
                    del dispositivos[direccion]
                break

    except Exception as e:
        print(f"[!] Error con {direccion}: {e}", flush=True)
    finally:
        writer.close()
        await writer.wait_closed()

async def heartbeat():
    """Imprime un heartbeat cada 60 segundos para mostrar que el servidor está vivo"""
    while True:
        await asyncio.sleep(60)
        print("[*] Servidor activo - esperando conexiones GPS...", flush=True)

async def main():
    global db_pool
    db_pool = await init_database()
    servidor = await asyncio.start_server(manejar_trafico_mixto, HOST, PORT)
    print(f"[*] GNXIS Server running on {HOST}:{PORT}")
    print(f"[*] Waiting for GPS trackers to connect...")
    print(f"[*] Health check disponible en http://{HOST}:{PORT}/", flush=True)
    
    # Iniciar heartbeat en background
    asyncio.create_task(heartbeat())
    
    try:
        async with servidor:
            await servidor.serve_forever()
    finally:
        await close_database()

if __name__ == "__main__":
    print("[*] Iniciando servidor GNXIS...", flush=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[*] Servidor detenido por el usuario")
    except Exception as e:
        print(f"[!] Error fatal: {e}", flush=True)
        sys.exit(1)
