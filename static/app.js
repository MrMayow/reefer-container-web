"use strict";

// Единственное состояние страницы: исходные данные, назначение и ответ Python.
let task = null;
let result = null;
let selectedContainer = null;
let currentMethod = "manual";
let requestNumber = 0;
const history = [];
let pointerDrag = null;
let suppressChipClick = false;
let autoScrollFrame = 0;
let geneticRun = null;
let geneticBusy = false;
let geneticGeneration = 0;
let branchRun = null;
let branchBusy = false;
let branchStage = 0;
let exhaustiveRun = null;
let exhaustiveBusy = false;
let exhaustiveStage = 0;
let taskRevision = 0;
const geneticSettings = { generations: 60, populationSize: 36, seed: 26 };
const branchSettings = { nodeLimit: 100000, useGeneticStart: false };
const exhaustiveSettings = { combinationLimit: 1000000 };

function invalidateSearch() {
  taskRevision++;
  geneticRun = null;
  branchRun = null;
  exhaustiveRun = null;
  branchSettings.useGeneticStart = false;
}

const byId = (id) => document.getElementById(id);
const rubles = (value) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value) + " ₽";
const number = (value) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value);
const nodesLabel = (value) => {
  const lastTwo = value % 100;
  const last = value % 10;
  const word = lastTwo >= 11 && lastTwo <= 14 ? "узлов"
    : last === 1 ? "узел" : last >= 2 && last <= 4 ? "узла" : "узлов";
  return `${number(value)} ${word}`;
};

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function showMessage(text) {
  byId("message").textContent = text;
}

async function post(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Не удалось выполнить запрос.");
  return value;
}

async function refresh(recordMove = "") {
  if (!task) return;
  const mine = ++requestNumber;
  try {
    const next = await post("/api/evaluate", task);
    if (mine !== requestNumber) return;
    result = next;
    if (recordMove) {
      history.push(`${recordMove} · ${rubles(next.totalCost)}${next.valid ? "" : " · есть нарушения"}`);
      if (history.length > 5) history.shift();
    }
    showMessage("");
    renderBoard();
    renderSummary();
    renderCostTable();
    renderMethod();
  } catch (error) {
    if (mine !== requestNumber) return;
    result = null;
    showMessage(`Проверьте данные: ${error.message}`);
    renderBoard();
    renderSummary();
    renderCostTable();
  }
}

function tableHeader(table, labels) {
  table.textContent = "";
  const head = element("thead");
  const row = element("tr");
  labels.forEach((label) => row.append(element("th", "", label)));
  head.append(row);
  table.append(head, element("tbody"));
  return table.tBodies[0];
}

function cell(row, content) {
  const td = element("td");
  if (content instanceof Node) td.append(content);
  else td.textContent = content;
  row.append(td);
  return td;
}

function numberInput(value, label, onChange) {
  const input = element("input");
  input.type = "number";
  input.min = "0";
  input.step = "1";
  input.value = value;
  input.setAttribute("aria-label", label);
  input.addEventListener("change", () => {
    onChange(Number(input.value));
    invalidateSearch();
    refresh();
  });
  return input;
}

function removeButton(label, onClick) {
  const button = element("button", "table-action", "×");
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", onClick);
  return button;
}

function renderEditors() {
  const containersBody = tableHeader(byId("containers-table"), ["№", "Масса, т", "Мощность, кВт", "Хранение, ч", ""]);
  task.containers.forEach((container) => {
    const row = element("tr");
    cell(row, container.id);
    [["weight", "Масса"], ["power", "Мощность"], ["storage", "Хранение"]].forEach(([key, label]) => {
      cell(row, numberInput(container[key], `${label} ${container.id}`, (value) => { container[key] = value; }));
    });
    cell(row, removeButton(`Удалить ${container.id}`, () => {
      if (task.containers.length <= 1) return showMessage("Нужен хотя бы один контейнер.");
      task.containers = task.containers.filter((item) => item.id !== container.id);
      delete task.assignment[container.id];
      selectedContainer = null;
      invalidateSearch();
      renderEditors();
      refresh();
    }));
    containersBody.append(row);
  });

  const sitesBody = tableHeader(byId("sites-table"), ["Площадка", "Мест, шт.", "Масса, т", "Мощность, кВт", "Хранение, ₽/ч", "Путь, ч", "Перевозка, d", ""]);
  task.sites.forEach((site) => {
    const row = element("tr");
    cell(row, site.id);
    [["places", "Места"], ["massLimit", "Предел массы"],
      ["powerLimit", "Предел мощности"], ["storageRate", "Тариф хранения"],
      ["travelTime", "Время перевозки"], ["travelRate", "Тариф перевозки"]].forEach(([key, label]) => {
      cell(row, numberInput(site[key], `${label} площадки ${site.id}`, (value) => { site[key] = value; }));
    });
    cell(row, removeButton(`Удалить площадку ${site.id}`, () => {
      if (task.sites.length <= 1) return showMessage("Нужна хотя бы одна площадка.");
      task.sites = task.sites.filter((item) => item.id !== site.id);
      Object.keys(task.assignment).forEach((id) => {
        if (task.assignment[id] === site.id) task.assignment[id] = null;
      });
      invalidateSearch();
      renderEditors();
      refresh();
    }));
    sitesBody.append(row);
  });
  byId("limit-hours").value = task.limitHours;
  byId("tariff-mode").value = task.tariffMode;
  renderFormula();
}

