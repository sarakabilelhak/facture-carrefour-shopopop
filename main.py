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
    infos = {
        "magasin": "CARREFOUR", 
        "adresse_magasin": "Non trouvée", 
        "num_facture": "NC", 
        "num_commande": "NC", 
        "date_livraison": "NC"
    }
    adresse_shopopop = "SHOPOPOP\n1 ter mail Pablo picasso\n44000 Nantes"

    # Liste de mots qui marquent l'arrêt immédiat de l'extraction de l'adresse
    STOP_WORDS = ["LIVRAISON", "UNE QUESTION", "POUR TOUTES DEMANDES", "RUBRIQUE AIDE", "MERCI POUR VOTRE", "DATE DE", "N° DE"]

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            texte_complet += (page.extract_text() or "") + "\n"
        
        # Nettoyage des lignes
        lines = [line.strip() for line in texte_complet.split('\n') if line.strip()]

        # 1. Extraction Magasin et Adresse par position (Lignes 2 à 6)
        if len(lines) > 1:
            # Le nom du magasin est généralement en ligne 2
            infos["magasin"] = lines[1]
            
            addr_parts = []
            # On scanne les lignes suivantes pour l'adresse
            for j in range(2, 7):
                if j < len(lines):
                    l_up = lines[j].upper()
                    # Si on croise un mot interdit, on stoppe l'adresse
                    if any(stop in l_up for stop in STOP_WORDS):
                        break
                    addr_parts.append(lines[j])
            
            infos["adresse_magasin"] = "\n".join(addr_parts)

        # 2. Extraction des numéros (Facture, Commande, Date)
        m_f = re.search(r"N° de facture\s*[:\s]*([A-Z0-9]+)", texte_complet)
        if m_f: infos['num_facture'] = m_f.group(1)
        
        m_c = re.search(r"N° de commande\s*[:\s]*(\d+)", texte_complet)
        if m_c: infos['num_commande'] = m_c.group(1)
        
        m_d = re.search(r"Date de livraison\s*[:\s]*([\d/]+)", texte_complet)
        if m_d: infos['date_livraison'] = m_d.group(1)

        # 3. Extraction des articles
        for i, ligne in enumerate(lines):
            match_ean = re.search(r"^(\d{13})", ligne)
            if match_ean:
                montants = re.findall(r"\d+[.,]\d+", ligne)
                if len(montants) >= 3:
                    total_ttc = float(montants[-1].replace(',', '.'))
                    # On ne garde que les articles réellement livrés (montant > 0)
                    if total_ttc > 0:
                        libelle = ligne[13:].split(montants[0])[0].strip()
                        if not libelle and i > 0: libelle = lines[i-1]
                        articles.append({
                            'ean': match_ean.group(1),
                            'libelle': libelle if libelle else "Produit",
                            'qte_livree': int(re.search(r"\s(\d+)\s", ligne).group(1)) if re.search(r"\s(\d+)\s", ligne) else 1,
                            'tva': montants[-5] if len(montants)>=5 else "5.5",
                            'prix_ht': montants[-4] if len(montants)>=4 else montants[-3],
                            'prix_ttc': montants[-2] if len(montants)>=3 else montants[-1],
                            'total_ttc': total_ttc
                        })
    
    return pd.DataFrame(articles).drop_duplicates(), infos, adresse_shopopop

def generer_pdf_depuis_selection(data_selection, infos_entree, adresse_dest, logo_path):
    output_filename = f"Facture_SHOPOPOP_{infos_entree['num_commande']}.pdf"
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, output_filename)
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    elements = []
    styles = getSampleStyleSheet()

    # Logo sécurisé
    try:
        path_eff = os.path.join(os.path.dirname(__file__), logo_path)
        if os.path.exists(path_eff):
            logo = Image(path_eff, width=5*cm, height=1.5*cm)
        else:
            logo = Paragraph(f"<b>{infos_entree['magasin']}</b>", styles["Title"])
    except:
        logo = Paragraph(f"<b>{infos_entree['magasin']}</b>", styles["Title"])

    # En-tête
    mag_info = f"<b>{infos_entree['magasin']}</b><br/>{infos_entree['adresse_magasin'].replace('\n', '<br/>')}"
    col_g = [logo, Spacer(1, 0.3*cm), Paragraph(mag_info, styles["Normal"])]
    col_d = [
        Paragraph(f"<b>FACTURATION :</b><br/>{adresse_dest.replace('\n', '<br/>')}", styles["Normal"]), 
        Spacer(1, 0.5*cm), 
        Paragraph(f"<b>N° Facture :</b> {infos_entree['num_facture']}<br/><b>Commande :</b> {infos_entree['num_commande']}<br/><b>Date :</b> {infos_entree['date_livraison']}", styles["Normal"])
    ]
    elements.append(Table([[col_g, col_d]], colWidths=[10*cm, 8.5*cm]))
    elements.append(Spacer(1, 0.8*cm))

    # Tableau
    data = [["EAN13", "Libellé", "Qté", "TVA", "P.U. TTC", "Total TTC"]]
    for art in data_selection:
        data.append([art['ean'], Paragraph(art['libelle'], styles["Normal"]), art['qte_rbt'], f"{art['tva']}%", f"{art['prix_ttc']}€", f"{art['total_ttc']:.2f}€"])
    
    t = Table(data, colWidths=[3.5*cm, 7.5*cm, 1.2*cm, 1.5*cm, 2.5*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('GRID',(0,0),(-1,-1),0.5,colors.black),
        ('FONTSIZE',(0,0),(-1,-1),8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE')
    ]))
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

            # Barre de recherche
            recherche = st.text_input("🔍 Rechercher un article (nom ou EAN)", "")
            mask = df_art['libelle'].str.contains(recherche, case=False) | df_art['ean'].str.contains(recherche)
            df_filtre = df_art[mask].copy()

            if 'sel_all' not in st.session_state: st.session_state.sel_all = False
            def cb(): st.session_state.sel_all = not st.session_state.sel_all
            st.button("✅ Tout Sélectionner / Désélectionner", on_click=cb)

            df_filtre.insert(0, "Selection", st.session_state.sel_all)

            edited_df = st.data_editor(
                df_filtre, 
                column_config={
                    "Selection": st.column_config.CheckboxColumn("Sel."),
                    "qte_livree": st.column_config.NumberColumn("Qté", min_value=1)
                }, 
                hide_index=True, 
                width="stretch"
            )

            if st.button("🚀 Générer la facture SHOPOPOP", type="primary"):
                selected = edited_df[edited_df["Selection"] == True]
                if selected.empty:
                    st.warning("Veuillez sélectionner au moins un article.")
                else:
                    sel_list = []
                    for _, row in selected.iterrows():
                        q = int(row['qte_livree'])
                        p_raw = str(row['prix_ttc']).replace('€','').replace(',','.')
                        p = float(p_raw)
                        sel_list.append({**row.to_dict(), 'qte_rbt': q, 'total_ttc': q * p})
                    
                    pdf = generer_pdf_depuis_selection(sel_list, infos, adresse, LOGO_PATH)
                    with open(pdf, "rb") as f:
                        st.download_button("📥 Télécharger le PDF", f, file_name=os.path.basename(pdf))
        
        if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    main()
