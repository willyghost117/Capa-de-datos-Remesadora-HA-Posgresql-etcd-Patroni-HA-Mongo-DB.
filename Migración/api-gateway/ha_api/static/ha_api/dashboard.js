const POLL_INTERVAL_MS = 2000;
const REMITTANCE_REFRESH_EVERY = 5;
const TRACE_POLL_INTERVAL_MS = 700;
const TRACE_WINDOW_MS = 30000;

const ui = {
  body: document.body,
  overall: document.querySelector("#overall-label"),
  lastUpdated: document.querySelector("#last-updated"),
  pgLeader: document.querySelector("#pg-leader"),
  mongoPrimary: document.querySelector("#mongo-primary"),
  writerEndpoint: document.querySelector("#writer-endpoint"),
  remittanceCount: document.querySelector("#remittance-count"),
  pgCluster: document.querySelector(".postgres-cluster"),
  pgClusterState: document.querySelector("#pg-cluster-state"),
  mongoCluster: document.querySelector(".mongo-cluster"),
  mongoClusterState: document.querySelector("#mongo-cluster-state"),
  haproxy: document.querySelector("#haproxy-node"),
  etcd: document.querySelector("#etcd-state"),
  timeline: document.querySelector("#event-timeline"),
  clearTimeline: document.querySelector("#clear-timeline"),
  remittancesBody: document.querySelector("#remittances-body"),
  insertButton: document.querySelector("#insert-remittance"),
  refreshButton: document.querySelector("#refresh-now"),
  autoRefresh: document.querySelector("#auto-refresh"),
  operationPanel: document.querySelector("#operation-panel"),
  operationTitle: document.querySelector("#operation-title"),
  operationMessage: document.querySelector("#operation-message"),
  operationAttempts: document.querySelector("#operation-attempts"),
  operationElapsed: document.querySelector("#operation-elapsed"),
  operationServer: document.querySelector("#operation-server"),
  operationJson: document.querySelector("#operation-json"),
  traceSection: document.querySelector("#trace-section"),
  traceRemittance: document.querySelector("#trace-remittance"),
  traceEvent: document.querySelector("#trace-event"),
  traceLsn: document.querySelector("#trace-lsn"),
  traceDetail: document.querySelector("#trace-detail"),
};

const state = {
  previous: null,
  polling: false,
  pollCount: 0,
  timer: null,
  insertionRunning: false,
  insertionTimer: null,
  insertionStarted: null,
  lastError: null,
  traceToken: 0,
  traceStages: {},
};