function renderFormula() {
  byId("formula-explanation").textContent = task.tariffMode === "ton_hour"
    ? "Стоимость контейнера: tᵢ × hⱼ + wᵢ × Tⱼ × dⱼ. Перевозка учитывает массу."
    : "Стоимость контейнера: tᵢ × hⱼ + Tⱼ × dⱼ. Тариф перевозки задан за целый контейнер.";
}

function nextContainerId() {
  let index = 1;
  while (task.containers.some((item) => item.id === `К${String(index).padStart(2, "0")}`)) index++;
  return `К${String(index).padStart(2, "0")}`;
}

function addContainer() {
  if (task.containers.length >= 80) return showMessage("В прототипе допускается не более 80 контейнеров.");
  const id = nextContainerId();
  task.containers.push({ id, weight: 18, power: 5, storage: 16 });
  task.assignment[id] = null;
  invalidateSearch();
  renderEditors();
  refresh();
}

function addSite() {
  if (task.sites.length >= 10) return showMessage("В прототипе допускается не более 10 площадок.");
  const id = "ABCDEFGHIJ".split("").find((name) => !task.sites.some((site) => site.id === name));
  task.sites.push({ id, places: 5, massLimit: 110, powerLimit: 35,
    storageRate: 145, travelTime: 2, travelRate: 550 });
  invalidateSearch();
  renderEditors();
  refresh();
}

function moveContainer(id, siteId) {
  if (!task || !task.containers.some((item) => item.id === id)) return;
  task.assignment[id] = siteId;
  selectedContainer = null;
  byId("selection-hint").textContent = "Выберите контейнер, затем площадку";
  refresh(`${id} → ${siteId || "без площадки"}`);
}

function chip(container) {
  const button = element("button", "chip" + (selectedContainer === container.id ? " selected" : ""), container.id);
  button.type = "button";
  button.title = `${container.id}: ${number(container.weight)} т, ${number(container.power)} кВт, ${number(container.storage)} ч`;
  button.setAttribute("aria-label", `${container.id}, выбрать для перемещения`);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (suppressChipClick) {
      suppressChipClick = false;
      return;
    }
    selectedContainer = selectedContainer === container.id ? null : container.id;
    byId("selection-hint").textContent = selectedContainer ? `${selectedContainer}: выберите площадку` : "Выберите контейнер, затем площадку";
    document.querySelectorAll(".chip").forEach((item) => {
      item.classList.toggle("selected", item.textContent === selectedContainer);
    });
  });
  button.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (event.isTrusted) button.setPointerCapture(event.pointerId);
    pointerDrag = {
      id: container.id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      source: button,
      ghost: null,
      target: null
    };
  });
  return button;
}

function dropTargetAt(x, y) {
  const item = document.elementFromPoint(x, y);
  return item ? item.closest(".site-card, .unassigned") : null;
}

function clearPointerDrag() {
  if (!pointerDrag) return;
  if (autoScrollFrame) window.cancelAnimationFrame(autoScrollFrame);
  autoScrollFrame = 0;
  pointerDrag.ghost?.remove();
  pointerDrag.source.classList.remove("dragging");
  pointerDrag.target?.classList.remove("drag-over");
  pointerDrag = null;
}

function highlightDropTarget(drag, x, y) {
  const target = dropTargetAt(x, y);
  if (target === drag.target) return;
  drag.target?.classList.remove("drag-over");
  target?.classList.add("drag-over");
  drag.target = target;
}

function scrollWhileDragging() {
  const drag = pointerDrag;
  if (!drag?.ghost) {
    autoScrollFrame = 0;
    return;
  }
  const edge = 65;
  const amount = drag.y < edge ? -12 : drag.y > innerHeight - edge ? 12 : 0;
  if (amount) {
    window.scrollBy(0, amount);
    highlightDropTarget(drag, drag.x, drag.y);
  }
  autoScrollFrame = window.requestAnimationFrame(scrollWhileDragging);
}

document.addEventListener("pointermove", (event) => {
  const drag = pointerDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (!drag.ghost && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 6) return;
  if (!drag.ghost) {
    drag.ghost = element("div", "drag-ghost", drag.id);
    document.body.append(drag.ghost);
    drag.source.classList.add("dragging");
  }
  event.preventDefault();
  drag.x = event.clientX;
  drag.y = event.clientY;
  drag.ghost.style.left = `${event.clientX + 12}px`;
  drag.ghost.style.top = `${event.clientY + 12}px`;
  highlightDropTarget(drag, event.clientX, event.clientY);
  if (!autoScrollFrame) autoScrollFrame = window.requestAnimationFrame(scrollWhileDragging);
});

document.addEventListener("pointerup", (event) => {
  const drag = pointerDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const wasDragging = Boolean(drag.ghost);
  const target = wasDragging ? dropTargetAt(event.clientX, event.clientY) : null;
  const id = drag.id;
  clearPointerDrag();
  if (wasDragging) {
    suppressChipClick = true;
    window.setTimeout(() => { suppressChipClick = false; }, 0);
    if (target) moveContainer(id, target.dataset.siteId || null);
  }
});

