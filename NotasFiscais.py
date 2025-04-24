import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont
from num2words import num2words
import datetime
import io
import base64
from pathlib import Path

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

# Função para quebrar texto em várias linhas conforme largura máxima
def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = current + (" " if current else "") + w
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def valor_por_extenso(valor: float) -> str:
    reais = int(valor)
    centavos = int(round((valor - reais) * 100))
    if reais and centavos:
        return f"{num2words(reais, lang='pt_BR')} reais e {num2words(centavos, lang='pt_BR')} centavos"
    if reais:
        return f"{num2words(reais, lang='pt_BR')} reais"
    return f"{num2words(centavos, lang='pt_BR')} centavos"


def gerar_recibo_image(
    valor: float,
    valor_ext: str,
    referente: str,
    desc: str,
    data_local: str,
    assinatura_img: Image.Image
) -> Image.Image:
    largura, altura = 800, 350
    img = Image.new("RGB", (largura, altura), "white")
    draw = ImageDraw.Draw(img)

    # Carrega o logo
    script_dir = Path(__file__).parent
    logo_path = script_dir / "logo.png"
    logo_w = logo_h = 0
    if logo_path.exists():
        try:
            logo = Image.open(logo_path)
            logo_w, logo_h = 80, 80
            try:
                logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            except AttributeError:
                logo = logo.resize((logo_w, logo_h), Image.ANTIALIAS)
            mask_logo = logo.split()[3] if logo.mode in ("RGBA", "LA") else None
            img.paste(logo, (20, 20), mask_logo)
        except Exception:
            logo_w = logo_h = 0

    # Carrega fontes
    fonte_path = script_dir / "DejaVuSans.ttf"
    try:
        fonte_titulo = ImageFont.truetype(str(fonte_path), 32)
        fonte_texto = ImageFont.truetype(str(fonte_path), 20)
    except IOError:
        fonte_titulo = fonte_texto = ImageFont.load_default()

    # Cabeçalho
    x_recibo = 20 + logo_w + 10
    draw.text((x_recibo, 45), "Recibo", fill="black", font=fonte_titulo)
    draw.text((largura - 250, 45), f"R$ {valor:.2f}", fill="black", font=fonte_titulo)

    # Corpo inicia abaixo do logo
    y = 20 + logo_h + 20
    linhas = [
        f"Recebi de SABOR DE LUNA PADARIA E PASTIFÍCIO a quantia de {valor_ext}; referente a {referente}; {desc}"
    ]
    # Quebra as linhas conforme largura
    max_text_width = largura - 40  # margem de 20px dos lados
    for texto in linhas:
        wrapped = wrap_text(texto, fonte_texto, max_text_width, draw)
        for line in wrapped:
            draw.text((20, y), line, fill="black", font=fonte_texto)
            y += 25  # espaçamento vertical entre linhas

    # Rodapé: assinatura e data
    assinatura_label_y = altura - 130
    draw.text((20, assinatura_label_y), "Assinatura:", fill="black", font=fonte_texto)

    # Inserir assinatura
    assinatura_w, assinatura_h = 300, 100
    assin = assinatura_img.resize((assinatura_w, assinatura_h))
    assinatura_y = assinatura_label_y + 5
    mask_assin = assin.split()[3] if assin.mode in ("RGBA", "LA") else None
    img.paste(assin, (20, assinatura_y), mask_assin)

    # Data alinhada à direita
    bbox = draw.textbbox((0, 0), data_local, font=fonte_texto)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    data_x = largura - text_w - 20
    data_y = altura - text_h - 20
    draw.text((data_x, data_y), data_local, fill="black", font=fonte_texto)

    return img


def main():
    st.set_page_config(page_title="Gerador de Recibos", layout="centered")
    st.title("Gerador de Recibos")

    valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
    referente = st.selectbox("Referente a:", [
        "Matriz, Carlos Trein, Gelato, Xangrilá",
        "Empório, Restaurante, Apoio, Fábrica",
        ""
    ])
    descricao = st.text_area("Descrição adicional")

    st.subheader("Assine abaixo:")
    canvas = st_canvas(
        stroke_width=2,
        stroke_color="black",
        background_color="white",
        height=150,
        width=800,
        drawing_mode="freedraw",
        key="canvas"
    )

    if st.button("Gerar Recibo"):
        if canvas.image_data is None:
            st.error("Desenhe sua assinatura antes de gerar o recibo.")
            return

        valor_ext = valor_por_extenso(valor)
        hoje = datetime.datetime.today()
        mes_pt = MESES_PT[hoje.month - 1]
        data_local = f"Porto Alegre, {hoje.day} de {mes_pt} de {hoje.year}"

        assin_pil = Image.fromarray(canvas.image_data.astype("uint8")).convert("RGBA")

        recibo_img = gerar_recibo_image(
            valor, valor_ext, referente, descricao, data_local, assin_pil
        )

        st.image(recibo_img)

        buf = io.BytesIO()
        recibo_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        href = f'<a href="data:image/png;base64,{b64}" download="recibo.png">📥 Baixar Recibo</a>'
        st.markdown(href, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
