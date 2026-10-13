#!/bin/bash
# Сессия 1: ТОЛЬКО чтение — дампы sml/trustos/miscdata/vbmeta/boot + reset.
# Ничего не пишет в телефон. Путь к инструментам определяется по расположению скрипта.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

SPD="${SPD_DUMP:-$ROOT/spd_dump/spd_dump.exe}"
FDL1="${FDL1:-$ROOT/fdl/fdl1-sign.bin}"
FDL2="${FDL2:-$ROOT/fdl/fdl2-sign.bin}"
LOG="$ROOT/spd_dump_$(date +%Y%m%d_%H%M%S).log"

fail() { echo "ABORT: $1"; exit 1; }

[ -f "$SPD" ]   || fail "нет spd_dump: $SPD (см. README)"
[ -f "$FDL1" ]  || fail "нет $FDL1 (см. README: FDL из прошивки)"
[ -f "$FDL2" ]  || fail "нет $FDL2 (см. README: FDL из прошивки)"

echo "Сессия дампов (read-only). Лог: $LOG"
echo "Сделайте ТАНЕЦ BROM: кабель вынуть → POWER 15-20с → пауза 5с → вставить кабель → пауза 5с → POWER+VOL↓ 8-10с"

for attempt in $(seq 1 3); do
    echo "=== ПОПЫТКА $attempt $(date +%H:%M:%S) ===" >> "$LOG"
    "$SPD" --wait 300 baudrate 230400 timeout 10000 \
        fdl "$FDL1" 0x65000800 fdl "$FDL2" 0x9EFFFE00 exec \
        disable_transcode partition_list partition.xml \
        read_part sml_a 0 1M sml \
        read_part trustos_a 0 6M trustos \
        read_part miscdata 0 1M miscdata_orig.bin \
        read_part vbmeta_a 0 1M vbmeta_a_orig.bin \
        read_part boot_a 0 64M boot_a_orig.img \
        reset >> "$LOG" 2>&1
    rc=$?
    echo "=== ОКОНЧАНИЕ попытки $attempt (code $rc) $(date +%H:%M:%S) ===" >> "$LOG"

    s=$(stat -c %s sml 2>/dev/null || echo 0)
    t=$(stat -c %s trustos 2>/dev/null || echo 0)
    b=$(stat -c %s boot_a_orig.img 2>/dev/null || echo 0)
    if [ "$s" = "1048576" ] && [ "$t" = "6291456" ] && [ "$b" = "67108864" ]; then
        echo "=== ДАМПЫ ГОТОВЫ ===" | tee -a "$LOG"
        sha256sum sml trustos miscdata_orig.bin vbmeta_a_orig.bin boot_a_orig.img | tee -a "$LOG"
        exit 0
    fi
    sleep 5
done

fail "дампы не получены (sml=$s trustos=$t boot=$b) — см. $LOG"
