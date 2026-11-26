# Открытые проекты с формальной проверкой CDC и наборы эталонных примеров

Обзор на 20.11.2026. Цель – взять готовые приёмы (модели тактов, метастабильности, оракулы, свойства) и тестовые случаи для Open Formal CDC.

Как сделано:
- репозитории клонированы `git clone --depth 1` во временную папку сессии (scratchpad, `repos-oss/<имя>/src`); ничего не запускалось и не собиралось, только чтение;
- лицензии проверены по файлам `LICENSE`/`COPYING`, заголовкам файлов и через GitHub API;
- PDF среди найденного нет: блоги ZipCPU – HTML-страницы, у остальных проектов статей нет. Папка `refs/pdf/oss-examples/` не создавалась;
- там, где вывод сделан без запуска, стоит пометка «не проверено».

Обозначения: `CRT` = `adibis/cdc-rdc-tests`, `AFC` = `ymt1001816-cyber/async-fifo-cdc`, `CP` = `hevangel/cdc_primitives`, `CC` = `pulp-platform/common_cells`, `OT` = `lowRISC/opentitan`.

---

## 1. Таблица проектов

| # | Проект | Коммит, дата | Лицензия | Что внутри | Полезность |
|---|---|---|---|---|---|
| 1 | [adibis/cdc-rdc-tests](https://github.com/adibis/cdc-rdc-tests) | `737825c`, 14.11.2026 | **Apache-2.0** (REUSE, `LICENSE`, `REUSE.toml`) | 213 эталонных случаев CDC/RDC (`design.sv` + `design.sdc` + `manifest.json`), 36 правил; три обвязки SBY с 17 поведенческими вердиктами | **высокая** – готовый регрессионный набор и формат |
| 2 | [hevangel/cdc_primitives](https://github.com/hevangel/cdc_primitives) | `82a85ca`, 03.11.2026 | **не указана** в репозитории; README: «Authored for the ai_hw_engineer project. See that repository for terms.» Родитель [ai_hw_engineer](https://github.com/hevangel/ai_hw_engineer) – MIT, `cdc_primitives` в нём – подмодуль `libs/cdc_primitives` | 15 ячеек CDC + 3 моста (APB, AXI-Lite, AXI-Stream), в каждой блок `ifdef FORMAL`, 18 заданий SBY (bmc/prove/cover), шаблоны SDC | средняя – таксономия ячеек и приём FTOP; сами свойства слабые (см. 2.2) |
| 3 | [ymt1001816-cyber/async-fifo-cdc](https://github.com/ymt1001816-cyber/async-fifo-cdc) | `da0fe77`, 01.11.2026 | **не указана** (нет `LICENSE`, API – нет лицензии) | Модель метастабильности для SBY, асинхронный FIFO с доказательством k-индукцией, импульсный синхронизатор и рукопожатие (PDR), испорченные варианты, синхронизатор сброса | **высокая** по идеям, код брать нельзя |
| 4 | [pulp-platform/common_cells](https://github.com/pulp-platform/common_cells) | `e73baae`, 18.09.2026 | **Solderpad Hardware License 0.51** (основана на Apache-2.0) | Ячейки `cc_cdc_2phase`, `cc_cdc_4phase`, `cc_cdc_fifo_gray`, `cc_cdc_fifo_2phase`, `*_clearable`, `cc_cdc_reset_ctrlr`; формальная проверка контроллера сброса **через `read_slang`** в SBY; тесты с внесением задержек по битам | средняя – единственный найденный пример SBY + yosys-slang для CDC; реальные ячейки для набора |
| 5 | [lowRISC/opentitan](https://github.com/lowRISC/opentitan) (только `hw/ip/prim*`, `hw/top_earlgrey/cdc`, `doc`) | `c03938e`, 20.11.2026 | **Apache-2.0** | Методология CDC, `prim_flop_2sync` + `prim_cdc_rand_delay` (рандомизация CDC в симуляции), утверждения в `prim_*` CDC, макросы утверждений для Yosys, FPV с внесением перекоса, отказы (waivers) Meridian CDC | средняя/высокая – модель MSI в простой форме, шаблоны свойств, внешний эталон (отказы) |
| 6 | [ZipCPU/wb2axip](https://github.com/ZipCPU/wb2axip) `rtl/afifo.v` | `2e8d3bc`, 02.06.2026 | **Apache-2.0** (заголовок файла и README) | Асинхронный FIFO с полным формальным контрактом («двойная запись»), такты из `(* gclk *)` и `(* anyseq *)` | средняя – оракул для FIFO, модель тактов |
| 7 | [ZipCPU/website](https://github.com/ZipCPU/website) `examples/` + блог ([afifo](https://zipcpu.com/blog/2018/07/06/afifo.html), [tfrvalue](https://zipcpu.com/blog/2020/10/03/tfrvalue.html), [areset](https://zipcpu.com/formal/2018/04/12/areset.html), [clkswitch](https://zipcpu.com/formal/2018/05/31/clkswitch.html)) | репозиторий обновлён 18.07.2026 | `examples/afifo.v` – **GPL-3.0**; `examples/tfrvalue.v` – **public domain** (заголовок файла) | Модель тактов счётчиками с шагом `anyconst`, свойства стабильности входов между фронтами, рукопожатие с проверкой стабильности данных | средняя – классика приёмов |
| 8 | [YosysHQ/sby](https://github.com/YosysHQ/sby) `docs/examples/multiclk/` | `b21f778`, 16.11.2026 | ISC (файл `COPYING`; GitHub API показывает NOASSERTION) | Минимальный пример `multiclock on`: двухпортовая память, теневой регистр по `anyconst`-адресу, `(* gclk *)` | низкая/средняя – справочный образец |
| 9 | [adibis/icarium](https://github.com/adibis/icarium) | `62bf1a4`, 15.11.2026 | **Apache-2.0** | Открытый **структурный** анализатор CDC/RDC (Zig, нетлист Yosys + SDC), 36 правил, отчёты JSON/SARIF, эталонный для CRT; сверен с отказами OpenTitan | средняя – кандидат во второй входной адаптер; в `background.md` его нет |
| 10 | [Mumunu-team/mununu PR #773](https://github.com/Mumunu-team/mununu/pull/773) | влит 24.10.2026 | не определена (API: NOASSERTION) | Структурный lint CDC + сценарий SBY `multiclock on`, метастабильность не моделируется (по описанию PR) | низкая |

Не вошли (просмотрены по результатам поиска, только асинхронные FIFO без модели метастабильности): `SatyajitMondal27/AsyncFIFO`, `drewbabel/fifo`, `navyathag13-ui/fifo-verification`, `gowthamaruthi/async-fifo-formal-sv`, `SarangKudtarkar/Formal_Verification_Async_FIFO`, `buttercutter/afifo`. Полезное наблюдение из README `navyathag13-ui/fifo-verification` (по результату поиска, код не читался): при `multiclock on` и синхронном сбросе решатель может не дать одному такту ни одного фронта во время сброса, и домен остаётся в произвольном состоянии. Отсюда правило: сброс держать до первого фронта каждого такта (у нас так уже сделано, `локальные заметки`).

По EBMC открытых примеров проверки CDC не найдено.

---

## 2. Разбор по проектам

### 2.1. adibis/cdc-rdc-tests (CRT)

**Что это.** Набор для проверки анализаторов CDC/RDC в духе sv-tests: на каждый случай известен точный ответ. Версия 0.1, автор – тот же, что у icarium. Единственный прогнанный анализатор – icarium (213/213).

**Состав (tier1, `docs/catalog.md`, `README.md`):**
- 213 случаев, 36 правил: CDC-001...CDC-026 (CDC-007 зарезервировано) и RDC-001...RDC-011;
- 220 ожидаемых находок: 176 нарушений (error/warning) и 44 записи (note);
- 62 «молчащих» случая: верная схема, анализатор должен промолчать;
- категории правил: safety, protocol, policy, constraint, record (`docs/rule-map.md`, `docs/rules.json`);
- происхождение: `cdc*`/`rdc*` написаны по контрактам правил, `fx_*` – из тестов icarium с ревизией, `e2e_*` – сквозные;
- tier2 (переходы OpenTitan, по которым дизайнеры выписали отказы) и tier3 (чистые промышленные модули) – в планах.

Распределение ожидаемых находок по правилам (подсчёт по `manifest.json`): CDC-001 – 13, CDC-010 – 12, CDC-024 – 10, CDC-011 – 7, RDC-001 – 6, остальные по 2–5, записи RDC-010 – 43, CDC-026 – 13.

**Формат случая.**
- `design.sv` – синтезируемый SV без начальных значений; CI собирает его Verilator, slang, Yosys и **yosys-slang**, так что синтаксис нам подходит;
- `design.sdc` – подмножество из пяти команд: `create_clock`, `create_generated_clock`, `set_clock_groups -asynchronous`, `set_input_delay`, `set_output_delay` (`docs/sdc-subset.md`);
- `manifest.json` – `id`, `top`, `expect[]` (`rule`, `line` или `dst`, `severity`), `params` (пока только `sync_depth`), `allow_extra`, `notes`; схема – `schema/manifest.json`;
- атрибуты-обещания дизайнера (`docs/attributes.md`): `cdc_sync`, `cdc_static`, `cdc_handshake`, `cdc_gray`, `reset_polarity`, `reset_sync`, `glitchless_clock_mux`, `scan_en`.

Пример: `cases/tier1/fx_cdc013_bad_toggle_bare/manifest.json` – одна находка `CDC-013`, строка 13, `warning`.

**Как сравнивают** (`docs/method.md`): точное совпадение по паре (правило, строка или имя порта), мультимножество; лишняя находка – провал, если нет `allow_extra`. Итог по случаю: `pass`, `fail`, `unsupported`, `error`; балл – число `pass` из всех 213. Для чужого анализатора нужно опубликовать отображение правил, заявленную область, команду и файл результатов.

**Формальная часть.** `formal/cases.json` + `scripts/formal-check.py` + три обвязки в `formal/`. Вердиктов 17:

| Обвязка | Случаев | Утверждение | Глубина |
|---|---|---|---|
| `event_conservation.sv` | 7 (CDC-013) | число принятых событий источника = числу событий на приёмнике после затишья | 450 |
| `gray_sequence.sv` | 8 | каждое изменение выхода – следующее значение кода Грея | 160 |
| `clock_switch.sv` | 2 (CDC-010) | на выходе мультиплексора тактов нет «коротышей» короче L шагов | 200 |

Задание SBY одно на все (`scripts/formal-check.py:119-134`): `mode bmc|cover`, `multiclock on`, `smtbmc yices`, `read -formal ... design.sv harness.sv` – **родной фронтенд Yosys, не slang**.

Такты в `event_conservation.sv` строятся из глобального такта с отношением полупериодов из SDC и свободной фазой приёмника (`formal/event_conservation.sv:29-38`):

```systemverilog
    (* gclk *) logic gclk;

    logic src_clk = 0, dst_clk = 0;
    logic [7:0] src_ph = 0, dst_ph = 0;
    (* anyconst *) logic [7:0] dst_off;
    always @* assume (dst_off < `DST_HALF);
    always @(posedge gclk) begin
        src_ph <= (src_ph == `SRC_HALF - 1) ? 0 : src_ph + 1;
        if (src_ph == `SRC_HALF - 1) src_clk <= !src_clk;
        dst_ph <= (dst_ph == `DST_HALF - 1) ? 0 : dst_ph + 1;
        if (dst_ph == dst_off) dst_clk <= !dst_clk;
    end
```

Счёт событий и само утверждение (`formal/event_conservation.sv:72-81, 106-108`):

```systemverilog
    logic [7:0] in_cnt = 0, since = 8'hff;
    always @(posedge src_clk)
        if (run && accept) begin
            in_cnt <= in_cnt + 1;
            since <= 0;
        end else if (since != 8'hff) since <= since + 1;
`ifdef SPACED
    always @* if (ev) assume (since >= 3 * `DST_HALF / `SRC_HALF);
`endif
...
    wire settled = run && quiet >= 5 && in_cnt == in_prev;
    always @* if (settled) assert (in_cnt == out_cnt);
    always @* cover (settled && out_cnt >= 3);
```

Проверка кода Грея через функцию «следующее значение» (`formal/gray_sequence.sv:59-76`):

```systemverilog
    function automatic logic [`W-1:0] succ(input logic [`W-1:0] g);
        logic [`W-1:0] b;
        b[`W-1] = g[`W-1];
        for (int i = `W - 2; i >= 0; i--) b[i] = b[i+1] ^ g[i];
        b = b + 1'b1;
        succ = b ^ (b >> 1);
    endfunction
    ...
    always @* if (step && changes != 0) assert (q == succ(q_d));
```

Главный приём – **пара задач на один вердикт** (`scripts/formal-check.py:142-157`):

```python
    if entry["events"] == "loses":
        return [("free", False, "bmc", "FAIL"),
                ("spaced", True, "bmc", "PASS"),
                ("cover", True, "cover", "PASS")]
    if entry["events"] == "conserves":
        return [("free", False, "bmc", "PASS"),
                ("cover", False, "cover", "PASS")]
```

«Теряет события» подтверждается только тогда, когда при свободном потоке есть контрпример, а при разреженном (раз в 3 периода приёмника) его нет. Так доказано, что дефект именно в темпе, а не в чём-то ещё. Кроме того, сценарий сверяет `cases.json` с манифестами: случай «теряет» тогда и только тогда, когда манифест ждёт CDC-013 (`formal-check.py:186-204`).

**Что взять:**
1. Формат `design.sv + design.sdc + manifest.json` – для наших `examples/`, с добавлением поля формального вердикта по каждому переходу.
2. 17 формальных вердиктов – сразу как регрессию формальной части.
3. Приём «свободный поток – контрпример, поток с допущением – доказано»: это и есть проверка того, что допущение из YAML снимает ложный контрпример.
4. Обязательное покрытие (cover) на каждое доказательство.
5. Отношение частот из SDC (`create_clock -period`) – вход для генератора тактов (целочисленное отношение, иначе отказ: `formal-check.py:73-74`).
6. Явное перечисление допущений (`docs/assumptions.md`): сброс держится весь прогрев и больше не подаётся, нет начальных значений, прогрев сбрасывает синхронизаторы, первая смена после прогрева не проверяется. Такая таблица допущений нужна и в нашем отчёте.
7. Набор как вход для проверки адаптера структурного анализа: прогнать `локальный структурный анализатор` (или icarium) на 213 случаях и сверить классы переходов.

**Что не годится или требует проверки для yosys-slang:**
- обвязки используют `(* gclk *)`, `(* anyconst *)`, начальные значения `logic x = 0` и немедленные `assert` в `always @*`. С родным `read -formal` это работает (так у автора). Атрибут `(* anyseq *)` slang сохраняет (навык `eda-oss`); сохраняет ли он `(* gclk *)` и `(* anyconst *)` – **не проверено**;
- проверки только ограниченные (BMC), неограниченных доказательств нет;
- метастабильность не моделируется: синхронизаторы – идеальные триггеры;
- допустимы только целочисленные отношения периодов.

**Лицензия.** Apache-2.0, как у нас. Можно копировать случаи и обвязки с сохранением строк `SPDX-FileCopyrightText: 2026 Aditya Shevade and the cdc-rdc-tests contributors` и пометкой об изменениях (п. 4 Apache-2.0). Лучше не копировать, а подключать как внешний набор (git submodule или скачивание фиксированного коммита в тестах). Тогда набор обновляется без ручного переноса, а наш репозиторий не смешивает авторство.

**Годится ли как регрессия.** Да, на двух уровнях:
- **структурный вход:** ответы точные, формат простой, есть молчащие случаи (защита от ложных срабатываний);
- **формальная часть:** 17 готовых вердиктов. Для правил, где поведенческий вердикт осмыслен, но его нет (CDC-003, CDC-005, CDC-009, CDC-012, CDC-019, CDC-020, RDC-009), мы можем сами добавить вердикты по тем же `design.sv` (раздел 3). Предложить их автору – только с согласия пользователя.

### 2.2. hevangel/cdc_primitives (CP)

**Устройство проверки.**
- 15 ячеек и 3 моста, у каждой в RTL блок `` `ifdef FORMAL ``;
- `.sby` создаёт `scripts/gen_sby.sh`: задачи `bmc` (`abc bmc3`, глубина 20), `prove` (`abc pdr`), `cover` (`smtbmc --syn --nopresat z3`, глубина 40);
- чтение – `read -formal -D FORMAL -D <МОДУЛЬ>_FTOP`, затем `prep`, `memory_map`;
- заявлено 54/54 (18 модулей × 3 задачи).

**Главный недостаток: ни в одном `.sby` нет `multiclock on`** (`grep multiclock` по репозиторию пуст). Без этого режима все триггеры в SBY работают от одного неявного глобального такта ([SBY issue #255](https://github.com/YosysHQ/sby/issues/255)). Значит `sclk` и `dclk` фактически один такт: ни асинхронность, ни метастабильность не моделируются. 54/54 – это проверка в синхронном приближении (`scripts/gen_sby.sh:17-34`):

```sh
        echo '[tasks]'
        echo 'bmc'
        echo 'prove'
        echo 'cover'
        echo
        echo '[options]'
        echo 'bmc: mode bmc'
        echo 'bmc: depth 20'
        echo 'prove: mode prove'
        echo 'prove: depth 20'
        echo 'cover: mode cover'
        echo 'cover: depth 40'
        echo
        echo '[engines]'
        echo 'bmc: abc bmc3'
        echo 'prove: abc pdr'
        echo 'cover: smtbmc --syn --nopresat z3'
```

**Свойства по ячейкам** (выборка из блоков `FORMAL`):

| Ячейка | Утверждения | Оценка |
|---|---|---|
| `cdc_sync_bit` | `dout == sync_q[last]`, последний каскад = `$past` предыдущего | повтор RTL |
| `cdc_sync_toggle` | `d_pulse == sync1_q ^ sync2_q` | повтор RTL |
| `cdc_sync_pulse` | `d_pulse == d_event` (с растяжкой – с учётом счётчика) | повтор RTL |
| `cdc_sync_event_handshake` | нет готовности при запросе в полёте, `d_event` = фронт синхронизированного запроса | частично полезно |
| `cdc_sync_sticky` | после `s_set` флаг поднят | полезно |
| `cdc_sync_gray` | `gray2bin(bin2gray(x)) == x` для `anyconst x`, `gray_q == bin2gray($past(s_bin))` | **не проверяет**, что `s_bin` меняется не больше чем на 1 |
| `cdc_bus_handshake`, `cdc_bus_mcp` | один запрос в полёте, `d_data == f_data` после `d_valid` (оракул `anyconst`) | оракул слабый, см. ниже |
| `cdc_async_fifo` | `wgray == bin2gray(wbin)`, заполнение ≤ DEPTH, указатель стоит при full/empty | полезно, но без асинхронности |
| `cdc_event_counter` | счётчик растёт не больше чем на 1 | полезно |
| `rst_sync` | при низком `raw_rst_n` выход низкий | полезно |
| `cdc_clock_stop_ctrl` | такт выключается только после подтверждения, при выключенном такте выходы изолированы | полезно |
| мосты APB, AXI-Lite, AXI-S | готовность = не полон / не пуст, протокол APB | локальные |

**Оракул `anyconst` для рукопожатия** (`rtl/cdc_bus_handshake.sv:109-124`):

```systemverilog
  (* anyconst *) logic [WIDTCASE-1:0] f_data;
  logic f_dpv = 1'b0;
  always_ff @(posedge dclk) begin
`ifdef CDC_BUS_HANDSHAKE_FTOP
    if (!f_dpv) assume (!drst_n && !srst_n);
    assume (drst_n == srst_n);
    assume (s_data == f_data);   // source holds the constant payload
`endif
    f_dpv <= 1'b1;
    if (drst_n) assert (d_valid == (req_sync2 & ~req_sync3));
`ifdef CDC_BUS_HANDSHAKE_FTOP
    // d_data is registered, so it carries the delivered word the cycle AFTER
    // the d_valid strobe. It must then equal the (constant) source payload.
    if (f_dpv && drst_n && $past(drst_n) && $past(d_valid))
      assert (d_data == f_data);
`endif
```

Здесь вход `s_data` весь прогон равен одной константе, поэтому данные никогда не меняются. Несогласованный захват многобитной шины такой оракул не может обнаружить в принципе. Нужен оракул по номеру транзакции: `anyconst` выбирает, какую передачу отслеживать; её данные запоминаются, остальные передачи свободны (так у ZipCPU в `afifo.v`, 2.6, и у AFC в `bus_props`, 2.3).

**Что взять:**
- **FTOP-защиту допущений:** допущения среды включаются только тогда, когда модуль – верх задания, и не «протекают» в родителя. У нас это решается тем, что допущения живут в отдельном модуле-обвязке, а не в RTL;
- таксономию переходов (A1–A7 – биты и события, B1–B7 – слова, C1–C7 – потоки, D1–D4, F1 – сброс, G3–G4 – останов такта) и таблицу «что передаём – какая ячейка» как перечень шаблонов свойств;
- шаблоны SDC (`constraints/*.sdc`): `set_max_delay -datapath_only` для шин Грея и данных под рукопожатием – полезно для раздела отчёта «что ещё нужно проверить в STA».

**Не годится для yosys-slang:** `$past` (11 мест), `read -formal` с `-D`. Перевод в немедленную форму нужен в любом случае.

**Лицензия.** В самом репозитории лицензии нет. Родительский проект ai_hw_engineer – MIT, но `cdc_primitives` в нём только подмодуль, и MIT родителя на него формально не распространяется. Код (RTL ячеек как «верные» примеры) брать только после явного подтверждения лицензии автором (вопрос автору – только с согласия пользователя). Идеи брать можно.

### 2.3. ymt1001816-cyber/async-fifo-cdc (AFC)

**Устройство проверки.**
- `multiclock on`, такты – свободные входы: любое отношение частот, любая фаза, остановленный такт;
- **модель метастабильности** в `rtl/sync2.v` и `rtl/async_capture.v` под `` `ifdef FORMAL ``;
- FIFO: k-индукция (`smtbmc yices`) со вспомогательными инвариантами; импульсный синхронизатор и рукопожатие – PDR (`abc pdr`);
- испорченные варианты обязаны давать FAIL (задачи `bug`, `bus_bug`).

**Модель метастабильности** (`rtl/sync2.v:20-34`):

```verilog
`else
    // formal model of metastability: a bit that changed just before the sampling edge may settle to its
    // old or its new value (chosen freely by the solver), independently of the other bits.
    // "Just before" = in this or the previous solver step; older changes have settled.
    reg  [W-1:0] d_q = 0, d_qq = 0;       // d one and two solver steps ago
    always @($global_clock) begin
        d_q  <= d;
        d_qq <= d_q;
    end
    wire [W-1:0] d_old = (d != d_q) ? d_q : d_qq;   // value before the most recent change
    wire [W-1:0] late  = $anyseq;                   // 1 = this bit still shows its old value
    wire [W-1:0] seen  = (late & d_old) | (~late & d);
    always @(posedge clk or negedge rst_n)
        if (!rst_n) {q, meta} <= 0;
        else        {q, meta} <= {meta, seen};
```

Та же модель стоит в `async_capture.v` – регистре, который захватывает шину из другого домена по разрешению `en`. Так доказывается, что под рукопожатием шина действительно неподвижна в момент захвата.

**Свойства.** Свойство CDC для FIFO: синхронизированный указатель может отставать, но не обгонять (`formal/fifo_props.vh:25-34`):

```verilog
    wire [AW:0] f_occ   = wbin - rbin;          // words in the FIFO
    wire [AW:0] f_lag_r = rbin - f_seen_r;      // how far the write domain's view of rbin lags behind
    wire [AW:0] f_lag_w = wbin - f_seen_w;      // how far the read domain's view of wbin lags behind
    always @(*) if (!f_init) begin
        // CDC: a synchronized pointer may lag behind the real one, but must never be ahead of it
        a_rptr_not_ahead: assert(f_lag_r <= (1 << AW));
        a_wptr_not_ahead: assert(f_lag_w <= (1 << AW));
        // consequence: never more than DEPTH words, never a read from an empty FIFO
        a_no_overflow:    assert(f_occ <= (1 << AW));
    end
```

Шина под рукопожатием: на приёмнике только реально посланные значения, по порядку, без потерь и повторов (`formal/cdc_props.sv:41-45, 57-66`):

```verilog
    reg [W-1:0] f_last = 0, f_prev = 0;           // the last two values handed to the synchronizer
    reg [3:0]   f_sc = 0, f_dc = 0;
    always @(posedge sclk) if (rst_n && send && sready) begin f_prev <= f_last; f_last <= sdata; f_sc <= f_sc + 1; end
    always @(posedge dclk) if (rst_n && dvalid) f_dc <= f_dc + 1;
    wire [3:0] f_pend = f_sc - f_dc;
    ...
        a_real_value: assert(!dvalid || ddata == f_last || ddata == f_prev);
`ifndef BUG
        a_in_order:   assert(!dvalid || (f_pend == 1 && ddata == f_last) || (f_pend == 2 && ddata == f_prev));
        a_no_loss:    assert(f_pend <= 2);
        a_no_dup:     assert(!dvalid || f_pend != 0);
`endif
```

Синхронизатор сброса: асинхронная установка, снятие только по фронту и только после снятия сырого сброса (`formal/rst_sync_props.sv:9-16`):

```verilog
    always @(*) if (!f_init) begin
        // asynchronous assertion: while the raw reset is low, the domain is in reset (no clock needed)
        a_assert_async: assert(arst_n || !rst_n_sync);
        // synchronous deassertion: the output only rises on a rising clock edge
        a_release_sync: assert(!(rst_n_sync && !out_q) || (clk && !clk_q));
        // and only after the raw reset was already high before that edge (at least the 2nd flip-flop stage)
        a_release_late: assert(!(rst_n_sync && !out_q) || arst_q);
    end
```

Испорченные варианты:
- `formal/make_bug.py` получает `async_fifo_binary_bug.v` из исходного RTL заменой строк, и каждая замена должна встретиться ровно один раз. Это простая «мутация по тексту»;
- в `bus_sync_bug.v` у каждого бита шины свой синхронизатор 2FF. По README: симуляция проходит, а формальная проверка с моделью находит смесь двух слов.

**Что взять (идеи, своей реализацией):**
1. Модель «старое или новое значение по каждому биту» для первого каскада и для регистров захвата под рукопожатием.
2. Свойство «синхронизированная копия не обгоняет оригинал» – общий шаблон для указателей FIFO и счётчиков Грея.
3. Оракул «последние два переданных значения + счётчики отправлено/принято» для рукопожатия и импульсов.
4. Три свойства синхронизатора сброса.
5. Задача «испорченный вариант обязан дать FAIL» в каждом примере и мутация по тексту с проверкой однократности замены.
6. Покрытия против пустого доказательства: полный, максимальное заполнение, оборот указателей.

**Что не годится для yosys-slang:**
- `$anyseq` (навык `eda-oss`: slang не знает `$anyseq`/`$anyconst`, но сохраняет атрибут `(* anyseq *)`);
- `always @($global_clock)` – поддержка в slang **не проверена**;
- именованные немедленные утверждения `a_x: assert(...)` в `always @(*)` – вероятно, работают, но метки yosys-slang теряет (`локальные заметки`).

Выход: модель метастабильности не писать в исходнике, а вставлять **проходом Yosys по нетлисту** (перед первым каскадом – ячейка `$anyseq` и мультиплексор). Либо читать модуль модели родным `read_verilog -formal`, а проект – через `read_slang` (смешение фронтендов **не проверено**, см. раздел 4).

**Лицензия.** Нет. По умолчанию все права у автора, код копировать нельзя. Сама модель – общеизвестный приём; у OpenTitan есть равноценная по смыслу модель под Apache-2.0 (2.5). Свою реализацию писать с нуля.

### 2.4. pulp-platform/common_cells (CC)

**Устройство проверки CDC.** Формально проверен только контроллер сброса `cc_cdc_reset_ctrlr` (две половины, протокол isolate/clear между доменами). Это **единственный найденный проект, где SBY работает через yosys-slang** (`formal/cdc_reset_ctrlr_half.sby:26-31`):

```
[script]
plugin -i slang.so
read_slang --std 1800-2017 -Wno-implicit-port-type-mismatch -DCC_CDC_RESET_CTRLR_ASSUME_REMOTE_PHASE --top cc_cdc_reset_ctrlr_half -F ../../cdc_reset_ctrlr.flist
prep -top cc_cdc_reset_ctrlr_half
async2sync
dffunmap
```

- `multiclock` выключен, вместо него `async2sync` + `dffunmap`: оба домена фактически на одном такте, как и в CP. Асинхронность не моделируется;
- движок `abc pdr`, `mode prove`;
- свойства подключаются через `bind` (`cc_cdc_reset_ctrlr_half_properties.sv:315`).

**Приём «assume-guarantee» одним параметром** (`formal/cc_cdc_reset_ctrlr_half_properties.sv:186-190`):

```systemverilog
        if (ASSUME_REMOTE_PHASE) begin
          assume (receiver_next_phase == $past(receiver_next_phase));
        end else begin
          assert (receiver_next_phase == $past(receiver_next_phase));
        end
```

При доказательстве одной половины протокол удалённой стороны – допущение. При доказательстве составной системы то же самое – утверждение. Для нас это готовый способ локализации: переход доказывается с допущениями о соседнем домене, а допущения отдельно проверяются как утверждения на стороне источника.

**Важное противоречие с нашими заметками.** Файлы свойств CC используют `$past` внутри `always_ff` (например, `cc_cdc_reset_ctrlr_properties.sv:145-148`) и читаются через `read_slang`. В `локальные заметки` записано, что yosys-slang не принимает `$past`. Либо yosys-slang уже поддерживает `$past` в немедленных утверждениях, либо у CC эти задания не проходят. В GitHub CI CC формальных заданий нет (только разбор slang), а `formal/README.md` устарел (2019, коммерческий Yosys). **Проверить на сборке 20261118** маленьким примером. Если `$past` работает, переводчик `sva2imm.py` упрощается.

Составная обвязка (`formal/cc_cdc_reset_ctrlr_properties.sv:72-86`): сброс в первом такте каждого домена отдельно, затем сброс снят:

```systemverilog
  always_ff @(posedge a_clk_i) begin
    a_init_q <= 1'b1;
    if (!a_init_q) begin
      assume (!a_rst_ni);
    end
  end

  always_ff @(posedge b_clk_i) begin
    b_init_q <= 1'b1;
    if (!b_init_q) begin
      assume (!b_rst_ni);
    end
  end
```

**Симуляция.** `test/cc_cdc_fifo_gray_tb.sv:475-560` (модуль `cc_cdc_fifo_gray_tb_delay_injector`) вставляет случайные задержки по каждой асинхронной шине (указатели и данные) между половинами FIFO. Это аналог MSI для симуляции, полезен для сравнения.

**Что взять:**
- проверенный образец `read_slang` в SBY;
- приём assume/assert одним параметром;
- `bind` модуля свойств;
- ячейки `cc_cdc_2phase`, `cc_cdc_4phase`, `cc_cdc_fifo_gray`, `cc_cdc_fifo_2phase`, `*_clearable` – как «реальные» верные примеры для регрессии. Это широко используемые ячейки, и их требования к сбросу описаны в заголовках: у `cc_cdc_fifo_gray.sv:54-75` сбросы обоих доменов должны устанавливаться одновременно. Отсюда испорченный сценарий «раздельный сброс» – аналог CASE-8 референсного блока.

**Лицензия.** Solderpad Hardware License 0.51 (основана на Apache-2.0, разрешительная, для аппаратуры). Файлы можно включать в наш набор с сохранением заголовка SHL и файла лицензии в подпапке, лицензия этих файлов остаётся SHL-0.51. Чище – брать как внешний набор фиксированного коммита (Bender или скачивание в тестах).

### 2.5. OpenTitan (OT): методология CDC и что из неё взять

**Методология** (`doc/contributing/hw/methodology.md:132-157`). Стратегия из трёх частей:
- список проверенных ячеек перехода;
- обязательное использование этих ячеек;
- проверка всего проекта промышленным средством CDC.

Подробный «CDC Methodology document» до сих пор помечен «TODO: Coming Soon». Средство – Meridian CDC (Real Intent): `hw/top_earlgrey/cdc/chip_earlgrey_asic_cdc_cfg.hjson`, `tool: meridiancdc`. Отказы в формате Verix выписаны по категориям: `cdc_waivers.w_masync.tcl`, `w_recon.tcl` (W_RECON_GROUPS), `w_data.tcl`, `w_interface.tcl`, `w_g_clk_glitch.tcl` и др., около 1500 строк. В контрольном списке выпуска (по результатам поиска): на D2 все синхронизаторы – только через `prim_flop_2sync`, на D3 прогон CDC чистый, отказы просмотрены.

**Рандомизация CDC в симуляции.** `prim_flop_2sync` под `SIMULATION` вставляет перед первым триггером `prim_cdc_rand_delay` (`hw/ip/prim_generic/rtl/prim_flop_2sync.sv:21-47`), а тот при каждом изменении входа случайно по каждому биту выбирает новое значение или выход первого каскада (`hw/ip/prim/rtl/prim_cdc_rand_delay.sv:50-60`):

```systemverilog
    // Set data_sel at random combinationally when the input changes.
    always @(src_data_i) begin
      data_sel = cdc_instrumentation_enabled ? fast_randomize() : 0;
    end

    // Clear data_del on any cycle start.
    always @(posedge clk_i or negedge rst_ni) begin
      data_sel <= 0;
    end

    always_comb dst_data_o = (prev_data_i & data_sel) | (src_data_i & ~data_sel);
```

- включается ключом `+cdc_instrumentation_enabled=1` в настройках симуляции (например, `hw/ip/prim/dv/prim_alert/prim_alert_sim_cfg.hjson:30`);
- модель: захват пропускает переход входа не больше чем на один такт приёмника, по каждому биту отдельно;
- известные последствия (по результатам поиска): [issue #18912](https://github.com/lowRISC/opentitan/issues/18912) – фильтр помех UART ломался от лишнего такта задержки; в программном тесте референсный блок при включённой рандомизации увеличивают `rise_cycles`. Это ровно наш случай CASE-4 (разброс SERIAL_CLK и SERIAL_DATA на такт);
- `hw/ip/prim/pre_dv/prim_flop_2sync/tb.sv` устарел: вызывает `set_prim_cdc_rand_delay_mode()`, которой в текущем RTL нет.

**Для нас это лучшая основа модели MSI.** Форма «`sel ? q_first : d`» использует только такт приёмника и выход первого каскада, без глобального такта. В формальной версии: `(* anyseq *) logic [W-1:0] sel;` и `d_eff = (q1 & sel & (d ^ q1)) | (d & ~(sel & (d ^ q1)))`. Отличие от модели AFC: «старое значение» – это значение на прошлом фронте приёмника, а не значение до последнего изменения в шагах решателя. Модель OT пессимистичнее при нескольких изменениях между фронтами, но выразима средствами, которые точно принимает yosys-slang. Лицензия Apache-2.0 позволяет взять и сам приём, и код.

**Утверждения в ячейках CDC – готовые шаблоны свойств:**
- данные неподвижны, пока ждём подтверждения (`hw/ip/prim/rtl/prim_sync_reqack_data.sv:119-122`):

  ```systemverilog
    // SRC domain cannot change data while waiting for ACK.
    `ASSERT(SyncReqAckDataHoldSrc2Dst, !$stable(data_i) && chk_flag_q |->
        (!src_req_i || (src_req_i && src_ack_o)),
        clk_src_i, !rst_src_ni || !rst_dst_ni || !chk_flag_q)
  ```
- код Грея: за такт меняется не больше одного бита (`hw/ip/prim/rtl/prim_fifo_async.sv:293-296`):

  ```systemverilog
  `ASSERT(GrayWptr_A, ##1 $countones(fifo_wptr_gray_q ^ $past(fifo_wptr_gray_q)) <= 1,
          clk_wr_i, !rst_wr_ni)
  `ASSERT(GrayRptr_A, ##1 $countones(fifo_rptr_gray_q ^ $past(fifo_rptr_gray_q)) <= 1,
          clk_rd_i, !rst_rd_ni)
  ```
- импульс источника не раньше, чем предыдущий принят (`prim_pulse_sync.sv:67`, `SrcPulseCheck_M`), выходной импульс длиной один такт (`:101`);
- многобитный синхронизатор меняет выход только после совпадения всех проверочных копий (`prim_multibit_sync.sv:80-83`);
- оба домена рукопожатия должны сбрасываться вместе (`prim_sync_reqack.sv:402-406`). Это требование к среде, ровно как CASE-8.

**Макросы утверждений для Yosys** (`hw/ip/prim/rtl/prim_assert_yosys_macros.svh:34-37`, включаются при `` `define YOSYS ``):

```systemverilog
`define ASSERT(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST) \
  always_ff @(posedge __clk) begin                                                       \
    if (! (__rst !== '0)) __name: assert (__prop);                                       \
  end
```

OT превращает `ASSERT` в немедленное утверждение. Но свойства с `|->`, `##1`, `$stable` в немедленной форме не разбираются, поэтому большинство CDC-утверждений OT без перевода в Yosys не пойдут. Для нас это подтверждение подхода «генератор сразу пишет немедленную форму».

**FPV с внесением перекоса** (`hw/ip/prim/fpv/tb/prim_alert_rxtx_async_tb.sv:52-73`). Асинхронный переход в однотактовой модели эмулируется так: каждый провод проходит через 2 регистра, свободный вход выбирает задержку 0 или 1 такт:

```systemverilog
  // for the purposes of FPV, we currently emulate the asynchronous transition
  // only in terms of the skew it may introduce (which is limited to +- 1 cycle)
  ...
  assign alert_rx_in.ping_p = ping_pq[ping_skew_i[0]] ^ ping_err_pi;
  assign alert_rx_in.ping_n = ping_nq[ping_skew_i[1]] ^ ping_err_ni;
```

Это дешёвая альтернатива `multiclock` для проверки сходимости (когда важен только разброс на такт между битами). Подходит для нашего этапа 4 (сходимость) и для CASE-4.

**Что взять:**
- модель MSI по образцу `prim_cdc_rand_delay` (Apache-2.0);
- шаблоны свойств (стабильность данных при рукопожатии, Грей, разнесение импульсов, совместный сброс);
- приём «перекос ±1 такт» для сходимости;
- отказы Meridian как внешний эталон структурной части (так делает icarium: 444 отказа EarlGrey) – позже, для сравнения с промышленным средством.

**Не годится для yosys-slang:** все `ASSERT` с временными операторами – только через перевод. FPV OT рассчитан на Jasper (`*.core` с `fpv`).

### 2.6. ZipCPU: wb2axip `afifo.v`, примеры и блог

**Модель тактов – три варианта:**
- **счётчики с шагом `anyconst`** (`examples/tfrvalue.v`, public domain; блог afifo 2018 – то же через `$global_clock`). Такт = старший бит счётчика, который на каждом шаге растёт на `f_step + 1`. Частоты свободны, но постоянны; скважность около 50 %, есть дрожание фронтов;

  ```verilog
	(* gclk *) reg gbl_clk;
	...
	(* anyconst *)	reg	[LGCLK-2:0]	f_step_a,  f_step_b;
	...
	always @(posedge gbl_clk)
	begin
		f_count_a <= f_count_a + { 1'b0, f_step_a } + 1;
		f_count_b <= f_count_b + { 1'b0, f_step_b } + 1;
	end

	always @(*)
		assume(i_a_clk == f_count_a[LGCLK-1]);
  ```
  (`tfrvalue.v:127-161`, с пропусками);
- **такт «на шаг вперёд»** (`wb2axip/rtl/afifo.v:577-588`, Apache-2.0): `(* anyseq *) reg pre_wclk` – значение такта на следующем шаге, `now_wclk <= pre_wclk`, `assume(i_wclk == now_wclk)`. Тогда `$rose(pre_wclk)` можно проверять комбинационно, без отставания на шаг. Автор отмечает, что `$past` по тактам в multiclock резко замедляет доказательство, поэтому строит свои регистры прошлых значений (`afifo.v:562-575`);
- **свободные такты без ограничений** – как у AFC и в `dpmem.sv` YosysHQ.

**Стабильность входов между фронтами** (`tfrvalue.v:195-205`): если нет фронта `i_a_clk`, входы домена A неподвижны (`assume($stable(...))`), а выходы домена утверждаются неподвижными. В multiclock без этого допущения входы меняются на каждом шаге решателя. Для нашей утилиты: свободный вход домена должен меняться только по фронту своего такта. Это обязательная часть обвязки, иначе получим ложные «иголки».

**Рукопожатие** (`tfrvalue.v:278-280`): пока цепочка синхронизатора запроса в переходе, регистр данных источника неподвижен:

```verilog
	always @(posedge i_b_clk)
	if ( (!(&{b_req, b_pipe})) && ({b_req, b_pipe} != 0) )
		assert($stable(a_data));
```

Это ровно наш шаблон «данные стабильны под рукопожатием», записанный на такте приёмника.

**Контракт FIFO «двойная запись»** (`wb2axip/rtl/afifo.v:616-700`): `anyconst` выбирает адрес; первые две записи по этому и следующему адресу запоминаются; конечный автомат из четырёх состояний требует, чтобы они были прочитаны по порядку и без искажения. Это правильный оракул целостности данных, в отличие от постоянного `f_data` в CP.

**Лицензии:**
- `wb2axip/rtl/afifo.v` – Apache-2.0, можно брать с уведомлением;
- `website/examples/afifo.v` – GPL-3.0, код не брать;
- `website/examples/tfrvalue.v` – public domain, можно брать.

**yosys-slang:** везде `$past`, `$rose`, `$stable`, `(* gclk *)`, `initial` – только родной фронтенд или перевод.

### 2.7. YosysHQ/sby `docs/examples/multiclk`

Двухпортовая память на двух тактах, `multiclock on`, `(* gclk *)`, теневой регистр по `anyconst`-адресу, `assume ($stable(rc) || $stable(wc))` – такты не переключаются на одном шаге. В `.sby` стоит `chformal -early -assume` (смысл опции **не проверялся**, сверить по справке Yosys). Полезен как минимальный образец для отладки нашей сборки заданий. Лицензия ISC.

### 2.8. adibis/icarium

Структурный анализатор (Zig, нетлист Yosys + SDC, 36 правил, JSON/SARIF/TOON, отказы через атрибуты и файлы, импорт отказов Meridian). Эталонный для CRT; на EarlGrey сопоставлен с 444 отказами OpenTitan. Ограничения (README): находки именуются ячейками Yosys (`$procdff$3`), шина – по битам. Формальной части нет.

Для нас icarium – **второй кандидат во входной адаптер** после `локальный структурный анализатор`, и, возможно, лучше OpenCDC: работает по нетлисту Yosys, как и мы, понимает SDC, отчёт JSON. В `docs/background.md` его нужно добавить. Код не смотрели, проверить на референсном блоке – отдельная задача.

### 2.9. Mumunu-team/mununu PR #773

Rust-библиотека; в PR – структурный lint CDC и сценарий `scripts/cdc_formal_sby.sh` с `multiclock on`, который показывает потерю импульса; метастабильность не моделируется (по описанию PR). Лицензия репозитория не определена. Полезность низкая, код не смотрели.

---

## 3. Предложение регрессионного набора

Принцип (из `CLAUDE.md` и CRT): на каждый шаблон свойства – верный вариант («доказано» или «нет контрпримера до глубины N» + достигнутое покрытие) и испорченный («контрпример»). Где есть допущение среды – ещё пара «без допущения / с допущением».

Обозначения итога: **Д** – доказано (PDR или k-индукция), **Дₙ** – нет контрпримера до глубины N (BMC), **К** – контрпример, **НС** – «нет схемы» (структурный итог без доказательства), **C** – покрытие предпосылки достигнуто.

| № | Схема / шаблон свойства | Верный вариант | Испорченный вариант | Ожидаемый итог | Откуда |
|---|---|---|---|---|---|
| 1 | Одиночный бит, 2FF | `fx_cdc001_good_2ff`, `fx_cdc014_good_clean_chain` | `fx_cdc001_bad_sync_missing` (один каскад), `fx_cdc014_bad_gate_between` | верный – схема принята; испорченный – НС | CRT, Apache-2.0 |
| 2 | Код Грея на шине через синхронизаторы (≤1 бит за такт источника) | `fx_cdc004_good_gray_fifo`, `cdc004_gray_chain_silent`, `fx_cdc019_good_gray_marked`, `fx_cdc020_good_gray_marked` | `fx_cdc004_bad_bare_bus`, `cdc004_bare_bus`; свой: счётчик Грея с шагом +2 | Д + C / К | CRT (8 вердиктов `gray_sequence`) + свой |
| 3 | Стабильность данных под рукопожатием | `fx_cdc012_good_handshake`, `cdc004_gated_gray_bus_clean`, `fx_cdc013_good_toggle_ack` | `fx_cdc012_bad_one_sided`, `fx_cdc004_good_mux_gated` (CDC-012 по манифесту) | Д + C / К | CRT (поведенческих вердиктов в CRT нет, добавляем свои) |
| 4 | Сохранение событий через переключающий синхронизатор | `fx_cdc013_good_toggle_ack`, `fx_cdc013_good_slow_toggle` | `fx_cdc013_bad_toggle_bare`, `fx_cdc013_bad_xor_tail`, `cdc013_*` (3 шт.) | верный – Дₙ; испорченный – К без допущения и Дₙ с допущением «события реже 3 периодов приёмника» | CRT (7 вердиктов `event_conservation`) |
| 5 | Ширина импульса быстрый → медленный (источник держит ≥ N тактов приёмника) | `fx_cdc009_good_level_signal`, `fx_cdc009_good_slow_ratio` | `fx_cdc009_bad_fast_pulse`, `cdc009_pulse_fast_slow` | Д / К при отношении частот из SDC | CRT + свой вердикт |
| 6 | Нет «иголки» перед синхронизатором (≤1 вход логики меняется за такт источника) | `fx_cdc003_good_direct_sync`, `fx_cdc003_good_reset_mux`; свой: дерево ИЛИ с одноединичным управлением (как CASE-7) | `fx_cdc003_bad_comb_before_sync`, `cdc003_gate_before_sync` | Д / К | CRT + свой |
| 7 | Сходимость: синхронизированные сигналы одного домена меняются по одному (одноединичный код / Грей) | `fx_cdc005_good_single_chain`, `fx_cdc019_good_gray_marked` | `fx_cdc019_bad_onehot_decode` (смена «один горячий» – 2 бита), `fx_cdc020_bad_sliced_bus`, `fx_cdc005_bad_reconvergent` | Д / К (для `bad_reconvergent` – только с моделью MSI или перекосом ±1) | CRT + свой вердикт; приём перекоса – OT |
| 8 | MSI: шина с синхронизатором на каждый бит | рукопожатие (`fx_cdc012_good_handshake`) с моделью захвата | шина 2FF по битам (`fx_cdc020_bad_sliced_bus`; свой аналог `bus_sync_bug`) | с MSI: Д / К «на приёмнике значение, которого не посылали»; без MSI испорченный даёт Дₙ – это показывает, зачем нужна модель | CRT + своя модель по образцу OT |
| 9 | Асинхронный FIFO: указатель не обгоняет, нет записи в полный и чтения из пустого, данные по порядку | `cc_cdc_fifo_gray` (CC); свой маленький FIFO | свой: указатели в двоичном коде (идея AFC, реализация своя); раздельные сбросы доменов (аналог CASE-8) | Д + C / К (двоичный – К только с MSI) | CC (SHL-0.51) + свой |
| 10 | Синхронизатор сброса (асинхронная установка, синхронное снятие) | `fx_rdc007_good_chain_deassert_polarity`; свой `rst_sync` | `fx_rdc007_bad_chain_deassert_polarity` (вечный сброс); свой: снятие без синхронизатора | Д / К (для «вечного сброса» – К на покрытии снятия) | CRT + свой; свойства – идея AFC |
| 11 | RDC: приёмник не захватывает данные источника, пока тот в сбросе или только что вышел | `fx_rdc009_good_ordered_release`, `fx_rdc009_good_shared_reset` | `fx_rdc009_bad_split_reset` | Д / К | CRT + свой вердикт (позже, этап RDC) |
| 12 | Мультиплексор тактов без «коротышей» | `fx_cdc010_good_glitch_free_mux` | `cdc010_leg_synced_select_runt` | Дₙ (глубина 200) / К | CRT (2 вердикта `clock_switch`) |
| 13 | Совместный сброс доменов для рукопожатия и FIFO (требование к среде) | `cc_cdc_4phase` / `cc_cdc_2phase` с общим сбросом | те же с раздельными свободными сбросами | Д / К | CC (SHL-0.51) |
| 14 | Реальный блок | референсный блок: верные FIFO и рукопожатия | CASE-8, CASE-7, CASE-4 | по локальные заметки | свой (только чтение референсного проекта) |

Порядок внедрения:
1. Случаи 2, 4, 12 – готовые 17 вердиктов CRT. Проверяют сборку заданий, генератор тактов и сравнение итогов без своих шаблонов.
2. Случаи 3, 6, 7 – первые свои шаблоны (этапы 2 и 4 `plan.md`).
3. Случаи 8, 9 – после модели MSI (этап 5).
4. Случаи 10, 11, 13 – RDC и требования к сбросу.

Хранение:
- CRT и CC не копировать, а получать фиксированным коммитом в `tests/external/` (скрипт загрузки + список случаев + наши ожидаемые формальные итоги в отдельном файле `tests/external/crt_formal.yaml`);
- свои примеры – в `examples/` с `SPDX-License-Identifier: Apache-2.0`;
- если всё же копировать файлы CRT – сохранить `SPDX-FileCopyrightText` и указать изменения; файлы CC – с заголовком SHL-0.51 и текстом лицензии в подпапке;
- код AFC, CP и `website/examples/afifo.v` (GPL-3.0) не копировать.

---

## 4. Выводы для архитектуры

1. **Модель тактов – три режима, выбор по YAML:**
   - `free` – свободные такты (`multiclock on`, как AFC): наиболее общий, для доказательства схем;
   - `ratio` – отношение периодов из SDC и свободная фаза (`anyconst`, как CRT): для свойств, зависящих от частот (импульсы, события, CDC-009/013);
   - `skew` – однотактовая модель с перекосом ±1 такт (как FPV OT): дешёвая проверка сходимости.

   Во всех режимах входы домена меняются только по фронту своего такта (допущение, как в `tfrvalue.v`).
2. **Модель MSI делать проходом Yosys по нетлисту**, а не правкой исходника: найти первый каскад по отчёту структурного анализатора и вставить перед ним `$anyseq` + мультиплексор «старое (выход первого каскада) / новое» с условием «вход изменился» (форма `prim_cdc_rand_delay` OT, Apache-2.0). Тогда не важно, принимает ли yosys-slang `$anyseq` и `$global_clock`. Модель для регистров захвата под рукопожатием – та же.
3. **Обвязку (harness) генерировать отдельным модулем,** а не встраивать в RTL. Допущения среды – только в обвязке (урок FTOP из CP). Свойства подключать через `bind`, как в CC.
4. **Фронтенды:** проект – `read_slang`, обвязку попробовать читать родным `read_verilog -formal -sv` (там есть `(* gclk *)`, `$past`, `$stable`). Смешение фронтендов в одном задании **не проверено** – первая проверка на ПК. Отдельно проверить пример CC: принимает ли yosys-slang `$past` в `always_ff` на сборке 20261118. Если да, то `sva2imm.py` упрощается.
5. **Оракулы данных – по номеру транзакции:** `anyconst` выбирает отслеживаемую передачу (адрес FIFO или номер рукопожатия), её данные запоминаются при отправке и сравниваются при приёме (ZipCPU «двойная запись», AFC «последние два значения»). Постоянный `f_data` (CP) не годится: он не видит несогласованности.
6. **Каждый вердикт – набор задач, а не одна:** утверждение + покрытие предпосылки, а при допущении – пара «без допущения → К, с допущением → Д/Дₙ» (CRT). Итог «доказано» без достигнутого покрытия – «не решено» (возможна пустота).
7. **Отчёт об итоге по переходу должен включать допущения:** режим тактов, отношение частот, глубину, модель MSI (вкл/выкл), сброс (общий / раздельный). Образец – таблица `docs/assumptions.md` CRT.
8. **Внешние наборы как регрессия:** CRT (Apache-2.0) – основной: 213 структурных ответов + 17 формальных вердиктов + наши дополнительные вердикты для CDC-003/005/009/012/019/020. CC (SHL-0.51) – реальные ячейки. Оба получать фиксированным коммитом, не копировать.
9. **Входной адаптер:** кроме `локальный структурный анализатор` и OpenCDC, рассмотреть icarium (Apache-2.0, нетлист Yosys + SDC, JSON, сверен с отказами OpenTitan). Тогда CRT проверяет всю цепочку «icarium → Open Formal CDC → SBY» на одних и тех же случаях.
10. **Требования ячеек к среде – отдельный вид свойств:** совместный сброс доменов (OT `SyncReqAckRstSrc/Dst`, заголовок `cc_cdc_fifo_gray.sv`), разнесение импульсов (OT `SrcPulseCheck_M`). Это не свойства схемы, а допущения, которые нужно доказывать на стороне окружения. Ровно они дают находки вида CASE-8.
11. **Слабые места чужих доказательств – в отчёт:** CP и CC доказывают CDC-ячейки без `multiclock`, то есть в синхронном приближении. Наша утилита должна явно отказываться выдавать «доказано» для перехода, если такты в задании не разделены (проверка сборки задания).

---

## Источники

- [adibis/cdc-rdc-tests](https://github.com/adibis/cdc-rdc-tests), [adibis/icarium](https://github.com/adibis/icarium)
- [hevangel/cdc_primitives](https://github.com/hevangel/cdc_primitives), [hevangel/ai_hw_engineer](https://github.com/hevangel/ai_hw_engineer)
- [ymt1001816-cyber/async-fifo-cdc](https://github.com/ymt1001816-cyber/async-fifo-cdc)
- [pulp-platform/common_cells](https://github.com/pulp-platform/common_cells)
- [lowRISC/opentitan](https://github.com/lowRISC/opentitan), [Design Methodology – CDC](https://opentitan.org/book/doc/contributing/hw/methodology.html), [issue #18912](https://github.com/lowRISC/opentitan/issues/18912)
- [ZipCPU/wb2axip](https://github.com/ZipCPU/wb2axip), [ZipCPU/website examples](https://github.com/ZipCPU/website/tree/master/examples)
- ZipCPU: [Crossing clock domains with an Asynchronous FIFO](https://zipcpu.com/blog/2018/07/06/afifo.html), [Moving values and strobes cross clock domains](https://zipcpu.com/blog/2020/10/03/tfrvalue.html), [Formally Verifying an Asynchronous Reset](https://zipcpu.com/formal/2018/04/12/areset.html), [Formally Verifying Asynchronous Components](https://zipcpu.com/formal/2018/05/31/clkswitch.html)
- [YosysHQ/sby docs/examples/multiclk](https://github.com/YosysHQ/sby/tree/main/docs/examples/multiclk), [SBY issue #255](https://github.com/YosysHQ/sby/issues/255) (без `multiclock` все триггеры – от одного неявного такта)
- [Mumunu-team/mununu PR #773](https://github.com/Mumunu-team/mununu/pull/773)
