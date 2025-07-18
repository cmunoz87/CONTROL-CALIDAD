
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
import io
import re

st.set_page_config(page_title="CC Cobas Pro PDF Generator", layout="centered")

st.image("logo_villarrica.png", width=250)

st.title("📄 Generador de PDF de Controles de Calidad Cobas Pro")
st.markdown("**LABORATORIO CLÍNICO Y UMT, HOSPITAL DE VILLARRICA**")
st.write("Sube tu archivo CSV y descarga el PDF generado.")

archivo_subido = st.file_uploader("Selecciona el archivo CSV", type=["csv"])

if archivo_subido:
    try:
        df = pd.read_csv(archivo_subido)

        # Usar fila 0 como referencia de etiquetas válidas
        valores_permitidos = ["Sample_ID", "Arrived_Date_Time", "Result", "Unit"]
        columnas_a_mantener = [col for col in df.columns if df.loc[0, col] in valores_permitidos]
        if not columnas_a_mantener:
            st.error("❌ No se encontraron columnas válidas.")
            st.stop()

        df_filtrado = df[columnas_a_mantener]
        nombres_originales = df_filtrado.columns.tolist()
        for i in range(2, len(nombres_originales) - 1, 2):
            nombre_derecha = nombres_originales[i + 1]
            valor_fila_0 = df_filtrado.iloc[0, i]
            if pd.notna(valor_fila_0):
                nombres_originales[i] = f"{nombre_derecha} {valor_fila_0}"

        df_filtrado.columns = nombres_originales
        df_modificado = df_filtrado.rename(columns={
            nombres_originales[0]: "Control",
            nombres_originales[1]: "Fecha"
        }).drop(index=0).reset_index(drop=True)

        filas_transformadas = []
        columnas = df_modificado.columns.tolist()
        for idx, fila in df_modificado.iterrows():
            control = fila['Control']
            fecha = fila['Fecha']
            for i in range(2, len(columnas)):
                col = columnas[i]
                if "Result" in col and pd.notna(fila[col]):
                    analito = col.replace(" Result", "").strip()
                    resultado = fila[col]
                    unidad = fila[columnas[i + 1]] if i + 1 < len(columnas) else None
                    reagent_priority = fila[columnas[i + 2]] if i + 2 < len(columnas) else None
                    uso = None
                    if pd.notna(reagent_priority):
                        if str(reagent_priority).strip() == "0":
                            uso = "EN USO"
                        elif str(reagent_priority).strip() == "1":
                            uso = "STB"
                    filas_transformadas.append({
                        "CONTROL": control,
                        "FECHA": fecha,
                        "ANALITO": analito,
                        "RESULTADO": resultado,
                        "UNIDAD": unidad,
                        "USO": uso
                    })

        df_resultado = pd.DataFrame(filas_transformadas)
        df_resultado['CONTROL'] = df_resultado['CONTROL'].astype(str)

        df_resultado['nombre control'] = None
        df_resultado['nivel'] = None
        df_resultado['lote'] = None

        mask_aec = df_resultado['CONTROL'].str.startswith("AEC-")
        df_resultado.loc[mask_aec, 'nombre control'] = 'AEC'
        df_resultado.loc[mask_aec, 'nivel'] = df_resultado.loc[mask_aec, 'CONTROL'].str.extract(r'^AEC-([A-Z])')[0]
        df_resultado.loc[mask_aec, 'lote'] = df_resultado.loc[mask_aec, 'CONTROL'].str.extract(r'^AEC-[A-Z]\s+(\d+)$')[0]

        mask_otros = ~mask_aec
        nombre_raw = df_resultado.loc[mask_otros, 'CONTROL'].str.extract(r'^(.+?)\s+\d')[0].str.strip()
        nombre_limpio = nombre_raw.str.replace(r'\d+$', '', regex=True).str.strip()
        df_resultado.loc[mask_otros, 'nombre control'] = nombre_limpio
        numeros = df_resultado.loc[mask_otros, 'CONTROL'].str.findall(r'(\d+)')
        df_resultado.loc[mask_otros, 'nivel'] = numeros.apply(lambda x: x[0] if len(x) > 0 else None)
        df_resultado.loc[mask_otros, 'lote'] = numeros.apply(lambda x: x[1] if len(x) > 1 else None)

        columnas_orden = ['nombre control', 'nivel', 'ANALITO', 'RESULTADO', 'UNIDAD', 'USO', 'lote', 'FECHA']
        df_resultado = df_resultado[columnas_orden].sort_values(by=['nombre control', 'ANALITO']).reset_index(drop=True)

        fecha_actual = datetime.now().strftime("%Y-%m-%d_%H-%M")
        buffer_pdf = io.BytesIO()
        with PdfPages(buffer_pdf) as pdf:
            fig_width, fig_height = 8.5, 11
            dpi = 300
            max_filas_por_hoja = 45
            espacio_entre_tablas = 0.05

            grupos = df_resultado.groupby('nombre control')
            fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
            ax.axis('off')
            y_cursor = 0.95
            filas_usadas = 0

            for nombre_control, grupo in grupos:
                grupo = grupo.reset_index(drop=True)
                n_filas = len(grupo)

                if filas_usadas + n_filas > max_filas_por_hoja:
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close()
                    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
                    ax.axis('off')
                    y_cursor = 0.95
                    filas_usadas = 0

                ax.text(0.5, y_cursor, f"CONTROL: {nombre_control}", fontsize=11, weight='bold', ha='center', transform=ax.transAxes)
                y_cursor -= 0.02
                altura_tabla = 0.018 * (n_filas + 1)

                tabla = ax.table(
                    cellText=grupo.values,
                    colLabels=grupo.columns,
                    cellLoc='center',
                    loc='upper center',
                    bbox=[0, y_cursor - altura_tabla, 1, altura_tabla]
                )

                tabla.auto_set_font_size(False)
                tabla.set_fontsize(8)
                tabla.scale(1.15, 1.15)

                col_indices = {col: idx for idx, col in enumerate(df_resultado.columns)}
                for (row, col), cell in tabla.get_celld().items():
                    cell.PAD = 0.15
                    if row == 0:
                        cell.set_text_props(weight='bold', fontsize=8, ha='center')
                    else:
                        if col in [col_indices['RESULTADO'], col_indices['nivel'], col_indices['lote']]:
                            cell.set_text_props(ha='right')
                        elif col == col_indices['FECHA']:
                            cell.set_text_props(ha='left')
                        else:
                            cell.set_text_props(ha='center')

                y_cursor -= altura_tabla + espacio_entre_tablas
                filas_usadas += n_filas

            pdf.savefig(fig, bbox_inches='tight')
            plt.close()

        buffer_pdf.seek(0)
        st.success("✅ PDF generado correctamente.")
        st.download_button(
            label="📥 Descargar PDF",
            data=buffer_pdf,
            file_name=f"CC_COBAS_PRO_{fecha_actual}.pdf",
            mime="application/pdf"
        )

    except Exception as e:
        st.error(f"⚠️ Error al procesar el archivo: {e}")
