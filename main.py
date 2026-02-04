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

# --- CONFIGURATION LOGO ---
# Chemin exact sur ton bureau
LOGO_PATH = r"C:\Users\KABILELS\Desktop\Remboursement SHOPOPOP\logo carrefour.png"

# --- 1. FONCTION D'EXTRACTION DES DONNÉES ---
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
    
    regex_colonnes = r"(\d+)\s+(\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(?:(\d+[.,]\d+)\s+)?(\d+[.,]\d+)"

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            texte_complet += (page.extract_text() or "") + "\n"

        lines = [line.strip() for line in texte_complet.split('\n')]

        # --- LOGIQUE D'EXTRACTION EN-TÊTE ---
        idx_mag = -1
        for i, line in enumerate(lines[:12]):
            l_up = line.upper()
            if any(x in l_up for x in ["HYPERMARCHES", "SUPERMARCHES", "MARKET"]):
                if "SERVICE" not in l_up and "CONTACT" not in l_up:
                    infos["magasin"] = line
                    idx_mag = i
                    break
        
        if idx_mag != -1:
            addr_parts = []
            for j in range(idx_mag + 1, idx_mag + 5):
                l = lines[j]
                if any(x in l.lower() for x in ["question", "contact", "commande", "identifiant"]) or l == "":
                    break
                addr_parts.append(l)
            infos["adresse_magasin"] = "\n".join(addr_parts)

        # Extraction des numéros et dates
        m_f = re.search(r"N° de facture\s*:\s*([A-Z0-9]+)", texte_complet)
        if m_f: infos['num_facture'] = m_f.group(1)
        m_c = re.search(r"N° de commande\s*:\s*(\d+)", texte_complet)
        if m_c: infos['num_commande'] = m_c.group(1)
        m_d = re.search(r"Date de livraison\s*:\s*([\d/]+)", texte_complet)
        if m_d: infos['date_livraison'] = m_d.group(1)

        # --- EXTRACTION ARTICLES AVEC FILTRE 0€ ---
        for i, ligne in enumerate(lines):
            match_ean = re.search(r"^(\d{13})", ligne.strip())
            if match_ean:
                m_n = re.search(regex_colonnes, ligne)
                if m_n:
                    total_ttc_val = float(m_n.group(7).replace(',', '.'))
                    # On ignore les produits dont le montant total est 0
                    if total_ttc_val > 0:
                        libelle = ligne[13:m_n.start()].strip()
                        if not libelle and i > 0: libelle = lines[i-1].strip()
                        articles.append({
                            'ean': match_ean.group(1),
                            'libelle': libelle if libelle else "Produit",
                            'qte_livree': int(m_n.group(2)),
                            'tva': m_n.group(3).replace(',', '.'),
                            'prix_ht': m_n.group(4).replace(',', '.'),
                            'prix_ttc': m_n.group(5).replace(',', '.'),
                            'total_ttc': total_ttc_val
                        })
    
    return pd.DataFrame(articles).drop_duplicates(), infos, adresse_shopopop

