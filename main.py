import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import cm

# --- CONFIGURATION ---
LOGO_PATH = "logo carrefour.png"

def extraire_donnees_carrefour(pdf_path):
    articles = []
    infos = {'num_facture': 'NC', 'num_commande': 'NC', 'date_livraison': 'NC', 'magasin': 'CARREFOUR', 'adresse_magasin': 'Adresse non détectée'}
    adresse_shopopop = "SHOPOPOP\n1 ter mail Pablo picasso\n44000 Nantes"
    
    # Ta logique de colonnes
    regex_colonnes = r"(\d+)\s+(\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(?:(\d+[.,]\d+)\s+)?(\d+[.,]\d+)"
    STOP_WORDS = ["LIVRAISON", "UNE QUESTION", "POUR TOUTES DEMANDES", "RUBRIQUE AIDE", "MERCI POUR VOTRE", "DATE DE", "N° DE"]

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            t = page.extract_text() or ""
            texte_complet += t + "\n"
            lignes = [l.strip() for l in t.split('\n') if l.strip()]
            
            # --- Extraction Nom & Adresse (Lignes 2 à 6) ---
            if not articles: # On ne le fait qu'une fois au début
                for i, line in enumerate(lignes[:15]):
                    if any(x in line.upper() for x in ["CARREFOUR", "CITY", "MARKET"]):
                        infos["magasin"] = line
                        addr_parts = []
                        for j in range(i + 1, i + 5):
                            if j < len(lignes):
                                if any(stop in lignes[j].upper() for stop in STOP_WORDS): break
                                addr_parts.append(lignes[j])
                        infos["adresse_magasin"] = "\n".join(addr_parts)
                        break

            # --- Extraction Articles avec TA LOGIQUE ---
            for i, ligne in enumerate(lignes):
                match_ean = re.search(r"^(\d{13})", ligne)
                if match_ean:
                    m_n = re.search(regex_colonnes, ligne)
                    if m_n:
                        # Libellé entre l'EAN et le début des colonnes chiffres
                        libelle = ligne[13:m_n.start()].strip()
                        # Secours ligne précédente si vide
                        if not libelle and i > 0: libelle = lignes[i-1]
                        
                        articles.append({
                            'ean': match_ean.group(1),
                            'libelle': libelle if libelle else "Produit",
                            'qte_livree': int(m_n.group(2)),
                            'tva': m_n.group(3).replace(',', '.'),
                            'prix_ht': m_n.group(4).replace(',', '.'),
                            'prix_ttc': m_n.group(5).replace(',', '.'),
                            'total_ttc': m_n.group(7).replace(',', '.')
                        })

    # Métadonnées
    m_f = re.search(r"N° de facture\s*[:\s]*([A-Z0-9]+)", texte_complet)
    if m_f: infos['num_facture'] = m_f.group(1)
    m_c = re.search(r"N° de commande\s*[:\s]*(\d+)", texte_complet)
    if m_c: infos['num_commande'] = m_c.group(1)
    m_d = re.search(r"Date de livraison\s*[:\s]*([\d/]+)", texte_complet)
    if m_d: infos['date_livraison'] = m_d.group(1)
    
    return pd.DataFrame(articles).drop_duplicates(), infos, adresse_shopopop

