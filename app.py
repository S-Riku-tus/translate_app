from flask import Flask, request, send_file, render_template
import pandas as pd
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import portrait, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from googletrans import Translator
import io
import time
import asyncio
import concurrent.futures

app = Flask(__name__)

# 非同期翻訳用の関数
async def async_translate(text, src_lang='en', dest_lang='ja'):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, translate_text, text, src_lang, dest_lang)
    return result

def translate_text(text, src_lang='en', dest_lang='ja'):
    translator = Translator()
    return translator.translate(text, src=src_lang, dest=dest_lang).text

# 自作関数の定義
def find_textboxes(layout):
    text_boxes = []
    for element in layout:
        if isinstance(element, (LTTextBox, LTTextLine)):
            text_boxes.append(element)
        elif isinstance(element, LTChar):
            continue
        if hasattr(element, '_objs'):
            text_boxes.extend(find_textboxes(element._objs))
    return text_boxes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    pdf_file = request.files['pdf']
    file_input = pdf_file.read()  
    file_out = "和訳_" + pdf_file.filename

    resource_manager = PDFResourceManager()
    laparams = LAParams(line_overlap=0.5, word_margin=0.1, char_margin=2, line_margin=0.5, detect_vertical=True)
    device = PDFPageAggregator(resource_manager, laparams=laparams)
    interpreter = PDFPageInterpreter(resource_manager, device)

    df = pd.DataFrame()
    with io.BytesIO(file_input) as fp:
        pdf_pages = PDFPage.get_pages(fp)
        for page_no, page in enumerate(pdf_pages, start=1):
            interpreter.process_page(page)
            layout = device.get_result()
            boxes = find_textboxes(layout)

            for box in boxes:
                df_page = pd.DataFrame({
                    "x_start": [box.x0],
                    "x_end": box.x1,
                    "y_start": box.y0,
                    "y_end": box.y1,
                    "text": [box.get_text().strip()],
                    "page": [page_no]
                })
                df = pd.concat([df, df_page])

    df = df.reset_index(drop=True)

    min_words = 80
    df_index = [ii for ii in range(len(df)) if len(df.iloc[ii, 4].replace('\n', '')) > min_words and df.iloc[ii, 4][0] != "["]

    font_name = "HeiseiKakuGo-W5"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    cc = canvas.Canvas(file_out, pagesize=portrait(A4))

    # 非同期でテキストを翻訳
    async def translate_and_draw():
        past_page = -1
        for dd in df_index:
            await asyncio.sleep(0.5)
            now_page = df.iloc[dd, 5]

            if now_page != past_page and past_page != -1:
                cc.showPage()

            TEXT = df.iloc[dd, 4]
            try:
                TEXT_JN = await async_translate(TEXT)
            except TypeError:
                TEXT_JN = TEXT

            pstyle = ParagraphStyle(name='Normal', fontName=font_name, fontSize=9, leading=8)
            JN_para = Paragraph(TEXT_JN, pstyle)
            left_low = [df.iloc[dd, 0], df.iloc[dd, 2]]
            colsize = [df.iloc[dd, 1] - df.iloc[dd, 0], df.iloc[dd, 3] - df.iloc[dd, 2]]

            table = Table([[JN_para]], colWidths=colsize[0], rowHeights=colsize[1])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.1, colors.white),
                ('VALIGN', (0, 0), (0, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (0, -1), colors.white)
            ]))

            table.wrapOn(cc, left_low[0], left_low[1])
            table.drawOn(cc, left_low[0], left_low[1])

            past_page = df.iloc[dd, 5]

    asyncio.run(translate_and_draw())
    cc.save()

    if request.form['download-option'] == 'download':
        return send_file(file_out, as_attachment=True)
    else:
        return send_file(file_out)

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
