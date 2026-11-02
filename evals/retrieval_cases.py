# Retrieval test questions. They check the SEARCH step only (no LLM): does the fact that answers the
# question appear in the chunks the search returns?
#
# Each case is (id, question, needle). The needle is a short exact phrase from the policy PDFs that the
# right chunk contains. Whitespace is ignored when matching. Questions are written the way customers ask,
# often with different words than the policy uses.

RETRIEVAL_CASES = [
    ("min_balance", "What is the minimum balance for a savings account?", "Metro/Urban: Rs. 10,000"),
    ("min_balance_penalty", "What happens if I don't keep enough money in my account?", "Up to 25% Rs. 150"),
    ("fd_senior_1y", "What is the FD interest rate for senior citizens for 1 year?", "1 year to less than 15 months"),
    ("fd_premature", "Is there a penalty if I break my fixed deposit early?", "0.50% below the applicable rate"),
    ("fd_tds", "When does the bank cut TDS on my FD interest?", "exceeds Rs. 40,000"),
    ("fd_min_amount", "What is the smallest amount I can put in an FD?", "minimum amount for a Fixed Deposit is Rs. 5,000"),
    ("tax_saver", "How long is the lock-in on a tax saving FD?", "lock-in period of 5 years"),
    ("rd_minimum", "What is the minimum monthly instalment for a recurring deposit?", "minimum monthly instalment is Rs. 500"),
    ("fd_overdraft", "Can I take a loan against my fixed deposit?", "up to 90% of the deposit value"),
    ("saturday", "Are branches open on Saturday?", "9:30 AM to 1:00 PM"),
    ("helpline_hours", "Is the phone helpline available at night?", "24x7 for card blocking and fraud"),
    ("atm_limit", "How much cash can I withdraw from an ATM with a classic debit card?", "ATM cash withdrawal Rs. 25,000 Rs. 1,00,000"),
    ("contactless", "Do I need a PIN for contactless payments?", "Contactless transactions above Rs. 5,000 require PIN entry"),
    ("block_card", "How do I block my card if it is stolen?", "Blocking is permanent and cannot be reversed"),
    ("freeze_card", "Can I temporarily freeze my card if I misplaced it?", "temporarily frozen through the app"),
    ("replacement_fee", "How much does a replacement card cost?", "replacement fee of Rs. 200"),
    ("international_fee", "What are the charges for using my card abroad?", "foreign currency mark-up fee of 3.5%"),
    ("cc_late_fee", "What is the late payment fee on my credit card?", "Late payment (Rs. 5,001 to Rs. 25,000)"),
    ("cc_interest", "How much interest do I pay if I don't clear the whole credit card bill?", "3.5% per month"),
    ("reward_value", "How much is a reward point worth?", "1 point = Rs. 0.25"),
    ("liability_3days", "Will I get a refund if I report an unauthorised transaction quickly?", "within 3 working days of receiving the communication"),
    ("upi_failed", "My UPI payment failed but money was deducted, when will I get it back?", "beneficiary not credited"),
    ("chargeback", "How long does a card chargeback take?", "merchant's bank has up to 45 days"),
    ("bank_never_asks", "Will the bank ever ask for my OTP over the phone?", "will never ask customers for their full card number"),
    ("human_cases", "Which fraud cases are handled by a human and not by the chatbot?", "suspected account takeover"),
    ("grievance_levels", "How do I escalate a complaint that the branch did not resolve?", "Grievance Redressal Officer"),
    ("ombudsman_deadline", "By when can I go to the Banking Ombudsman?", "within one year of receiving the Bank's reply"),
    ("dormant", "When does my account become dormant?", "no customer-induced transactions for 12 months"),
    ("nri", "Can an NRI open this savings account?", "Non-resident Indians (NRIs) are not eligible"),
    ("kyc_docs", "Which documents do I need to open an account?", "PAN card (mandatory)"),
    ("salary_conversion", "What if my salary stops coming to my salary account?", "three consecutive months"),
    ("closure_charge", "Is there a charge for closing my savings account?", "closure charge of Rs. 500"),
    ("locker", "How much does a locker cost per year?", "Rs. 1,500 (small, rural)"),
    ("cheque_return", "What is the penalty if my cheque bounces?", "Rs. 500 per instance"),
    ("home_loan", "Do you give home loans?", "Home loans, personal loans"),
]