# --- 2. FONCTION GÉNÉRATION PDF ---
def generer_pdf_depuis_selection(data_selection, infos_entree, adresse_dest, logo_path):
    output_filename = f"Facture_SHOPOPOP_{infos_entree.get('num_commande', '000')}.pdf"
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, output_filename)

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    elements = []
    styles = getSampleStyleSheet()

    # Gestion du Logo en haut à gauche
    try:
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=5*cm, height=1.5*cm)
            logo.hAlign = 'LEFT'
        else:
            logo = Paragraph(f"<font color='red'>LOGO NON TROUVÉ</font>", styles["Normal"])
    except:
        logo = Paragraph("<b>CARREFOUR</b>", styles["Title"])

    # Construction de l'en-tête
    mag_info = f"<b>{infos_entree['magasin']}</b><br/>{infos_entree['adresse_magasin'].replace('\n', '<br/>')}"
    col_gauche = [logo, Spacer(1, 0.3*cm), Paragraph(mag_info, styles["Normal"])]
    col_droite = [
        Paragraph(f"<b>ADRESSE DE FACTURATION :</b><br/>{adresse_dest.replace('\n', '<br/>')}", styles["Normal"]),
        Spacer(1, 0.5*cm),
        Paragraph(f"<b>N° Facture :</b> {infos_entree['num_facture']}<br/><b>Commande :</b> {infos_entree['num_commande']}<br/><b>Date :</b> {infos_entree['date_livraison']}", styles["Normal"])
    ]

    elements.append(Table([[col_gauche, col_droite]], colWidths=[10*cm, 8.5*cm], style=[('VALIGN',(0,0),(-1,-1),'TOP')]))
    elements.append(Spacer(1, 0.8*cm))

    # Tableau des articles
    data = [["EAN13", "Libellé", "Qté", "TVA", "P.U. HT", "P.U. TTC", "Total TTC"]]
    for art in data_selection:
        data.append([
            art['ean'], Paragraph(art['libelle'], styles["Normal"]), 
            art['qte_rbt'], f"{art['tva']}%", f"{art['prix_ht']}€", 
            f"{float(art['prix_ttc']):.2f}€", f"{float(art['total_ttc']):.2f}€"
        ])

    t = Table(data, colWidths=[3*cm, 6*cm, 1*cm, 1.3*cm, 2.2*cm, 2.3*cm, 2.7*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.grey), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke), ('GRID',(0,0),(-1,-1),0.5,colors.black), ('FONTSIZE',(0,0),(-1,-1),8), ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    elements.append(t)
    
    # Section Taxes
    elements.append(Spacer(1, 1*cm))
    elements.append(Paragraph("<b>DÉTAIL DES TAXES</b>", styles["Normal"]))
    tax_data = [["Taux", "Base HT", "TVA", "Total TTC"]]
    grouped_taxes = {}
    for art in data_selection:
        rate = float(art['tva'])
        grouped_taxes[rate] = grouped_taxes.get(rate, 0) + float(art['total_ttc'])

    total_ttc, total_ht = 0, 0
    for r in sorted(grouped_taxes.keys()):
        ttc = grouped_taxes[r]
        ht = ttc / (1 + r/100)
        total_ttc += ttc
        total_ht += ht
        tax_data.append([f"{r}%", f"{ht:.2f}€", f"{(ttc-ht):.2f}€", f"{ttc:.2f}€"])
    
    tax_data.append(["TOTAL", f"{total_ht:.2f}€", f"{(total_ttc-total_ht):.2f}€", f"{total_ttc:.2f}€"])
    t_tax = Table(tax_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm])
    t_tax.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black), ('ALIGN',(0,0),(-1,-1),'RIGHT'), ('FONTSIZE',(0,0),(-1,-1),9), ('BOLD', (-1,-1), (-1,-1), True), ('BACKGROUND',(-1,-1),(-1,-1),colors.lightgrey)]))
    elements.append(t_tax)

    doc.build(elements)
    return output_path

# --- 3. INTERFACE STREAMLIT ---
def main():
    st.set_page_config(page_title="Carrefour x SHOPOPOP", layout="wide")
    st.title("📄 Réédition de Factures Carrefour x SHOPOPOP")

    uploaded_file = st.file_uploader("Importer la facture PDF originale", type=["pdf"])

    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            path = tmp.name

        df_art, infos, adresse = extraire_donnees_carrefour(path)

        if not df_art.empty:
            # --- AFFICHAGE DES INFOS DE COMMANDE ---
            st.markdown("### 📝 Informations commande")
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.info(f"**Magasin :** {infos['magasin']}\n\n**Adresse :**\n{infos['adresse_magasin']}")
            
            with col_info2:
                st.success(f"**N° Facture :** {infos['num_facture']}\n\n**N° Commande :** {infos['num_commande']}\n\n**Date :** {infos['date_livraison']}")

            st.divider()

            # --- BOUTON TOUT SÉLECTIONNER ---
            if 'sel_all' not in st.session_state: st.session_state.sel_all = False
            def cb_toggle(): st.session_state.sel_all = not st.session_state.sel_all

            st.button("✅ Tout Sélectionner / Désélectionner", on_click=cb_toggle)

            df_art.insert(0, "Selection", st.session_state.sel_all)

            # --- ÉDITEUR DE DONNÉES (CORRIGÉ POUR 2026) ---
            edited_df = st.data_editor(
                df_art,
                column_config={
                    "Selection": st.column_config.CheckboxColumn("Sel."),
                    "qte_livree": st.column_config.NumberColumn("Qté", min_value=1),
                    "total_ttc": st.column_config.NumberColumn("Total (€)", disabled=True, format="%.2f"),
                },
                hide_index=True,
                width="stretch", # Correction ici pour éviter le message d'erreur
                height=400
            )

            # --- BOUTON GÉNÉRER ---
            if st.button("🚀 Générer", type="primary"):
                selected = edited_df[edited_df["Selection"] == True]
                if selected.empty:
                    st.warning("Veuillez sélectionner au moins un article.")
                else:
                    selection_list = []
                    for _, row in selected.iterrows():
                        q = int(row['qte_livree'])
                        p = float(row['prix_ttc'])
                        selection_list.append({**row.to_dict(), 'qte_rbt': q, 'total_ttc': q * p})
                    
                    pdf_final = generer_pdf_depuis_selection(selection_list, infos, adresse, LOGO_PATH)
                    with open(pdf_final, "rb") as f:
                        st.download_button(
                            label="📥 Télécharger la Facture PDF",
                            data=f,
                            file_name=os.path.basename(pdf_final),
                            mime="application/pdf"
                        )
        else:
            st.error("Aucun article valide trouvé (produits à 0€ ignorés).")
        
        # Nettoyage
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    main()