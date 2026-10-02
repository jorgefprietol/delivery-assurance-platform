"use strict";
const $ = (id) => document.getElementById(id);
let apiKey = "",
  identity = null,
  projectId = "",
  saveEditor = null;
const labels = {
  draft: "Borrador",
  approved: "Aprobado",
  implemented: "Implementado",
  verified: "Verificado",
  open: "Abierto",
  mitigated: "Mitigado",
  passed: "Aprobada",
  failed: "Fallida",
  must: "Esencial",
  should: "Importante",
  could: "Opcional",
  functional: "Funcional",
  nonfunctional: "No funcional",
  unit: "Unitaria",
  integration: "Integración",
  system: "Sistema",
  acceptance: "Aceptación",
};
const node = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
};
const status = (value) =>
  node("span", labels[value] || value, `status ${value}`);
function notify(message, error = false) {
  $("notice").textContent = message;
  $("notice").setAttribute("role", error ? "alert" : "status");
}
async function api(path, method = "GET", body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "X-API-Key": apiKey, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Revisa los campos: el servidor rechazó la solicitud.",
    );
  return data;
}
async function action(task) {
  try {
    await task();
    notify("Cambios guardados.");
    await refresh();
  } catch (error) {
    notify(error.message, true);
  }
}
function editor(title, fields, save) {
  $("editor-title").textContent = title;
  $("editor-error").textContent = "";
  $("editor-fields").replaceChildren();
  for (const field of fields) {
    const label = node("label", field.label);
    label.htmlFor = `field-${field.name}`;
    const input = node(
      field.options ? "select" : field.area ? "textarea" : "input",
    );
    input.id = label.htmlFor;
    input.name = field.name;
    input.required = true;
    if (field.options)
      for (const value of field.options) {
        const option = node("option", labels[value] || value);
        option.value = value;
        input.append(option);
      }
    if (field.number) {
      input.type = "number";
      input.min = "1";
      input.max = "5";
    }
    if (!field.options && !field.number) {
      input.minLength = 3;
      input.maxLength = field.area ? 500 : 120;
    }
    if (field.value !== undefined) input.value = field.value;
    if (field.commit) {
      input.minLength = 40;
      input.maxLength = 40;
      input.pattern = "[a-f0-9]{40}";
    }
    if (field.readOnly) input.readOnly = true;
    $("editor-fields").append(label, input);
  }
  saveEditor = save;
  $("editor").showModal();
}
const requirementFields = (r = {}) => [
  { name: "title", label: "Título del requisito", value: r.title || "" },
  {
    name: "acceptance",
    label: "Criterio de aceptación observable",
    area: true,
    value: r.acceptance || "",
  },
  {
    name: "priority",
    label: "Prioridad",
    options: ["must", "should", "could"],
    value: r.priority || "must",
  },
  {
    name: "category",
    label: "Tipo",
    options: ["functional", "nonfunctional"],
    value: r.category || "functional",
  },
];
$("editor-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  for (const input of event.target.querySelectorAll('input[type="number"]'))
    values[input.name] = Number(input.value);
  const submit = event.target.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await saveEditor(values);
    $("editor").close();
    notify("Registro guardado.");
    await loadProjects();
  } catch (error) {
    $("editor-error").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});
