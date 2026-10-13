#!/bin/bash
# Сессия 2: запись trustos (патч SITE0) + Magisk-patched boot + reset.
# Предусловия проверяются ДО входа в BROM: при любой проблеме — выход без действий.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

SPD="${SPD_DUMP:-$ROOT/spd_dump/spd_dump.exe}"
FDL1="${FDL1:-$ROOT/fdl/fdl1-sign.bin}"
FDL2="${FDL2:-$ROOT/fdl/fdl2-sign.bin}"
LOG="$ROOT/spd_patched_$(date +%Y%m%d_%H%M%S).log"
TOS_IMG="tos-noavb-bsp-bypassed-site0"
MAX_TOS=$((6 * 1024 * 1024))
MAX_BOOT=$((64 * 1024 * 1024))

fail() { echo "ABORT: $1 — ничего не записываем"; exit 1; }

[ -f "$SPD" ]   || fail "нет spd_dump: $SPD"
[ -f "$FDL1" ]  || fail "нет $FDL1"
[ -f "$FDL2" ]  || fail "нет $FDL2"
[ -f "$TOS_IMG" ] || fail "нет $TOS_IMG — сначала: python tools/dis_avb_port.py patch sml trustos 0"
[ -f "patched_boot.img" ] || fail "нет patched_boot.img — см. README, Шаг 4 (Magisk)"

msz=$(stat -c %s "$TOS_IMG")
[ "$msz" -le "$MAX_TOS" ] || fail "merged слишком большой: $msz"

if [ -f merged-site0.sha256 ]; then
    expected=$(head -1 merged-site0.sha256 | tr -d '\r' | awk '{print $1}')
    actual=$(sha256sum "$TOS_IMG" | awk '{print $1}')
    [ "$expected" = "$actual" ] || fail "sha256 $TOS_IMG не совпал (ожидался $expected, получено $actual)"
fi

bsz=$(stat -c %s patched_boot.img)
[ "$bsz" -le "$MAX_BOOT" ] || fail "patched_boot.img слишком большой: $bsz"
python -c "import sys; sys.exit(0 if open('patched_boot.img','rb').read(8)==b'ANDROID!' else 1)" \
    || fail "patched_boot.img не начинается с магии ANDROID!"

echo "Предусловия ОК. Запись: trustos_a ($msz B) + boot_a ($bsz B)"
echo "Сделайте ТАНЕЦ BROM: кабель вынуть → POWER 15-20с → пауза 5с → вставить кабель → пауза 5с → POWER+VOL↓ 8-10с"

for attempt in $(seq 1 3); do
    echo "=== ПОПЫТКА $attempt $(date +%H:%M:%S) ===" >> "$LOG"
    "$SPD" --wait 300 baudrate 230400 timeout 10000 \
        fdl "$FDL1" 0x65000800 fdl "$FDL2" 0x9EFFFE00 exec \
        disable_transcode partition_list partition.xml \
        w trustos_a "$TOS_IMG" \
        read_part trustos_a 0 6M trustos_after.bin \
        w boot_a patched_boot.img \
        reset >> "$LOG" 2>&1
    rc=$?
    echo "=== ОКОНЧАНИЕ попытки $attempt (code $rc) $(date +%H:%M:%S) ===" >> "$LOG"

    ta=$(stat -c %s trustos_after.bin 2>/dev/null || echo 0)
    if [ "$ta" = "6291456" ] && grep -q "Write Part Done: boot_a" "$LOG"; then
        echo "=== СЕССИЯ ЗАПИСИ ВЫПОЛНЕНА (лог: $LOG) ===" | tee -a "$LOG"
        sha256sum trustos_after.bin | tee -a "$LOG"
        echo "Ждём загрузку, затем: adb shell magisk -v"
        exit 0
    fi
    sleep 5
done

fail "запись не подтверждена — см. $LOG (для отката: scripts/flash_restore.sh)"
