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

    # Liste des phrases qui marquent la FIN de l'adresse
    STOP_WORDS = [
        "LIVRAISON", "UNE QUESTION", "POUR TOUTES DEMANDES", 
        "RUBRIQUE AIDE", "MERCI POUR VOTRE", "DATE DE", "N° DE"
    ]

    with pdfplumber.open(pdf_path) as pdf:
        texte_complet = ""
        for page in pdf.pages:
            texte_complet += (page.extract_text() or "") + "\n"
        
        # On nettoie les lignes vides
        lines = [line.strip() for line in texte_complet.split('\n') if line.strip()]

        # --- LOGIQUE DE POSITION SÉCURISÉE ---
        if len(lines) > 1:
            # Le magasin est presque toujours en ligne 2 (index 1) [cite: 215, 336]
            infos["magasin"] = lines[1]
            
            addr_parts = []
            # On regarde de la ligne 3 à la ligne 6 [cite: 216, 217, 337, 338]
            for j in range(2, 7):
                if j < len(lines):
                    l_up = lines[j].upper()
                    # Si on rencontre un mot interdit, on s'arrête immédiatement
                    if any(stop in l_up for stop in STOP_WORDS):
                        break
                    addr_parts.append(lines[j])
            
            infos["adresse_magasin"] = "\n".join(addr_parts)

        # --- EXTRACTION DES NUMÉROS ---
        m_f = re.search(r"N° de facture\s*[:\s]*([A-Z0-9]+)", texte_complet) # [cite: 223, 343]
        if m_f: infos['num_facture'] = m_f.group(1)
        
        m_c = re.search(r"N° de commande\s*[:\s]*(\d+)", texte_complet) # [cite: 223, 343]
        if m_c: infos['num_commande'] = m_c.group(1)
        
        m_d = re.search(r"Date de livraison\s*[:\s]*([\d/]+)", texte_complet) # [cite: 222, 342]
        if m_d: infos['date_livraison'] = m_d.group(1)

        # --- EXTRACTION ARTICLES ---
        for i, ligne in enumerate(lines):
            match_ean = re.search(r"^(\d{13})", ligne) # [cite: 231, 353]
            if match_ean:
                montants = re.findall(r"\d+[.,]\d+", ligne)
                if len(montants) >= 3:
                    total_ttc = float(montants[-1].replace(',', '.'))
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