document.addEventListener("pointercancel", clearPointerDrag);

function makeDropTarget(node, siteId) {
  node.tabIndex = 0;
  node.dataset.siteId = siteId || "";
  node.setAttribute("aria-label", siteId ? `Площадка ${siteId}; Enter переносит выбранный контейнер` : "Без площадки; Enter снимает назначение");
  node.addEventListener("click", (event) => {
    if (event.target.closest(".chip")) return;
    if (selectedContainer) moveContainer(selectedContainer, siteId);
  });
  node.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && selectedContainer) {
      event.preventDefault();
      moveContainer(selectedContainer, siteId);
    }
  });
}

function meter(used, maximum) {
  const outer = element("div", "meter" + (used > maximum ? " over" : ""));
  const inner = element("span");
  inner.style.width = `${Math.min(100, maximum > 0 ? used / maximum * 100 : used > 0 ? 100 : 0)}%`;
  outer.append(inner);
  return outer;
}

function renderBoard() {
  const board = byId("board");
  board.textContent = "";
  if (!task) return;
  task.sites.forEach((site) => {
    const load = result?.loads.find((item) => item.id === site.id);
    const card = element("article", "site-card" + (load?.issues.length ? " has-issue" : ""));
    makeDropTarget(card, site.id);
    const head = element("div", "site-card-head");
    head.append(element("h3", "", `Площадка ${site.id}`), element("span", "site-cost", load ? rubles(load.cost) : "—"));
    card.append(head);
    const metrics = element("div", "site-metrics");
    metrics.append(element("div", "", `Места: ${load?.count ?? 0} / ${site.places}`));
    metrics.append(meter(load?.count ?? 0, site.places));
    metrics.append(element("div", "", `Масса: ${number(load?.weight ?? 0)} / ${number(site.massLimit)} т`));
    metrics.append(meter(load?.weight ?? 0, site.massLimit));
    metrics.append(element("div", "", `Мощность: ${number(load?.power ?? 0)} / ${number(site.powerLimit)} кВт`));
    metrics.append(meter(load?.power ?? 0, site.powerLimit));
    card.append(metrics);
    const list = element("div", "chip-list");
    task.containers.filter((item) => task.assignment[item.id] === site.id).forEach((item) => list.append(chip(item)));
    card.append(list);
    if (!list.childElementCount) card.append(element("div", "empty-drop", "Перенесите контейнер сюда"));
    board.append(card);
  });
  const tray = element("div", "unassigned");
  makeDropTarget(tray, null);
  tray.append(element("strong", "", "Без площадки"));
  const list = element("div", "chip-list");
  task.containers.filter((item) => !task.assignment[item.id] || !task.sites.some((site) => site.id === task.assignment[item.id])).forEach((item) => list.append(chip(item)));
  tray.append(list);
  if (!list.childElementCount) tray.append(element("span", "empty-drop", " Все контейнеры размещены"));
  board.append(tray);
}

function renderSummary() {
  byId("total-cost").textContent = result ? rubles(result.totalCost) : "—";
  const status = byId("plan-status");
  status.textContent = !result ? "Нужно исправить данные" : result.valid ? "План допустим" : "План недопустим";
  status.className = "status" + (!result || !result.valid ? " invalid" : "");
  const summary = byId("load-summary");
  summary.textContent = "";
  if (result) result.loads.forEach((load) => {
    const site = task.sites.find((item) => item.id === load.id);
    const row = element("div", "load-row");
    const title = element("div");
    title.append(element("strong", "", `Площадка ${load.id}`), element("strong", "", rubles(load.cost)));
    row.append(title, element("small", "", `${load.count}/${site.places} мест · ${number(load.weight)}/${number(site.massLimit)} т · ${number(load.power)}/${number(site.powerLimit)} кВт`), meter(load.count, site.places));
    summary.append(row);
  });
  const issues = byId("issues");
  issues.textContent = "";
  if (!result) issues.textContent = "Расчёт временно недоступен.";
  else if (!result.issues.length) issues.textContent = "Ограничения соблюдены.";
  else {
    const list = element("ul");
    result.issues.forEach((issue) => list.append(element("li", "", issue)));
    issues.append(list);
  }
}

function renderCostTable() {
  const body = tableHeader(byId("cost-table"), ["Контейнер", "Площадка", "Хранение", "Перевозка", "Итого", "Проверка", "Изменить"]);
  if (!result) return;
  result.rows.forEach((item) => {
    const row = element("tr");
    cell(row, item.id);
    cell(row, item.site || "—");
    cell(row, rubles(item.storageCost));
    cell(row, rubles(item.travelCost));
    cell(row, rubles(item.cost));
    cell(row, item.issues.length ? element("span", "row-issue", item.issues.join("; ")) : "В сроке");
    const select = element("select");
    select.setAttribute("aria-label", `Площадка для ${item.id}`);
    const none = element("option", "", "Без площадки");
    none.value = "";
    select.append(none);
    task.sites.forEach((site) => {
      const option = element("option", "", `Площадка ${site.id}`);
      option.value = site.id;
      select.append(option);
    });
    select.value = item.site || "";
    select.addEventListener("change", () => moveContainer(item.id, select.value || null));
    cell(row, select);
    body.append(row);
  });
}

