@app.route("/webhook", methods=["GET", "POST"])
def webhook():
  if request.method == "GET":
    return "Servidor Webhook activo", 200

  if request.method == "POST":
    data = request.json
    # Imprimir el JSON completo en los logs de Render para depurar
    print("--- JSON RECIBIDO DE EVOLUTION ---")
    print(json.dumps(data, indent=2))

    try:
      incoming_data = data.get("data", {})
      key = incoming_data.get("key", {})

      if key.get("fromMe", False):
        print("Mensaje ignorado por ser propio (fromMe=True)")
        return "OK", 200

      remote_jid = key.get("remoteJid", "")
      telefono = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

      if not telefono:
        print("No se pudo extraer el teléfono de remoteJid:", remote_jid)
        return "No phone found", 200

      print(f"Procesando mensaje dirigido al número: {telefono}")

      # Consultar inventario y armar el menú
      productos = conectar_inventario()
      mensaje_respuesta = "🍔 *Menú de Mateo's Food* 🍔\n\n"
      for p in productos:
        if p.get("estado") == "disponible":
          mensaje_respuesta += (
              f"• *{p.get('producto')}* - ${p.get('precio')} (Stock:"
              f" {p.get('stock')})\n"
          )
      mensaje_respuesta += (
          "\n¿Qué te gustaría ordenar hoy? Responde con tu pedido."
      )

      evo_url = os.environ.get("EVOLUTION_API_URL")
      evo_instance = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
      evo_apikey = os.environ.get("EVOLUTION_API_KEY")

      if evo_url and evo_apikey:
        send_url = f"{evo_url}/message/sendText/{evo_instance}"
        headers = {"apikey": evo_apikey, "Content-Type": "application/json"}
        payload = {"number": telefono, "text": mensaje_respuesta}

        res = requests.post(send_url, json=payload, headers=headers)
        print("Respuesta de envío Evolution:", res.status_code, res.text)
      else:
        print("Faltan variables de entorno de Evolution API")

    except Exception as e:
      print("Error crítico al procesar el mensaje:", str(e))

    return "EVENT_RECEIVED", 200
