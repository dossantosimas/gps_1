import asyncio
import os
import sys

# Desactivar buffering para que Railway vea los logs inmediatamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Puerto dinámico asignado por Railway
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

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

        # 2. SI ES TRAFICO TCP (Rastreador GPS GNXIS)
        print(f"[GPS] Conexión GPS establecida desde: {direccion}", flush=True)
        print(f"[GPS] Datos iniciales: {datos.hex().upper()}", flush=True)
        
        while True:
            if datos:
                try:
                    datos_texto = datos.decode('utf-8').strip()
                    print(f"[{direccion}] Texto: {datos_texto}", flush=True)
                except UnicodeDecodeError:
                    print(f"[{direccion}] Hex: {datos.hex().upper()}", flush=True)

                # Protocolo de confirmación obligatorio para GNXIS / GT06
                if datos.startswith(b'\x78\x78') and len(datos) > 4:
                    confirmacion = b'\x78\x78\x05\x01' + datos[4:6] + b'\x00\x05\x99\x99\x0D\x0A'
                    writer.write(confirmacion)
                    await writer.drain()
                    print(f"[GPS] Confirmación enviada a {direccion}", flush=True)

            # Leer siguientes paquetes
            try:
                datos = await asyncio.wait_for(reader.read(1024), timeout=300.0)
            except asyncio.TimeoutError:
                print(f"[!] GPS {direccion} sin actividad por 5 min", flush=True)
                break
                
            if not datos:
                print(f"[-] GPS {direccion} desconectado.", flush=True)
                break

    except Exception as e:
        print(f"[!] Error con {direccion}: {e}", flush=True)
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    servidor = await asyncio.start_server(manejar_trafico_mixto, HOST, PORT)
    print(f"[*] GNXIS Server running on {HOST}:{PORT}")
    print(f"[*] Waiting for GPS trackers to connect...")
    print(f"[*] Health check disponible en http://{HOST}:{PORT}/", flush=True)
    
    async with servidor:
        await servidor.serve_forever()

if __name__ == "__main__":
    print("[*] Iniciando servidor GNXIS...", flush=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[*] Servidor detenido por el usuario")
    except Exception as e:
        print(f"[!] Error fatal: {e}", flush=True)
        sys.exit(1)
