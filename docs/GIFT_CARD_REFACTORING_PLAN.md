# Gift Card Refactoring Plan - ERPNext Native Integration

## 📊 Progression

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Custom Fields ERPNext Coupon Code | ✅ Done |
| 2 | Refactoring gift_cards.py | ✅ Done |
| 3 | Refactoring offers.py | ✅ Done |
| 4 | Patch de Migration | ✅ Done |
| 5 | Bouton de Création Rapide | ✅ Done |
| 6 | Adaptation Frontend | ✅ Done |
| 7 | Nettoyage | ✅ Done |
| 8 | Referral Code Migration | ✅ Done |
| 9 | Tests Backend | ✅ Done (53 tests passés) |
| 10 | Tests Frontend (Chrome) | ✅ Done |

### Détails Phase 9 - Tests Backend (Complété 2026-01-14)

**53 tests passés** couvrant:
- Gift card code generation (format GC-XXXX-XXXX, unicité)
- Création manuelle de gift cards
- Pricing Rule création avec/sans validity
- Application de gift cards (montant partiel, complet)
- Mise à jour du solde après utilisation
- Validation coupons (expirés, restriction client, dates)
- Récupération des gift cards actifs
- CRUD coupons promotionnels
- Referral Code (création, application, génération coupons)

---

## 🎯 Objectif

Supprimer la dépendance à `POS Coupon` et utiliser directement `ERPNext Coupon Code` pour:
- Simplifier l'architecture (une seule source de vérité)
- Éliminer la synchronisation complexe
- Compatibilité native avec Webshop et autres modules ERPNext
- Meilleure intégration comptable

---

## 📊 État Actuel

### Ce qui existe dans POS Coupon (à migrer)

| Champ | Description | Équivalent ERPNext |
|-------|-------------|-------------------|
| `coupon_code` | Code du coupon | `coupon_code` ✅ |
| `coupon_type` | Gift Card, Promotional | `coupon_type` ✅ |
| `customer` | Client assigné | `customer` (à ajouter) |
| `discount_amount` | Montant de réduction | Via Pricing Rule |
| `gift_card_amount` | Solde gift card | `gift_card_amount` (custom) ✅ |
| `original_amount` | Montant original | `original_gift_card_amount` (custom) ✅ |
| `valid_from/upto` | Validité | `valid_from/upto` ✅ |
| `used` | Compteur utilisation | `used` ✅ |
| `maximum_use` | Limite utilisation | `maximum_use` ✅ |
| `company` | Société | Via Pricing Rule |
| `source_invoice` | Facture source | `source_pos_invoice` (custom) ✅ |

### Fichiers impactés

```
Backend (pos_next/):
├── api/gift_cards.py          # À refactorer (principal)
├── api/offers.py              # À refactorer (get_active_coupons, validate_coupon)
├── api/invoices.py            # À adapter (coupon_code handling)
├── api/promotions.py          # À vérifier
├── hooks.py                   # À nettoyer (retirer hooks POS Coupon)
├── fixtures/custom_field.json # À compléter
└── pos_next/doctype/
    └── pos_coupon/            # À SUPPRIMER (après migration)

Frontend (POS/src/):
├── composables/useGiftCard.js # À adapter
├── composables/usePermissions.js # À vérifier
└── components/sale/CouponDialog.vue # À adapter
```

---

## 🚀 Plan de Refactoring

### Phase 1: Custom Fields ERPNext Coupon Code

**Statut: ✅ Partiellement fait**

Champs déjà créés dans `fixtures/custom_field.json`:
- `gift_card_amount` - Solde actuel
- `original_gift_card_amount` - Montant original
- `coupon_code_residual` - Référence au coupon original (split)
- `pos_coupon` - Lien vers POS Coupon (à retirer après migration)
- `source_pos_invoice` - Facture d'origine

**À ajouter:**
```json
{
  "dt": "Coupon Code",
  "fieldname": "pos_next_gift_card",
  "fieldtype": "Check",
  "label": "POS Next Gift Card",
  "description": "Gift card managed by POS Next"
},
{
  "dt": "Coupon Code",
  "fieldname": "customer",
  "fieldtype": "Link",
  "options": "Customer",
  "label": "Customer",
  "description": "Customer assigned to this coupon (optional for gift cards)"
}
```

---

### Phase 2: Refactoring gift_cards.py

**Statut: 🔄 À faire**

#### 2.1 Créer Gift Card directement dans ERPNext

