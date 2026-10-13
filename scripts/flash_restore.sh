#!/bin/bash
# Откат: восстановление ОРИГИНАЛЬНЫХ разделов из локальных дампов Сессии 1.
# usage: flash_restore.sh boot|trustos|both
# Никаких format/factory reset здесь НЕТ и не будет.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

SPD="${SPD_DUMP:-$ROOT/spd_dump/spd_dump.exe}"
FDL1="${FDL1:-$ROOT/fdl/fdl1-sign.bin}"
FDL2="${FDL2:-$ROOT/fdl/fdl2-sign.bin}"
LOG="$ROOT/spd_restore_$(date +%Y%m%d_%H%M%S).log"
MODE="${1:-}"

fail() { echo "ABORT: $1 — ничего не записываем"; exit 1; }

case "$MODE" in
    boot|trustos|both) ;;
    *) echo "usage: flash_restore.sh boot|trustos|both"; exit 1;;
esac

[ -f "$SPD" ]  || fail "нет spd_dump: $SPD"
[ -f "$FDL1" ] || fail "нет $FDL1"
[ -f "$FDL2" ] || fail "нет $FDL2"

WRITES=()
if [ "$MODE" = "boot" ] || [ "$MODE" = "both" ]; then
    [ -f boot_a_orig.img ] || fail "нет boot_a_orig.img (оригинальный дамп Сессии 1)"
    sz=$(stat -c %s boot_a_orig.img)
    [ "$sz" = "67108864" ] || fail "boot_a_orig.img: размер $sz != 67108864"
    WRITES+=("w boot_a boot_a_orig.img")
fi
if [ "$MODE" = "trustos" ] || [ "$MODE" = "both" ]; then
    [ -f trustos ] || fail "нет trustos (оригинальный дамп Сессии 1)"
    sz=$(stat -c %s trustos)
    [ "$sz" = "6291456" ] || fail "trustos: размер $sz != 6291456"
    WRITES+=("w trustos_a trustos")
fi

echo "Будут восстановлены: $MODE"
echo "Файлы-источники (сверьте sha с логом Сессии 1):"
for f in boot_a_orig.img trustos; do
    [ -f "$f" ] && sha256sum "$f"
done
echo "Сделайте ТАНЕЦ BROM: кабель вынуть → POWER 15-20с → пауза 5с → вставить кабель → пауза 5с → POWER+VOL↓ 8-10с"

ARGS=(--wait 300 baudrate 230400 timeout 10000 \
      fdl "$FDL1" 0x65000800 fdl "$FDL2" 0x9EFFFE00 exec \
      disable_transcode partition_list partition.xml)
for w in "${WRITES[@]}"; do
    # shellcheck disable=SC2206
    ARGS+=($w)
done
ARGS+=(reset)

for attempt in $(seq 1 3); do
    echo "=== ПОПЫТКА $attempt $(date +%H:%M:%S) ===" >> "$LOG"
    "$SPD" "${ARGS[@]}" >> "$LOG" 2>&1
    rc=$?
    echo "=== ОКОНЧАНИЕ попытки $attempt (code $rc) $(date +%H:%M:%S) ===" >> "$LOG"
    ok=1
    if [ "$MODE" = "boot" ] || [ "$MODE" = "both" ]; then
        grep -q "Write Part Done: boot_a" "$LOG" || ok=0
    fi
    if [ "$MODE" = "trustos" ] || [ "$MODE" = "both" ]; then
        grep -q "Write Part Done: trustos_a" "$LOG" || ok=0
    fi
    if [ "$ok" = "1" ]; then
        echo "=== ВОССТАНОВЛЕНИЕ ВЫПОЛНЕНО ($MODE) ===" | tee -a "$LOG"
        exit 0
    fi
    sleep 5
done

fail "восстановление не подтверждено — см. $LOG"