function geneticField(label, key, min, max) {
  const wrapper = element("label", "ga-field", label);
  const input = element("input");
  input.type = "number";
  input.min = String(min);
  input.max = String(max);
  input.step = "1";
  input.value = String(geneticSettings[key]);
  input.addEventListener("change", () => { geneticSettings[key] = Number(input.value); });
  wrapper.append(input);
  return wrapper;
}

function geneticChart(records, selected) {
  const wrap = element("div", "ga-chart-wrap");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 640 190");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Лучшая стоимость по поколениям");
  const values = records.map((item) => item.bestCost);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const range = Math.max(1, high - low);
  const xy = (item, index) => ({
    x: 44 + index * 578 / Math.max(1, records.length - 1),
    y: 152 - (item.bestCost - low) * 119 / range
  });
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", records.map((item, index) => {
    const point = xy(item, index);
    return `${point.x},${point.y}`;
  }).join(" "));
  line.setAttribute("class", "ga-line");
  svg.append(line);
  const point = xy(records[selected], selected);
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("cx", String(point.x));
  dot.setAttribute("cy", String(point.y));
  dot.setAttribute("r", "5");
  dot.setAttribute("class", "ga-dot");
  svg.append(dot);
  wrap.append(svg);
  const axis = element("div", "ga-chart-axis");
  axis.append(element("span", "", `0 поколение · ${rubles(records[0].bestCost)}`),
    element("span", "", `${records.length - 1} поколение · ${rubles(records.at(-1).bestCost)}`));
  wrap.append(axis);
  return wrap;
}

function renderGenetic(content) {
  content.append(element("p", "", "Python создаёт допустимые планы, отбирает более дешёвые, скрещивает и меняет назначения. Лучший план сохраняется в каждом поколении."));
  const controls = element("div", "ga-controls");
  controls.append(geneticField("Поколения", "generations", 1, 200),
    geneticField("Популяция", "populationSize", 4, 80),
    geneticField("Зерно", "seed", 0, 999999));
  const runButton = element("button", "button primary", geneticBusy ? "Вычисляется…" : "Запустить поиск");
  runButton.type = "button";
  runButton.disabled = geneticBusy;
  runButton.addEventListener("click", runGenetic);
  controls.append(runButton);
  content.append(controls);
  if (geneticBusy) {
    content.append(element("p", "ga-status", "Генетический алгоритм выполняется на локальном сервере…"));
    return;
  }
  if (!geneticRun) {
    content.append(element("p", "ga-status", "Нажмите «Запустить поиск», чтобы увидеть реальные поколения и найденное размещение."));
    return;
  }
  if (geneticRun.error) {
    content.append(element("p", "ga-status", geneticRun.error));
    return;
  }
  if (geneticRun.status === "not_found") {
    content.append(element("p", "ga-status", geneticRun.message));
    return;
  }
  const records = geneticRun.history;
  geneticGeneration = Math.min(geneticGeneration, records.length - 1);
  const stage = records[geneticGeneration];
  const headline = element("div", "ga-headline");
  headline.append(element("div", "", `Лучший найденный план: ${rubles(geneticRun.bestCost)}`));
  const compare = result?.valid
    ? `Текущий план: ${rubles(result.totalCost)} · разница: ${rubles(result.totalCost - geneticRun.bestCost)}`
    : "Текущий ручной план недопустим; сравнение стоимости скрыто.";
  headline.append(element("small", "", compare));
  content.append(headline, element("p", "ga-proof", geneticRun.message));
  content.append(geneticChart(records, geneticGeneration));
  const selector = element("div", "ga-selector");
  const label = element("label", "", `Поколение ${geneticGeneration} из ${geneticRun.generationsRun}`);
  label.setAttribute("for", "ga-generation");
  const slider = element("input");
  slider.id = "ga-generation";
  slider.type = "range";
  slider.min = "0";
  slider.max = String(records.length - 1);
  slider.value = String(geneticGeneration);
  slider.addEventListener("change", () => {
    geneticGeneration = Number(slider.value);
    renderMethod();
    byId("ga-generation")?.focus();
  });
  selector.append(label, slider);
  content.append(selector);
  const metrics = element("div", "ga-metrics");
  [["Лучшая стоимость", rubles(stage.bestCost)],
    ["Разных планов", number(stage.distinctPlans)],
    ["Скрещиваний", number(stage.crossovers)],
    ["Мутаций", number(stage.mutations)],
    ["Исправлений", number(stage.repairs)]].forEach(([name, value]) => {
    const box = element("div", "ga-metric");
    box.append(element("small", "", name), element("strong", "", value));
    metrics.append(box);
  });
  content.append(metrics);
  content.append(element("div", "preview-label", "ЛУЧШИЙ ДОПУСТИМЫЙ ПЛАН К ЭТОМУ ПОКОЛЕНИЮ"));
  const preview = element("div", "ga-preview");
  task.sites.forEach((site, j) => {
    const box = element("div", "ga-site");
    box.append(element("strong", "", `Площадка ${site.id}`));
    const ids = task.containers.filter((_, i) => stage.bestChromosome[i] === j).map((item) => item.id);
    box.append(element("span", "", ids.length ? ids.join(" · ") : "Нет контейнеров"));
    preview.append(box);
  });
  content.append(preview);
  const apply = element("button", "button secondary ga-apply", "Применить лучший итоговый план");
  apply.type = "button";
  apply.addEventListener("click", () => {
    task.assignment = { ...geneticRun.bestAssignment };
    selectedContainer = null;
    refresh("Применён генетический план");
  });
  content.append(apply);
}

