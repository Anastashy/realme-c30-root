# Root Realme C30 (RMX3581) без разблокировки загрузчика

> **EN abstract:** A working root method for Realme C30 / RMX3581 (Unisoc SC9863A, Android 11, build RMX3581_11.A.75) that **does not unlock the bootloader** and **does not wipe data**: patch a single `mov w0, #0` at offset `0x5AFBC` inside the `trustos` partition (the *inner* verified-boot check function) to disable the boot-image verification, then flash a Magisk-patched `boot` image via `spd_dump` in BROM mode (serial/COM transport). No `sign.bat`, no signing, no factory reset. Verified on real hardware, 2026.

## Совместимость

| Параметр | Значение |
|---|---|
| Модель | Realme C30 (RMX3581 / RMX3581RU) |
| SoC | Unisoc SC9863A |
| Прошивка (проверено) | RMX3581_11.A.75, Android 11 |
| Слот | `_a` |
| Транспорт | BROM `1782:4D00` → драйвер **sprdvcom** (COM-порт, последовательный) |
| Инструмент | `spd_dump` (stable build, serial path) |

На других прошивках/моделях метод **скорее всего сработает**, но смещения в `trustos` могут отличаться — патчер сам находит кандидатов (см. `tools/dis_avb_port.py`).

## Принцип метода

Загрузчик Realme C30 проверяет boot-образ через функцию проверки внутри раздела `trustos` (доверенная ОС TEE). Если заставить эту функцию возвращать `0` («проверка пройдена»), неподписанный Magisk-патченный boot принимается.

**Главная находка метода (проверено empirically):** в `trustos` эвристика находит **две** точки патча:

- **site0 — offset `0x5AFBC`** — возврат **внутренней** функции (точка входа `0x5AF0C`). ⭐ **Работает.**
- **site2 — offset `0x5CB74`** — возврат **обёртки**, которая просто возвращает результат внутренней функции. ❌ **Не работает** — с этим патчем телефон входит в **bootloop** (петля заставки), потому что цепочка загрузки вызывает внутреннюю функцию напрямую, минуя обёртку.

Поэтому **всегда патчите site0**:

```bash
python tools/dis_avb_port.py patch sml trustos 0
```

(последний аргумент `0` = site0; апстрёмный C-код по умолчанию выбирает site2 — поэтому «готовые» dis_avb-утилиты на этой модели и петляют.)

После патча `trustos` + запись `Magisk-patched boot` → телефон грузится с активным Magisk (`magisk -v` → `30.7:MAGISK:R`).

### Что НЕ делается

- ❌ Не разблокируется загрузчик (`unlock.bat` не нужен)
- ❌ Не стираются данные (userdata не трогается **никогда**)
- ❌ Не используется подпись boot (`sign.bat` / `sign1.rar` с 4PDA не нужны)
- ❌ Не устанавливается custom recovery (TWRP-метод тут не работает)
- ❌ Никаких `format`/`factory reset` в скриптах нет и не будет

## Что вам понадобится (ПК)

1. **Windows** + **python3** (только стандартная библиотека, `pip install` не нужен)
2. **Драйвер sprdvcom** — пакет `SPD_Driver_R4.20.0201` (ищите на 4PDA / зеркалах, в репозиторий не входит). Установка:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install_driver.ps1 -DriverDir "C:\path\to\SPD_Driver_R4.20.0201"
   ```
   После установки BROM-устройство (`VID_1782&PID_4D00`) должно определяться как **sprdvcom (COMx)** в Диспетчере устройств.
3. **spd_dump** — соберите из [TomKing062/spreadtrum_flash](https://github.com/TomKing062/spreadtrum_flash) (решение Visual Studio, путь `serial`) или возьмите готовый stable-релиз. Положите бинарник как `spd_dump/spd_dump.exe` (этот репозиторий не распространяет бинарники).
4. **FDL-загрузчики** `fdl1-sign.bin`, `fdl2-sign.bin` — извлеките из **официального пакета вашей прошивки** (архив PAC/zip Realme) и положите в `fdl/`. Эти файлы из соображений авторских прав сюда не входят.
5. **Magisk** (apk, v24+) — [github.com/topjohnwu/Magisk](https://github.com/topjohnwu/Magisk)
6. USB-кабель, заряженный телефон (>30%).

## Подготовка (однократно)

```
realme-c30-root/
├── README.md
├── .gitignore
├── scripts/
│   ├── install_driver.ps1    # установка sprdvcom
│   ├── flash_dump.sh         # Сессия 1: ТОЛЬКО чтение — дампы всех разделов
│   ├── flash_patched.sh      # Сессия 2: запись патченного trustos + boot
│   └── flash_restore.sh      # Откат: восстановление ОРИГИНАЛОВ из дампов
├── tools/
│   └── dis_avb_port.py       # офлайн-патчер trustos (сайт 0)
└── docs/
    └── trustos-analysis.md   # дизассембл-анализ: почему site0, а не site2
