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
    
    regex_colonnes = r"(\d+)\s+(\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(?:(\d+[.,]\d+)\s+)?(\d+[.,]\d+)"
    STOP_WORDS = ["LIVRAISON", "UNE QUESTION", "POUR TOUTES DEMANDES", "RUBRIQUE AIDE", "MERCI POUR VOTRE", "DATE DE", "N° DE", "ADRESSE DE"]

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            t = page.extract_text() or ""
            texte_complet += t + "\n"
        
        lignes = [l.strip() for l in texte_complet.split('\n') if l.strip()]

        if len(lignes) > 1:
            infos["magasin"] = lignes[1]
            addr_parts = []
            for j in range(2, 7):
                if j < len(lignes):
                    if any(stop in lignes[j].upper() for stop in STOP_WORDS): break
                    addr_parts.append(lignes[j])
            infos["adresse_magasin"] = "\n".join(addr_parts)

        for i, ligne in enumerate(lignes):
            match_ean = re.search(r"^(\d{13})", ligne)
            if match_ean:
                m_n = re.search(regex_colonnes, ligne)
                if m_n:
                    libelle = ligne[13:m_n.start()].strip()
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
    grouped_taxes = {}
    
    for art in data_selection:
        data.append([art['ean'], Paragraph(art['libelle'], styles["Normal"]), art['qte_rbt'], f"{art['tva']}%", f"{art['prix_ht']}€", f"{art['prix_ttc']}€", f"{art['total_ttc']}€"])
        tva_rate = float(art['tva'])
        total_ttc_art = float(art['total_ttc'])
        grouped_taxes[tva_rate] = grouped_taxes.get(tva_rate, 0) + total_ttc_art
    
    t = Table(data, colWidths=[3*cm, 6.5*cm, 1.2*cm, 1.3*cm, 2.2*cm, 2.3*cm, 2.5*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.grey), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke), ('GRID',(0,0),(-1,-1),0.5,colors.black), ('FONTSIZE',(0,0),(-1,-1),8), ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    elements.append(t)
    elements.append(Spacer(1, 1*cm))

    elements.append(Paragraph("<b>DÉTAIL DES TAXES</b>", styles["Normal"]))
    tax_data = [["Taux", "Base HT", "TVA", "Total TTC"]]
    tot_ht, tot_tva, tot_ttc = 0, 0, 0
    
    for rate in sorted(grouped_taxes.keys()):
        ttc = grouped_taxes[rate]
        ht = ttc / (1 + rate/100)
        tva = ttc - ht
        tot_ht += ht; tot_tva += tva; tot_ttc += ttc
        tax_data.append([f"{rate}%", f"{ht:.2f}€", f"{tva:.2f}€", f"{ttc:.2f}€"])
    
    tax_data.append(["TOTAL", f"{tot_ht:.2f}€", f"{tot_tva:.2f}€", f"{tot_ttc:.2f}€"])
    t_tax = Table(tax_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm])
    t_tax.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black), ('ALIGN',(0,0),(-1,-1),'RIGHT'), ('BACKGROUND',(0,0),(-1,0),colors.lightgrey), ('FONTSIZE',(0,0),(-1,-1),9), ('BOLD', (-1,-1), (-1,-1), True)]))
    elements.append(t_tax)

    doc.build(elements)
    return output_path

def main():
    st.set_page_config(page_title="Carrefour x SHOPOPOP", layout="wide")
    st.title("📄 Réédition de Factures Carrefour x SHOPOPOP")

    if 'panier' not in st.session_state:
        st.session_state.panier = set()

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

            col_search, col_count = st.columns([3, 1])
            with col_search:
                recherche = st.text_input("🔍 Rechercher un article (nom ou EAN)", "")
            with col_count:
                st.metric("Articles sélectionnés", len(st.session_state.panier))

            mask = df_art['libelle'].str.contains(recherche, case=False) | df_art['ean'].str.contains(recherche)
            df_filtre = df_art[mask].copy()

            if 'sel_all' not in st.session_state: st.session_state.sel_all = False
            def toggle_all():
                if not st.session_state.sel_all:
                    st.session_state.panier.update(df_art['ean'].tolist())
                else:
                    st.session_state.panier.clear()
                st.session_state.sel_all = not st.session_state.sel_all

            st.button("✅ Tout Sélectionner / Désélectionner", on_click=toggle_all)

            df_filtre.insert(0, "Selection", df_filtre['ean'].apply(lambda x: x in st.session_state.panier))

            edited_df = st.data_editor(
                df_filtre, 
                column_config={
                    "Selection": st.column_config.CheckboxColumn("Sel."), 
                    "qte_livree": st.column_config.NumberColumn("Qté", min_value=1)
                }, 
                hide_index=True, 
                width="stretch",
                key="editor"
            )

            # Synchronisation du panier
            for _, row in edited_df.iterrows():
                ean = row['ean']
                if row['Selection']:
                    st.session_state.panier.add(ean)
                else:
                    st.session_state.panier.discard(ean)

            # --- CALCUL DU RÉCAPITULATIF EN TEMPS RÉEL ---
            selected_items = df_art[df_art['ean'].isin(st.session_state.panier)]
            
            total_ttc_global = 0.0
            total_ht_global = 0.0
            
            for _, row in selected_items.iterrows():
                # On récupère la quantité modifiée depuis l'éditeur si possible, sinon celle du DF original
                qte = float(row['qte_livree'])
                ttc_u = float(str(row['prix_ttc']).replace(',', '.'))
                tva_taux = float(str(row['tva']).replace(',', '.'))
                
                total_ttc_global += qte * ttc_u
                total_ht_global += (qte * ttc_u) / (1 + tva_taux / 100)

            total_tva_global = total_ttc_global - total_ht_global

            st.markdown("### 💰 Récapitulatif du remboursement")
            # Design en colonnes pour le récap
            m1, m2, m3 = st.columns(3)
            m1.metric("Total HT", f"{total_ht_global:.2f} €")
            m2.metric("TVA", f"{total_tva_global:.2f} €")
            m3.subheader(f"Total TTC : {total_ttc_global:.2f} €")
            
            st.divider()

            # --- GÉNÉRATION ---
            if st.button("🚀 Générer la facture SHOPOPOP", type="primary"):
                selected = df_art[df_art['ean'].isin(st.session_state.panier)]
                
                if selected.empty: 
                    st.warning("Sélectionnez au moins un article.")
                else:
                    sel_list = []
                    for _, row in selected.iterrows():
                        q = int(row['qte_livree'])
                        p_ttc = float(str(row['prix_ttc']).replace(',','.'))
                        sel_list.append({**row.to_dict(), 'qte_rbt': q, 'total_ttc': f"{q * p_ttc:.2f}"})
                    
                    pdf = generer_pdf_depuis_selection(sel_list, infos, adresse, LOGO_PATH)
                    with open(pdf, "rb") as f:
                        st.download_button("📥 Télécharger la facture", f, file_name=os.path.basename(pdf))
        
        if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    main()