async function runGenetic() {
  if (!task || geneticBusy) return;
  geneticBusy = true;
  geneticRun = null;
  const revision = taskRevision;
  const snapshot = JSON.parse(JSON.stringify(task));
  renderMethod();
  try {
    const answer = await post("/api/solve", { method: "genetic", task: snapshot,
      options: { ...geneticSettings } });
    if (revision === taskRevision) {
      geneticRun = answer;
      geneticGeneration = Math.max(0, answer.history.length - 1);
    }
  } catch (error) {
    if (revision === taskRevision) geneticRun = { error: `Поиск не выполнен: ${error.message}` };
  } finally {
    geneticBusy = false;
    renderMethod();
  }
}

function branchChart(records, selected, countKey = "nodesVisited", countLabel = "Просмотрено узлов") {
  const visible = records.filter((item) => item.bestCost !== null);
  if (!visible.length) return element("p", "ga-status", "Допустимый план на этих этапах не найден.");
  const wrap = element("div", "ga-chart-wrap");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 640 190");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Лучшая стоимость. ${countLabel}`);
  const low = Math.min(...visible.map((item) => item.bestCost));
  const high = Math.max(...visible.map((item) => item.bestCost));
  const range = Math.max(1, high - low);
  const lastNode = Math.max(1, records.at(-1)[countKey]);
  const point = (item) => ({ x: 44 + item[countKey] * 578 / lastNode,
    y: 152 - (item.bestCost - low) * 119 / range });
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", visible.map((item) => {
    const p = point(item);
    return `${p.x},${p.y}`;
  }).join(" "));
  line.setAttribute("class", "ga-line");
  svg.append(line);
  if (records[selected].bestCost !== null) {
    const p = point(records[selected]);
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(p.x));
    dot.setAttribute("cy", String(p.y));
    dot.setAttribute("r", "5");
    dot.setAttribute("class", "ga-dot");
    svg.append(dot);
  }
  wrap.append(svg);
  const axis = element("div", "ga-chart-axis");
  axis.append(element("span", "", "Начало поиска"),
    element("span", "", `${countKey === "nodesVisited" ? nodesLabel(records.at(-1)[countKey]) : `${number(records.at(-1)[countKey])} проверок`} · ${rubles(visible.at(-1).bestCost)}`));
  wrap.append(axis);
  return wrap;
}

function branchProgressChart(records, selected) {
  const wrap = element("div", "ga-chart-wrap");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 640 150");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Число отсечённых ветвей по мере поиска");
  const lastNode = Math.max(1, records.at(-1).nodesVisited);
  const maximum = Math.max(1, ...records.map((item) => Math.max(item.prunedBound, item.prunedCapacity)));
  const coordinate = (item, key) => ({
    x: 12 + item.nodesVisited * 616 / lastNode,
    y: 132 - item[key] * 112 / maximum
  });
  [["prunedBound", "bb-bound-line", "bb-bound-dot"],
    ["prunedCapacity", "bb-capacity-line", "bb-capacity-dot"]].forEach(([key, lineClass, dotClass]) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", records.map((item) => {
      const p = coordinate(item, key);
      return `${p.x},${p.y}`;
    }).join(" "));
    line.setAttribute("class", lineClass);
    svg.append(line);
    const p = coordinate(records[selected], key);
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(p.x));
    dot.setAttribute("cy", String(p.y));
    dot.setAttribute("r", "4");
    dot.setAttribute("class", dotClass);
    svg.append(dot);
  });
  wrap.append(svg);
  const legend = element("div", "bb-legend");
  legend.append(element("span", "bb-bound-key", "По нижней оценке"),
    element("span", "bb-capacity-key", "По ресурсам"));
  wrap.append(legend);
  return wrap;
}

