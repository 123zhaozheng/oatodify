# -*- coding: utf-8 -*-
"""生成规范仿真 DAT + 6 份假文档（投产联调用途，与 OA/数据开发契约一致）。

DAT 契约：\\x01 分隔、11 列、无表头、tokenkey 第 10 列、tokenkey=完整 NAS 路径；
列序：[0]跳过 [1]fileid [2]分类 [3]is_zw [4]附件JSON [5]文件名 [6]类型 [7]is_zip [8]大小 [9]asecode [10]tokenkey
文档形态：3 份 .txt（可直接解析成功）+ 2 份 .pdf + 2 份 .docx 形态（可读二进制；解析服务不在本地栈内）。
"""

import os
import struct
import zlib

NAS = "D:/oato-sim/sim-nas/2026"
DAT_DIR = "D:/oato-sim/sim-dat/20261013"
os.makedirs(NAS, exist_ok=True)
os.makedirs(DAT_DIR, exist_ok=True)
PREFIX = "/xxx/xxx/xxx/2026/"


def txt_file(name, body):
    open(f"{NAS}/{name}", "w", encoding="utf-8").write(body)
    return os.path.getsize(f"{NAS}/{name}")


def minimal_pdf(name, lines):
    def esc(s):
        return (s.encode("unicode_escape").decode("ascii")
                .replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))
    stream = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({esc(l)}) Tj 0 -24 Td " for l in lines) + "ET"
    subjects = [
        ("catalog", b"<< /Type /Catalog /Pages 2 0 R >>"),
        ("pages", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        ("page", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                  b"/Resources << /Font << /F1 5 0 R >> >> >>"),
        ("stream", (f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream").encode()),
        ("font", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    pdf, offsets = b"%PDF-1.4\n", []
    for i, (_, body) in enumerate(subjects, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(subjects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(subjects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    open(f"{NAS}/{name}", "wb").write(pdf)
    return os.path.getsize(f"{NAS}/{name}")


def minimal_docx(name, lines):
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;").replace("'", "&apos;"))
    paras = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{esc(l)}</w:t></w:r></w:p>' for l in lines
    )
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           "<w:body>" + paras +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>")
    z = _make_zip([
        ("[Content_Types].xml", ctypes.encode()),
        ("_rels/.rels", rels.encode()),
        ("word/document.xml", doc.encode("utf-8")),
    ])
    open(f"{NAS}/{name}", "wb").write(z)
    return os.path.getsize(f"{NAS}/{name}")


def _make_zip(entries):
    out, central, offset = bytearray(), [], 0
    for name, data in entries:
        name_b = name.encode("utf-8")
        comp, crc = zlib.compress(data), zlib.crc32(data)
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x800, 8, 0, 0,
                           crc, len(comp), len(data), len(name_b), 0)
        out += name_b + comp
        central.append((name_b, crc, len(comp), len(data), offset))
        offset += 30 + len(name_b) + len(comp)
    body = bytearray(out)
    for name_b, crc, csize, usize, off in central:
        body += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0x800, 8, 0, 0,
                            crc, csize, usize, len(name_b), 0, 0, 0, 0, 0, off) + name_b
    body += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), len(body) - offset, offset, 0)
    return bytes(body)


TXT_A = ("商用密码产品使用管理办法\n\n第一条 为规范商用密码产品采购、使用和管理，依据相关法律法规制定本办法。\n"
         "第二条 各岗位应使用经核准的商用密码产品。\n第三条 本办法自2026年1月1日起施行。")
TXT_B = ("反洗钱客户尽职调查管理办法（正文，含2个附件）\n\n第一章 总则\n"
         "第一条 客户身份识别、受益所有人识别与风险分级适用本办法。\n第二章 尽职调查\n"
         "第二条 开户及大额交易触发尽职调查；附件一为高风险客户清单，附件二为受益所有人识别表。")

# (fileid, 文件名, 分类, is_zw, 附件文件ID JSON)
DOC_SPECS = [
    ("DOC-SIM-001", "SIM-001-商用密码产品使用管理办法.txt", "PUBLIC_STANDARD", 1, "",
     lambda fn: txt_file(fn, TXT_A)),
    ("DOC-SIM-002", "SIM-002-2026年度零售条线业务公告.pdf", "RETAIL_ANNOUNCEMENT", 1, "",
     lambda fn: minimal_pdf(fn, ["Retail bulletin 2026: new product line",
                                  "Effective 2026-03-01 to 2026-12-31", "All branches must comply"])),
    ("DOC-SIM-003", "SIM-003-总行发文·数字人民币运营规范.docx", "HEADQUARTERS_ISSUE", 1, "",
     lambda fn: minimal_docx(fn, ["数字人民币运营规范（总行发文）", "第一章 总则：场景准入与风控要求。",
                                   "第二章 运营：商户接入、钱包限额、异常交易处置。", "本规范自2026年8月1日起施行。"])),
    ("DOC-SIM-004", "SIM-004-反洗钱客户尽职调查管理办法.txt", "PUBLIC_STANDARD", 1,
     '["DOC-SIM-005","DOC-SIM-006"]', lambda fn: txt_file(fn, TXT_B)),
    ("DOC-SIM-005", "SIM-005-附件一·高风险客户清单.pdf", "PUBLIC_STANDARD", 0, "",
     lambda fn: minimal_pdf(fn, ["Appendix A: high-risk customer list",
                                  "Fields: id, name, risk level, review cycle"])),
    ("DOC-SIM-006", "SIM-006-附件二·受益所有人识别表.doc", "PUBLIC_STANDARD", 0, "",
     lambda fn: minimal_docx(fn, ["附件二：受益所有人识别表", "客户名称 / 控股股东 / 实际控制人 / 持有比例 ≥25%"])),
]

built = {}
for fid, fname, cat, is_zw, fj, writer in DOC_SPECS:
    built[fid] = (fname, cat, is_zw, fj, writer(fname) if callable(writer) else writer(fname))


def dat_line(seq, fid):
    fname, cat, is_zw, fj, size = built[fid]
    ext = fname.rsplit(".", 1)[-1]
    return "\x01".join([
        str(seq), fid, cat, str(is_zw), fj, fname, ext, "0", str(size), "",
        f"{PREFIX}{fname}",
    ])


def write_dat(name, lines):
    content = "".join(l + "\n" for l in lines)
    open(f"{DAT_DIR}/{name}", "w", encoding="utf-8", newline="").write(content)
    print(f"--- {name} ({len(lines)} lines) ---")
    for l in lines:
        print(repr(l))


write_dat("oa_files_a.dat",
          [dat_line(1, "DOC-SIM-001"), dat_line(2, "DOC-SIM-002"), dat_line(3, "DOC-SIM-003")])
write_dat("oa_files_b.DAT",
          [dat_line(4, "DOC-SIM-004"), dat_line(5, "DOC-SIM-005"), dat_line(6, "DOC-SIM-006")])

print("--- NAS files ---")
for f in sorted(os.listdir(NAS)):
    print(f"{f}  {os.path.getsize(f'{NAS}/{f}')} bytes  tokenkey={PREFIX}{f}")
