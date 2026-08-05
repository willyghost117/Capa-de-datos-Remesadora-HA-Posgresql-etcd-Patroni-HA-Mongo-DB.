const scenarios = {
  remittance: {
    title: "Nueva remesa",
    summaryLabel: "OBJETIVO",
    summaryValue: "Confirmar sin doble escritura",
    summaryCopy: "La remesa y el evento Outbox se confirman en una sola transacción.",
    metricA: ["Autoridad", "PostgreSQL"],
    metricB: ["Entrega", "Idempotente"],
    steps: [
      { node: "channel", line: null, text: "El usuario inicia una remesa con contexto del canal." },
      { node: "api", line: "line-channel-api", text: "La API valida identidad, límites, KYC y AML." },
      { node: "proxy", line: "line-api-proxy", text: "HAProxy dirige la escritura al líder actual." },
      { node: "postgres", line: "line-proxy-pg", text: "PostgreSQL confirma remesa, movimientos y Outbox." },
      { node: "outbox", line: "line-pg-outbox", text: "El publicador lee el evento pendiente de forma idempotente." },
      { node: "mongo", line: "line-outbox-mongo", text: "MongoDB actualiza la proyección analítica." },
      { node: "products", line: "line-mongo-products", text: "Fraude, cumplimiento y operaciones consumen el producto." }
    ]
  },
  fraud: {
    title: "Alerta de fraude",
    summaryLabel: "RESPUESTA",
    summaryValue: "Señal explicable, decisión gobernada",
    summaryCopy: "La analítica detecta la señal; la acción financiera regresa a la autoridad transaccional.",
    metricA: ["Señales de prueba", "223"],
    metricB: ["Decisión monetaria", "PostgreSQL"],
    steps: [
      { node: "mongo", line: null, text: "Una proyección analítica presenta un patrón anómalo." },
      { node: "products", line: "line-mongo-products", text: "El motor de fraude genera una señal trazable." },
      { node: "api", line: "line-products-loop", text: "La señal vuelve al servicio como una solicitud controlada." },
      { node: "proxy", line: "line-api-proxy", text: "HAProxy mantiene el punto estable hacia el líder." },
      { node: "postgres", line: "line-proxy-pg", text: "PostgreSQL registra revisión, bloqueo o decisión autorizada." },
      { node: "outbox", line: "line-pg-outbox", text: "La decisión produce un nuevo evento auditable." },
      { node: "mongo", line: "line-outbox-mongo", text: "La vista analítica queda actualizada sin asumir autoridad." }
    ]
  },
  postgres: {
    title: "Failover PostgreSQL",
    summaryLabel: "CONTINUIDAD OBSERVADA",
    summaryValue: "≈45 segundos",
    summaryCopy: "Patroni promueve una réplica y HAProxy conserva el mismo punto de conexión.",
    metricA: ["RPO observado", "0 min*"],
    metricB: ["Alcance", "Un host"],
    steps: [
      { node: "postgres", line: null, state: "failed", text: "Se aísla el líder PostgreSQL durante el ejercicio de resiliencia." },
      { node: "proxy", line: "line-proxy-pg", state: "warning", text: "HAProxy retira temporalmente el destino no saludable." },
      { node: "postgres", line: "line-proxy-pg", state: "warning", text: "Patroni y etcd coordinan la elección de una réplica." },
      { node: "postgres", line: "line-proxy-pg", text: "pg2 asume el rol de líder y acepta escrituras." },
      { node: "proxy", line: "line-api-proxy", text: "El endpoint estable vuelve a enrutar al nuevo líder." },
      { node: "api", line: "line-channel-api", text: "La API reanuda el procesamiento sin cambiar su configuración." }
    ],
    pgRole: "pg2 líder · pg1 detenido · pg3 réplica"
  },
  mongo: {
    title: "Failover MongoDB",
    summaryLabel: "CONTINUIDAD OBSERVADA",
    summaryValue: "≈8 segundos",
    summaryCopy: "El conjunto elige un nuevo primario y conserva los productos ya replicados.",
    metricA: ["RPO observado", "0 min*"],
    metricB: ["Reingreso", "Como secundario"],
    steps: [
      { node: "mongo", line: null, state: "failed", text: "Se detiene mongo1, primario del conjunto." },
      { node: "outbox", line: "line-outbox-mongo", state: "warning", text: "El publicador conserva el evento para reintento." },
      { node: "mongo", line: "line-outbox-mongo", state: "warning", text: "Los secundarios ejecutan una nueva elección." },
      { node: "mongo", line: "line-outbox-mongo", text: "mongo2 queda como primario del conjunto." },
      { node: "products", line: "line-mongo-products", text: "Las consultas analíticas reanudan su servicio." },
      { node: "mongo", line: "line-outbox-mongo", text: "mongo1 regresa posteriormente como secundario." }
    ],
    mongoRole: "mongo2 primario · mongo1/mongo3 secundarios"
  }
};

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const architecture = document.querySelector("#architecture");
const scenarioButtons = [...document.querySelectorAll(".scenario-button")];
const playButton = document.querySelector("#play-button");
const resetButton = document.querySelector("#reset-button");
const eventLog = document.querySelector("#event-log");
const eventBadge = document.querySelector("#event-badge");
const pgRole = document.querySelector("#pg-role");
const mongoRole = document.querySelector("#mongo-role");

