from http.server import HTTPServer, BaseHTTPRequestHandler
import datetime
from urllib.parse import urlparse, parse_qs

class GPSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        id_dispositivo = params.get('id', ['desconocido'])[0]
        lat = params.get('lat', ['0'])[0]
        lon = params.get('lon', ['0'])[0]
        speed = params.get('speed', ['0'])[0]
        
        linea = f"{fecha} | ID: {id_dispositivo} | LAT: {lat} | LON: {lon} | VEL: {speed}\n"
        
        with open("datos_gps.txt", "a") as f:
            f.write(linea)
        
        print(f"📍 {linea}")
        
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Silencia logs innecesarios

print("✅ Servidor HTTP escuchando en puerto 80...")
print("📁 Guardando en datos_gps.txt")
HTTPServer(('0.0.0.0', 80), GPSHandler).serve_forever()