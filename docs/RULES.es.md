# Signal Hunt — reglas del juego

> Idiomas: [English](RULES.md) · [Русский](RULES.ru.md) · **Español** · [Français](RULES.fr.md) · [中文](RULES.zh.md)
> Guía completa: [Español](GUIDE.es.md)
> Terminología: [glosario de localización](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) (sección Signal Hunt)

## 1. Objetivo

Identificar la condición de una instantánea real de AIMarket, expresar confianza calibrada
y obtener la mayor puntuación reproducible. No existe juez humano oculto.

Signal Hunt es **también un laboratorio educativo**: cada ronda es una práctica en vivo
sobre telemetría federada, coste de evidencia, puntuación probabilística y compromisos
criptográficos — no una simulación con fixtures.

## 1.1 Valor educativo

Una ronda entrena habilidades que se trasladan al stack AIMarket / AICOM:

| Habilidad | Qué obliga a practicar el laboratorio |
|---|---|
| Leer el estado vivo de la federación | Manifest, fuentes, precios, roster de peers, sondas de latencia, procedencia — solo medido |
| Disciplina de evidencia | Abrir menos bloques conserva puntos; los datos tienen coste |
| Confianza calibrada | El skill de Brier premia la honestidad; la sobreconfianza se penaliza |
| Verificación criptográfica | Compromisos de respuesta y recálculo independiente del veredicto |
| Alfabetización de detectores | Umbrales nombrados (aislamiento, desaparición, churn de peers, clima de latencia, concentración, …) en orden declarado |
| Dinámica federada | Crecimiento, altas/bajas de peers, clima de latencia y precios cambian los diagnósticos |
| Prueba pública honesta | El relevo de héroes solo lleva órbitas firmadas y verificadas |

Léalo como **juego + curso de laboratorio**: el juego sostiene la atención; la matemática
reproducible y el Hub vivo son el temario.

## 2. Ronda

- Ventana predeterminada: 1.800 segundos (30 minutos), configurable con
  `SIGNAL_HUNT_ROUND_SECONDS`.
- La ronda se clavea por el state hash del campo, no por el reloj. Una ronda resuelta
  queda congelada; una no jugada puede refrescarse si snapshots posteriores cambian el diagnóstico.
- La tarjeta de misión pública permanece **sellada**: solo severity (`anomaly` / `calm`)
  y profundidad del baseline hasta el veredicto. La clase del detector se revela con la respuesta.
- Una sesión envía una vez; repetir devuelve el resultado almacenado.
- Se muestran cuatro diagnósticos. El orden puede usar entropía VRF remota firmada; una
  llamada no disponible se registra de forma explícita.
- La respuesta correcta se compromete antes de cualquier acción del jugador.

## 3. Precedencia del detector

Gana la primera condición cumplida:

1. **Federación aislada:** cero capabilities externas.
2. **Fuente desaparecida:** falta una fuente cuyo histórico mediano era al menos tres.
3. **Cambio de roster de peers:** el endpoint de peers está disponible y el roster medido
   cambió — un peer establecido (≥2 snapshots previos) salió y/ o un peer nuevo apareció
   con profundidad histórica ≥2. La desaparición de una fuente de capabilities es otra
   señal y tiene prioridad.
4. **Contracción:** al menos tres capabilities menos y 15% bajo la mediana histórica.
5. **Expansión:** al menos tres más y 15% sobre la mediana.
6. **Cambio de precio:** diferencia absoluta mínima `$0.001` y relativa mínima 20%.
7. **Clima de latencia:** al menos un peer tiene un RTT de sonda **medido con éxito** por
   encima de `500 ms`. Sondas fallidas/omitidas guardan `latency_ms = null` y no inventan clima.
8. **Concentración:** con dos fuentes o más, la mayor aporta al menos 60% **y esa
   dominancia es nueva frente al snapshot anterior**. La primera observación sin
   historial aún puede disparar. Un 60% persistente es `stable`.
9. **Estable:** no se cruzó ningún umbral declarado.

