"""
Holdout benchmark image list -- fresh US letters that were NOT used to
build, tune, or threshold Phase 3. None of these appear in holdout_set's
dev list (run_full20.py IMAGES) or in ground_truth_20.py.

Each entry: (key, source_dir, filename, category). webp/avif originals were
converted to PNG (content-preserving) into holdout_images/.
"""

DEMO = "/Users/willeychen/Desktop/mama-helper/demo_image"
CONV = "holdout_images"   # relative to this dir

HOLDOUT = [
    # utility (electric / water / gas / trash / telecom)
    ("Water_Bill3",              CONV, "Water_Bill3.png",              "utility"),
    ("water_bill",               CONV, "water_bill.png",               "utility"),
    ("waste_managment",          CONV, "waste_managment.png",          "utility"),
    ("att_bill",                 CONV, "att_bill.png",                 "utility"),
    # hospital / medical
    ("UCLA_Health_Bill",         DEMO, "UCLA_Health_Bill.png",         "medical"),
    ("UCLA_Health_Bill2",        DEMO, "UCLA_Health_Bill2.png",        "medical"),
    ("Eye_care-invoice",         CONV, "Eye_care-invoice.png",         "medical"),
    # insurance
    ("Progressive_Insurance_Bill", DEMO, "Progressive_Insurance_Bill.jpg", "insurance"),
    ("Penny_Insurance_Bill",     DEMO, "Penny_Insurance_Bill.png",     "insurance"),
    ("State_Farm_Insurance_Card", DEMO, "State_Farm_Insurance_Card.jpg", "insurance"),
    ("Coverage_Care_Insurance_Card", DEMO, "Coverage_Care_Insurance_Card.png", "insurance"),
    ("State_Farm_Insurance",     CONV, "State_Farm_Insurance.png",     "insurance"),
    ("statefarm_bill",           CONV, "statefarm_bill.png",           "insurance"),
    ("aaa-policy_renew",         DEMO, "aaa-policy_renew.jpg",         "insurance"),
    # DMV
    ("DMV_registration_late_fee", CONV, "DMV_registration_late_fee.png", "dmv"),
    ("ca-dmv-registration-fee",  CONV, "ca-dmv-registration-fee.png",  "dmv"),
    # Medicare
    ("Medicare_Notice_PartB",    DEMO, "Medicare_Notice_PartB.png",    "medicare"),
    ("Medicare_Notice_of_Denial", DEMO, "Medicare_Notice_of_Denial.png", "medicare"),
    ("Medixare_Premium_Bill",    DEMO, "Medixare_Premium_Bill.png",    "medicare"),
    # bank
    ("Bank_Bill_Example",        DEMO, "Bank_Bill_Example.jpg",        "bank"),
    ("EastWest_Bank_Form",       DEMO, "EastWest_Bank_Form.png",       "bank"),
    ("EastWest_Bank_Bill",       CONV, "EastWest_Bank_Bill.png",       "bank"),
    ("Chase_Bank_Bill_Example",  CONV, "Chase_Bank_Bill_Example.png",  "bank"),
    ("Chase_Bank_Bill_Example2", CONV, "Chase_Bank_Bill_Example2.png", "bank"),
    ("First_Bank_Bill",          CONV, "First_Bank_Bill.png",          "bank"),
    # HOA
    ("HOA1",                     DEMO, "HOA1.png",                     "hoa"),
    ("HOA2",                     DEMO, "HOA2.png",                     "hoa"),
    ("HOA3",                     DEMO, "HOA3.png",                     "hoa"),
    ("HOA4",                     CONV, "HOA4.png",                     "hoa"),
    # general invoice / letter
    ("aws_invoice",              DEMO, "aws_invoice.png",              "general"),
]
