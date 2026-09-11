      chat_activo = obtener_o_crear_chat(telefono)
      respuesta = chat_activo.send_message(texto_usuario)
      texto_respuesta = respuesta.text

      # 1. Buscamos y extraemos el JSON para procesar la comanda internamente
      match = re.search(r"```json\s*(\{.*?\})\s*```", texto_respuesta, re.DOTALL)
      if match:
        json_str = match.group(1)
        try:
          comanda = json.loads(json_str)
          if "cliente" not in comanda or comanda["cliente"] == "Nombre":
            comanda["cliente"] = push_name
          print("--------------------------------------------------")
          print(f"🚀 PROCESANDO COMANDA DE {telefono}...")
          registrar_comanda_en_sheets(comanda)
          print("--------------------------------------------------\n")
        except json.JSONDecodeError as je:
          print("Error al decodificar JSON de comanda:", je)

      # 2. Limpiamos el texto eliminando el bloque JSON para que el cliente NO lo vea en WhatsApp
      texto_para_cliente = re.sub(
          r"```json\s*(\{.*?\})\s*```", "", texto_respuesta, flags=re.DOTALL
      ).strip()

      evo_url = os.environ.get("EVOLUTION_API_URL")
      evo_instance = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
      evo_apikey = os.environ.get("EVOLUTION_API_KEY")

      if evo_url and evo_apikey:
        send_url = f"{evo_url}/message/sendText/{evo_instance}"
        headers = {"apikey": evo_apikey, "Content-Type": "application/json"}
        # 3. Enviamos el texto limpio de vuelta a WhatsApp
        payload = {"number": telefono, "text": texto_para_cliente}
        requests.post(send_url, json=payload, headers=headers)