function localTime(value = new Date()) {
  return new Intl.DateTimeFormat("es-GT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(value);
}

function shortName(value) {
  if (!value) return "No disponible";
  return value
    .replace("globalremit-patroni-", "")
    .replace("globalremit-", "")
    .replace(":27017", "");
}

function stateLabel(value) {
  const labels = {
    operational: "OPERATIVO",
    degraded: "DEGRADADO",
    critical: "CRÍTICO",
    electing: "EN ELECCIÓN",
    offline: "SIN SERVICIO",
    unknown: "DESCONOCIDO",
  };
  return labels[value] || String(value || "desconocido").toUpperCase();
}

function roleLabel(role, healthy) {
  if (!healthy) return "CAÍDO";
  const labels = {
    leader: "LÍDER",
    replica: "RÉPLICA",
    primary: "PRIMARY",
    secondary: "SECONDARY",
    arbiter: "ÁRBITRO",
    unknown: "RECUPERANDO",
  };
  return labels[role] || String(role || "desconocido").toUpperCase();
}

function addTimeline(source, message, tone = "info") {
  const initial = ui.timeline.querySelector("li time")?.textContent === "--:--:--";
  if (initial) ui.timeline.innerHTML = "";

  const item = document.createElement("li");
  item.dataset.tone = tone;
  const time = document.createElement("time");
  time.textContent = localTime();
  const content = document.createElement("div");
  const label = document.createElement("strong");
  label.textContent = source;
  const copy = document.createElement("span");
  copy.textContent = message;
  content.append(label, copy);
  item.append(time, content);
  ui.timeline.prepend(item);

  while (ui.timeline.children.length > 35) {
    ui.timeline.lastElementChild.remove();
  }
}

function setOverall(value) {
  ui.overall.textContent = stateLabel(value);
  ui.overall.className = `status-label status-${value || "unknown"}`;
}

function renderMember(selector, node) {
  const member = document.querySelector(selector);
  if (!member) return;
  member.dataset.health = node.healthy ? "up" : "down";
  member.dataset.role = node.role || "unknown";
  member.querySelector(".member-role").textContent = roleLabel(node.role, node.healthy);
  member.title = node.healthy
    ? `${node.name}: ${node.state} · ${roleLabel(node.role, true)}`
    : `${node.name}: no disponible`;
}

function renderTopology(data) {
  setOverall(data.overall);
  ui.lastUpdated.textContent = `Última lectura ${localTime(new Date(data.generated_at))}`;
  ui.pgLeader.textContent = shortName(data.postgres.leader);
  ui.mongoPrimary.textContent = shortName(data.mongodb.primary);

  const endpoint = data.postgres.endpoint;
  ui.writerEndpoint.textContent = endpoint.healthy ? "HAProxy :5432 · disponible" : "HAProxy :5432 · sin líder";
  ui.remittanceCount.textContent = endpoint.total_remittances ?? "—";
  ui.haproxy.dataset.health = endpoint.healthy ? "up" : "down";
  ui.haproxy.querySelector(".node-state").textContent = endpoint.healthy ? "ENRUTANDO AL LÍDER" : "ESPERANDO LÍDER";

  ui.pgCluster.dataset.state = data.postgres.state;
  ui.pgClusterState.textContent = stateLabel(data.postgres.state);
  for (const node of data.postgres.nodes) {
    renderMember(`[data-pg-node="${node.name}"]`, node);
  }

  const etcd = data.postgres.coordinator;
  ui.etcd.dataset.health = etcd.healthy ? "up" : "down";
  ui.etcd.textContent = etcd.healthy ? "etcd · coordinando" : "etcd · no disponible";

  ui.mongoCluster.dataset.state = data.mongodb.state;
  ui.mongoClusterState.textContent = stateLabel(data.mongodb.state);
  for (const node of data.mongodb.nodes) {
    renderMember(`[data-mongo-node="${node.name}"]`, node);
  }
}

function nodeMap(nodes) {
  return new Map(nodes.map((node) => [node.name, node]));
}

function describeChanges(previous, current) {
  if (!previous) {
    addTimeline(
      "LABORATORIO",
      `Conectado. ${shortName(current.postgres.leader)} es líder PostgreSQL y ${shortName(current.mongodb.primary)} es PRIMARY MongoDB.`,
      current.overall === "operational" ? "success" : "warning",
    );
    return;
  }

  if (previous.overall !== current.overall) {
    const tone = current.overall === "operational" ? "success" : current.overall === "critical" ? "danger" : "warning";
    addTimeline("PLATAFORMA", `Estado general: ${stateLabel(previous.overall)} → ${stateLabel(current.overall)}.`, tone);
  }

  if (previous.postgres.leader !== current.postgres.leader) {
    if (!current.postgres.leader) {
      addTimeline("PATRONI", "No hay líder PostgreSQL confirmado; el clúster está coordinando la elección.", "warning");
    } else {
      addTimeline("PATRONI", `${shortName(current.postgres.leader)} fue confirmado como nuevo líder PostgreSQL.`, "success");
    }
  }

  if (previous.postgres.endpoint.healthy !== current.postgres.endpoint.healthy) {
    addTimeline(
      "HAPROXY",
      current.postgres.endpoint.healthy
        ? "El endpoint estable volvió a aceptar escrituras."
        : "El destino de escritura no está disponible mientras cambia el líder.",
      current.postgres.endpoint.healthy ? "success" : "warning",
    );
  }

  if (previous.postgres.coordinator.healthy !== current.postgres.coordinator.healthy) {
    addTimeline(
      "ETCD",
      current.postgres.coordinator.healthy ? "El coordinador distribuido responde." : "El coordinador distribuido no responde.",
      current.postgres.coordinator.healthy ? "success" : "danger",
    );
  }

  const previousPg = nodeMap(previous.postgres.nodes);
  for (const node of current.postgres.nodes) {
    const before = previousPg.get(node.name);
    if (before && before.healthy !== node.healthy) {
      addTimeline(
        "POSTGRESQL",
        node.healthy ? `${shortName(node.name)} volvió como ${roleLabel(node.role, true)}.` : `${shortName(node.name)} dejó de responder.`,
        node.healthy ? "success" : "danger",
      );
    } else if (before && before.role !== node.role && node.healthy) {
      addTimeline("POSTGRESQL", `${shortName(node.name)} cambió de ${roleLabel(before.role, true)} a ${roleLabel(node.role, true)}.`, "info");
    }
  }

  if (previous.mongodb.primary !== current.mongodb.primary) {
    if (!current.mongodb.primary) {
      addTimeline("MONGODB", "El Replica Set está eligiendo un nuevo PRIMARY.", "warning");
    } else {
      addTimeline("MONGODB", `${shortName(current.mongodb.primary)} fue elegido como PRIMARY.`, "success");
    }
  }

  const previousMongo = nodeMap(previous.mongodb.nodes);
  for (const node of current.mongodb.nodes) {
    const before = previousMongo.get(node.name);
    if (before && before.healthy !== node.healthy) {
      addTimeline(
        "MONGODB",
        node.healthy ? `${shortName(node.name)} volvió como ${roleLabel(node.role, true)}.` : `${shortName(node.name)} dejó de responder.`,
        node.healthy ? "success" : "danger",
      );
    } else if (before && before.role !== node.role && node.healthy) {
      addTimeline("MONGODB", `${shortName(node.name)} cambió de ${roleLabel(before.role, true)} a ${roleLabel(node.role, true)}.`, "info");
    }
  }
}

async function refreshTopology() {
  if (state.polling) return;
  state.polling = true;
  ui.body.classList.add("is-polling");
  try {
    const response = await fetch("/api/topology/", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    describeChanges(state.previous, data);
    renderTopology(data);
    state.previous = data;
    state.lastError = null;
    state.pollCount += 1;
    if (state.pollCount === 1 || state.pollCount % REMITTANCE_REFRESH_EVERY === 0) {
      await refreshRemittances();
    }
  } catch (error) {
    setOverall("critical");
    ui.lastUpdated.textContent = "Sin telemetría del backend";
    if (state.lastError !== String(error)) {
      addTimeline("DJANGO", `No fue posible consultar la topología: ${error}.`, "danger");
      state.lastError = String(error);
    }
  } finally {
    state.polling = false;
    ui.body.classList.remove("is-polling");
  }
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value ?? "—";
  row.append(cell);
}

function renderRemittances(remittances) {
  ui.remittancesBody.innerHTML = "";
  if (!remittances.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "empty-row";
    cell.textContent = "No hay remesas registradas.";
    row.append(cell);
    ui.remittancesBody.append(row);
    return;
  }

  for (const remittance of remittances) {
    const row = document.createElement("tr");
    appendCell(row, remittance.remittance_id);
    appendCell(row, remittance.remittance_code);
    appendCell(row, remittance.corridor);
    appendCell(row, `${remittance.send_amount} ${remittance.send_currency}`);
    appendCell(row, `${remittance.payout_amount} ${remittance.payout_currency}`);
    appendCell(row, remittance.status);
    appendCell(row, new Date(remittance.created_at).toLocaleString("es-GT"));
    ui.remittancesBody.append(row);
  }
}

async function refreshRemittances() {
  try {
    const response = await fetch("/api/events/", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderRemittances(data.remittances || []);
  } catch (error) {
    if (!ui.remittancesBody.querySelector("tr:not(:only-child)")) {
      ui.remittancesBody.innerHTML = '<tr><td colspan="7" class="empty-row">Esperando un líder PostgreSQL disponible…</td></tr>';
    }
  }
}

function startOperationClock() {
  clearInterval(state.insertionTimer);
  state.insertionStarted = Date.now();
  state.insertionTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.insertionStarted) / 1000);
    ui.operationElapsed.textContent = `${elapsed} s`;
    if (elapsed > 5) {
      ui.operationMessage.textContent = "La solicitud continúa activa. Django reintentará mientras Patroni completa la elección.";
    }
  }, 1000);
}