def generer_pdf_depuis_selection(data_selection, infos_entree, adresse_dest, logo_path):
    output_filename = f"Facture_SHOPOPOP_{infos_entree['num_commande']}.pdf"
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, output_filename)
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    elements = []
    styles = getSampleStyleSheet()

    try:
        path_eff = os.path.join(os.path.dirname(__file__), logo_path)
        logo = Image(path_eff, width=5*cm, height=1.5*cm) if os.path.exists(path_eff) else Paragraph(f"<b>{infos_entree['magasin']}</b>", styles["Title"])
    except: logo = Paragraph(f"<b>{infos_entree['magasin']}</b>", styles["Title"])

    mag_info = f"<b>{infos_entree['magasin']}</b><br/>{infos_entree['adresse_magasin'].replace('\n', '<br/>')}"
    col_g = [logo, Spacer(1, 0.3*cm), Paragraph(mag_info, styles["Normal"])]
    col_d = [
        Paragraph(f"<b>ADRESSE DE FACTURATION :</b><br/>{adresse_dest.replace('\n', '<br/>')}", styles["Normal"]), 
        Spacer(1, 0.5*cm), 
        Paragraph(f"<b>N° Facture :</b> {infos_entree['num_facture']}<br/><b>Commande :</b> {infos_entree['num_commande']}<br/><b>Date :</b> {infos_entree['date_livraison']}", styles["Normal"])
    ]
    elements.append(Table([[col_g, col_d]], colWidths=[10*cm, 8.5*cm]))
    elements.append(Spacer(1, 0.8*cm))

    data = [["EAN13", "Libellé", "Qté", "TVA", "P.U. HT", "P.U. TTC", "Total TTC"]]
    for art in data_selection:
        data.append([art['ean'], Paragraph(art['libelle'], styles["Normal"]), art['qte_rbt'], f"{art['tva']}%", f"{art['prix_ht']}€", f"{art['prix_ttc']}€", f"{art['total_ttc']}€"])
    
    t = Table(data, colWidths=[3*cm, 6.5*cm, 1.2*cm, 1.3*cm, 2.2*cm, 2.3*cm, 2.5*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.grey), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke), ('GRID',(0,0),(-1,-1),0.5,colors.black), ('FONTSIZE',(0,0),(-1,-1),8), ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    elements.append(t)
    doc.build(elements)
    return output_path

def main():
    st.set_page_config(page_title="Carrefour x SHOPOPOP", layout="wide")
    st.title("📄 Réédition de Factures Carrefour x SHOPOPOP")

    uploaded_file = st.file_uploader("Importer le PDF Carrefour", type=["pdf"])

    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            path = tmp.name
        
        df_art, infos, adresse = extraire_donnees_carrefour(path)

        if not df_art.empty:
            st.markdown("### 📝 Informations détectées")
            c1, c2 = st.columns(2)
            with c1: st.info(f"**Magasin :** {infos['magasin']}\n\n**Adresse :**\n{infos['adresse_magasin']}")
            with c2: st.success(f"**Facture :** {infos['num_facture']}\n\n**Commande :** {infos['num_commande']}\n\n**Date :** {infos['date_livraison']}")
            
            st.divider()

            recherche = st.text_input("🔍 Rechercher un article (nom ou EAN)", "")
            mask = df_art['libelle'].str.contains(recherche, case=False) | df_art['ean'].str.contains(recherche)
            df_filtre = df_art[mask].copy()

            if 'sel_all' not in st.session_state: st.session_state.sel_all = False
            def cb(): st.session_state.sel_all = not st.session_state.sel_all
            st.button("✅ Tout Sélectionner / Désélectionner", on_click=cb)

            df_filtre.insert(0, "Selection", st.session_state.sel_all)

            edited_df = st.data_editor(df_filtre, column_config={"Selection": st.column_config.CheckboxColumn("Sel."), "qte_livree": st.column_config.NumberColumn("Qté", min_value=1)}, hide_index=True, width="stretch")

            if st.button("🚀 Générer la facture SHOPOPOP", type="primary"):
                selected = edited_df[edited_df["Selection"] == True]
                if selected.empty: st.warning("Sélectionnez au moins un article.")
                else:
                    sel_list = []
                    for _, row in selected.iterrows():
                        q = int(row['qte_livree'])
                        sel_list.append({**row.to_dict(), 'qte_rbt': q, 'total_ttc': f"{q * float(str(row['prix_ttc']).replace('€','')): .2f}"})
                    pdf = generer_pdf_depuis_selection(sel_list, infos, adresse, LOGO_PATH)
                    with open(pdf, "rb") as f:
                        st.download_button("📥 Télécharger", f, file_name=os.path.basename(pdf))
        
        if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    main()
