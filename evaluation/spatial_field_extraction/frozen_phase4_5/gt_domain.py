"""
Phase 4 research -- hand-assigned document DOMAIN for all 50 benchmark
images (20 dev + 30 holdout), read from each document's content.

Labels are my best call per the 8-class taxonomy. `note` flags the cases
where the taxonomy itself is the problem (no general/home/life insurance
class; Medicare split; membership vs insurance; B2B service). These flags
are the point of the experiment -- not classifier bugs.

DOMAINS = AUTO_INSURANCE HEALTHCARE BANKING_FINANCE CREDIT_CARD
          GOVERNMENT_TAX UTILITIES_SERVICES HOUSING_PROPERTY OTHER
"""

GT_DOMAIN = {
    # ---- dev 20 ----
    "SCE_Bill_Letter":        ("UTILITIES_SERVICES", ""),
    "SCE_Letter":             ("OTHER", "utility<->state-regulator correspondence, not a consumer letter"),
    "SCE_Sample_Bill":        ("UTILITIES_SERVICES", ""),
    "SoCalGas":               ("UTILITIES_SERVICES", ""),
    "Water_Bill2":            ("UTILITIES_SERVICES", "teaching handout, still a water bill in form"),
    "BOA_Bill_Example":       ("BANKING_FINANCE", ""),
    "Bank_Bill_Due":          ("BANKING_FINANCE", "'sample credit card statement' handout"),
    "AAA_insurance_Bill":     ("INSURANCE", "GAP: personal umbrella / excess liability, not auto; no general-insurance class"),
    "All_State_Insurance_Card": ("INSURANCE", ""),
    "Auto_Insurance_Bill1":   ("INSURANCE", ""),
    "Great_American_Insurance_Invoice": ("INSURANCE", "GAP: generic commercial premium invoice, type not stated"),
    "DMV_Registration":       ("GOVERNMENT", "vehicle + government; taxonomy routes DMV -> GOVERNMENT_TAX"),
    "DMV_Notice":             ("GOVERNMENT", ""),
    "Hospital_Bill":          ("HEALTHCARE", ""),
    "Medical_Invoice":        ("HEALTHCARE", ""),
    "CMS_EOB":                ("HEALTHCARE", ""),
    "hoag-invoice-mychart":   ("HEALTHCARE", ""),
    "IRS_CP504_Notice":       ("GOVERNMENT", ""),
    "IRS_cp503":              ("GOVERNMENT", ""),
    "Medicare_Notice_PartA":  ("HEALTHCARE", "CONFUSION: Medicare Summary Notice -- health context, not gov notice"),

    # ---- holdout 30 ----
    "Water_Bill3":            ("UTILITIES_SERVICES", "rate sheet, not a bill"),
    "water_bill":             ("UTILITIES_SERVICES", ""),
    "waste_managment":        ("UTILITIES_SERVICES", ""),
    "att_bill":               ("UTILITIES_SERVICES", "phone/telecom"),
    "UCLA_Health_Bill":       ("HEALTHCARE", ""),
    "UCLA_Health_Bill2":      ("HEALTHCARE", ""),
    "Eye_care-invoice":       ("HEALTHCARE", "optometry"),
    "Progressive_Insurance_Bill": ("INSURANCE", "auto claim repair estimate"),
    "Penny_Insurance_Bill":   ("INSURANCE", ""),
    "State_Farm_Insurance_Card": ("INSURANCE", ""),
    "Coverage_Care_Insurance_Card": ("HEALTHCARE", "health-plan member ID card"),
    "State_Farm_Insurance":   ("INSURANCE", ""),
    "statefarm_bill":         ("HOUSING_PROPERTY", "GAP: renters insurance -- home-related, no home-insurance class"),
    "aaa-policy_renew":       ("INSURANCE", "GAP: AAA roadside membership, not insurance"),
    "DMV_registration_late_fee": ("GOVERNMENT", ""),
    "ca-dmv-registration-fee": ("GOVERNMENT", "phone photo of a DMV fee screen"),
    "Medicare_Notice_PartB":  ("HEALTHCARE", "CONFUSION: Medicare Summary Notice"),
    "Medicare_Notice_of_Denial": ("HEALTHCARE", "CONFUSION: CMS Part D denial -- coverage decision vs gov notice"),
    "Medixare_Premium_Bill":  ("GOVERNMENT", "CONFUSION: CMS premium DELINQUENT BILL -- gov biller vs healthcare topic"),
    "Bank_Bill_Example":      ("BANKING_FINANCE", "non-US (PHP) credit card statement"),
    "EastWest_Bank_Form":     ("BANKING_FINANCE", "CONFUSION: mortgage-hardship financial form -- bank vs housing"),
    "EastWest_Bank_Bill":     ("BANKING_FINANCE", "business checking statement"),
    "Chase_Bank_Bill_Example": ("BANKING_FINANCE", "checking statement"),
    "Chase_Bank_Bill_Example2": ("BANKING_FINANCE", "checking statement"),
    "First_Bank_Bill":        ("BANKING_FINANCE", "checking statement"),
    "HOA1":                   ("HOUSING_PROPERTY", ""),
    "HOA2":                   ("HOUSING_PROPERTY", ""),
    "HOA3":                   ("HOUSING_PROPERTY", ""),
    "HOA4":                   ("HOUSING_PROPERTY", ""),
    "aws_invoice":            ("OTHER", "GAP: B2B cloud-services invoice, not a personal life domain"),
}