let activeScenario = "remittance";
let runToken = 0;

function resetVisualState() {
  runToken += 1;
  architecture.querySelectorAll(".node").forEach((node) => {
    node.classList.remove("is-active", "is-warning", "is-failed");
  });
  architecture.querySelectorAll(".connections path").forEach((line) => {
    line.classList.remove("is-active", "is-warning");
  });
  pgRole.textContent = "pg1 líder · pg2/pg3 réplicas";
  mongoRole.textContent = "mongo1 primario · 2 secundarios";
  eventBadge.textContent = "LISTO";
  eventBadge.className = "event-badge";
  playButton.disabled = false;
}

function renderIntroLog() {
  eventLog.innerHTML = `
    <li class="is-current">
      <time>00:00</time>
      <span>Escenario preparado. Inicie la simulación.</span>
    </li>
  `;
}

function selectScenario(key) {
  activeScenario = key;
  const scenario = scenarios[key];
  resetVisualState();
  renderIntroLog();

  document.querySelector("#active-title").textContent = scenario.title;
  document.querySelector("#summary-label").textContent = scenario.summaryLabel;
  document.querySelector("#summary-value").textContent = scenario.summaryValue;
  document.querySelector("#summary-copy").textContent = scenario.summaryCopy;
  document.querySelector("#metric-a-label").textContent = scenario.metricA[0];
  document.querySelector("#metric-a-value").textContent = scenario.metricA[1];
  document.querySelector("#metric-b-label").textContent = scenario.metricB[0];
  document.querySelector("#metric-b-value").textContent = scenario.metricB[1];

  scenarioButtons.forEach((button) => {
    const selected = button.dataset.scenario === key;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function timestamp(index) {
  return `00:${String((index + 1) * 2).padStart(2, "0")}`;
}

function addLogEntry(index, text) {
  eventLog.querySelectorAll("li").forEach((item) => item.classList.remove("is-current"));
  const item = document.createElement("li");
  item.className = "is-current";
  item.innerHTML = `<time>${timestamp(index)}</time><span></span>`;
  item.querySelector("span").textContent = text;
  eventLog.append(item);
  eventLog.scrollTop = eventLog.scrollHeight;
}

function activateStep(step) {
  architecture.querySelectorAll(".node").forEach((node) => {
    node.classList.remove("is-active", "is-warning", "is-failed");
  });

  const node = architecture.querySelector(`[data-node="${step.node}"]`);
  if (node) {
    if (step.state === "failed") node.classList.add("is-failed");
    else if (step.state === "warning") node.classList.add("is-warning");
    else node.classList.add("is-active");
  }

  if (step.line) {
    const line = document.querySelector(`#${step.line}`);
    if (line) {
      line.classList.add(step.state === "warning" || step.state === "failed" ? "is-warning" : "is-active");
    }
  }
}

async function playScenario() {
  const scenario = scenarios[activeScenario];
  resetVisualState();
  const token = runToken;
  eventLog.innerHTML = "";
  playButton.disabled = true;
  eventBadge.textContent = "EN CURSO";
  eventBadge.className = "event-badge is-running";

  for (let index = 0; index < scenario.steps.length; index += 1) {
    if (token !== runToken) return;
    const step = scenario.steps[index];
    activateStep(step);
    addLogEntry(index, step.text);
    await delay(720);
  }

  if (token !== runToken) return;
  if (scenario.pgRole) pgRole.textContent = scenario.pgRole;
  if (scenario.mongoRole) mongoRole.textContent = scenario.mongoRole;
  eventBadge.textContent = "COMPLETADO";
  eventBadge.className = "event-badge";
  playButton.disabled = false;
}

scenarioButtons.forEach((button) => {
  button.addEventListener("click", () => selectScenario(button.dataset.scenario));
});

playButton.addEventListener("click", playScenario);
resetButton.addEventListener("click", () => {
  resetVisualState();
  renderIntroLog();
});

selectScenario(activeScenario);