```

Рабочая папка (рядом с `scripts/`) после подготовки будет выглядеть так:

```
<рабочая папка>/
├── spd_dump/spd_dump.exe
├── fdl/fdl1-sign.bin, fdl2-sign.bin
├── scripts/…
├── tools/…
├── sml, trustos, miscdata_orig.bin, vbmeta_a_orig.bin, boot_a_orig.img   ← из Сессии 1
├── tos-noavb, tos-noavb-bsp-bypassed-site0, merged-site0.sha256          ← из патчера
└── patched_boot.img                                                      ← из Magisk
```

**Второй телефон** — просто сделайте новую рабочую копию папки: дампы и `patched_boot.img` свои для каждого устройства/сборки.

---

## Пошаговая инструкция

### Шаг 1 — Танец BROM

Все сессии начинаются с входа в BROM (режим низкого уровня, телефон **выключен**):

1. **Вынуть кабель** из телефона
2. **POWER** держать **15–20 секунд** — телефон должен полностью отключиться (если был в bootloop — может сопротивляться, дольше держать)
3. Пауза **~5 сек** (телефон в покое)
4. **Вставить кабель** (в тот же порт, лучше напрямую в ПК, не в хаб)
5. Пауза **~5 сек** (начинается зарядка)
6. **POWER + VOL↓** крепко держать **8–10 секунд** — экран погаснет и останется чёрным. **Не отпускать** и не вынимать кабель. Как только на экране появилась **зарядка** — режим не поймали, повторить с шага 2.

Признаки успеха: консоль пишет `CHECK BAUD`/справляет скорость — BROM пойман. Скрипт сам повторит попытку до 3 раз (зарядка = пропущенная попытка, без последствий).

> ⚠️ **Зомби-BROM**: если после сорванной сессии на COM-порту пишется `usb_send failed (0 / 1)` — просто **выньте кабель**, подождите 3 сек и вставьте заново. Порт «завис»; танец не нужен.

### Шаг 2 — Сессия дампов (только чтение)

```bash
bash scripts/flash_dump.sh
```

(запускайте → выполните танец → ждите «ДАМПЫ ГОТОВЫ»). Скрипт **ничего не пишет** в телефон, только читает:

| Файл | Раздел | Размер | Зачем |
|---|---|---|---|
| `sml` | `sml_a` | 1 M | исходник для слияния (cert/payload) |
| `trustos` | `trustos_a` | 6 M | **оригинал для патча и отката** |
| `miscdata_orig.bin` | `miscdata` | 1 M | страховка |
| `vbmeta_a_orig.bin` | `vbmeta_a` | 1 M | страховка |
| `boot_a_orig.img` | `boot_a` | 64 M | **оригинал boot: для Magisk-патча и отката** |

На выходе — `sha256` каждого файла (запишите/сохраните лог — это ваши ключи к откату).

### Шаг 3 — Офлайн-патч trustos

```bash
python tools/dis_avb_port.py patch sml trustos 0
```

Ожидаемый вывод (для прошивки A.75):

```
detected mov at 0x5afbc (bl=5 cbz=1 start=0x5af10)
detected mov at 0x5cb74 (bl=5 cbz=11 start=0x5ca18)
patch mov at 0x5afbc (raw=2)
written: tos-noavb-site0 …
written: tos-noavb-bsp-bypassed-site0 size=0x2b8570 (2852208) …
RESULT: OK — можно писать в trustos_a
```

- `0x5afbc` — именно site0 (внутренняя функция) — это то, что нужно
- Если вместо `patch mov at 0x5afbc` патчер пишет другой адрес — **не продолжайте** (см. `docs/trustos-analysis.md`)
- `RESULT: ABORT` — паттерн не найден / образ уже патчен / размер не влезает — **ничего не записывается**

Проверка (необязательно): `sha256sum` файла `tos-noavb-bsp-bypassed-site0` должен совпасть с записанным в `merged-site0.sha256` (скрипт записи сверит это сам).

### Шаг 4 — Патч boot через Magisk

```bash
adb push boot_a_orig.img /sdcard/Download/
```

На телефоне: **Magisk → Установить → Выбрать образ** → `/sdcard/Download/boot_a_orig.img` → патч. Получится файл `/sdcard/Download/patched_boot.img` (именно это имя и ожидает скрипт):

```bash
adb pull /sdcard/Download/patched_boot.img .
```

### Шаг 5 — Сессия записи

> 🔴 Перед запуском — телефон должен быть **выключен по танцу BROM** (см. Шаг 1), и вы должны нажать Enter/запустить скрипт **первым**, и только потом делать танец.

```bash
bash scripts/flash_patched.sh
```

Предусловия (проверяются **до** входа в BROM, при любой проблеме — выход без действий):
- есть `tos-noavb-bsp-bypassed-site0` и `patched_boot.img`
- размер merged ≤ 6 M, sha совпадает с `merged-site0.sha256`
- `patched_boot.img` начинается с магии `ANDROID!`, размер ≤ 64 M

Порядок: запись `trustos_a` → **readback** (сверка sha) → запись `boot_a` → `reset`. Успех = `Write Part Done: boot_a` + `trustos_after.bin` читается обратно.

### Шаг 6 — Проверка

Телефон загрузится штатно. На ПК:

```bash
adb shell magisk -v      # → 30.7:MAGISK:R (или ваша версия)
```

На телефоне: приложение Magisk → «Установлено: …». Root-запросы (`su`) подтверждаются в Magisk. `adb shell su -c id` вернёт `Permission denied` — это **нормально** (shell не в белом списке).

---

## Откат

```bash
bash scripts/flash_restore.sh boot      # вернуть оригинал boot (быстрый тест)
bash scripts/flash_restore.sh trustos   # вернуть оригинал trustos
bash scripts/flash_restore.sh both      # полный возврат в сток
```

Откат читает **ваши же дампы** из Сессии 1, сверяет размеры и печатает sha перед записью.

**Bootloop после записи?** Порядок диагностики:
1. `flash_restore.sh boot` → грузится → проблема была в boot-образе
2. грузится `оригинал boot + патченный trustos` → патч trustos сам по себе безвреден
3. не грузится вообще → `flash_restore.sh both` (полный сток)

Известно: патч **site2** (вместо site0) даёт именно петлю заставки — верните сток и перепатчите site0.

## Troubleshooting

| Симптом | Причина | Действие |
|---|---|---|
| `usb_send failed (0 / 1)` на COM | зомби-BROM (сорванная сессия) | вынуть кабель → 3 сек → вставить; танец не нужен |
| `CHECK BAUD FAIL` / не подключается | не в BROM | повторить танец с шага 2; зарядка на экране = не тот режим |
| Устройство не появляется / «Unknown» | нет драйвера | `install_driver.ps1`, проверить Диспетчер: sprdvcom (COMx) |
| Порт пропадает сразу после `exec` | экономия USB-питания/хаб | другой порт/кабель напрямую в ПК; powered hub |
| `FDL2: incompatible partition` | штатное сообщение | безобидно, не мешает |
| `sha256 … не совпал` (до BROM) | битые/чужие файлы | перезапустить Шаг 3, ничего не записано |
| Мигает логотип + вибрация (петля) | неверная точка патча (site2) или битый boot | `flash_restore.sh boot`; если не поможет — `both`; перепатчить site0 |
| После OTA пропал root | OTA затёрла boot | телефон рабочий; повторить Шаги 4–5 (trustos остаётся) |

## Важные замечания

- **userdata не трогается никогда.** Все ваши приложения и данные на месте (проверено).
- **OTA**: системное обновление перезапишет `boot` — root пропадёт, телефон останется рабочим. Лечится повторной записью `patched_boot.img` (trustos-патч сохраняется).
- **sha256 дампов** в `docs/trustos-analysis.md` даны справочно для свежих дампов с прошивки A.75; на других устройствах/сборках будут свои (особенно `sml` — может содержать индивидуальные данные).
- Повторное использование на втором телефоне: **свои дампы** (Шаг 2 заново), **свой** `patched_boot.img` (Шаг 4 заново). `fdl/`, драйвер и `spd_dump` общие.
- Скрипты упорядочивают попытки автоматически, но **танец выполняете вы** (см. Шаг 1).

## Как это соотносится с методом 4PDA (`sign.bat`)

В теме [4PDA, Realme C30](https://4pda.to/forum/index.php?showtopic=1081475) для обхода проверки используется **подпись** патченного boot (`sign.bat`, архив `sign1.rar` под логином форума). Данный метод — **альтернатива без подписи и без разблокировки**: одна инструкция (`mov w0,#0`) внутри `trustos` отключает проверку целиком, после чего подпись не нужна. Оба метода дополняют друг друга; этот — полностью воспроизводим офлайн.

## Credits

- [TomKing062/spreadtrum_flash](https://github.com/TomKing062/spreadtrum_flash) — `spd_dump`
- [Magisk](https://github.com/topjohnwu/Magisk) — topjohnwu
- Сообщество 4PDA (тема 1081475) — методология, драйверы, альтернативный путь подписи
- Дизассембл-анализ и порт `dis_avb` — см. `docs/trustos-analysis.md`

> Только для работы с **собственными** устройствами. Не распространяйте прошивки, FDL и дампы разделов.