Sin historial suficiente, los umbrales históricos no pueden activarse. No hay baseline
sintético. El RTT se mide pidiendo `/.well-known/ai-market.json` del peer (con tope).

## 4. Evidencia

- **Distribución:** total externo y cantidad/cuota por fuente.
- **Cambio:** total actual, muestras históricas y mediana medida.
- **Precios:** agregados actuales y medianas históricas disponibles.
- **Roster:** peers de la federación (url, nombre, capabilities), altas/bajas vs historia.
- **Latencia:** RTT medidos, umbral (`500 ms`), conteo de lentos.
- **Procedencia:** URL, fechas, state hash, signer key y estados de peticiones.

Cada bloque distinto reduce el factor 0,05. Seis bloques producen 0,70 (el mínimo).
Reabrir un bloque no aplica otra penalización.

## 5. Confianza

Es la probabilidad del diagnóstico elegido, entre 0,25 y 1,00. El resto se divide entre
las otras tres opciones:

```text
r = (1 − confidence) / (K − 1), con K = 4
```

Las probabilidades devueltas suman uno.

## 6. Puntuación

```text
Brier = Σ(pᵢ − oᵢ)²
baseline = 1 − 1/K
skill = max(0, 1 − Brier / baseline)
evidence_factor = max(0.70, 1 − 0.05 × opened_evidence)
base_score = round(1000 × skill × evidence_factor)
```

**Segundo cierre** opcional (micropregunta sobre el mismo campo medido):

```text
follow_up_bonus = 150 si el follow-up es correcto; si no, 0
combined = base_score + follow_up_bonus
```

**Ventana PRIME:** los primeros 15 minutos de cada hora UTC. Las rondas creadas en PRIME
fijan `×1.5`:

```text
round_score = round(combined × (1.5 si prime_locked; si no, 1.0))
```

La confianza correcta puntúa alto. Una respuesta incorrecta y categórica se penaliza más
que una duda razonable. Adivinar 25% uniforme tiene skill cero. El API devuelve todos los
operandos para repetir el cálculo.

## 7. Reglas de engagement (en claro)

Estas mecánicas usan los mismos datos medidos del Hub. Nada se inventa «para el espectáculo».

### 7.1 Segundo cierre (doble jugada)

Tras elegir el diagnóstico puedes responder una micropregunta opcional del mismo
observatorio, por ejemplo:

- qué fuente lidera el campo,
- si el precio efectivo mediano subió / bajó / se mantuvo plano frente a la historia,
- en qué banda está el conteo externo de capabilities,
- qué peer medido es el más lento ahora (`latency_weather`),
- si el roster de peers entró / salió / ambos / se mantuvo (`peer_churn`).

Omitir está permitido. Un segundo cierre correcto suma **+150** a `base_score` **antes**
de PRIME. Diagnóstico correcto **y** follow-up correcto en la misma ronda desbloquean
**Doble cierre**.

### 7.2 Ventana PRIME

Cada hora UTC, los minutos **0–14** son PRIME (`×1.5`).

- El multiplicador se **fija al crear la ronda**.
- Enviar más tarde en una ronda nacida en PRIME sigue dando `×1.5`.
- Una ronda nacida fuera de PRIME permanece en `×1.0` aunque envíes durante una ventana
  caliente posterior.

### 7.3 Racha diaria y escudo

Jugar en días calendario UTC construye una **racha de retorno diaria**. Un **escudo** puede
cubrir exactamente un día perdido. Al llegar a tres días vivos puedes obtener **Guardián
de racha**. La UI muestra si la racha vive y si el escudo sigue disponible.

### 7.4 Presencia en vivo

La tarjeta de ronda muestra cuántas sesiones estuvieron activas hace poco y cuántas ya
resolvieron **esta** ronda. Son agregados reales de la base de datos, no una muchedumbre
simulada.

### 7.5 Pasaporte semanal de temporada

Cada semana ISO tiene su pasaporte:

