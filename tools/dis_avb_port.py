#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Офлайн-порт dis_avb() + bsp_cve_2img() из src_main_common.c (TomKing062/spreadtrum_flash).
# Байт-в-байт повторяет логику main_249, включая беззнаковую арифметику size_t.
# Использование:
#   python dis_avb_port.py patch <sml_file> <trustos_file>
#   python dis_avb_port.py selftest
import struct, sys, hashlib, os, tempfile

HDR = 0x200          # sizeof(sys_img_header)
MIMG_OFF = 0x30      # sys_img_header.mImgSize
PO_OFF = 24          # sprdsignedimageheader.payload_offset
CO_OFF = 40          # sprdsignedimageheader.cert_offset


def load(fn):
    with open(fn, "rb") as f:
        return bytearray(f.read())


def u32(b, off):
    return struct.unpack_from("<I", b, off)[0]


def u16(b, off):
    return struct.unpack_from("<H", b, off)[0]


def u64(b, off):
    return struct.unpack_from("<Q", b, off)[0]


def sha256(fn):
    h = hashlib.sha256()
    with open(fn, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dis_avb(filename, outfile="tos-noavb", pick=None):
    """Порт dis_avb() из src_main_common.c:2615. Возвращает mov_count (0 = fail/skip).
    pick — явный индекс кандидата (0/1) вместо эвристики C."""
    mem = load(filename)
    size = len(mem)
    if size < HDR + 0x100:
        print("dis_avb: file too small"); return 0
    mimg = u32(mem, MIMG_OFF)
    hdr_at = mimg + HDR
    if hdr_at + CO_OFF + 8 > size:
        print("dis_avb: signed header out of range (mImgSize=0x%x)" % mimg); return 0
    payload_offset = u64(mem, hdr_at + PO_OFF)
    if payload_offset != HDR:
        print("image already patched (payload_offset=0x%x)" % payload_offset)
        return 0
    magic = u32(mem, 0)
    print("dis_avb: file=%s size=0x%x magic=0x%08x mImgSize=0x%x" %
          (filename, size, magic, mimg))

    pmov = [0, 0, 0]
    mov_count = 0
    raw_count = 0
    last_start_pos = 0
    start_pos = 0
    i = HDR
    while i < size:
        current = u32(mem, i)
        if current == 0xD65F03C0 or (current & 0xFF00FFFF) == 0xA8007BFD:
            last_start_pos = 0
            start_pos = 0
        elif (current & 0xFF00FFFF) == 0xA9007BFD:
            if start_pos:
                last_start_pos = start_pos
            start_pos = i
        elif start_pos:
            if i + 32 <= size:
                ldp_count = 0
                for m in range(0, 20, 4):
                    if mem[i + m + 3] == 0xA9:
                        ldp_count += 1
                    else:
                        break
                if ldp_count == 5:
                    ret_flag = 0
                    for m in range(24, 32, 4):
                        if u32(mem, i + m) == 0xD65F03C0:
                            ret_flag += 1
                    if ret_flag:
                        if u16(mem, i - 4) == 0x3E0 and mem[i - 7] == 0x3:
                            if start_pos > i and last_start_pos:
                                start_pos = last_start_pos
                            count1 = 0
                            count2 = 0
                            m2 = start_pos
                            while m2 < i:
                                w = u32(mem, m2)
                                if w >> 16 == 0x9400:
                                    count1 += 1
                                elif w >> 16 == 0xb400:
                                    count2 += 1
                                m2 += 4
                            if count1 and count2 and count1 + count2 > 2:
                                print("detected mov at 0x%x (bl=%d cbz=%d start=0x%x)" %
                                      (i - 4, count1, count2, start_pos))
                                if mov_count < 3:
                                    pmov[mov_count] = i - 4
                                    mov_count += 1
                                else:
                                    pmov[0] = pmov[1]
                                    pmov[1] = pmov[2]
                                    pmov[2] = i - 4
                                raw_count += 1
        i += 4

    if mov_count < 2:
        print("dis_avb: skip saving!!! (mov_count=%d)" % mov_count)
        return 0
    if pick is not None:
        if pick < 0 or pick > 2 or pick >= raw_count:
            print("dis_avb: pick %d вне диапазона (detected %d)" % (pick, raw_count))
            return 0
        sel = pick
    else:
        # C: size_t арифметика — переполнение даёт "> 0" всегда, кроме точного нуля
        if mov_count > 2:
            diff = (pmov[2] - 2 * pmov[1] + pmov[0]) & 0xFFFFFFFFFFFFFFFF
            mov_count = 1 if diff > 0 else 2
        else:
            mov_count -= 1
        sel = mov_count
    print("patch mov at 0x%x (raw=%d)" % (pmov[sel], raw_count))
    struct.pack_into("<I", mem, pmov[sel], 0x52800000)
    with open(outfile, "wb") as f:
        f.write(mem)
    print("written: %s (sha256=%s)" % (outfile, sha256(outfile)))
    return mov_count


def bsp_cve_2img(signed_img_name, unsigned_img_name, merged_img_name):
    """Порт bsp_cve_2img() из src_main_common.c:2718 (MULTI_HEADER=0)."""
    signed_img = load(signed_img_name)
    modified_img = load(unsigned_img_name)
    signed_size = len(signed_img)
    modified_size = len(modified_img)
    if signed_size <= HDR:
        print("bsp_cve_2img: signed img too small"); return 0
    modified_size = ((modified_size + 15) // 16) * 16
    if len(modified_img) < MIMG_OFF + 4:
        print("bsp_cve_2img: modified img too small"); return 0
    orig_modified_img_size = u32(modified_img, MIMG_OFF)
    if u32(modified_img, 0) == 0x42544844 and orig_modified_img_size:
        modified_size = orig_modified_img_size
        modified_img = modified_img[HDR:]
    if len(modified_img) < modified_size:
        print("bsp_cve_2img: modified payload truncated"); return 0

    signed_body_size = signed_size - HDR
    mimg_s = u32(signed_img, MIMG_OFF)
    hdr_at = mimg_s + HDR
    if hdr_at + CO_OFF + 8 > signed_size:
        print("bsp_cve_2img: signed header out of range (mImgSize=0x%x)" % mimg_s); return 0
    payload_offset = u64(signed_img, hdr_at + PO_OFF)
    cert_offset = u64(signed_img, hdr_at + CO_OFF)
    print("bsp_cve_2img: sml mImgSize=0x%x payload_offset=0x%x cert_offset=0x%x" %
          (mimg_s, payload_offset, cert_offset))

    # мутации копии bуфера signed_img (как в C: указатели указывают в буфер)
    struct.pack_into("<I", signed_img, MIMG_OFF, mimg_s + modified_size)
    struct.pack_into("<Q", signed_img, hdr_at + PO_OFF, payload_offset + modified_size)
    struct.pack_into("<Q", signed_img, hdr_at + CO_OFF, cert_offset + modified_size)

    out = bytes(signed_img[:HDR]) + bytes(modified_img[:modified_size]) + \
          bytes(signed_img[HDR:HDR + signed_body_size])
    with open(merged_img_name, "wb") as f:
        f.write(out)
    print("written: %s size=0x%x (%d) new mImgSize=0x%x" %
          (merged_img_name, len(out), len(out), mimg_s + modified_size))
    return len(out)


def patch(sml_fn, tos_fn, pick=None):
    suffix = "" if pick is None else "-site%d" % pick
    tos_out = "tos-noavb" + suffix
    merged_out = "tos-noavb-bsp-bypassed" + suffix
    sha_file = "merged%s.sha256" % suffix
    if not dis_avb(tos_fn, tos_out, pick):
        print("RESULT: ABORT — паттерн не найден или образ уже патчен (ничего не пишем)")
        return 2
    # проверка патча
    mem = load(tos_out)
    if len(mem) < HDR:
        print("RESULT: ABORT — %s повреждён" % tos_out)
        return 2
    merged_size = bsp_cve_2img(sml_fn, tos_out, merged_out)
    if not merged_size:
        print("RESULT: ABORT — слияние не удалось")
        return 2
    max_part = 6 * 1024 * 1024
    if merged_size > max_part:
        print("RESULT: ABORT — merged (%d) больше trustos_a (%d)" % (merged_size, max_part))
        return 3
    with open(sha_file, "w", newline="\n") as f:
        f.write("%s  %s\n" % (sha256(merged_out), merged_out))
    print("sha256 %-28s = %s" % (tos_out, sha256(tos_out)))
    print("sha256 %-28s = %s" % (merged_out, sha256(merged_out)))
    print("RESULT: OK — можно писать в trustos_a (см. flash_d3.sh)")
    return 0


def selftest():
    t = bytearray(0x4000)
    struct.pack_into("<I", t, 0, 0x42544844)      # DHTB magic
    struct.pack_into("<I", t, MIMG_OFF, 0x2000)   # mImgSize
    base = 0x2000 + HDR
    struct.pack_into("<Q", t, base + PO_OFF, HDR)      # payload_offset == 0x200
    struct.pack_into("<Q", t, base + CO_OFF, 0x2500)   # cert_offset
    # паттерн: start STP @0x600
    struct.pack_into("<I", t, 0x600, 0xA9007BFD)
    struct.pack_into("<I", t, 0x610, 0x94000000)  # BL
    struct.pack_into("<I", t, 0x614, 0xB4000000)  # CBZ
    struct.pack_into("<I", t, 0x618, 0x94000000)
    struct.pack_into("<I", t, 0x61C, 0xB4000000)
    struct.pack_into("<I", t, 0x638, 0x00000300)  # mem[i-7]==0x3 (bits 8..15)
    struct.pack_into("<I", t, 0x63C, 0x528003E0)  # MOV W0,#0x1F0 — цель (u16==0x3E0)
    for k in range(5):
        struct.pack_into("<I", t, 0x640 + 4 * k, 0xA9417BFE)   # 5x слов с high byte 0xA9 (не STP-класс)
    struct.pack_into("<I", t, 0x658, 0xD65F03C0)  # RET
    # второй экземпляр паттерна (mov_count обязан быть >=2)
    struct.pack_into("<I", t, 0x700, 0xA9007BFD)
    struct.pack_into("<I", t, 0x710, 0x94000000)
    struct.pack_into("<I", t, 0x714, 0xB4000000)
    struct.pack_into("<I", t, 0x718, 0x94000000)
    struct.pack_into("<I", t, 0x71C, 0xB4000000)
    struct.pack_into("<I", t, 0x738, 0x00000300)
    struct.pack_into("<I", t, 0x73C, 0x528003E0)  # MOV W0,#0x1F0 (та же маска low16==0x3E0)
    for k in range(5):
        struct.pack_into("<I", t, 0x740 + 4 * k, 0xA9417BFE)
    struct.pack_into("<I", t, 0x758, 0xD65F03C0)

    s = bytearray(0x4000)
    struct.pack_into("<I", s, MIMG_OFF, 0x3000)
    sbase = 0x3000 + HDR
    struct.pack_into("<Q", s, sbase + PO_OFF, HDR)
    struct.pack_into("<Q", s, sbase + CO_OFF, 0x3500)

    d = tempfile.mkdtemp()
    tosf = os.path.join(d, "trustos")
    smlf = os.path.join(d, "sml")
    with open(tosf, "wb") as f:
        f.write(t)
    with open(smlf, "wb") as f:
        f.write(s)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        rc = dis_avb(tosf, "tos-noavb")
        assert rc == 1, "mov_count != 1 (%d)" % rc
        out = load("tos-noavb")
        assert u32(out, 0x73C) == 0x52800000, "патч не применился на pmov[1]"
        assert u32(out, 0x63C) == 0x528003E0, "pmov[0] не должен меняться"
        n = bsp_cve_2img(smlf, "tos-noavb", "merged")
        assert n == 0x4000 + 0x2000, "merged size %x" % n
        m = load("merged")
        assert u32(m, MIMG_OFF) == 0x5000, "merged mImgSize"
        shdr = u32(m, MIMG_OFF) + HDR     # подзаголовок sml в merged
        new_po = u64(m, shdr + PO_OFF)
        assert new_po == HDR + 0x2000, "payload_offset %x" % new_po
        new_co = u64(m, shdr + CO_OFF)
        assert new_co == 0x3500 + 0x2000, "cert_offset %x" % new_co
        print("SELFTEST: ALL PASS")
        return 0
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    if len(sys.argv) >= 4 and sys.argv[1] == "patch":
        pick = int(sys.argv[4]) if len(sys.argv) >= 5 else None
        sys.exit(patch(sys.argv[2], sys.argv[3], pick))
    print("usage: dis_avb_port.py patch <sml> <trustos> [site_idx] | selftest")
    sys.exit(64)
