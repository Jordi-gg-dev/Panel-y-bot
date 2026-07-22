# 🛰️ AstroCube — Bot + Panel (proyecto único)

Este proyecto contiene el bot de Discord **AstroCube Anti-Raid** y su panel web de administración **en un solo sitio**. Antes eran dos proyectos separados que se desplegaban como dos servicios de Railway; se han unido porque Railway no permite compartir un mismo volumen/archivo entre dos servicios distintos, y eso hacía que el panel y el bot NO vieran de verdad los mismos datos (por ejemplo, los mensajes privados que recibía el bot no llegaban a aparecer en el panel). Ahora ambos corren dentro del mismo proceso y comparten el archivo de verdad.

**Acceso al panel restringido**: solo puede entrar quien inicie sesión con la cuenta de Discord que pongas en `OWNER_IDS`. Nadie más puede ni siquiera ver el panel, aunque conozca la URL.

---

## 1. Instalar y configurar

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip3 install -r requirements.txt
cp .env.example .env
```

Rellena `.env` (ver los comentarios de cada variable dentro del propio archivo):
- `DISCORD_TOKEN` — token del bot (Developer Portal > tu app > Bot > Reset Token).
- `DISCORD_CLIENT_ID` y `DISCORD_CLIENT_SECRET` — pestaña OAuth2 de esa misma app. Añade también el Redirect exacto (`http://localhost:5000/callback` en local).
- `OWNER_IDS` — tu ID de usuario de Discord (clic derecho sobre tu perfil con el Modo Desarrollador activo → Copiar ID). Sin esto, nadie puede entrar al panel, y ningún servidor recibe Premium automático.
- `FLASK_SECRET_KEY` — cualquier cadena larga aleatoria.

## 2. Arrancar (bot + panel juntos, un solo comando)

```bash
python3 run.py
```

Esto arranca el bot de Discord y el panel web a la vez, en el mismo proceso. El panel queda disponible en **http://localhost:5000** (o el puerto que pongas en `PANEL_PORT`).

**Nota macOS:** si te sale error de certificados SSL, usa:
```bash
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
python3 run.py
```
(si `certifi` no está instalado en este venv: `pip3 install certifi` primero)

## 3. Desplegar en Railway (UN solo servicio)

1. Sube esta carpeta completa (bot + panel juntos) a un único repositorio de GitHub.
2. En Railway, crea un proyecto nuevo → "Deploy from GitHub repo" → elige ese repositorio. Railway detecta el `Procfile` (`web: python3 run.py`) automáticamente.
3. Añade un **Volume** persistente al servicio (pestaña "Volumes" del servicio → Add Volume), móntalo por ejemplo en `/data`.
4. En las variables de entorno del servicio, añade `DB_PATH=/data/antiraid.db` (además de todas las demás del `.env`).
5. Guarda y espera el deploy. A partir de ahora, bot y panel comparten de verdad el mismo archivo, y ese archivo sobrevive a cada redeploy gracias al Volume.

Ya no hace falta crear un segundo servicio para el bot: `run.py` arranca los dos.

---

## Qué puedes hacer desde el panel

- **Servidores** — lista de todos los servidores donde está el bot.
- **Configuración** (por servidor) — activar/desactivar anti-nuke/anti-spam/anti-raid, castigo automático, umbrales, canal de logs, rol automático (autorole).
- **Logs** — historial de incidentes detectados, con opción de borrarlo.
- **Embeds** — enviar un embed con tu marca a cualquier canal del servidor.
- **Whitelist** — usuarios y bots de confianza excluidos de los castigos automáticos.
- **Backups** — crear, restaurar y borrar copias de seguridad de canales/roles.
- **Global** — bloquear servidores o usuarios a nivel de todo el bot.

### Funciones Premium (de pago, vía Stripe)

- **Premium** — activar la suscripción del servidor (Stripe Checkout) y gestionarla (portal de facturación, cancelar, ver estado).
- **Comandos personalizados** — crear disparadores de texto con respuesta automática (solo servidores premium).
- **Perfil de bot** — apodo personalizado del bot en ese servidor (solo servidores premium).
- **Niveles** — XP por mensaje, subida de nivel automática, anuncio de subida de nivel, tabla de clasificación.
- **Sorteos** — crear sorteos con botón de participación, cierre automático o manual, elección de ganadores.
- **Tickets** — panel con botón para abrir tickets de soporte en canales privados, con cierre por staff.
- **Roles de reacción** — paneles con botones para que los miembros se autoasignen roles.

El dashboard principal muestra ahora una insignia 💎 junto a cada servidor con Premium activo, además del contador de tickets abiertos.

## Seguridad

- No expongas este panel a internet tal cual (está pensado para `localhost`). Si algún día quieres acceder desde fuera de tu casa, hazlo por una VPN o un túnel con autenticación adicional (ej. Cloudflare Tunnel con Access) — no lo publiques abierto en un puerto de tu router.
- `.env` nunca debe compartirse ni subirse a un repositorio.
- Si sospechas que tu `DISCORD_CLIENT_SECRET` se ha filtrado, resetéalo en el Developer Portal (OAuth2 → Reset Secret) y actualiza el `.env`.
