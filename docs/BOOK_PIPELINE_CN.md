# 书籍处理流水线

这个流水线用于把投资书籍、股东信、访谈和问答资料沉淀成可复用的投资原则库与公司研究 checklist。

## 目录约定

```text
library/raw/          原始文件：PDF、epub、txt、docx
library/ocr/          扫描版 PDF 的 OCR 输出
library/notes/        深度读书笔记
library/principles/   投资原则库
library/checklists/   公司分析 checklist
research/companies/   个股研究稿
```

## 扫描版 PDF 转文字

当前项目使用纯 Python 方案处理扫描版中文 PDF：

- PyMuPDF：把 PDF 页渲染成图片
- RapidOCR：识别中文图片文字
- JSON page cache：每页单独保存，支持断点续跑
- Markdown：合并成后续阅读和总结用的文本

安装依赖：

```bash
.venv/bin/pip install pymupdf pillow rapidocr-onnxruntime pypdf
```

先抽样检查：

```bash
.venv/bin/python tools/book_pipeline/ocr_book.py \
  "library/raw/投资最重要的事.pdf" \
  --title "投资最重要的事" \
  --pages 1-25
```

完整 OCR：

```bash
.venv/bin/python tools/book_pipeline/ocr_book.py \
  "library/raw/投资最重要的事.pdf" \
  --title "投资最重要的事"
```

输出位置：

```text
library/ocr/投资最重要的事/pages/page_0001.json
library/ocr/投资最重要的事/投资最重要的事.md
```

## 原则库字段

每条原则尽量包含：

```text
原则名称
核心含义
来源章节/页码
作者想反对的常见错误
适用场景
误用风险
公司研究问题
示例说明
```

## 从书到 checklist

处理顺序：

1. OCR 或抽取原文文本。
2. 按章节整理作者观点。
3. 把观点提炼为原则库。
4. 将原则转成公司分析问题。
5. 用真实公司试跑。
6. 把试跑中暴露出的好问题补回原则库。

注意：原则库不是摘抄库。它的目标是把作者的投资思想转化为可用于研究公司的判断工具。


## 系统 OCR 推荐链路

如果 VPS 已安装 ocrmypdf、tesseract、poppler-utils 和中文语言包，优先使用系统链路。它会生成可搜索 PDF，再用 pdftotext 抽出全文。

```bash
ocrmypdf -l chi_sim+eng --deskew --rotate-pages --skip-text --output-type pdf \
  "library/raw/投资最重要的事.pdf" \
  "library/ocr/投资最重要的事/投资最重要的事_ocr.pdf"

pdftotext -layout \
  "library/ocr/投资最重要的事/投资最重要的事_ocr.pdf" \
  "library/ocr/投资最重要的事/投资最重要的事_ocr.txt"
```

系统 OCR 的优点是标准、可搜索、便于复用；缺点是中文文本里可能出现多余空格和少量错字。对于需要深读的章节，可以再用 tools/book_pipeline/ocr_book.py 的 RapidOCR 输出做交叉校验。