function renderBranch(content) {
  content.append(element("p", "", "Python перебирает допустимые назначения и отсекает ветви, которые уже не могут улучшить лучший план. Полный поиск доказывает оптимум либо отсутствие решения."));
  const controls = element("div", "ga-controls");
  const field = element("label", "ga-field", "Лимит узлов");
  const input = element("input");
  input.type = "number";
  input.min = "1";
  input.max = "1000000";
  input.step = "1";
  input.value = String(branchSettings.nodeLimit);
  input.addEventListener("change", () => { branchSettings.nodeLimit = Number(input.value); });
  field.append(input);
  const button = element("button", "button primary", branchBusy ? "Вычисляется…" : "Запустить точный поиск");
  button.type = "button";
  button.disabled = branchBusy;
  button.addEventListener("click", runBranch);
  controls.append(field, button);
  content.append(controls);
  const geneticAvailable = geneticRun?.status === "found" && !!geneticRun.bestAssignment;
  const choice = element("label", "bb-start-option");
  if (!geneticAvailable) choice.classList.add("disabled");
  const checkbox = element("input");
  checkbox.type = "checkbox";
  checkbox.checked = geneticAvailable && branchSettings.useGeneticStart;
  checkbox.disabled = !geneticAvailable || branchBusy;
  checkbox.addEventListener("change", () => { branchSettings.useGeneticStart = checkbox.checked; });
  choice.append(checkbox, element("span", "", "Использовать результат генетического алгоритма как начальный план"));
  content.append(choice, element("p", "bb-start-hint", geneticAvailable
    ? `Доступен план ГА: ${rubles(geneticRun.bestCost)}. Передача выполняется только при установленной отметке.`
    : "Сначала запустите генетический алгоритм для этих исходных данных, чтобы передать его план."));
  if (branchBusy) {
    content.append(element("p", "ga-status", "Метод ветвей и границ выполняется на локальном сервере…"));
    return;
  }
  if (!branchRun) {
    content.append(element("p", "ga-status", "Запустите метод, чтобы увидеть реальные этапы поиска и его итог."));
    return;
  }
  if (branchRun.error) {
    content.append(element("p", "ga-status", branchRun.error));
    return;
  }
  const records = branchRun.history;
  branchStage = Math.min(branchStage, records.length - 1);
  const stage = records[branchStage];
  const title = branchRun.status === "optimal" ? `Доказанный оптимум: ${rubles(branchRun.bestCost)}`
    : branchRun.bestCost !== undefined ? `Лучший найденный план: ${rubles(branchRun.bestCost)}`
      : branchRun.status === "infeasible" ? "Допустимого размещения нет" : "План пока не найден";
  const headline = element("div", "ga-headline");
  headline.append(element("div", "", title));
  if (result?.valid && branchRun.bestCost !== undefined) {
    headline.append(element("small", "", `Текущий план: ${rubles(result.totalCost)} · разница: ${rubles(result.totalCost - branchRun.bestCost)}`));
  }
  content.append(headline, element("p", "ga-proof", branchRun.message));
  content.append(element("p", "bb-run-mode", branchRun.usedGeneticStart
    ? "Этот запуск использовал план генетического алгоритма как начальный."
    : "Этот запуск выполнен без передачи плана генетического алгоритма."));
  content.append(element("p", "", `Нижняя оценка в начале: ${branchRun.rootLowerBound === null ? "нет допустимой площадки для части контейнеров" : rubles(branchRun.rootLowerBound)}. Просмотрено ${nodesLabel(branchRun.nodesVisited)} из лимита ${number(branchRun.nodeLimit)}.`));
  if (geneticRun?.status === "found" &&
      (branchRun.bestCost === undefined || geneticRun.bestCost < branchRun.bestCost)) {
    content.append(element("p", "ga-status", `Генетический план стоит ${rubles(geneticRun.bestCost)}. Если хотите использовать его как начальную верхнюю границу, установите отметку выше и запустите поиск ещё раз.`));
  }
  content.append(element("div", "preview-label", "ЛУЧШАЯ ДОПУСТИМАЯ СТОИМОСТЬ"));
  content.append(branchChart(records, branchStage));
  content.append(element("div", "preview-label bb-chart-title", "ОТСЕЧЁННЫЕ ВЕТВИ ПО МЕРЕ ПОИСКА"));
  content.append(branchProgressChart(records, branchStage));
  const selector = element("div", "ga-selector");
  const label = element("label", "", `Этап ${branchStage + 1} из ${records.length}: ${stage.event}`);
  label.setAttribute("for", "bb-stage");
  const slider = element("input");
  slider.id = "bb-stage";
  slider.type = "range";
  slider.min = "0";
  slider.max = String(records.length - 1);
  slider.value = String(branchStage);
  slider.addEventListener("change", () => {
    branchStage = Number(slider.value);
    renderMethod();
    byId("bb-stage")?.focus();
  });
  selector.append(label, slider);
  content.append(selector);
  const metrics = element("div", "ga-metrics");
  [["Просмотрено узлов", number(stage.nodesVisited)],
    ["Отсечено по оценке", number(stage.prunedBound)],
    ["Отсечено по ресурсам", number(stage.prunedCapacity)],
    ["Глубина ветви", `${stage.depth} / ${task.containers.length}`],
    ["Лучший план", stage.bestCost === null ? "Пока нет" : rubles(stage.bestCost)]].forEach(([name, value]) => {
    const box = element("div", "ga-metric");
    box.append(element("small", "", name), element("strong", "", value));
    metrics.append(box);
  });
  content.append(metrics);
  if (stage.bestChromosome) {
    content.append(element("div", "preview-label", "ЛУЧШИЙ ДОПУСТИМЫЙ ПЛАН К ЭТОМУ ЭТАПУ"));
    const preview = element("div", "ga-preview");
    task.sites.forEach((site, j) => {
      const box = element("div", "ga-site");
      box.append(element("strong", "", `Площадка ${site.id}`));
      const ids = task.containers.filter((_, i) => stage.bestChromosome[i] === j).map((item) => item.id);
      box.append(element("span", "", ids.length ? ids.join(" · ") : "Нет контейнеров"));
      preview.append(box);
    });
    content.append(preview);
  }
  if (branchRun.bestAssignment) {
    const apply = element("button", "button secondary ga-apply", "Применить лучший итоговый план");
    apply.type = "button";
    apply.addEventListener("click", () => {
      task.assignment = { ...branchRun.bestAssignment };
      selectedContainer = null;
      refresh("Применён план метода ветвей и границ");
    });
    content.append(apply);
  }
}

