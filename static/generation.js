"use strict";

let generationDetailsOpen = false;

function addGenerationDetails(box, run, index) {
  const details = make("details", "", "generation-details");
  const panel = make("div");
  details.append(make("summary", "Подробно о поколении " + run.history[index].generation), panel);
  details.open = generationDetailsOpen;
  details.ontoggle = () => {
    generationDetailsOpen = details.open;
    if (details.open && !panel.children.length) renderGenerationDetails(panel, run, index);
  };
  box.append(details);
  if (details.open) renderGenerationDetails(panel, run, index);
}

function renderGenerationDetails(box, run, index) {
  const stage = run.history[index];
  const before = index ? run.history[index - 1].population : [];
  const formatPlan = (id) => id === null ? "не найден" : "П" + (id + 1);
  const price = (id) => id === null ? "—" : run.plans[id].valid ? money(run.plans[id].cost) : "недопустим";
  const controls = make("div", "", "controls");
  function button(parent, text, action) {
    const node = make("button", text);
    node.onclick = action;
    parent.append(node);
    return node;
  }
  function chooseGeneration(value) {
    stages.genetic = value;
    renderRun("genetic");
  }
  button(controls, "Предыдущее поколение", () => chooseGeneration(index - 1)).disabled = index === 0;
  const label = make("label", "Поколение для просмотра");
  const generation = make("select");
  run.history.forEach((item, i) => {
    const option = make("option", item.generation + " · " + money(item.bestCost));
    option.value = i;
    generation.append(option);
  });
  generation.value = index;
  generation.onchange = () => chooseGeneration(Number(generation.value));
  label.append(generation);
  controls.append(label);
  button(controls, "Следующее поколение", () => chooseGeneration(index + 1)).disabled = index === run.history.length - 1;
  box.append(controls, make("p", index === 0 ? "Создание начальной популяции. Родители ещё не выбирались." :
    run.selectionMethod === "best_half" ? "Прежняя популяция отсортирована по стоимости. Верхняя половина — родители, нижняя — резерв. Группа доступных родителей сохраняется до конца поколения." :
      "Для каждого родителя проводится отдельный турнир: выбираются до трёх разных участников, побеждает самый дешёвый."));
  if (index) box.append(make("p", run.selectionMethod === "best_half" ?
    "После неудачного исправления сразу берётся самый дешёвый ещё не добавленный план нижней половины. Если резерв исчерпан, пробуется следующая пара родителей. Добор старых планов в конце также использует только нижнюю половину." :
    "После неудачного исправления сразу берётся самый дешёвый ещё не добавленный план прежней популяции, который не выбирался родителем. Он исключается из дальнейшего выбора родителей этого поколения."));
  box.append(make("p", "Позиции хромосомы соответствуют контейнерам: " + task.containers.map((c) => c.id).join(", ") +
    ". Значение — площадка. Номер плана сохраняется во всём запуске."));

  function populationTable(title, ids, roles = false) {
    const section = make("details");
    section.append(make("summary", title + " (" + ids.length + ")"));
    const scroll = make("div", "", "scroll");
    const table = make("table");
    const head = make("tr");
    for (const text of ["План", "Стоимость", "Хромосома", ...(roles ? ["Отбор"] : [])]) head.append(make("th", text));
    table.append(head);
    const eligible = new Set(stage.parentPool);
    const used = new Set(stage.events.flatMap((event) => event.parents || []));
    const reserved = new Set(stage.events.filter((event) => event.kind === "reserve").map((event) => event.result));
    const carried = new Set(stage.events.filter((event) => event.kind === "carry").map((event) => event.result));
    [...ids].sort((a, b) => run.plans[a].cost - run.plans[b].cost).forEach((id) => {
      const row = make("tr");
      row.append(make("td", formatPlan(id)), make("td", price(id)),
        make("td", run.plans[id].chromosome.map((j) => task.sites[j].id).join(" ")));
      if (roles) row.append(make("td", reserved.has(id) ?
        (run.selectionMethod === "best_half" ? "Добавлен из резерва нижней половины" : "Добавлен из резерва; исключён из родителей") :
        used.has(id) ? "Выбран родителем" : eligible.has(id) ? "Доступен для выбора" :
        carried.has(id) ? "Добран из нижней половины" : "Нижняя половина: резерв"));
      table.append(row);
    });
    scroll.append(table);
    section.append(scroll);
    box.append(section);
  }
  if (before.length) populationTable("Популяция до отбора", before, true);

  const kinds = { manual: "Текущий ручной план", initial: "Начальный поиск", elite: "Сохранение лучшего плана",
    crossover: "Скрещивание", reserve: "Резерв после неудачного исправления",
    carry: "Добор из прежней популяции", generate: "Поиск нового плана" };
  const statuses = { accepted: "Добавлен в популяцию", duplicate: "Отклонён: повтор в новом поколении",
    retired: "Отклонён: ранее выбывший план", not_found: "Подходящий план не найден" };
  box.append(make("h4", "Действия поколения"));
  const actions = make("div", "", "controls");
  const actionLabel = make("label", "Действие поколения");
  const action = make("select");
  stage.events.forEach((event, i) => {
    const option = make("option", (i + 1) + ". " + kinds[event.kind] + " · " + statuses[event.status]);
    option.value = i;
    action.append(option);
  });
  actionLabel.append(action);
  const previous = button(actions, "Предыдущее действие", () => showAction(Number(action.value) - 1));
  actions.append(actionLabel);
  const next = button(actions, "Следующее действие", () => showAction(Number(action.value) + 1));
  const preview = make("div", "", "preview");
  box.append(actions, preview);
  action.onchange = () => showAction(Number(action.value));

  function showAction(value) {
    action.value = value;
    previous.disabled = value === 0;
    next.disabled = value === stage.events.length - 1;
    const event = stage.events[value];
    preview.replaceChildren(make("h4", kinds[event.kind] + ": " + statuses[event.status]));
    const columns = [];
    if (event.parents) {
      event.parents.forEach((id, i) => {
        columns.push({ label: "Родитель " + (i + 1), id });
        const participants = event.participants[i];
        if (participants.length) preview.append(make("p", "Турнир " + (i + 1) + ": " +
          participants.map((p) => formatPlan(p) + " (" + price(p) + ")").join("; ") + ". Победитель: " + formatPlan(id) + "."));
      });
      columns.push({ label: "После скрещивания", id: event.crossed, compare: event.parents[0] });
      if ("repaired" in event) {
        columns.push({ label: "После исправления", id: event.repaired, compare: event.crossed });
        preview.append(make("p", "Исправление: " + fmt.format(event.repairNodes) + " проверок назначений." +
          (event.repairLimited ? " Достигнут предел 5 000 проверок." : "") +
          " Сначала пробуются назначения потомка, затем другие площадки, если продолжение не подходит." +
          " Ранее выбывшие планы и повторы нового поколения исключены из поиска."));
        if ("reserve" in event) {
          preview.append(make("p", event.reserve === null ? "Подходящего плана в резерве нет. Будет выбрана следующая пара родителей." :
            "Исправление не удалось. В новое поколение сразу добавлен " + formatPlan(event.reserve) +
            (run.selectionMethod === "best_half" ? " из нижней половины; группа родителей сохраняется." :
              " из резерва; он больше не выбирается родителем в этом поколении.")));
          if (event.reserve !== null) columns.push({ label: "Из резерва", id: event.reserve });
        }
      } else preview.append(make("p", "Потомок после скрещивания допустим, исправление не требуется."));
      if (event.mutation) {
        const messages = { disabled: "Мутации выключены.", skipped: "В этой попытке мутация не выполнялась.",
          changed: "Мутация изменила план.", unchanged: "Допустимого изменения выбранного типа не найдено." };
        preview.append(make("p", messages[event.mutation] + (event.mutationAttempts ?
          " Попыток: " + event.mutationAttempts + ". Запрещённых выбывших планов пропущено: " + event.mutationRetiredSkips + "." : "")));
        columns.push({ label: "После мутации", id: event.result, compare: columns.at(-1).id });
      }
    } else if (event.result !== null) columns.push({ label: "План", id: event.result });
    if (event.nodes !== undefined) preview.append(make("p", "Проверок назначений: " + fmt.format(event.nodes) +
      (event.limited ? ". Поиск остановлен по пределу проверок." : ". Поиск этой попытки завершён.")));
    if (event.kind === "carry") preview.append(make("p", run.selectionMethod === "best_half" ?
      "Для добора взят ещё не добавленный план нижней половины прежней популяции." :
      "Этот план не выбирался родителем и ещё не добавлен в новое поколение."));
    if (event.kind === "reserve") preview.append(make("p", run.selectionMethod === "best_half" ?
      "Предыдущее исправление не удалось. Взята самая дешёвая ещё не добавленная особь нижней половины. Верхняя половина остаётся доступной для выбора родителей." :
      "Предыдущее исправление не удалось. Взята самая дешёвая особь прежней популяции среди тех, которые ещё не добавлены и не выбирались родителями. Она исключена из дальнейшего выбора родителей этого поколения."));
    if (event.kind === "elite") preview.append(make("p", "Лучший известный план сохранён по правилу элитизма."));
    if (!columns.length) return;
    const scroll = make("div", "", "scroll");
    const table = make("table");
    const head = make("tr");
    head.append(make("th", "Контейнер"));
    columns.forEach((column) => head.append(make("th", column.label + " · " + formatPlan(column.id) + " · " + price(column.id))));
    table.append(head);
    task.containers.forEach((container, i) => {
      const row = make("tr");
      row.append(make("td", container.id));
      columns.forEach((column) => {
        const j = column.id === null ? null : run.plans[column.id].chromosome[i];
        const changed = column.compare != null && j !== null && j !== run.plans[column.compare].chromosome[i];
        row.append(make("td", j === null ? "—" : task.sites[j].id, changed ? "gene-changed" : ""));
      });
      table.append(row);
    });
    scroll.append(table);
    preview.append(scroll, make("p", "Рамка отмечает изменённые назначения. Скрещивание сравнивается с первым родителем; исправление и мутация — с предыдущим этапом."));
  }
  showAction(0);
  populationTable("Итоговая популяция", stage.population);
  populationTable("Планы, выбывшие в этом поколении", stage.discarded);
  box.append(make("p", "Всего выбывших планов к этому поколению: " + stage.discardedCount +
    ". Они исключены из дальнейшего поиска в этом запуске."));
}
