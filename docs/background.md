# Что уже есть (обзор на 20.11.2026)

## Коммерческие средства
- **Jasper CDC (Cadence).** Состоит из двух частей:
  - структурной: домены, переходы, схемы, правила `no_scheme`, `glitch_check`, `convergence_check` и другие;
  - формальной: для найденных схем сам создаёт свойства и доказывает их (`check_cdc -waiver -prove`).

  В референсном проекте он создавал свойства двух видов: `CDC_p_datapath_meta_safe` (путь данных устойчив к метастабильности) и `CDC_p_one_hot` (сходящиеся сигналы меняются по одному). Числа сохранены в локальных заметках и не публикуются.
- **Questa CDC (Siemens), Meridian CDC (Real Intent)** – тот же класс средств.

## Открытые структурные анализаторы (формальной части нет)

| Проект | Основа | Замечания |
|---|---|---|
| [OpenCDC](https://github.com/Ayoubbelguellaoui/CDC) (зеркало [AUDIY/CDC](https://github.com/AUDIY/CDC)) | C++20, slang v8.0 | Apache-2.0. Правила CDC001-CDC013, SDC/YAML, исключения, отчёты JSON, SARIF, HTML. В README прямо сказано: «not a formal CDC tool». Проверен на референсном блоке. |
| [rtl-buddy-cdc](https://github.com/rtl-buddy/rtl-buddy-cdc) | Python, нетлист Yosys или pyslang | Нумерованные правила CDC и RDC, сами авторы называют его экспериментальным. |
| [crux](https://github.com/jyrj/crux) | Python, Yosys + slang | CDC и RDC. |
| [clockguard](https://github.com/sushantlokhande14/clockguard) | C++, Yosys | Для каждого нарушения строит тест и волны (Icarus). |
| [vyges-tools/cdc](https://github.com/vyges-tools/cdc) | нетлист после синтеза + Liberty | CDC и RDC на уровне вентилей. |
| [OpenCDC с FOSS Hack 2026](https://fossunited.org/hack/fosshack26/p/6r2q817j82) | Python, Yosys + PyVerilog | Проект с хакатона. |
| [icarium](https://github.com/adibis/icarium) | Python, нетлист Yosys + SDC | Apache-2.0, отчёт JSON, сверен с отказами OpenTitan. Кандидат во входной адаптер (найден 20.11.2026, `docs/literature/oss-examples.md`). |
| Локальный структурный анализатор | Python, нетлист Yosys + slang | Классы `sync`, `sync_logic`, `sync_glitch`, `fifo`, `qualified`, `unsync`, а также сходимость, реконвергенция и RDC. Использовался как исходная модель для обобщения. |

В Verilator был экспериментальный ключ `--cdc`, его удалили в 5.008 (2023), см. [историю изменений](https://verilator.org/guide/latest/changes.html). В Yosys и Verible проверок CDC нет.

## Открытые формальные части (по отдельности, без автоматической связки)

| Проект | Что есть | Чего нет |
|---|---|---|
| [ymt1001816-cyber/async-fifo-cdc](https://github.com/ymt1001816-cyber/async-fifo-cdc) | Модель метастабильности для SBY: в `rtl/sync2.v` под `ifdef FORMAL` решатель выбирает, захватить старое или новое значение каждого бита. Ошибку CDC, которую симуляция не видит, формальная проверка находит за 11 шагов. Есть задание на синхронизатор сброса. | Один FIFO, модель синхронизатора написана вручную. |
| [hevangel/cdc_primitives](https://github.com/hevangel/cdc_primitives) | 18 ячеек CDC со свойствами, доказанными в SBY (bmc, prove, cover; 54 из 54). Оракул `anyconst` для данных рукопожатия. | Проверяются сами ячейки, генерации свойств нет. |
| [adibis/cdc-rdc-tests](https://github.com/adibis/cdc-rdc-tests) | Набор эталонных примеров для анализаторов CDC/RDC. Три ограниченные проверки в SBY: потеря события в синхронизаторе с переключением, порядок Грея, переключение тактов без коротких импульсов. Нужен Yosys 0.70+. | Это тесты, а не инструмент. **Подходит для проверки нашей утилиты.** |
| [Pragmatic Formal Verification Methodology for CDC](https://arxiv.org/pdf/2406.06533) ([DVCon](https://dvcon-proceedings.org/wp-content/uploads/91837.pdf)) | Генератор SVA по шаблонам для схем синхронизации, проверок управления тактами и конфигурации; модель покрытия пар CDC. | Кода нет. Данные о синхронизаторах берутся из Jasper. **Главная статья для сравнения.** |
| [Efficient Verification of a RADAR SoC](https://arxiv.org/pdf/2404.15371) | Свойства по схемам синхронизации и проверка с внедрением метастабильности (MSI). | Только Jasper. |
| [assertforge](https://github.com/ZhangYangyi03/assertforge), [FormalSynapse](https://github.com/saintbate/FormalSynapse) | Утверждения предлагает языковая модель, проверяет SBY. | Не CDC. По их наблюдению, открытый Yosys не принимает `assert property`. |

Ниша: связки «отчёт структурного анализатора → свойства по каждой схеме → SBY → итог по переходам» в открытом виде нет.

## Дополнения 20.11.2026
- Стандарт Accellera CDC/RDC 1.0 утверждён 02.03.2026. Описывает границу блока (такты и сбросы портов, Грей, порядок сбросов), внутренних переходов не описывает. Применение – вход допущений и выход модели блока (`docs/literature/structural.md`, разд. 3).
- Подробные обзоры – `docs/literature/`, выводы сведены в `docs/architecture.md`.
