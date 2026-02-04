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
LOGO_PATH = "logo carrefour.png"

def extraire_donnees_carrefour(pdf_path):
    articles = []
    infos = {
        "magasin": "CARREFOUR",
        "adresse_magasin": "Adresse non détectée",
        "num_facture": "NC",
        "num_commande": "NC",
        "date_livraison": "NC"
    }
    adresse_shopopop = "SHOPOPOP\n1 ter mail Pablo picasso\n44000 Nantes"

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            texte_complet += (page.extract_text() or "") + "\n"
        
        lines = [line.strip() for line in texte_complet.split('\n')]

        # 1. GÉNÉRALISATION DU MAGASIN
        # On cherche la première ligne qui contient un mot clé Carrefour
        for line in lines[:15]:
            if any(x in line.upper() for x in ["CARREFOUR", "CITY", "MARKET", "CONTACT"]):
                if "SERVICE" not in line.upper() and "FACTURE" not in line.upper():
                    infos["magasin"] = line
                    break

        # 2. GÉNÉRALISATION DE L'ADRESSE (Recherche de motif CP + Ville)
        # On cherche un bloc : [Chiffre] [Rue/Av/Place...] [Code Postal 5 chiffres]
        # On scanne tout le texte pour trouver le code postal
        motif_adresse = re.search(r"(\d+[\s,]+(?:RUE|AVENUE|BD|PLACE|RTE|ROUTE|CH|CHEMIN).*?\d{5}.*?)(?:\n|$)", texte_complet, re.IGNORECASE | re.DOTALL)
        if motif_adresse:
            infos["adresse_magasin"] = motif_adresse.group(1).replace('\n', ' ').strip()
        else:
            # Secours : si on trouve un code postal seul avec une ville
            motif_cp = re.search(r"(\d{5}\s+[A-Z\s\-]{3,})", texte_complet)
            if motif_cp:
                # On remonte de deux lignes pour prendre la rue
                infos["adresse_magasin"] = motif_cp.group(1)

        # 3. EXTRACTION MÉTADONNÉES (Facture, Commande, Date)
        m_f = re.search(r"N° de facture\s*[:\s]*([A-Z0-9]+)", texte_complet)
        if m_f: infos['num_facture'] = m_f.group(1)
        
        m_c = re.search(r"N° de commande\s*[:\s]*(\d+)", texte_complet)
        if m_c: infos['num_commande'] = m_c.group(1)
        
        m_d = re.search(r"Date de livraison\s*[:\s]*([\d/]+)", texte_complet)
        if m_d: infos['date_livraison'] = m_d.group(1)

        # 4. EXTRACTION ARTICLES (Logique de colonnes robuste)
        # On cherche les lignes qui commencent par un EAN (13 chiffres)
        regex_colonnes = r"(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(?:(\d+[.,]\d+)\s+)?(\d+[.,]\d+)"
        
        for i, ligne in enumerate(lines):
            match_ean = re.search(r"^(\d{13})", ligne)
            if match_ean:
                # On cherche les montants en fin de ligne
                montants = re.findall(r"\d+[.,]\d+", ligne)
                if len(montants) >= 4:
                    total_ttc = float(montants[-1].replace(',', '.'))
                    if total_ttc > 0:
                        # Le libellé est entre l'EAN et le premier montant
                        libelle = ligne[13:].split(montants[0])[0].strip()
                        if not libelle and i > 0: libelle = lines[i-1]
                        
                        articles.append({
                            'ean': match_ean.group(1),
                            'libelle': libelle if libelle else "Produit",
                            'qte_livree': int(re.search(r"\s(\d+)\s", ligne).group(1)) if re.search(r"\s(\d+)\s", ligne) else 1,
                            'tva': montants[-5] if len(montants)>=5 else "5.5",
                            'prix_ht': montants[-4],
                            'prix_ttc': montants[-3],
                            'total_ttc': total_ttc
                        })
    
    return pd.DataFrame(articles).drop_duplicates(), infos, adresse_shopopop

# --- LE RESTE DU CODE (PDF ET STREAMLIT) NE CHANGE PAS ---
# (Garde les fonctions generer_pdf_depuis_selection et main de la version précédente)
