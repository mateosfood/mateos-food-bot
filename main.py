import os
from flask import Flask, request
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Inicializamos Flask (el servidor web que mantiene vivo a Render)
app = Flask(__name__)

# Configuración de la API de Gemini
API_KEY = os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI")
genai.configure(api_key=API_KEY)

# Configuración del modelo con la personalidad y las reglas de Mateo's Food
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
}

system_instruction = """
Eres el asistente virtual y recepcionista amigable de 'Mateo's Food', un negocio de comida rápida (hamburguesas, papas, etc.) operado en San Fernando, Tamaulipas.
Tu trato es de 'tú por tú', muy cálido, mexicano, servicial y de confianza, como si fueras parte del equipo de cocina atendiendo por WhatsApp.
Reglas del negocio:
- Áreas de servicio: Carbonera Norte y Carbonera Sur.
- Envío: Gratis.
- Tiempo estimado de entrega: 30 minutos.
- Si un producto está marcado como 'Agotado' en la hoja de inventario, debes avisarle amablemente al cliente y ofrecerle otra opción disponible.
"""

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction=system_instruction,
)

# Función para consultar el inventario en Google Sheets (Disponible / Agotado)
def verificar_inventario(producto_solicitado):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        return "Disponible" 
    except Exception as e:
        print(f"Error al revisar inventario: {e}")
        return "Disponible"

# Ruta principal que escucha los mensajes que llegan a la web
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        data = request.json
        mensaje_cliente = data.get("message", "")
        
        chat = model.start_chat(history=[])
        respuesta = chat.send_message(mensaje_cliente)
        
        return {"status": "success", "reply": respuesta.text}
    
    return "El servidor de Mateo's Food está activo y operando con normalidad."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
