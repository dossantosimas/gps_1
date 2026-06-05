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
    try:
        # Leer los primeros bytes para identificar el protocolo
        datos = await reader.read(1024)
        if not datos:
            return

        # 1. SI ES TRAFICO HTTP (Railway Health Check o Navegador)
        if datos.startswith(b'GET') or b'HTTP/' in datos:
            # Respondemos un HTTP 200 OK para que Railway sepa que estamos vivos
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
        print(f"[*] Conexión GPS establecida desde: {direccion}")
        
        while True:
            # Procesar el paquete inicial que ya leímos
            if datos:
                try:
                    datos_texto = datos.decode('utf-8').strip()
                    print(f"[{direccion}] Texto: {datos_texto}")
                except UnicodeDecodeError:
                    print(f"[{direccion}] Hex: {datos.hex().upper()}")

                # Protocolo de confirmación obligatorio para GNXIS / GT06
                if datos.startswith(b'\x78\x78') and len(datos) > 4:
                    confirmacion = b'\x78\x78\x05\x01' + datos[4:6] + b'\x00\x05\x99\x99\x0D\x0A'
                    writer.write(confirmacion)
                    await writer.drain()

            # Leer siguientes paquetes en bucle
            datos = await reader.read(1024)
            if not datos:
                print(f"[-] GPS {direccion} desconectado.")
                break

    except Exception as e:
        print(f"[!] Error con {direccion}: {e}")
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
