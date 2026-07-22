"""
AstroCube - Punto de entrada único para Railway.

Antes, el bot de Discord y el panel web eran dos servicios de Railway
separados. El problema: Railway NO permite compartir un mismo volumen (ni
por tanto un mismo archivo) entre dos servicios distintos, así que aunque el
código de ambos apuntara a "la misma" base de datos SQLite, en producción
cada uno tenía en realidad su propio archivo separado. Resultado: el panel
nunca veía los mensajes privados que recibía el bot, y en general nada que
un lado escribiera era visible para el otro de forma fiable.

Este archivo arranca los dos dentro del MISMO proceso (el panel web en un
hilo aparte, con un servidor de producción real -waitress-, y el bot de
Discord en el hilo principal vía asyncio). Al ser un solo proceso, comparten
sin ningún truco extra el mismo archivo de base de datos.

Cómo desplegar en Railway ahora: UN solo servicio para todo este proyecto,
con UN Volume persistente (por ejemplo montado en /data) y la variable de
entorno DB_PATH apuntando dentro de ese Volume (ej: /data/antiraid.db).
"""

import asyncio
import os
import threading

from waitress import serve as waitress_serve

import main as bot_main
import panel


def _run_panel():
    port = int(os.getenv("PORT", "5000"))
    print(f"[run.py] Panel web escuchando en 0.0.0.0:{port}")
    waitress_serve(panel.app, host="0.0.0.0", port=port)


def main():
    panel_thread = threading.Thread(target=_run_panel, name="panel-web", daemon=True)
    panel_thread.start()

    # El bot corre en el hilo principal (bloqueante) usando su propio main()
    # asíncrono, tal cual como si se ejecutara "python3 main.py" a solas.
    asyncio.run(bot_main.main())


if __name__ == "__main__":
    main()