function stopOperationClock() {
  clearInterval(state.insertionTimer);
  state.insertionTimer = null;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function traceTone(status) {
  if (status === "done") return "success";
  if (status === "error") return "danger";
  if (status === "active" || status === "partial") return "warning";
  return "info";
}

function traceSource(stageId) {
  const sources = {
    django: "DJANGO",
    haproxy: "HAPROXY",
    postgres: "POSTGRESQL",
    audit: "AUDITORÍA",
    replication: "WAL",
    outbox: "OUTBOX",
    mongodb: "MONGODB",
    analytics: "ANALÍTICA",
  };
  return sources[stageId] || stageId.toUpperCase();
}

function resetTraceVisuals(result) {
  state.traceStages = {};
  ui.traceSection.hidden = false;
  ui.traceRemittance.textContent = result.remittance_code || `Remesa ${result.remittance_id}`;
  ui.traceEvent.textContent = `event_id ${result.event_id}`;
  ui.traceLsn.textContent = `LSN ${result.commit_lsn || "pendiente"}`;
  ui.traceDetail.textContent = "Correlacionando la transacción con los nodos del laboratorio…";
  document.querySelectorAll("[data-trace-stage]").forEach((element) => {
    element.dataset.status = "waiting";
    element.querySelector("small").textContent = "Esperando evidencia";
  });
  document.querySelectorAll("[data-trace-node], [data-trace-link]").forEach((element) => {
    delete element.dataset.traceStatus;
  });
  document.querySelectorAll(".member-proof").forEach((element) => {
    element.textContent = "Esperando evidencia";
  });
}

function renderTraceStage(stage) {
  const element = document.querySelector(`[data-trace-stage="${stage.id}"]`);
  if (!element) return;
  element.dataset.status = stage.status;
  element.querySelector("small").textContent = stage.detail;

  const prior = state.traceStages[stage.id];
  if (prior !== stage.status && stage.status !== "waiting") {
    addTimeline(traceSource(stage.id), stage.detail, traceTone(stage.status));
    state.traceStages[stage.id] = stage.status;
  }

  const flowNode = document.querySelector(`[data-trace-node="${stage.id}"]`);
  const flowLink = document.querySelector(`[data-trace-link="${stage.id}"]`);
  const visualStatus = stage.status === "done" ? "done" : stage.status === "waiting" ? "active" : stage.status;
  if (flowNode) flowNode.dataset.traceStatus = visualStatus;
  if (flowLink) flowLink.dataset.traceStatus = visualStatus;
}

function renderPostgresProof(nodes, commitLsn) {
  for (const node of nodes) {
    const member = document.querySelector(`[data-pg-node="${node.name}"]`);
    if (!member) continue;
    const proof = member.querySelector(".member-proof");
    if (!node.healthy) {
      proof.textContent = "SIN RESPUESTA";
    } else if (node.role === "leader") {
      proof.textContent = `COMMIT ${commitLsn || node.replay_lsn || "confirmado"}`;
    } else if (node.caught_up) {
      proof.textContent = `WAL ${node.replay_lsn} · CONFIRMADO`;
    } else {
      proof.textContent = `WAL ${node.replay_lsn || "pendiente"}`;
    }
  }
}

function renderMongoProof(nodes) {
  for (const node of nodes) {
    const member = document.querySelector(`[data-mongo-node="${node.name}"]`);
    if (!member) continue;
    const proof = member.querySelector(".member-proof");
    if (!node.healthy) {
      proof.textContent = "SIN RESPUESTA";
    } else if (node.document_found) {
      proof.textContent = "EVENTO CONFIRMADO";
    } else {
      proof.textContent = "ESPERANDO EVENTO";
    }
  }
}

function renderRemittanceTrace(trace) {
  for (const stage of trace.stages) renderTraceStage(stage);
  renderPostgresProof(trace.postgres_nodes || [], trace.commit_lsn);
  renderMongoProof(trace.mongodb_nodes || []);

  const outbox = trace.stages.find((stage) => stage.id === "outbox");
  const outboxNode = document.querySelector('[data-trace-node="outbox"] .node-state');
  if (outbox && outboxNode) {
    outboxNode.textContent = outbox.detail.toUpperCase();
    outboxNode.classList.toggle("state-up", outbox.status === "done");
  }

  const completedStages = trace.stages.filter((stage) => stage.status === "done").length;
  ui.traceDetail.textContent = trace.complete
    ? `Recorrido completo: ${trace.event.remittance_code} quedó confirmado en PostgreSQL y proyectado con mayoría en MongoDB.`
    : `${completedStages}/${trace.stages.length} etapas confirmadas. La vista seguirá consultando evidencia real.`;
}

async function startRemittanceTrace(result) {
  if (!result.event_id) {
    addTimeline("TRAZA", "La inserción no devolvió event_id; no puede correlacionarse.", "warning");
    return;
  }
  const token = ++state.traceToken;
  resetTraceVisuals(result);
  const deadline = Date.now() + TRACE_WINDOW_MS;
  const query = new URLSearchParams({ commit_lsn: result.commit_lsn || "" });

  while (token === state.traceToken && Date.now() < deadline) {
    try {
      const response = await fetch(`/api/remittance-trace/${result.event_id}/?${query}`, { cache: "no-store" });
      const trace = await response.json();
      if (!response.ok) throw new Error(trace.error || `HTTP ${response.status}`);
      renderRemittanceTrace(trace);
      if (trace.complete) {
        ui.operationPanel.dataset.state = "success";
        ui.operationMessage.textContent = "COMMIT, auditoría, WAL, Outbox y mayoría MongoDB confirmados.";
        return;
      }
    } catch (error) {
      ui.traceDetail.textContent = `La comprobación sigue activa: ${error.message || error}`;
    }
    await sleep(TRACE_POLL_INTERVAL_MS);
  }

  if (token === state.traceToken) {
    addTimeline("TRAZA", "Finalizó la ventana de seguimiento; se conserva la última evidencia obtenida.", "warning");
  }
}

async function insertRemittance() {
  if (state.insertionRunning) return;
  state.insertionRunning = true;
  ui.insertButton.disabled = true;
  ui.operationPanel.dataset.state = "running";
  ui.operationTitle.textContent = "Insertando remesa por el endpoint estable";
  ui.operationMessage.textContent = "Django envió la solicitud a HAProxy. Si el líder cae, la operación se reintentará automáticamente.";
  ui.operationAttempts.textContent = "…";
  ui.operationElapsed.textContent = "0 s";
  ui.operationServer.textContent = "Esperando";
  ui.operationJson.textContent = "Solicitud en curso…";
  addTimeline("DJANGO", "Solicitud de remesa completa enviada mediante HAProxy.", "info");
  startOperationClock();

  try {
    const response = await fetch("/api/generator/insert-remittance/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const data = await response.json();
    ui.operationJson.textContent = JSON.stringify(data, null, 2);
    ui.operationAttempts.textContent = data.attempts?.length ?? 1;
    ui.operationElapsed.textContent = `${data.elapsed_seconds ?? 0} s`;

    if (!response.ok || data.status !== "completed") {
      throw new Error(data.error || "No fue posible confirmar la remesa.");
    }

    const result = data.parsed || {};
    const currentLeader = state.previous?.postgres?.leader;
    ui.operationPanel.dataset.state = "success";
    ui.operationTitle.textContent = `${result.remittance_code || "Remesa"} confirmada`;
    ui.operationMessage.textContent = `${result.customer || "Cliente"} → ${result.beneficiary || "Beneficiario"} · ${result.corridor || "Corredor"}`;
    ui.operationServer.textContent = shortName(currentLeader) || result.server_addr || "Líder actual";
    addTimeline(
      "REMESA",
      `${result.remittance_code || "La remesa"} fue confirmada por ${shortName(currentLeader)} después de ${data.attempts?.length || 1} intento(s).`,
      "success",
    );
    startRemittanceTrace(result);
    await Promise.all([refreshTopology(), refreshRemittances()]);
  } catch (error) {
    ui.operationPanel.dataset.state = "error";
    ui.operationTitle.textContent = "La remesa no fue confirmada";
    ui.operationMessage.textContent = String(error.message || error);
    ui.operationServer.textContent = "No disponible";
    addTimeline("REMESA", `La operación finalizó sin confirmación: ${error.message || error}.`, "danger");
  } finally {
    stopOperationClock();
    state.insertionRunning = false;
    ui.insertButton.disabled = false;
  }
}

function schedulePolling() {
  clearInterval(state.timer);
  if (ui.autoRefresh.checked) {
    state.timer = setInterval(refreshTopology, POLL_INTERVAL_MS);
  }
}

ui.insertButton.addEventListener("click", insertRemittance);
ui.refreshButton.addEventListener("click", refreshTopology);
ui.autoRefresh.addEventListener("change", schedulePolling);
ui.clearTimeline.addEventListener("click", () => {
  ui.timeline.innerHTML = "";
  addTimeline("SISTEMA", "La traza visual fue reiniciada.", "info");
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && ui.autoRefresh.checked) refreshTopology();
});

refreshTopology();
schedulePolling();
