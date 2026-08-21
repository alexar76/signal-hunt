# Signal Hunt — guía completa

> Idiomas: [English](GUIDE.md) · [Русский](GUIDE.ru.md) · **Español** · [Français](GUIDE.fr.md) · [中文](GUIDE.zh.md)
> Reglas: [English](RULES.md) · [Русский](RULES.ru.md) · [Español](RULES.es.md) · [Français](RULES.fr.md) · [中文](RULES.zh.md)

## 1. Qué es Signal Hunt

Signal Hunt es un juego de investigación nativo de la federación **y un laboratorio
educativo**. Cada ronda nace de una instantánea real de un Hub AIMarket normal:
capabilities externas indexadas, distribución por fuente, precios efectivos, identidad
firmada e historial guardado. El jugador examina evidencia, elige un diagnóstico y
declara su confianza.

Léalo como un **curso de laboratorio envuelto en un juego**: el bucle entretiene, pero
el temario es alfabetización federada en vivo — leer telemetría del Hub, pagar por
evidencia, calibrar confianza con Brier, verificar compromisos criptográficos y ver cómo
el crecimiento, las altas/bajas de peers y el clima de latencia cambian los diagnósticos.

No es un panel simulado. Si el Hub no puede medirse, el juego declara indisponibilidad en
lugar de usar fixtures. La historia o los precios ausentes siguen siendo datos ausentes.

### Resultados educativos

Tras varias rondas, un jugador atento debería poder:

1. Explicar una observación del Hub desde fuentes medidas, no desde especulación.
2. Equilibrar el coste de evidencia frente a la puntuación con el evidence factor publicado.
3. Declarar una confianza que sobreviva al Brier en lugar de fingir certeza.
4. Recalcular un veredicto a partir de sal, compromiso y operandos devueltos.
5. Relacionar clases de detector (aislamiento, desaparición, churn de peers, clima de
   latencia, concentración, …) con la dinámica real de catálogo, roster y latencia al
   crecer la federación.

## 2. Servicios del servidor

El despliegue de producción contiene PostgreSQL, un Hub AIMarket ordinario, el motor del
juego y Caddy como entrada TLS. Un bootstrap registra cinco capabilities locales:

| Capability | Función |
|---|---|
| `signal.case@v1` | Investigación actual e inmutable |
| `signal.evidence@v1` | Revelar un bloque de evidencia comprometido |
| `signal.submit@v1` | Verificar diagnóstico y calcular puntuación |
| `signal.leaderboard@v1` | Ranking derivado de veredictos persistidos |
| `signal.heroes@v1` | Hitos públicos voluntarios y firmados |

La aleatoriedad general no se copia localmente. Cuando existe, el motor descubre
`sortes.draw@v1` mediante su Hub y guarda ruta, Hub fuente, receipt nonce y result hash.
Un fallo queda como `unavailable`; nunca se presenta como llamada exitosa.

## 3. Recorrido del jugador

1. **Observar.** Se muestran Hub medido, fuentes, cantidades, latencia del manifest,
   identificador de observación y state hash.
2. **Investigar.** Hay seis bloques: distribución, evolución, precios, roster de peers,
   superficie de latencia y procedencia.
3. **Decidir.** Se elige un diagnóstico entre cuatro, opcionalmente el segundo cierre
   (follow-up) y una confianza del 25–100%.
4. **Verificar.** El servidor revela la sal, verifica el commitment, aplica el bonus de
   follow-up y el multiplicador PRIME fijado, guarda un veredicto inmutable y muestra el
   cliffhanger de la siguiente ventana.
5. **Progresar.** Los puntos fijan el estado; la racha diaria, el pasaporte semanal y
   predicados explícitos abren reliquias. Las órbitas fuertes se pueden emitir con un
   toque tras el opt-in. No se acuña nada ni se promete valor financiero.

Consulta [las reglas completas](RULES.es.md) (§6–7 para puntuación y engagement).

## 4. Verdad y procedencia