async function runBranch() {
  if (!task || branchBusy) return;
  const useGeneticStart = branchSettings.useGeneticStart &&
    geneticRun?.status === "found" && !!geneticRun.bestAssignment;
  branchBusy = true;
  branchRun = null;
  const revision = taskRevision;
  const snapshot = JSON.parse(JSON.stringify(task));
  const options = { nodeLimit: branchSettings.nodeLimit };
  if (useGeneticStart) options.incumbentAssignment = geneticRun.bestAssignment;
  renderMethod();
  try {
    const answer = await post("/api/solve", { method: "branch_bound", task: snapshot,
      options });
    if (revision === taskRevision) {
      answer.usedGeneticStart = useGeneticStart;
      branchRun = answer;
      branchStage = Math.max(0, answer.history.length - 1);
    }
  } catch (error) {
    if (revision === taskRevision) branchRun = { error: `Поиск не выполнен: ${error.message}` };
  } finally {
    branchBusy = false;
    renderMethod();
  }
}

function renderExhaustive(content) {
  content.append(element("p", "", "Python проверяет каждое полное назначение контейнеров на площадки, включая недопустимые. Ветви не отсекаются. После проверки всех вариантов результат доказан."));
  const controls = element("div", "ga-controls");
  const field = element("label", "ga-field", "Лимит назначений");
  const input = element("input");
  input.type = "number";
  input.min = "1";
  input.max = "5000000";
  input.step = "1";
  input.value = String(exhaustiveSettings.combinationLimit);
  input.addEventListener("input", () => { exhaustiveSettings.combinationLimit = Number(input.value); });
  field.append(input);
  const button = element("button", "button primary", exhaustiveBusy ? "Вычисляется…" : "Запустить полный перебор");
  button.type = "button";
  button.disabled = exhaustiveBusy;
  button.addEventListener("click", runExhaustive);
  controls.append(field, button);
  content.append(controls);
  if (exhaustiveBusy) {
    content.append(element("p", "ga-status", "Полный перебор выполняется на локальном сервере. Этапы появятся после завершения запроса…"));
    return;
  }
  if (!exhaustiveRun) {
    content.append(element("p", "ga-status", "Запустите метод, чтобы увидеть проверки, этапы и лучший план."));
    return;
  }
  if (exhaustiveRun.error) {
    content.append(element("p", "ga-status", exhaustiveRun.error));
    return;
  }
  const records = exhaustiveRun.history;
  exhaustiveStage = Math.min(exhaustiveStage, records.length - 1);
  const stage = records[exhaustiveStage];
  const title = exhaustiveRun.status === "optimal" ? `Доказанный оптимум: ${rubles(exhaustiveRun.bestCost)}`
    : exhaustiveRun.bestCost !== undefined ? `Лучший найденный план: ${rubles(exhaustiveRun.bestCost)}`
      : exhaustiveRun.status === "infeasible" ? "Допустимого размещения нет" : "План пока не найден";
  const headline = element("div", "ga-headline");
  headline.append(element("div", "", title));
  if (result?.valid && exhaustiveRun.bestCost !== undefined) {
    headline.append(element("small", "", `Текущий план: ${rubles(result.totalCost)} · разница: ${rubles(result.totalCost - exhaustiveRun.bestCost)}`));
  }
  content.append(headline, element("p", "ga-proof", exhaustiveRun.message));
  const total = BigInt(exhaustiveRun.totalCombinations);
  content.append(element("p", "", `Всего назначений: ${number(total)}. Проверено: ${number(exhaustiveRun.checkedCount)} из лимита ${number(exhaustiveRun.combinationLimit)}.`));
  content.append(element("div", "preview-label", "ЛУЧШАЯ ДОПУСТИМАЯ СТОИМОСТЬ"));
  content.append(branchChart(records, exhaustiveStage, "checkedCount", "Проверено назначений"));
  const selector = element("div", "ga-selector");
  const label = element("label", "", `Этап ${exhaustiveStage + 1} из ${records.length}: ${stage.event}`);
  label.setAttribute("for", "exhaustive-stage");
  const slider = element("input");
  slider.id = "exhaustive-stage";
  slider.type = "range";
  slider.min = "0";
  slider.max = String(records.length - 1);
  slider.value = String(exhaustiveStage);
  slider.addEventListener("change", () => {
    exhaustiveStage = Number(slider.value);
    renderMethod();
    byId("exhaustive-stage")?.focus();
  });
  selector.append(label, slider);
  content.append(selector);
  const percent = Number(BigInt(stage.checkedCount) * 10000n / total) / 100;
  const percentLabel = stage.checkedCount > 0 && percent === 0 ? "менее 0,01"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(percent);
  content.append(element("p", "ga-status", `На этом этапе проверено ${number(stage.checkedCount)} из ${number(total)} назначений (${percentLabel}%).`));
  const progress = element("div", "exhaustive-progress");
  progress.setAttribute("role", "progressbar");
  progress.setAttribute("aria-label", "Доля проверенных назначений");
  progress.setAttribute("aria-valuemin", "0");
  progress.setAttribute("aria-valuemax", "100");
  progress.setAttribute("aria-valuenow", String(percent));
  const fill = element("div", "exhaustive-progress-fill");
  fill.style.width = `${percent}%`;
  progress.append(fill);
  content.append(progress);
  const metrics = element("div", "ga-metrics");
  [["Проверено", number(stage.checkedCount)],
    ["Допустимых", number(stage.validCount)],
    ["Недопустимых", number(stage.invalidCount)],
    ["Лучший план", stage.bestCost === null ? "Пока нет" : rubles(stage.bestCost)]].forEach(([name, value]) => {
    const box = element("div", "ga-metric");
    box.append(element("small", "", name), element("strong", "", value));
    metrics.append(box);
  });
  content.append(metrics);
  if (stage.bestChromosome) {
    content.append(element("div", "preview-label", "ЛУЧШИЙ ДОПУСТИМЫЙ ПЛАН К ЭТОМУ ЭТАПУ"));
    const preview = element("div", "ga-preview");
    task.sites.forEach((site, j) => {
      const box = element("div", "ga-site");
      box.append(element("strong", "", `Площадка ${site.id}`));
      const ids = task.containers.filter((_, i) => stage.bestChromosome[i] === j).map((item) => item.id);
      box.append(element("span", "", ids.length ? ids.join(" · ") : "Нет контейнеров"));
      preview.append(box);
    });
    content.append(preview);
  }
  if (exhaustiveRun.bestAssignment) {
    const apply = element("button", "button secondary ga-apply", "Применить лучший итоговый план");
    apply.type = "button";
    apply.addEventListener("click", () => {
      task.assignment = { ...exhaustiveRun.bestAssignment };
      selectedContainer = null;
      refresh("Применён план полного перебора");
    });
    content.append(apply);
  }
}

