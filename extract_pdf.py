# -*- coding: utf-8 -*-
"""提取 LubanCat-RK3588 手册的目录和正文到 UTF-8 文件。"""
from pypdf import PdfReader

PDF = r"E:\rk3588\lubancat\0-[野火]《快速使用手册—基于LubanCat-RK3588系列板卡》\[野火]《快速使用手册—基于LubanCat-RK3588系列板卡》_20260729.pdf"

reader = PdfReader(PDF)
print("总页数:", len(reader.pages))

# 目录
lines = []


def walk(outline, depth=0):
    for item in outline:
        if isinstance(item, list):
            walk(item, depth + 1)
        else:
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = "?"
            lines.append("  " * depth + f"{item.title} ... p{page}")


try:
    walk(reader.outline)
except Exception as e:
    lines.append("目录提取失败: " + str(e))

with open("toc.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("目录条数:", len(lines))

# 正文
with open("fulltext.txt", "w", encoding="utf-8") as f:
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        f.write(f"\n\n===== 第 {i + 1} 页 =====\n")
        f.write(txt)
print("正文已导出")
