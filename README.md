# Kids YouTube Jukebox

Una pequeña jukebox doméstica para buscar canciones de YouTube desde un móvil y escuchar solo su audio en la propia web. La miniatura se muestra como portada. El servidor funciona con FastAPI dentro de Podman; PostgreSQL conserva las búsquedas y reproducciones, y el móvil solo necesita un navegador en la misma red Wi-Fi.

La app usa **YouTube Data API v3** para buscar y **yt-dlp** para resolver la pista de audio. El backend la transmite al navegador sin guardar archivos de vídeo o audio en disco. No utiliza el reproductor embebido de YouTube ni necesita cuentas de usuario.

## Qué necesitas

- Un Mac con [Podman Desktop](https://podman-desktop.io/) o Podman instalado.
- Un proyecto de Google Cloud con **YouTube Data API v3** habilitada.
- Una clave de API de YouTube.
- El ordenador y el móvil conectados a la misma Wi-Fi.

## 1. Conseguir `YOUTUBE_API_KEY`

1. Abre [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto o selecciona uno existente.
3. En **APIs y servicios → Biblioteca**, busca y habilita **YouTube Data API v3**.
4. En **APIs y servicios → Credenciales**, elige **Crear credenciales → Clave de API**.
5. Copia la clave. Google recomienda restringirla; como mínimo, limita la clave a **YouTube Data API v3**. Si aplicas restricciones por IP, recuerda que las peticiones salen desde el ordenador que ejecuta el contenedor.

La API de búsqueda consume cuota del proyecto de Google. Si la cuota diaria se agota, la app mostrará el error recibido de YouTube.

## 2. Configurar el entorno

Desde la carpeta del proyecto:

```sh
cp .env.example .env
```

Edita `.env` y sustituye el valor de ejemplo:

```dotenv
YOUTUBE_API_KEY=tu_clave_real
YOUTUBE_REGION_CODE=ES
YOUTUBE_RELEVANCE_LANGUAGE=es
YOUTUBE_SAFE_SEARCH=none
YOUTUBE_MUSIC_ONLY=true
APP_PORT=8000
POSTGRES_DB=jukebox
POSTGRES_USER=jukebox
POSTGRES_PASSWORD=elige_una_contraseña_local
```

`.env` está excluido de Git para evitar publicar la clave.

## 3. Construir y ejecutar con Podman

Si usas Podman en macOS por primera vez, inicia su máquina virtual:

```sh
podman machine init
podman machine start
```

La forma recomendada levanta la app y PostgreSQL juntos, espera a que la base de datos esté preparada y crea automáticamente las tablas:

```sh
podman compose up --build -d
```

Comprueba el estado:

```sh
podman compose ps
```

La app escucha dentro del contenedor en `0.0.0.0`. En el propio Mac, abre [http://localhost:8000](http://localhost:8000).

Para ver los logs o detener el stack:

```sh
podman compose logs -f jukebox
podman compose down
```

Los datos permanecen en el volumen `postgres_data` al ejecutar `podman compose down`. Solo se eliminan si solicitas explícitamente borrar volúmenes.

### Ejecución sin PostgreSQL

La imagen todavía puede ejecutarse sola, pero el historial aparecerá desactivado:

```sh
podman build -t kids-youtube-jukebox .
podman run --rm --env-file .env -p 8000:8000 kids-youtube-jukebox
```

## 4. Abrirla desde el móvil

Busca la IP local del Mac. Normalmente la Wi-Fi es `en0`:

```sh
ipconfig getifaddr en0
```

Si no devuelve nada, prueba `ipconfig getifaddr en1` o mira **Ajustes del Sistema → Wi-Fi → Detalles → TCP/IP**. Si la dirección es, por ejemplo, `192.168.1.45`, abre esto en el navegador del móvil:

```text
http://192.168.1.45:8000
```

Ambos dispositivos deben estar en la misma Wi-Fi. Una red de invitados puede impedir que los dispositivos se vean entre sí.

## 5. Sacar el audio por un Amazon Echo

1. Di al Echo: **“Alexa, emparejar Bluetooth”**.
2. En el móvil, abre los ajustes de Bluetooth.
3. Selecciona el Echo en la lista de dispositivos.
4. Abre la jukebox y reproduce una canción. La portada aparece en el móvil y el audio se envía al Echo.

También se puede iniciar el emparejamiento desde la app Alexa, en **Dispositivos → Echo y Alexa → tu Echo → Dispositivos Bluetooth**. Los nombres exactos pueden variar según la versión del sistema.

## Configuración de las búsquedas

### Solo música

Con `YOUTUBE_MUSIC_ONLY=true`, la app añade `videoCategoryId=10` para intentar limitar los resultados a la categoría Música. Para buscar cualquier tipo de vídeo:

```dotenv
YOUTUBE_MUSIC_ONLY=false
```

Reinicia el contenedor después de cambiar `.env`.

### Safe Search

El valor predeterminado solicitado es:

```dotenv
YOUTUBE_SAFE_SEARCH=none
```

YouTube también acepta `moderate` y `strict`:

```dotenv
YOUTUBE_SAFE_SEARCH=strict
```

Este ajuste lo aplica YouTube a la búsqueda. La aplicación no implementa controles parentales propios.

## Historial persistente

PostgreSQL guarda:

- Cada consulta, su fecha, estado, número de resultados y configuración aplicada.
- Los vídeos devueltos por cada búsqueda, con posición, identificador, título, canal y miniatura.
- Cada canción que empieza a sonar, enlazada a la búsqueda original y con una instantánea de sus datos.

La sección plegable **Historial reciente** de la web muestra las últimas búsquedas y canciones reproducidas. También están disponibles:

- `GET /api/history?limit=20`
- `POST /api/playback`
- `GET /health`, que indica si PostgreSQL está conectado.

Las tablas se crean automáticamente al iniciar la aplicación. Para una copia de seguridad local del historial:

```sh
podman compose exec db pg_dump -U jukebox jukebox > jukebox-backup.sql
```

## Problemas frecuentes

### El móvil no conecta

- Comprueba primero que `http://localhost:8000` funciona en el Mac.
- Confirma que móvil y Mac están en la misma Wi-Fi y no en una red de invitados aislada.
- Revisa que usas la IP actual del Mac y el puerto correcto.
- macOS puede pedir permiso para aceptar conexiones entrantes; concédelo a Podman. Revisa también **Ajustes del Sistema → Red → Firewall**.
- Comprueba que la máquina de Podman está en marcha con `podman machine list`.

### PostgreSQL no está listo

- Ejecuta `podman compose ps` y comprueba que `db` está saludable.
- Revisa `podman compose logs db`.
- Confirma que `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` tienen valores coherentes en `.env`.
- Si cambias usuario o contraseña después del primer arranque, el volumen conserva las credenciales anteriores. Restaura los valores previos o crea un volumen nuevo solo si no necesitas conservar el historial.

### El puerto no está expuesto

El comando debe incluir `-p 8000:8000`. Compruébalo con:

```sh
podman port kids-youtube-jukebox
```

### La app escucha en `127.0.0.1`

Dentro del contenedor Uvicorn debe escuchar en `0.0.0.0`. El `Containerfile` incluido ya lo configura. En los logs debe aparecer `Uvicorn running on http://0.0.0.0:8000`.

### Falta la API key

Si ves `Falta YOUTUBE_API_KEY`, revisa que `.env` existe, contiene una clave real y que arrancaste con `--env-file .env`. Tras editarlo, recrea el contenedor.

### El audio no empieza hasta tocar la pantalla

Es una protección normal de los navegadores móviles contra la reproducción automática. Pulsa **Reproducir** en un resultado o **Reanudar** si el navegador ha dejado la pista preparada.

### Una canción no tiene audio disponible

`yt-dlp` resuelve cada pista en el momento de reproducirla. Algunos vídeos privados, eliminados, restringidos por edad o bloqueados geográficamente pueden fallar; elige otro resultado y consulta `podman logs kids-youtube-jukebox` si el problema se repite con todas las canciones.

### YouTube rechaza la búsqueda

Revisa que YouTube Data API v3 esté habilitada, que la clave no tenga restricciones incompatibles y que el proyecto conserve cuota. Consulta los logs con:

```sh
podman logs kids-youtube-jukebox
```

## Desarrollo local sin contenedor

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port "${APP_PORT:-8000}"
```

La ruta `GET /api/search?q=Frozen%20libre%20soy` devuelve el identificador de la búsqueda persistida y como máximo diez objetos con `video_id`, `title`, `channel_title` y `thumbnail_url`. La ruta `GET /api/audio/{video_id}` resuelve y transmite la pista seleccionada con soporte para peticiones parciales (`Range`).

## Referencias oficiales

- [YouTube Data API: `search.list`](https://developers.google.com/youtube/v3/docs/search/list)
- [yt-dlp: uso desde Python y selección de formatos](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)
- [Podman: publicar puertos con `--publish`](https://docs.podman.io/en/latest/markdown/podman-run.1.html#publish-p-ip-hostport-containerport-protocol)