async function runExhaustive() {
  if (!task || exhaustiveBusy) return;
  exhaustiveBusy = true;
  exhaustiveRun = null;
  const revision = taskRevision;
  const snapshot = JSON.parse(JSON.stringify(task));
  renderMethod();
  try {
    const answer = await post("/api/solve", { method: "exhaustive", task: snapshot,
      options: { ...exhaustiveSettings } });
    if (revision === taskRevision) {
      exhaustiveRun = answer;
      exhaustiveStage = Math.max(0, answer.history.length - 1);
    }
  } catch (error) {
    if (revision === taskRevision) exhaustiveRun = { error: `Перебор не выполнен: ${error.message}` };
  } finally {
    exhaustiveBusy = false;
    renderMethod();
  }
}

function renderMethod() {
  document.querySelectorAll(".method-tab").forEach((tab) => {
    const active = tab.dataset.method === currentMethod;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  const content = byId("method-content");
  content.textContent = "";
  if (currentMethod === "manual") {
    content.append(element("p", "", "Вы сами строите план. Каждое изменение проверяется по четырём условиям: места, масса, мощность и срок."));
    content.append(element("div", "preview-label", "ПОСЛЕДНИЕ ПЕРЕМЕЩЕНИЯ"));
    const line = element("div", "history");
    if (history.length) history.slice().reverse().forEach((item) => line.append(element("span", "", item)));
    else line.append(element("span", "", "Переместите контейнер, чтобы увидеть изменение стоимости"));
    content.append(line);
  } else if (currentMethod === "genetic") {
    renderGenetic(content);
  } else if (currentMethod === "branch_bound") {
    renderBranch(content);
  } else {
    renderExhaustive(content);
  }
}

async function loadExample() {
  try {
    const response = await fetch("/api/example");
    if (!response.ok) throw new Error("Сервер не вернул пример.");
    task = await response.json();
    renderEditors();
    await refresh();
  } catch (error) { showMessage(`Не удалось загрузить пример: ${error.message}`); }
}

async function generate() {
  try {
    const counts = [byId("generate-count"), byId("generate-sites"), byId("generate-seed")].map((input) => Number(input.value));
    task = await post("/api/generate", { containerCount: counts[0], siteCount: counts[1], seed: counts[2] });
    invalidateSearch();
    selectedContainer = null;
    history.length = 0;
    renderEditors();
    await refresh();
  } catch (error) { showMessage(`Генерация не выполнена: ${error.message}`); }
}

byId("generate-button").addEventListener("click", generate);
byId("add-container").addEventListener("click", addContainer);
byId("add-site").addEventListener("click", addSite);
byId("limit-hours").addEventListener("change", (event) => {
  task.limitHours = Number(event.target.value);
  invalidateSearch();
  refresh();
});
byId("tariff-mode").addEventListener("change", (event) => {
  task.tariffMode = event.target.value;
  invalidateSearch();
  renderFormula();
  refresh();
});
document.querySelectorAll(".method-tab").forEach((tab) => tab.addEventListener("click", () => {
  currentMethod = tab.dataset.method;
  renderMethod();
}));
loadExample();
