"""
Ground truth for the full 20-image benchmark, 6 fields.

GT_CONFIDENCE per image:
  "authoritative" -> sender / total_amount / due_date / payment_status come
      from mama-helper/frontend/src/utils/ground_truth.json (human truth).
      recipient / action are still derived here (that file has no such keys).
  "derived" -> no ground_truth.json entry; all 6 fields were read from the
      document's own OCR full text + document type. Lower confidence,
      wider `accept` sets. Flagged so the report can separate them.

payment_action -> payment_status:  pay->unpaid  none->not_applicable
                                   autopay->paid

`accept` holds extra values (incl. None) that also score as correct, for
placeholder names, genuinely ambiguous senders, and multi-total coupons.
"""

GT_FIELDS = ["sender", "recipient", "total_amount", "payment_status",
             "due_date", "action"]

GT20 = {
    # ---------------- authoritative (ground_truth.json) ----------------
    "SCE_Bill_Letter": {
        "sender": {"value": "SCE", "accept": ["southern california edison", "edison"]},
        "recipient": {"value": "BAKER, NATE", "accept": ["nate baker", None]},
        "total_amount": {"value": "99.36"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None},
        "action": {"value": "pay", "accept": [None]},
    },
    "SCE_Letter": {  # SCE -> CA energy-safety regulator; NOT a bill
        "sender": {"value": "SCE", "accept": ["southern california edison", "edison"]},
        "recipient": {"value": "Shannon O'Rourke",
                      "accept": ["office of energy infrastructure safety",
                                 "deputy director", None]},
        "total_amount": {"value": None},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": None, "accept": ["respond", "review"]},
    },
    "SCE_Sample_Bill": {
        "sender": {"value": "SCE", "accept": ["southern california edison", "edison"]},
        "recipient": {"value": "VALUED CUSTOMER", "accept": [None]},
        "total_amount": {"value": "2149.55"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2020-05-11"},
        "action": {"value": "pay"},
    },
    "SoCalGas": {
        "sender": {"value": "SoCalGas", "accept": ["the gas company", "southern california gas"]},
        "recipient": {"value": "JOHN B DOE", "accept": [None]},
        "total_amount": {"value": "40.56"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2016-01-08"},
        "action": {"value": "pay"},
    },
    "DMV_Registration": {
        "sender": {"value": "DMV", "accept": ["department of motor vehicles",
                                              "california dmv", "state of california"]},
        "recipient": {"value": "GONZELES C", "accept": ["c gonzeles", None]},
        "total_amount": {"value": "95.00", "accept": ["95"]},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2010-10-16"},
        "action": {"value": "pay", "accept": ["renew"]},
    },
    "Hospital_Bill": {
        "sender": {"value": "Allina Health", "accept": ["allina"]},
        "recipient": {"value": "JANE DOE"},
        "total_amount": {"value": "419.07"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2013-04-18"},
        "action": {"value": "pay"},
    },
    "Medical_Invoice": {
        "sender": {"value": None, "accept": ["zylker heathcare", "zylker healthcare"]},
        "recipient": {"value": "Aaron Brown"},
        "total_amount": {"value": "14595.00", "accept": ["14595", "14595.0"]},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2024-09-05"},
        "action": {"value": "pay"},
    },
    "hoag-invoice-mychart": {
        "sender": {"value": "Hoag", "accept": ["hoag orthopedic institute",
                                               "orthopedic hospital"]},
        "recipient": {"value": "JANE DOE"},
        "total_amount": {"value": "333.33"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None},
        "action": {"value": "pay"},
    },
    "IRS_CP504_Notice": {
        "sender": {"value": "IRS", "accept": ["internal revenue service",
                                              "department of the treasury"]},
        "recipient": {"value": None, "accept": [None]},  # 'BUSINESS NAME' placeholder
        "total_amount": {"value": "9533.53"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None, "accept": [None]},  # 'within 30 days', no date
        "action": {"value": "pay"},
    },
    "IRS_cp503": {
        "sender": {"value": "IRS", "accept": ["internal revenue service",
                                              "department of the treasury"]},
        "recipient": {"value": "JAMES & KAREN Q. HINDS",
                      "accept": ["james & karen q. hinds"]},
        "total_amount": {"value": "9533.53"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2018-01-29"},
        "action": {"value": "pay"},
    },
    "Medicare_Notice_PartA": {
        "sender": {"value": "Medicare", "accept": ["centers for medicare", "cms", "medicaid"]},
        "recipient": {"value": "JENNIFER WASHINGTON"},
        "total_amount": {"value": None},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": "review", "accept": [None]},
    },

    # ---------------- derived (no ground_truth.json entry) ----------------
    "Water_Bill2": {  # BUILDING BLOCKS student handout: two hypothetical customers
        "sender": {"value": None, "accept": ["water", "water district"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": ["25.57", "113.90", "10.30"]},
        "payment_status": {"value": "not_applicable", "accept": ["unpaid"]},
        "due_date": {"value": "2015-11-07", "accept": [None]},
        "action": {"value": "pay", "accept": [None, "review"]},
    },
    "BOA_Bill_Example": {
        "sender": {"value": "Bank of America", "accept": ["bankamericard"]},
        "recipient": {"value": None, "accept": [None]},  # customer name not in crop
        "total_amount": {"value": "4543.36", "accept": ["112.00"]},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2018-02-05"},
        "action": {"value": "pay"},
    },
    "Bank_Bill_Due": {  # BUILDING BLOCKS student handout, 'XX' placeholder dates
        "sender": {"value": None, "accept": [None]},
        "recipient": {"value": "Susan Doe", "accept": [None]},
        "total_amount": {"value": "1392.71", "accept": ["25"]},
        "payment_status": {"value": "unpaid", "accept": ["not_applicable"]},
        "due_date": {"value": None, "accept": [None]},  # '1/23/XX' has no year
        "action": {"value": "pay", "accept": [None, "call"]},
    },
    "AAA_insurance_Bill": {
        "sender": {"value": "AAA Insurance", "accept": ["aaa", "memberselect insurance"]},
        "recipient": {"value": "PAT SMITH"},
        "total_amount": {"value": "12.20"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2020-04-08"},
        "action": {"value": "pay"},
    },
    "All_State_Insurance_Card": {  # proof-of-insurance card, NOT a bill
        "sender": {"value": "Allstate", "accept": ["allstate fire and casualty insurance company"]},
        "recipient": {"value": "George and Christine E Murphy",
                      "accept": ["george and christine e murphy", "george murphy"]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None, "review"]},
    },
    "Auto_Insurance_Bill1": {  # 'THIS IS NOT A BILL'
        "sender": {"value": "Farmers Insurance", "accept": ["farmers"]},
        "recipient": {"value": "Jack Smith", "accept": ["jane smith", "jack smith jr."]},
        "total_amount": {"value": None, "accept": ["798.48"]},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None, "contact", "review"]},
    },
    "Great_American_Insurance_Invoice": {
        "sender": {"value": "Great American Insurance",
                   "accept": ["great american insurance group",
                              "great american insurance company"]},
        "recipient": {"value": "PARKER", "accept": ["peter", None]},
        "total_amount": {"value": "336.30", "accept": ["1000.00", "1003.00"]},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2009-01-10"},
        "action": {"value": "pay"},
    },
    "DMV_Notice": {  # NC DMV licence-suspension notice; 'JOEY HOPKINS' is the Secretary
        "sender": {"value": "NC Division of Motor Vehicles",
                   "accept": ["state of north carolina", "department of transportation",
                              "dmv", "ncdot"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": "83.50"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None, "accept": ["2025-09-10"]},
        "action": {"value": "pay"},
    },
    "CMS_EOB": {  # 'THIS IS NOT A BILL', all values redacted to XXXXX
        "sender": {"value": None, "accept": ["cms", "medicare", "customer service number"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": ["0.00", "85.27", "35.00", "406.60"]},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None, "review"]},
    },
}

GT_CONFIDENCE = {
    "SCE_Bill_Letter": "authoritative", "SCE_Letter": "authoritative",
    "SCE_Sample_Bill": "authoritative", "SoCalGas": "authoritative",
    "DMV_Registration": "authoritative", "Hospital_Bill": "authoritative",
    "Medical_Invoice": "authoritative", "hoag-invoice-mychart": "authoritative",
    "IRS_CP504_Notice": "authoritative", "IRS_cp503": "authoritative",
    "Medicare_Notice_PartA": "authoritative",
    "Water_Bill2": "derived", "BOA_Bill_Example": "derived",
    "Bank_Bill_Due": "derived", "AAA_insurance_Bill": "derived",
    "All_State_Insurance_Card": "derived", "Auto_Insurance_Bill1": "derived",
    "Great_American_Insurance_Invoice": "derived", "DMV_Notice": "derived",
    "CMS_EOB": "derived",
}