```python
def create_gift_card_from_invoice(doc, method=None):
    """
    Crée un Coupon Code ERPNext + Pricing Rule quand on vend un item gift card.

    Flow:
    1. Détecte l'item gift card dans la facture
    2. Crée le Pricing Rule avec le montant
    3. Crée le Coupon Code ERPNext directement
    4. Retourne les infos du gift card créé
    """
    # Plus de POS Coupon intermédiaire!
```

#### 2.2 Simplifier apply_gift_card

```python
def apply_gift_card(coupon_code, invoice_total, customer=None, company=None):
    """
    Applique un gift card (Coupon Code ERPNext) à une facture.

    - Vérifie le solde dans gift_card_amount
    - Calcule le discount
    - Retourne les infos pour l'UI
    """
```

#### 2.3 Simplifier process_gift_card_on_submit

```python
def process_gift_card_on_submit(doc, method=None):
    """
    Met à jour le solde du Coupon Code ERPNext après utilisation.

    - Réduit gift_card_amount
    - Met à jour le Pricing Rule associé
    - Gère le splitting si nécessaire
    """
```

---

### Phase 3: Refactoring offers.py

**Statut: 🔄 À faire**

#### 3.1 get_active_coupons

Actuellement utilise `POS Coupon`. À refactorer pour:
- Récupérer les `Coupon Code` ERPNext avec `pos_next_gift_card = 1`
- Inclure les coupons standard ERPNext aussi
- Retourner le format attendu par le frontend

#### 3.2 validate_coupon

Actuellement utilise `POS Coupon`. À refactorer pour:
- Valider contre `Coupon Code` ERPNext
- Vérifier le solde `gift_card_amount` pour les gift cards
- Vérifier le Pricing Rule associé

---

### Phase 4: Patch de Migration

**Statut: ⏳ À créer**

Fichier: `pos_next/patches/v1_x/migrate_pos_coupons_to_erpnext.py`

```python
def execute():
    """
    Migre tous les POS Coupon vers ERPNext Coupon Code.

    Pour chaque POS Coupon:
    1. Crée le Pricing Rule si nécessaire
    2. Crée le Coupon Code ERPNext
    3. Copie tous les champs
    4. Met à jour les références dans les factures
    5. Garde POS Coupon en lecture seule (ne pas supprimer immédiatement)
    """
```

---

### Phase 5: Bouton de Création Rapide

**Statut: ⏳ À créer**

#### 5.1 Client Script pour Coupon Code List

Fichier: `pos_next/public/js/coupon_code_list.js`

```javascript
frappe.listview_settings['Coupon Code'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__('Create Gift Card'), function() {
            // Dialog pour créer rapidement un gift card
            let d = new frappe.ui.Dialog({
                title: __('Create Gift Card'),
                fields: [
                    { fieldname: 'amount', fieldtype: 'Currency', label: __('Amount'), reqd: 1 },
                    { fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer (Optional)') },
                    { fieldname: 'company', fieldtype: 'Link', options: 'Company', label: __('Company'), reqd: 1 },
                    { fieldname: 'validity_months', fieldtype: 'Int', label: __('Validity (Months)'), default: 12 }
                ],
                primary_action: function() {
                    // Appel API pour créer le gift card
                }
            });
            d.show();
        });
    }
};
```

#### 5.2 API de création manuelle

```python
@frappe.whitelist()
def create_gift_card_manual(amount, company, customer=None, validity_months=12):
    """
    Crée un gift card manuellement (depuis le bouton ERPNext).

    Returns:
        dict: Infos du gift card créé (code, montant, validité)
    """
```

---

### Phase 6: Adaptation Frontend

**Statut: 🔄 À faire**

#### 6.1 useGiftCard.js

- Retirer les références à `POS Coupon`
- Appeler directement les APIs qui utilisent `Coupon Code`
- Garder la même interface pour les composants

#### 6.2 CouponDialog.vue

