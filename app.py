from flask import Flask, request, send_file, render_template
import pandas as pd
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from googletrans import Translator
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import portrait, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
import io
import time

app = Flask(__name__)

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
    return render_template('index.html')  # あなたのHTMLフォームが保存されているファイル名

@app.route('/upload', methods=['POST'])
def upload():
    # PDFファイルの取得
    pdf_file = request.files['pdf']

    # PDFファイルをメモリ内で処理
    file_input = pdf_file.read()  # PDFファイルの内容を取得
    file_out = "和訳_" + pdf_file.filename

    # 翻訳機の設定
    translator = Translator()

    # PDFの読み込みと解析
    resource_manager = PDFResourceManager()
    laparams = LAParams(line_overlap=0.5,
                        word_margin=0.1,
                        char_margin=2,
                        line_margin=0.5,
                        detect_vertical=True)

    device = PDFPageAggregator(resource_manager, laparams=laparams)
    interpreter = PDFPageInterpreter(resource_manager, device)

    # 文章情報の取得
    df = pd.DataFrame()
    with io.BytesIO(file_input) as fp:
        pdf_pages = PDFPage.get_pages(fp)
        for page_no, page in enumerate(pdf_pages, start=1):
            interpreter.process_page(page)
            layout = device.get_result()
            boxes = find_textboxes(layout)

            # 各テキストボックスをデータフレームに追加
            for box in boxes:
                df_page = pd.DataFrame({"x_start": [box.x0],
                                        "x_end": box.x1,
                                        "y_start": box.y0,
                                        "y_end": box.y1,
                                        "text": [box.get_text().strip()],
                                        "page": [page_no]})
                df = pd.concat([df, df_page])

    df = df.reset_index(drop=True)

    # 翻訳ルールの設定
    min_words = 80  # 翻訳するテキストの最小文字数（調整可能）
    df_index = []
    for ii in range(len(df)):
        df.iloc[ii, 4] = df.iloc[ii, 4].replace('\n', '')
        if len(df.iloc[ii, 4]) > min_words:
            if df.iloc[ii, 4][0] != "[":
                df_index.append(ii)

    # 出力の設定
    font_name = "HeiseiKakuGo-W5"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    cc = canvas.Canvas(file_out, pagesize=portrait(A4))
    past_page = -1

    # 翻訳する
    for dd in df_index:
        time.sleep(0.5)
        now_page = df.iloc[dd, 5]

        if now_page != past_page:
            if past_page != -1:
                cc.showPage()

        # 翻訳した日本語の設定
        TEXT = df.iloc[dd, 4]
        try:
            TEXT_JN = translator.translate(TEXT, src='en', dest="ja").text
        except TypeError:
            TEXT_JN = TEXT

        # 元の文章の位置に翻訳した文章を貼り付ける
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

    cc.save()

    # PDFをダウンロードまたは表示
    if request.form['download-option'] == 'download':
        return send_file(file_out, as_attachment=True)
    else:
        return send_file(file_out)  # ブラウザで表示

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
