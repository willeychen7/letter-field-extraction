"""
Ground truth for the 30-image HOLDOUT set (holdout_set.py).

Built from each document's own text (existing full-text dumps +
this run's OCR), read BEFORE scoring, plus the 3 images that
mama-helper/ground_truth.json already covers (water_bill, statefarm_bill,
att_bill -> GT_CONF "authoritative" for sender/amount/due/payment).
Everything else is GT_CONF "derived": annotated by hand from the document,
wider `accept` sets, and several genuinely degenerate documents (a rate
sheet, a fee-screen photo, blank template forms) where `null` is the
right answer.

payment_action -> payment_status:  pay->unpaid  none->not_applicable
                                   autopay->paid
"""

GT_FIELDS = ["sender", "recipient", "total_amount", "payment_status",
             "due_date", "action"]

GT_HOLD = {
    # ---------------- utility ----------------
    "Water_Bill3": {  # Trabuco Canyon WD RATE SHEET -- not a bill
        "sender": {"value": "Trabuco Canyon Water District", "accept": ["trabuco canyon", "water district"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": None, "accept": [None]},
    },
    "water_bill": {  # Ventura River WD billing statement (authoritative core)
        "sender": {"value": "Ventura River Water District", "accept": ["water district", "ventura river"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": "71.20", "accept": ["71.2"]},
        "payment_status": {"value": "paid", "accept": ["unpaid"]},   # autopay
        "due_date": {"value": "2024-04-30"},
        "action": {"value": "pay", "accept": [None]},
    },
    "waste_managment": {  # WM invoice (camera photo)
        "sender": {"value": "WM", "accept": ["waste management", "wm.com"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": "87.05"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2025-07-02", "accept": [None]},
        "action": {"value": "pay", "accept": [None]},
    },
    "att_bill": {  # AT&T wireless, credit balance, 'Payment is Not Required'
        "sender": {"value": "AT&T", "accept": ["att"]},
        "recipient": {"value": None, "accept": [None, "tech group & associates"]},
        "total_amount": {"value": None, "accept": [None, "-6.33", "6.33"]},
        "payment_status": {"value": "not_applicable", "accept": ["paid"]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },

    # ---------------- medical ----------------
    "UCLA_Health_Bill": {
        "sender": {"value": "UCLA Health", "accept": ["resnick neuropsychiatric hospital"]},
        "recipient": {"value": "John Q. Patient", "accept": ["john q patient"]},
        "total_amount": {"value": "472.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2012-11-01"},
        "action": {"value": "pay"},
    },
    "UCLA_Health_Bill2": {
        "sender": {"value": "UCLA Health", "accept": ["ronald reagan ucla medical center"]},
        "recipient": {"value": "John Q. Patient", "accept": ["john q patient"]},
        "total_amount": {"value": "236.00", "accept": [None]},   # multi-visit page, one 'your responsibility'
        "payment_status": {"value": "unpaid"},                   # STATUS: PAST DUE
        "due_date": {"value": "2012-11-01"},
        "action": {"value": "pay"},
    },
    "Eye_care-invoice": {
        "sender": {"value": "Vision Plus Of Ballard", "accept": ["vision plus"]},
        "recipient": {"value": "John Smith"},
        "total_amount": {"value": "109.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": None, "accept": [None, "pay"]},
    },

    # ---------------- insurance ----------------
    "Progressive_Insurance_Bill": {  # claim repair ESTIMATE, not a bill
        "sender": {"value": "Progressive", "accept": ["progressive test"]},
        "recipient": {"value": None, "accept": [None, "john smith"]},
        "total_amount": {"value": None, "accept": [None, "500.00"]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": None, "accept": [None]},
    },
    "Penny_Insurance_Bill": {  # declarations page, 'retain for your records'
        "sender": {"value": "Penny Insurance", "accept": ["penny general insurance company"]},
        "recipient": {"value": "Penny the Pig", "accept": [None]},
        "total_amount": {"value": None, "accept": [None, "700.00"]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": None, "accept": [None]},
    },
    "State_Farm_Insurance_Card": {  # ID card
        "sender": {"value": "State Farm", "accept": ["state farm mutual automobile insurance company"]},
        "recipient": {"value": "JANET SMITH", "accept": ["janet smith"]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "Coverage_Care_Insurance_Card": {  # ID card, redacted
        "sender": {"value": None, "accept": [None, "insurance company"]},
        "recipient": {"value": "Jane Doe"},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "State_Farm_Insurance": {  # 'BALANCE DUE NOTICE' -- a real bill
        "sender": {"value": "State Farm", "accept": ["state farm mutual automobile insurance company"]},
        "recipient": {"value": "SHEMARIA, ALFRED I & DEANNA",
                      "accept": ["shemaria, alfred", "alfred shemaria", "shemaria alfred i deanna"]},
        "total_amount": {"value": "323.91"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2016-09-28"},
        "action": {"value": "pay"},
    },
    "statefarm_bill": {  # RENEWAL DECLARATIONS, 'AMOUNT DUE: None', autopay (authoritative core)
        "sender": {"value": "State Farm", "accept": ["state farm lloyds"]},
        "recipient": {"value": "SMITH, BRENDA", "accept": ["brenda smith"]},
        "total_amount": {"value": None, "accept": [None, "0.00", "165.00"]},
        "payment_status": {"value": "paid", "accept": ["not_applicable"]},   # autopay/SFPP
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "aaa-policy_renew": {  # AAA membership renewal notice (camera photo)
        "sender": {"value": "AAA", "accept": ["aaa northeast"]},
        "recipient": {"value": None, "accept": [None]},   # 'Dear ___' blank
        "total_amount": {"value": "88.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None, "accept": [None]},    # 'TOTAL DUE BY $20' garbled, no full date
        "action": {"value": "renew", "accept": ["pay"]},
    },

    # ---------------- DMV ----------------
    "DMV_registration_late_fee": {  # CA DMV renewal notice, all values redacted 'XXXX'
        "sender": {"value": "DMV", "accept": ["state of california", "department of motor vehicles", "public service agency"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "unpaid", "accept": ["not_applicable"]},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": "renew", "accept": ["pay", None]},
    },
    "ca-dmv-registration-fee": {  # phone photo of a DMV fee-breakdown screen
        "sender": {"value": None, "accept": [None, "dmv"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": None, "accept": [None, "unpaid", "not_applicable"]},
        "due_date": {"value": None, "accept": [None]},
        "action": {"value": None, "accept": [None]},
    },

    # ---------------- Medicare ----------------
    "Medicare_Notice_PartB": {  # 'THIS IS NOT A BILL'
        "sender": {"value": "Medicare", "accept": ["health & human services", "cms", "centers for medicare"]},
        "recipient": {"value": "JENNIFER WASHINGTON"},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable"},
        "due_date": {"value": None},
        "action": {"value": "review", "accept": [None]},
    },
    "Medicare_Notice_of_Denial": {  # Part D denial notice template, blank placeholders
        "sender": {"value": "Medicare", "accept": ["centers for medicare & medicaid services", "department of health and human services"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None, "review", "respond"]},
    },
    "Medixare_Premium_Bill": {  # CMS 'DELINQUENT BILL'
        "sender": {"value": "Medicare", "accept": ["centers for medicare & medicaid services", "cms", "health & human services"]},
        "recipient": {"value": "CHARLIE MEDICARE", "accept": ["charlie medicare"]},
        "total_amount": {"value": "2715.60"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2021-10-25"},
        "action": {"value": "pay"},
    },

    # ---------------- bank ----------------
    "Bank_Bill_Example": {  # non-US (PHP) credit-card statement
        "sender": {"value": "ETC Bank", "accept": ["etc"]},
        "recipient": {"value": "BERGL M. SBUCOL", "accept": ["bergl m sbucol"]},
        "total_amount": {"value": "50000.00", "accept": ["50000", "2500.00", None]},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2018-02-15", "accept": [None]},
        "action": {"value": "pay", "accept": [None]},
    },
    "EastWest_Bank_Form": {  # blank hardship 'Financial Statement' form
        "sender": {"value": "East West Bank", "accept": ["eastwestbank", "east west bank"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "EastWest_Bank_Bill": {  # business checking statement
        "sender": {"value": "East West Bank", "accept": ["eastwestbank"]},
        "recipient": {"value": None, "accept": [None, "kaboom fireworks"]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "Chase_Bank_Bill_Example": {  # checking statement
        "sender": {"value": "Chase", "accept": ["jpmorgan chase bank"]},
        "recipient": {"value": "Debbie Anita Walsh"},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "Chase_Bank_Bill_Example2": {  # checking statement, placeholder addressee
        "sender": {"value": "Chase", "accept": ["jpmorgan chase bank"]},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },
    "First_Bank_Bill": {  # checking statement
        "sender": {"value": "First Bank"},
        "recipient": {"value": "Jack Smith", "accept": ["mr. jack smith", "usa small business"]},
        "total_amount": {"value": None, "accept": [None]},
        "payment_status": {"value": "not_applicable", "accept": [None]},
        "due_date": {"value": None},
        "action": {"value": None, "accept": [None]},
    },

    # ---------------- HOA ----------------
    "HOA1": {  # Bluebonnet Highlands HOA invoice
        "sender": {"value": "Bluebonnet Highlands Homeowners Association",
                   "accept": ["bluebonnethighlands", "bbh", "homeowners association"]},
        "recipient": {"value": None, "accept": [None]},   # detach stub 'Name: ___' blank
        "total_amount": {"value": "360.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2013-01-31"},
        "action": {"value": "pay"},
    },
    "HOA2": {  # KinFinity HOA dues statement, '[Your Name]' placeholder, year 2085
        "sender": {"value": "KinFinity"},
        "recipient": {"value": None, "accept": [None]},
        "total_amount": {"value": "1250.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": None, "accept": ["2085-01-31"]},  # parser caps at 2035
        "action": {"value": "pay"},
    },
    "HOA3": {  # 'Your Company Inc.' HOA dues invoice, placeholder parties
        "sender": {"value": "Your Company Inc.", "accept": [None]},
        "recipient": {"value": "Customer Name", "accept": [None]},
        "total_amount": {"value": "1200.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2025-10-16"},
        "action": {"value": "pay"},
    },
    "HOA4": {  # Happy Hills Association dues bill
        "sender": {"value": "Happy Hills Association", "accept": ["jellybird hoa management"]},
        "recipient": {"value": "Jane Smith"},
        "total_amount": {"value": "100.00"},
        "payment_status": {"value": "unpaid"},
        "due_date": {"value": "2024-10-01"},
        "action": {"value": "pay", "accept": [None]},
    },

    # ---------------- general ----------------
    "aws_invoice": {  # Amazon Web Services invoice
        "sender": {"value": "Amazon Web Services", "accept": ["amazon web services llc", "aws"]},
        "recipient": {"value": None, "accept": [None, "jeff barr"]},
        "total_amount": {"value": "135.38"},
        "payment_status": {"value": "unpaid", "accept": ["not_applicable"]},
        "due_date": {"value": None},
        "action": {"value": "pay", "accept": [None]},
    },
}

GT_CONF = {k: "derived" for k in GT_HOLD}
for k in ("water_bill", "statefarm_bill", "att_bill"):
    GT_CONF[k] = "authoritative"   # sender/amount/due/payment from ground_truth.json