$("close-dialog").addEventListener("click", () => $("editor").close());
$("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  apiKey = $("api-key").value;
  $("api-key").value = "";
  try {
    identity = await api("/me");
    $("operator").textContent =
      `${identity.subject} · ${identity.role === "engineer" ? "Implementación" : "Revisión"}`;
    $("change-identity").hidden = false;
    for (const id of ["new-project", "new-requirement", "new-risk"])
      $(id).disabled = identity.role !== "engineer";
    await loadProjects();
    $("connection").hidden = true;
    if (projectId) notify("Workspace conectado.");
  } catch (error) {
    apiKey = "";
    identity = null;
    $("content").hidden = true;
    notify(error.message, true);
  }
});
$("change-identity").addEventListener("click", () => {
  apiKey = "";
  identity = null;
  $("content").hidden = true;
  $("connection").hidden = false;
  $("operator").textContent = "Sin conexión";
  $("change-identity").hidden = true;
  $("api-key").focus();
});
$("project").addEventListener("change", () => {
  projectId = $("project").value;
  refresh().catch((e) => notify(e.message, true));
});
$("new-project").addEventListener("click", () => {
  if (!apiKey)
    return notify("Conecta primero la credencial del workspace.", true);
  editor(
    "Nuevo proyecto",
    [
      { name: "name", label: "Nombre" },
      { name: "description", label: "Objetivo y alcance", area: true },
      { name: "owner", label: "Responsable" },
    ],
    async (values) => {
      const p = await api("/projects", "POST", values);
      projectId = p.id;
    },
  );
});
$("new-requirement").addEventListener("click", () =>
  editor("Añadir requisito", requirementFields(), (values) =>
    api(`/projects/${projectId}/requirements`, "POST", values),
  ),
);
$("new-risk").addEventListener("click", () =>
  editor(
    "Registrar riesgo",
    [
      { name: "title", label: "Riesgo" },
      { name: "owner", label: "Responsable" },
      {
        name: "probability",
        label: "Probabilidad (1–5)",
        number: true,
        value: 3,
      },
      { name: "impact", label: "Impacto (1–5)", number: true, value: 3 },
    ],
    (values) => api(`/projects/${projectId}/risks`, "POST", values),
  ),
);
$("release-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(() =>
    api(`/projects/${projectId}/releases`, "POST", {
      label: $("release-label").value,
    }),
  );
});
async function loadProjects() {
  const projects = await api("/projects");
  $("project").replaceChildren();
  for (const p of projects) {
    const option = node("option", p.name);
    option.value = p.id;
    $("project").append(option);
  }
  if (!projects.some((p) => p.id === projectId))
    projectId = projects[0]?.id || "";
  $("project").value = projectId;
  await refresh();
}
async function refresh() {
  $("content").hidden = !projectId;
  if (!projectId) {
    notify(
      "Crea tu primer proyecto para definir requisitos y criterios de entrega.",
    );
    return;
  }
  const [data, releases, audit] = await Promise.all([
    api(`/projects/${projectId}`),
    api(`/projects/${projectId}/releases`),
    api(`/projects/${projectId}/audit`),
  ]);
  $("project-name").textContent = data.project.name;
  $("project-description").textContent = data.project.description;
  $("total").textContent = data.gate.requirements;
  $("coverage").textContent = `${data.gate.coverage_percent}%`;
  $("risk-count").textContent = data.gate.high_open_risks;
  $("gate-title").textContent = data.gate.ready
    ? "Lista para registrar una entrega"
    : "Entrega bloqueada";
  $("release-button").disabled =
    !data.gate.ready || identity.role !== "reviewer";
  $("blockers").replaceChildren(
    ...data.gate.blockers.map((reason) => {
      const requirement = data.requirements.find((item) =>
        reason.includes(item.id),
      );
      const risk = data.risks.find((item) => reason.includes(item.id));
      return node(
        "li",
        requirement
          ? `Requisito pendiente: ${requirement.title}`
          : risk
            ? `Riesgo alto sin mitigación: ${risk.title}`
            : "Añade al menos un requisito con evidencia de aceptación.",
      );
    }),
  );
  $("requirement-rows").replaceChildren();
  for (const r of data.requirements) {
    const row = node("tr"),
      detail = node("td");
    detail.append(
      node("strong", r.title),
      node("p", r.acceptance),
      node(
        "small",
        `${labels[r.category]} · revisión ${r.revision} · versión ${r.version}`,
      ),
    );
    const priority = node("td", labels[r.priority]),
      state = node("td");
    state.append(status(r.status));
    const cell = node("td"),
      actions = node("div", undefined, "actions");
    const button = (text, fn) => {
      const b = node("button", text, "secondary");
      b.type = "button";
      b.addEventListener("click", fn);
      actions.append(b);
    };
    if (
      (r.status === "draft" && identity.role === "reviewer") ||
      (r.status === "approved" && identity.role === "engineer")
    ) {
      const next = r.status === "draft" ? "approved" : "implemented";
      button(next === "approved" ? "Aprobar" : "Implementado", () => {
        const save = (fields = {}) =>
          api(`/requirements/${r.id}/status`, "PATCH", {
            ...fields,
            version: r.version,
            status: next,
          });
        if (next === "implemented")
          editor(
            "Vincular implementación",
            [
              {
                name: "commit_sha",
                label: "SHA completo del commit implementado",
                commit: true,
              },
            ],
            save,
          );
        else action(() => save());
      });
    }
    if (
      ["implemented", "verified"].includes(r.status) &&
      identity.role === "reviewer"
    )
      button("Añadir prueba", () =>
        editor(
          "Evidencia de prueba",
          [
            { name: "test_name", label: "Escenario probado" },
            {
              name: "commit_sha",
              label: "Commit de la implementación",
              commit: true,
              value: r.implementation_sha,
              readOnly: true,
            },
            {
              name: "kind",
              label: "Nivel",
              options: ["unit", "integration", "system", "acceptance"],
            },
            {
              name: "outcome",
              label: "Resultado",
              options: ["passed", "failed"],
            },
            {
              name: "reference",
              label: "Referencia o descripción de evidencia",
              area: true,
            },
          ],
          (v) =>
            api(`/requirements/${r.id}/evidence`, "POST", {
              ...v,
              version: r.version,
            }),
        ),
      );
    if (identity.role === "engineer")
      button("Revisar", () =>
        editor(
          "Revisar requisito · reinicia su verificación",
          requirementFields(r),
          (v) =>
            api(`/requirements/${r.id}`, "PUT", { ...v, version: r.version }),
        ),
      );
    cell.append(actions);
    row.append(detail, priority, state, cell);
    $("requirement-rows").append(row);
  }
  if (!data.requirements.length) {
    const row = node("tr"),
      cell = node(
        "td",
        "Añade requisitos con criterios de aceptación para comenzar.",
      );
    cell.colSpan = 4;
    row.append(cell);
    $("requirement-rows").append(row);
  }
  $("risk-cards").replaceChildren();
  for (const r of data.risks) {
    const card = node("article", undefined, "risk-card");
    card.append(
      node("h3", r.title),
      status(r.status),
      node(
        "p",
        `${r.owner} · Probabilidad ${r.probability} × Impacto ${r.impact} = ${r.probability * r.impact}`,
      ),
    );
    if (r.mitigation) card.append(node("p", r.mitigation));
    if (r.status === "open" && identity.role === "engineer") {
      const b = node("button", "Registrar mitigación", "secondary");
      b.addEventListener("click", () =>
        editor(
          "Plan de mitigación",
          [
            {
              name: "mitigation",
              label: "Acción aplicada y evidencia de control",
              area: true,
            },
          ],
          (v) => api(`/risks/${r.id}`, "PATCH", { ...v, version: r.version }),
        ),
      );
      card.append(b);
    }
    $("risk-cards").append(card);
  }
  if (!data.risks.length)
    $("risk-cards").append(node("p", "Sin riesgos registrados.", "muted"));
  $("release-list").replaceChildren();
  for (const release of releases) {
    const entry = node("div", undefined, "entry"),
      b = node("button", "Descargar evidencia", "secondary");
    entry.append(
      node("strong", release.label),
      node("small", new Date(release.created_at).toLocaleString("es")),
      node("code", release.sha256),
    );
    b.addEventListener("click", () => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(release, null, 2)], {
          type: "application/json",
        }),
      );
      const a = node("a");
      a.href = url;
      a.download = `delivery-${release.label}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    entry.append(b);
    $("release-list").append(entry);
  }
  if (!releases.length)
    $("release-list").append(
      node("p", "Aún no hay entregas registradas.", "muted"),
    );
  $("evidence-list").replaceChildren();
  for (const e of data.evidence) {
    const r = data.requirements.find((r) => r.id === e.requirement_id),
      entry = node("div", undefined, "entry");
    entry.append(
      status(e.outcome),
      node("strong", ` ${e.test_name}`),
      node("p", e.reference),
      node(
        "small",
        `${r?.title || e.requirement_id} · ${labels[e.kind]} · revisión ${e.revision} · commit ${e.commit_sha?.slice(0, 12) || "histórico sin SHA"}${r?.revision !== e.revision ? " · evidencia histórica" : ""}`,
      ),
    );
    $("evidence-list").append(entry);
  }
  if (!data.evidence.length)
    $("evidence-list").append(
      node("p", "Las pruebas registradas aparecerán aquí.", "muted"),
    );
  $("activity").replaceChildren(
    ...audit
      .slice(0, 30)
      .map((e) =>
        node(
          "li",
          `${new Date(e.at).toLocaleString("es")} · ${e.actor} (${e.role || "histórico"}) · ${e.action} · ${e.entity_id.slice(0, 8)} · v${e.version}`,
        ),
      ),
  );
}