| Objetivo | Insignia |
|---|---|
| 3 diagnósticos correctos distintos | Políglota de temporada |
| 3.000 de puntuación semanal | Cazador de temporada |
| 3 veredictos correctos en ventana PRIME | Corredor PRIME |

El progreso se reinicia con la semana ISO. Una **clasificación semanal** aparte ordena la
puntuación ganada en la semana actual.

### 7.6 Cliffhanger

Tras el veredicto se muestra cuándo abre la siguiente ventana de campo sellada. Es un
recordatorio del `expires_at` real de la ronda, no un teaser de anomalías inventadas.

### 7.7 Emisión Perfect Orbit

Con score ≥ 950 puedes enviar el resultado al feed firmado de héroes con un toque tras
activar el relevo público. El opt-in tardío también vale: resuelve en privado → activa el
relevo → emite. Los eventos automáticos por recompensas / score ≥ 900 siguen el §11.

## 8. Estados

| Estado | Puntos mínimos |
|---|---:|
| Observador estelar | 0 |
| Explorador | 500 |
| Analista de señales | 1.500 |
| Navegante del vacío | 3.500 |
| Guardián de constelaciones | 7.500 |
| Oráculo de la federación | 15.000 |

El estado es una función pura de puntos persistidos y no puede comprarse.

## 9. Reliquias

| Insignia | Predicado exacto |
|---|---|
| Primer contacto | Completar una ronda verificada |
| Mente calibrada | Brier actual ≤ 0,08 |
| Escaneo profundo | Acertar tras abrir las seis evidencias |
| Vector limpio | Acertar con puntuación ≥ 800 |
| Instinto de señal | Acertar sin evidencia y confianza ≥ 75% |
| Triple bloqueo | Alcanzar racha correcta de tres |
| Observador veterano | Completar cinco rondas verificadas |
| Órbita perfecta | Acertar con puntuación ≥ 950 |
| Doble cierre | Diagnóstico y follow-up correctos en una ronda |
| Guardián de racha | Racha diaria de retorno de tres (un escudo por hueco) |
| Políglota de temporada | ≥ 3 diagnósticos correctos distintos en la semana ISO |
| Cazador de temporada | ≥ 3.000 de puntuación semanal en la semana ISO |
| Corredor PRIME | ≥ 3 veredictos correctos en ventana PRIME en la semana ISO |

Cada insignia se guarda una sola vez. Son registros cosméticos, no dinero, tokens, NFT,
propiedad transferible ni promesa de valor externo.

## 10. Clasificación

Publica indicativo, puntos, rondas, aciertos, puesto y estado. Orden: puntos, aciertos,
menor Brier medio y hora de última partida más temprana. No publica tokens ni evidencia
privada.

Una **clasificación semanal** aparte suma la puntuación de la semana ISO actual.

## 11. Héroes

La difusión está desactivada por defecto. Tras consentimiento, una ronda futura que
abra una recompensa **o** sume ≥ 900 puntos crea como máximo un evento.

También puedes **emitir** con un toque un Perfect Orbit / score ≥ 950 tras activar el
relevo (incluido opt-in tardío tras un veredicto privado fuerte).

El feed se firma sobre bytes JSON canónicos con Ed25519. DIOSCURI rechaza feeds antiguos,
futuros, modificados o con clave incorrecta; la entrega posterior es idempotente por
separado en Discord y X.

## 12. Juego limpio

- No automatices envíos ni crees sesiones para manipular la clasificación.
- No uses tokens ajenos ni presentes un cliente/DB modificado como despliegue público.
- Se anima a verificar, revisar código y autoalojar.
- El operador puede excluir automatización y nombres abusivos, pero no cambiar la
  matemática persistida para favorecer a una persona.

## 13. Verificación independiente

```text
SHA256(round_id:answer_code:answer_salt) == answer_commitment
```

Después recalcula probabilidades, Brier, skill, evidence factor, bonus de follow-up,
multiplicador PRIME y score redondeado. Informa de un fallo con round ID y state hash,
nunca con el session token.