Cada observación guarda fecha upstream y local, URL y signer key del Hub, cantidades por
fuente, agregados de precio, estado de peticiones y state hash canónico. Una ronda apunta
a esa observación inmutable; datos nuevos no cambian su evidencia.

El diagnóstico se obtiene por umbrales deterministas declarados. Antes de exponer la
ronda el motor genera una sal y publica:

```text
SHA256(round_id:answer_code:answer_salt)
```

Respuesta y sal se revelan con el veredicto. Cualquier persona puede recomputar el
commitment y todos los operandos de puntuación.

## 5. Identidad, privacidad y héroes

El juego es anónimo por defecto. El navegador recibe un token opaco firmado y lo guarda
en el dispositivo. No requiere wallet, correo ni acceso social; las tablas del juego no
guardan IP sin procesar.

La difusión pública está desactivada y solo afecta a hitos futuros tras consentimiento
explícito. El feed contiene indicativo, estadísticas agregadas verificadas, códigos de
recompensa y referencias de prueba; excluye token, IP y evidencia privada.

DIOSCURI extrae el feed y verifica la clave Ed25519 fijada por el operador. Discord y X
tienen estado de entrega independiente. El juego nunca almacena credenciales sociales.

## 6. API HTTP

| Método | Ruta | Acceso |
|---|---|---|
| `POST` | `/api/v1/session` | público |
| `GET`, `PUT` | `/api/v1/profile` | bearer session |
| `GET` | `/api/v1/rounds/live` | bearer session |
| `GET` | `/api/v1/rounds/{id}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/evidence/{evidence}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/submit` | bearer session |
| `POST` | `/api/v1/rounds/{id}/broadcast` | bearer session |
| `GET` | `/api/v1/leaderboard` | público |
| `GET` | `/api/v1/leaderboard/weekly` | público |
| `GET` | `/api/v1/heroes/feed` | público, payload firmado |
| `GET` | `/provider/public-key` | público |
| `POST` | `/provider/invoke` | superficie provider AIMarket |

## 7. Desarrollo local

Inicia primero un Hub AIMarket y después backend e interfaz:

```bash
cd signal-hunt
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
SIGNAL_HUNT_HUB_URL=http://127.0.0.1:9183 .venv/bin/python -m signal_hunt.main
```

```bash
cd signal-hunt/frontend
npm ci
npm run dev
```

La página falla de forma explícita si el Hub configurado no ofrece un manifest válido.

## 8. Producción

1. Apunta DNS A/AAAA al servidor y abre TCP 80/443 y UDP 443.
2. Copia `.env.example` como `.env`.
3. Genera por separado `AIMARKET_ADMIN_TOKEN` y `POSTGRES_PASSWORD`.
4. Verifica las claves públicas seed por un canal independiente.
5. Ejecuta `scripts/deploy.sh`.
6. Desde una máquina confiable ejecuta `scripts/register-upstream.sh` para anunciar,
   aprobar y rastrear el Hub nuevo.
7. Ejecuta `scripts/verify.sh https://<dominio-signal-hunt>`.

Solo Caddy publica puertos. Las claves de Hub/provider deben respaldarse junto con
PostgreSQL y el estado del juego.

## 9. Operación y fallos

- `503 federation_unavailable`: no se pudo formar una ronda viva válida.
- Baseline `null`: falta historial medido; no significa cambio cero.
- `federation_assist.status=unavailable`: degradación honesta sin afirmar que hubo VRF.
- Repetir un envío devuelve el veredicto guardado y no crea otra recompensa.
- Perder una clave cambia la identidad y exige recuperar la confianza.
- Un error del relay aparece en `/health` de DIOSCURI y no bloquea el juego.

## 10. Verificación y contribución

```bash
cd signal-hunt && pytest -q
cd frontend && npm run build
```

GitHub Actions ejecuta pytest de Signal Hunt, el build del frontend y `docker compose config`.
El contrato de firma DIOSCURI del hero feed se cubre en los tests del paquete DIOSCURI del monorepo.
El código se distribuye bajo [MIT](../LICENSE). Un cambio de puntuación, precedencia o
recompensas debe actualizar pruebas y reglas en los cinco idiomas.