- Aucun changement majeur nécessaire (utilise déjà l'API)
- Vérifier l'affichage du solde gift card

---

### Phase 7: Nettoyage

**Statut: ⏳ À faire (après migration réussie)**

1. Retirer le doctype `POS Coupon` du module
2. Retirer les fixtures liés à POS Coupon
3. Nettoyer les hooks
4. Retirer les logs de debug

---

## 📋 Checklist de Tests

### Tests Backend (Phase 9) ✅ Complété

- [x] **Génération Code Gift Card**
  - [x] Code au format GC-XXXX-XXXX
  - [x] Codes uniques
  - [x] Caractères valides (uppercase + digits)

- [x] **Création Manuelle Gift Card**
  - [x] Création basique avec montant et company
  - [x] Création avec customer assigné
  - [x] Création avec validité 0 (illimité)
  - [x] Pricing Rule créé correctement

- [x] **Application Gift Card**
  - [x] Appliquer gift card montant < total facture
  - [x] Appliquer gift card montant > total facture (splitting logic)
  - [x] Mise à jour solde après utilisation partielle
  - [x] Mise à jour solde à zéro (exhausted)

- [x] **Validation Coupon**
  - [x] Coupon valide accepté
  - [x] Coupon invalide rejeté
  - [x] Coupon expiré rejeté
  - [x] Coupon pas encore valide rejeté
  - [x] Restriction customer respectée
  - [x] Gift card solde zéro rejeté

- [x] **Coupons Promotionnels**
  - [x] Création avec pourcentage
  - [x] Création avec montant fixe
  - [x] Mise à jour discount
  - [x] Mise à jour validité
  - [x] Suppression coupon + pricing rule

- [x] **Referral Code**
  - [x] Création avec pourcentage/montant
  - [x] Génération coupon referrer
  - [x] Génération coupon referee
  - [x] Application referral code
  - [x] Validation des champs requis

### Tests Frontend (Phase 10) ✅ Complété (2026-01-14)

- [x] **Bouton Création Manuelle ERPNext** ✅
  - [x] Bouton visible dans liste Coupon Code
  - [x] Dialog de création fonctionne (Amount, Company, Customer, Validity)
  - [x] Gift card créé correctement avec Pricing Rule
  - [x] Code affiché dans dialog de confirmation

- [x] **Application Gift Card dans POS** ✅
  - [x] Dialog de coupon fonctionne
  - [x] Gift cards disponibles affichés avec solde
  - [x] Discount s'applique correctement au total
  - [x] Grand_total final correct (CHF 0.00 quand couvert)
  - [x] Checkout avec gift card fonctionne
  - [x] Solde gift card réduit après utilisation
  - [x] Compteur "used" incrémenté

- [x] **Création Gift Card via Vente** ✅
  - [x] Vendre item gift card → Coupon Code ERPNext créé
  - [x] Dialog notification (GiftCardCreatedDialog.vue)
  - [x] API get_gift_cards_from_invoice

- [x] **Flow Complet de Splitting** ✅
  - [x] Gift card 75 CHF sur facture 29.90 CHF → solde 45.10 CHF
  - [x] Peut réutiliser le même code pour le solde restant

- [x] **Annulation** ✅
  - [x] Annuler facture FA-2026-00042 → solde restauré (45.10 → 75 CHF)

### Tests Intégration (Optionnel)

- [ ] **Webshop**
  - [ ] Gift card utilisable sur Webshop
  - [ ] Solde réduit après commande Webshop

- [ ] **Migration**
  - [x] Patch de migration existe
  - [ ] Migration testée sur prod avec données réelles

---

## 📅 Ordre d'Exécution Recommandé

1. **Phase 1** - Compléter les custom fields (30 min)
2. **Phase 2** - Refactorer gift_cards.py (2-3h)
3. **Phase 3** - Refactorer offers.py (1h)
4. **Phase 6** - Adapter frontend (30 min)
5. **Tests** - Tester le flow complet (1h)
6. **Phase 4** - Créer patch migration (1h)
7. **Phase 5** - Bouton création rapide (1h)
8. **Phase 7** - Nettoyage final (30 min)

**Temps estimé total: 7-9 heures**

---

## 🔗 Compatibilité

### Webshop ERPNext
Le Webshop utilise nativement `Coupon Code` + `Pricing Rule`, donc:
- ✅ Compatible automatiquement
- ✅ Gift cards utilisables sur le web
- ✅ Solde partagé entre POS et Web

### API Standard ERPNext
- ✅ `apply_pricing_rule` fonctionne
- ✅ Rapports Coupon Code incluent les gift cards
- ✅ Workflow standard de validation

---

## ⚠️ Points d'Attention

1. **Ne pas supprimer POS Coupon immédiatement**
   - Garder en lecture seule après migration
   - Supprimer dans une version ultérieure

2. **Pricing Rule par Company**
   - Un Pricing Rule par société
   - Vérifier la company dans les validations

3. **Mode Offline**
   - Cacher les Coupon Code localement
   - Sync au retour online

4. **Performance**
   - Indexer `gift_card_amount` si beaucoup de coupons
   - Cacher les settings
