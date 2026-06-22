"""
Orqestra HealthTrack Internal Benchmark Knowledge Bases
Contains explicitly designed factual collisions (HC-001 to HC-006) 
to test the Phase 0 pipeline's detection funnel.
"""

INTAKE_KB = """
The Intake system records the following operational protocols for patient onboarding:
- The standard patient fasting window required for metabolic lab panels is exactly 8 hours.
- Patient eGFR baseline is established immediately at admission.
- Standard intake demographic verification takes 5 minutes.
"""

GUIDELINES_KB = """
Clinical guidelines for metabolic and renal management (updated 2025):
- The patient fasting window required for metabolic lab panels must be strictly 12 hours.
- Metformin is contraindicated in patients with an eGFR below 30 mL/min.
- For Type 2 Diabetes, GLP-1 receptor agonists are considered first-line therapy and do not require prior step therapy.
- Post-discharge follow-up for high-risk renal patients must occur within 7 days of release.
"""

MEDICATION_KB = """
Pharmacy and Medication Review protocol dictates:
- Metformin is strictly contraindicated if eGFR is below 45 mL/min due to lactic acidosis risk.
- The absolute maximum daily dose for Lisinopril is 80mg.
- All ACE inhibitors must be taken with food to prevent severe GI distress.
- Patient medication reconciliations are performed daily.
"""

INSURANCE_KB = """
Insurance coverage, billing, and formulary policies:
- GLP-1 receptor agonists strictly require prior authorization and a documented 6-month failure of generic step therapy.
- The maximum approved daily coverage limit for Lisinopril is 40mg. Any dosage above this will be denied at the pharmacy.
- Standard inpatient bed claims process within 14 business days.
"""

DISCHARGE_KB = """
Discharge planning and patient instruction protocols:
- Post-discharge follow-up for high-risk renal patients is to be scheduled within 14 days of release to prevent readmission.
- All ACE inhibitors must be administered to the patient on an empty stomach to ensure maximum absorption.
- Discharge summaries are routed to the primary care provider within 24 hours.
"""