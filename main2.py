from http.server import HTTPServer, BaseHTTPRequestHandler
import datetime
import os
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
        print(linea, flush=True)
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        pass

PORT = int(os.environ.get('PORT', 8080))
print(f"✅ Servidor corriendo en puerto {PORT}", flush=True)
HTTPServer(('0.0.0.0', PORT), GPSHandler).serve_forever()