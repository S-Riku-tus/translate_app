from flask import Flask, render_template, request, redirect, url_for, send_file
import os
import PyPDF2
import pandas as pd
import time
from googletrans import Translator
from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import portrait, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle, Paragraph
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from pdfminer.layout import LTTextBox, LAParams, LTContainer
from pdfminer.pdfpage import PDFPage
from pdfminer.converter import PDFPageAggregator
import io
import sys
sys.path.append(r".\transvenv\Lib\site-packages")

app = Flask(__name__)

# PDFからテキストボックスの情報を抽出
def find_textboxes(layout):
    if isinstance(layout, LTTextBox):
        return [layout]
    elif isinstance(layout, LTContainer):
        boxes = []
        for child in layout:
            boxes.extend(find_textboxes(child))
        return boxes
    else:
        return []

# 翻訳機能
translator = Translator()

def translate_text(text):
    return translator.translate(text, src='en', dest='ja').text

# PDFからテキストを抽出しDataFrameに保存
def extract_text_from_pdf(pdf_file, margin_input="0.5", min_words=80):
    resourceManager = PDFResourceManager()
    laParams = LAParams(line_overlap=0.5,
                        word_margin=0.1,
                        char_margin=2,
                        line_margin=float(margin_input),
                        detect_vertical=True)
    device = PDFPageAggregator(resourceManager, laparams=laParams)
    interpreter = PDFPageInterpreter(resourceManager, device)

    df = pd.DataFrame()
    pdfPages = PDFPage.get_pages(pdf_file)

    for page_no, page in enumerate(pdfPages, start=1):
        interpreter.process_page(page)
        layout = device.get_result()
        boxes = find_textboxes(layout)
        for box in boxes:
            df_page = pd.DataFrame({
                "x_start": [box.x0],
                "x_end": [box.x1],
                "y_start": [box.y0],
                "y_end": [box.y1],
                "text": [box.get_text().strip()],
                "page": [page_no]
            })
            df = pd.concat([df, df_page])
    df = df.reset_index(drop=True)

    # 翻訳する文章のみフィルタリング
    math_list = [ii for ii, row in df.iterrows() if "=" in row['text'] and "." not in row['text']]
    df_index = [ii for ii, row in df.iterrows() if ii not in math_list and len(row['text']) > min_words and row['text'][0] != "["]
    return df, df_index

# 翻訳したPDFを保存
def save_translated_pdf(df, df_index, pdf_file):
    font_name = "HeiseiKakuGo-W5"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    buffer = io.BytesIO()  # メモリ上のバッファを作成
    cc = canvas.Canvas(buffer, pagesize=portrait(A4))
    past_page = -1

    pages = PdfReader(pdf_file, decompress=False).pages  # pdf_fileを使用

    for dd in df_index:
        time.sleep(0.5)
        nowpage = df.iloc[dd, 5]
        if nowpage != past_page:
            if past_page != -1:
                cc.showPage()
            pp = pagexobj(pages[nowpage-1])
            cc.doForm(makerl(cc, pp))

        left_low = [df.iloc[dd, 0], df.iloc[dd, 2]]
        colsize = [df.iloc[dd, 1] - df.iloc[dd, 0], df.iloc[dd, 3] - df.iloc[dd, 2]]
        TEXT = df.iloc[dd, 4]
        try:
            TEXT_JN = translate_text(TEXT)
        except TypeError:
            TEXT_JN = TEXT

        pstyle = ParagraphStyle(name='Normal', fontName=font_name, fontSize=9, leading=8)
        try:
            JN_para = Paragraph(TEXT_JN, pstyle)
        except ValueError:
            continue

        table = Table([[JN_para]], colWidths=colsize[0], rowHeights=colsize[1])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.1, colors.white),
            ('VALIGN', (0, 0), (0, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (0, -1), colors.white)
        ]))

        table.wrapOn(cc, left_low[0], left_low[1])
        try:
            table.drawOn(cc, left_low[0], left_low[1])
        except AttributeError:
            print("ERROR", nowpage)

        past_page = df.iloc[dd, 5]

    cc.save()
    buffer.seek(0)  # バッファのポインタを先頭に戻す
    return buffer

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'pdf' not in request.files:
        return redirect(url_for('index'))
    
    pdf = request.files['pdf']
    if pdf.filename == '':
        return redirect(url_for('index'))
    
    # PDFファイルをメモリ上で処理
    pdf_file = pdf.stream  # 直接メモリのストリームを取得
    
    # PDFからテキストボックスを抽出
    df, df_index = extract_text_from_pdf(pdf_file)
    
    # 翻訳とPDF生成
    translated_pdf_buffer = save_translated_pdf(df, df_index, pdf_file)

    # ダウンロードオプションの取得
    download_option = request.form.get('download-option', 'download')
    
    if download_option == 'download':
        response = send_file(translated_pdf_buffer, as_attachment=True, download_name='translated_' + pdf.filename)
    else:
        # PDFをブラウザで表示
        response = send_file(translated_pdf_buffer)

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
