import asyncio
import os

# Railway asigna variables de entorno. Escuchamos en el puerto asignado
# Si no encuentra la variable localmente (por ejemplo, en tu PC), usará el 5000 por defecto.
SERVER_PORT = int(os.environ.get("PORT", 5000))
SERVER_HOST = "0.0.0.0"  # Obligatorio para Railway

async def manejar_rastreador(reader, writer):
    direccion_cliente = writer.get_extra_info('peername')
    print(f"[*] Conexión entrante desde el GPS: {direccion_cliente}")

    try:
        while True:
            # Lee paquetes del GPS continuamente
            datos = await reader.read(1024)
            
            if not datos:
                print(f"[-] El GPS {direccion_cliente} cerró la conexión.")
                break

            # Intenta decodificar los datos recibidos
            try:
                datos_texto = datos.decode('utf-8').strip()
                print(f"[{direccion_cliente}] Datos (Texto): {datos_texto}")
            except UnicodeDecodeError:
                datos_hex = datos.hex().upper()
                print(f"[{direccion_cliente}] Datos (Hexadecimal): {datos_hex}")

            # Respuesta obligatoria para evitar desconexión (Protocolos Concox/GT06 comunes en GNXIS)
            if datos.startswith(b'\x78\x78') and len(datos) > 4:
                respuesta = b'\x78\x78\x05\x01' + datos[4:6] + b'\x00\x05\x99\x99\x0D\x0A'
                writer.write(respuesta)
                await writer.drain()
                print(f"[->] Confirmación (Handshake) enviada a {direccion_cliente}")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[!] Error con el GPS {direccion_cliente}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"[*] Conexión finalizada para {direccion_cliente}")

async def main():
    servidor = await asyncio.start_server(manejar_rastreador, SERVER_HOST, SERVER_PORT)
    print(f"[*] Servidor GNXIS Activo. Escuchando internamente en {SERVER_HOST}:{SERVER_PORT}")
    
    async with servidor:
        # Esto mantiene el servidor corriendo infinitamente en Railway
        await servidor.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Servidor detenido manualmente.")
