"""
orqestra_50.py — Orqestra Golden Seed Dataset
===============================================
50-row pristine calibration set for DSPy NLI logic engine compilation.
Teaches the model to distinguish Contradiction / Neutral / Entailment
across five enterprise domains using hard factual assertions only.

Distribution Matrix:
  Healthcare (Primary):     17 examples  (7C / 7N / 3E)
  Finance (Secondary):      12 examples  (5C / 5N / 2E)
  Legal / Compliance:        7 examples  (3C / 3N / 1E)
  HR / Corporate Policy:     7 examples  (3C / 3N / 1E)
  DevOps / Cybersecurity:    7 examples  (3C / 3N / 1E)
  ─────────────────────────────────────────────────────
  TOTAL:                    50 examples (21C / 21N / 8E)

Usage:
  from orqestra_50 import ORQESTRA_50
  trainset = ORQESTRA_50
"""

import dspy

train_set = [

    # =========================================================================
    # DOMAIN 1: HEALTHCARE (Primary)  —  7 Contradictions
    # =========================================================================

    # HC-C1: eGFR / Metformin discontinuation threshold conflict
    dspy.Example(
        claim_a="Metformin is contraindicated when eGFR falls below 45 mL/min/1.73m².",
        claim_b="Metformin may be continued at a reduced dose until eGFR drops below 30 mL/min/1.73m².",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C2: HbA1c threshold for endocrinology referral
    dspy.Example(
        claim_a="Patients on basal insulin with HbA1c above 9.0% must be referred to endocrinology within 30 days.",
        claim_b="Endocrinology referral for insulin-managed patients is indicated only when HbA1c exceeds 10.0% on two consecutive measurements.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C3: Post-MI cardiac monitoring window before discharge
    dspy.Example(
        claim_a="Post-myocardial infarction patients require 72-hour continuous cardiac monitoring before discharge eligibility.",
        claim_b="Stable post-MI patients with no detected arrhythmia in the first 24 hours may be discharged after a 48-hour observation window.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C4: Acetaminophen daily dose ceiling for hepatic impairment
    dspy.Example(
        claim_a="The maximum daily acetaminophen dose for patients with mild hepatic impairment is 2,000 mg.",
        claim_b="Patients with any degree of hepatic impairment must not exceed 3,000 mg of acetaminophen per 24-hour period.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C5: Uncomplicated UTI antibiotic treatment duration
    dspy.Example(
        claim_a="Uncomplicated urinary tract infections in non-pregnant adults are treated with a 3-day course of trimethoprim-sulfamethoxazole.",
        claim_b="Standard antibiotic therapy for uncomplicated UTI requires a minimum 7-day treatment course.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C6: Abnormal mammogram diagnostic follow-up window
    dspy.Example(
        claim_a="An abnormal mammogram result requires diagnostic imaging follow-up within 14 days.",
        claim_b="Patients with BI-RADS 4 findings on screening mammogram must complete follow-up imaging within 30 days of notification.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-C7: GLP-1 agonist BMI eligibility threshold
    dspy.Example(
        claim_a="GLP-1 receptor agonist therapy is indicated for patients with BMI ≥ 30 kg/m².",
        claim_b="GLP-1 agonist prescriptions require a documented BMI of 35 kg/m² or greater prior to authorization.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 1: HEALTHCARE (Primary)  —  7 Neutrals
    # =========================================================================

    # HC-N1: Same-day ambulatory discharge vs. general post-surgical hold
    dspy.Example(
        claim_a="Post-surgical patients must complete a minimum 24-hour in-hospital observation period before discharge.",
        claim_b="Patients undergoing same-day ambulatory procedures classified as ASA Class I or II may be discharged within 6 hours of procedure completion if all vital sign criteria are met.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N2: Penicillin-allergy antibiotic substitution for cardiac surgery
    dspy.Example(
        claim_a="Antibiotic prophylaxis with cefazolin 2g IV is mandatory for all patients undergoing cardiac valve replacement surgery.",
        claim_b="Patients with a documented penicillin or cephalosporin allergy presenting for cardiac valve surgery must receive clindamycin 600 mg IV as the prophylactic antibiotic substitution.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N3: HbA1c monitoring interval reduced for well-controlled patients
    dspy.Example(
        claim_a="All Type 2 diabetic patients must have HbA1c measured every 90 days.",
        claim_b="Patients with well-controlled Type 2 diabetes, defined as two consecutive HbA1c readings below 7.0%, require HbA1c measurement every 180 days.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N4: Emergency MRI exemption from prior authorization
    dspy.Example(
        claim_a="Prior authorization is required before ordering an MRI for musculoskeletal complaints.",
        claim_b="MRI orders for suspected acute spinal cord compression must be placed immediately without prior authorization and completed within 2 hours of the clinical decision.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N5: Accelerated follow-up for post-hypoglycemic patients
    dspy.Example(
        claim_a="The standard post-discharge follow-up window for Type 2 diabetes patients is 4 weeks.",
        claim_b="Patients discharged following a hypoglycemic episode that required IV dextrose administration must schedule follow-up within 72 hours of discharge.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N6: Extended controlled substance supply for palliative care
    dspy.Example(
        claim_a="Controlled substances must be prescribed in 30-day supply increments.",
        claim_b="Patients enrolled in a certified palliative care or hospice program may receive controlled substance prescriptions in 90-day supplies if the treating physician provides written certification.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-N7: Emergency exception to informed consent
    dspy.Example(
        claim_a="Informed consent must be obtained from the patient before any surgical procedure is initiated.",
        claim_b="In cases of life-threatening emergencies where the patient is incapacitated and no surrogate is available, surgical intervention may proceed without explicit informed consent under the emergency exception doctrine.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 1: HEALTHCARE (Primary)  —  3 Entailments
    # =========================================================================

    # HC-E1: Baseline renal function = creatinine + eGFR measurement
    dspy.Example(
        claim_a="Renal function must be assessed before initiating nephrotoxic drug therapy.",
        claim_b="A baseline serum creatinine and calculated eGFR measurement is required prior to prescribing any drug with a documented nephrotoxic profile.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-E2: 8 hours NPO = 480 minutes
    dspy.Example(
        claim_a="Patients must be NPO for 8 hours prior to the administration of general anesthesia.",
        claim_b="No food or liquid intake is permitted in the 480 minutes preceding the induction of general anesthetic agents.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # HC-E3: Elevated troponin T → same-day cardiology consult (explicit values both sides)
    dspy.Example(
        claim_a="A troponin T result above 0.04 ng/mL must trigger an immediate cardiology consult.",
        claim_b="Cardiac biomarker testing showing troponin T greater than 0.04 ng/mL mandates same-day cardiology evaluation.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 2: FINANCE (Secondary)  —  5 Contradictions
    # =========================================================================

    # FIN-C1: Wire transfer processing timeline conflict (same-day vs. 3-day hold)
    dspy.Example(
        claim_a="Cross-border wire transfers exceeding $10,000 require same-day SWIFT confirmation filing.",
        claim_b="International wire transactions above $10,000 are subject to a 3-business-day compliance review hold before processing proceeds.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-C2: Margin account minimum equity ratio conflict — same condition, different thresholds
    dspy.Example(
        claim_a="Margin accounts must maintain a minimum equity ratio of 25% at all times.",
        claim_b="Margin accounts must maintain a minimum equity ratio of 30% at all times.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-C3: Mortgage prepayment threshold conflict (20% vs. 25%)
    dspy.Example(
        claim_a="Fixed-rate mortgage early repayment penalties apply to any payment exceeding 20% of the outstanding principal in a single calendar year.",
        claim_b="Borrowers may prepay up to 25% of the original mortgage principal annually without incurring early repayment charges.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-C4: Credit limit approval authority conflict ($50K vs. $75K single-officer)
    dspy.Example(
        claim_a="Customer credit limit increases above $50,000 require approval from two senior credit officers.",
        claim_b="Credit line expansions up to $75,000 are authorized by a single credit officer with the appropriate risk tier designation.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-C5: SAR filing deadline conflict (24 hours vs. 72 hours)
    dspy.Example(
        claim_a="Suspicious transaction reports must be filed within 24 hours of initial detection.",
        claim_b="AML compliance officers have 72 hours to file suspicious activity reports after a transaction has been formally flagged.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 2: FINANCE (Secondary)  —  5 Neutrals
    # =========================================================================

    # FIN-N1: Youth Investor Program minimum deposit exception
    dspy.Example(
        claim_a="All retail investment accounts require a minimum opening deposit of $1,000.",
        claim_b="Accounts established under the Youth Investor Program for clients under 18 years of age may be opened with a minimum deposit of $100.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-N2: Large-loan daily compounding exception
    dspy.Example(
        claim_a="Interest on personal loans is compounded monthly.",
        claim_b="Unless otherwise specified in the executed loan agreement, interest on loans exceeding $500,000 in principal is compounded daily.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-N3: SEPA wire transfer fee exception
    dspy.Example(
        claim_a="Wire transfers to international accounts are subject to a flat $45 processing fee.",
        claim_b="Wire transfers to accounts held within SEPA-member countries are processed at a flat fee of $12 under the EU low-cost remittance framework.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-N4: Drift-triggered rebalancing exception to quarterly schedule
    dspy.Example(
        claim_a="Portfolio rebalancing triggers are evaluated on a fixed quarterly basis.",
        claim_b="Accounts with a declared risk tolerance below 3 on a 10-point scale trigger a mandatory rebalancing review if any single asset class deviates more than 5% from its target allocation, regardless of the quarterly schedule.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-N5: Extended-hours trading platform exception
    dspy.Example(
        claim_a="Equity trades placed after 3:30 PM Eastern Time are executed at the next trading day's opening price.",
        claim_b="Pre-authorized after-hours trades submitted through the extended trading session platform between 4:00 PM and 8:00 PM Eastern Time are executed at the available after-hours market price.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 2: FINANCE (Secondary)  —  2 Entailments
    # =========================================================================

    # FIN-E1: 150 basis points = 1.5%
    dspy.Example(
        claim_a="The platform charges a flat processing fee of 150 basis points on all cross-border wire transfers.",
        claim_b="International wire transfers incur a transactional fee of 1.5% of the transferred principal.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # FIN-E2: 3% of $200,000 = $6,000
    dspy.Example(
        claim_a="Loan origination fees are capped at 3% of the total loan value.",
        claim_b="For a $200,000 mortgage, the maximum permissible origination fee is $6,000.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 3: LEGAL / COMPLIANCE  —  3 Contradictions
    # =========================================================================

    # LC-C1: DSAR response window conflict (30 days vs. 45 days)
    dspy.Example(
        claim_a="Data subject access requests must be fulfilled within 30 calendar days of receipt.",
        claim_b="GDPR Article 15 access requests are subject to a 45-day response window from the date of verified receipt.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # LC-C2: NDA termination notice period conflict — same condition, different required notice windows
    dspy.Example(
        claim_a="Non-disclosure agreements require a minimum written notice period of 14 days before termination takes effect.",
        claim_b="Non-disclosure agreements may be terminated by either party with 7 days written notice.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # LC-C3: Human review requirement for AI decisions vs. low-impact exemption
    dspy.Example(
        claim_a="All AI-generated outputs used in customer-facing decisions must include a mandatory human review step before delivery.",
        claim_b="Automated AI decision systems operating below a $500 customer impact threshold are exempt from mandatory human review requirements.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 3: LEGAL / COMPLIANCE  —  3 Neutrals
    # =========================================================================

    # LC-N1: Pre-approved MSA contracts exempt from legal countersignature
    dspy.Example(
        claim_a="All vendor contracts exceeding $100,000 in annual value require legal department countersignature.",
        claim_b="Vendor contracts negotiated under pre-approved master service agreements with existing suppliers are exempt from legal countersignature requirements regardless of contract value.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # LC-N2: Top Secret documents have stronger encryption requirements than baseline
    dspy.Example(
        claim_a="Confidential documents must be stored in encrypted format at rest.",
        claim_b="Documents classified as Top Secret require AES-256 encryption at rest and may not be stored on any cloud infrastructure without explicit CISO approval.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # LC-N3: New hire compliance training exception to annual cycle
    dspy.Example(
        claim_a="Employees must complete annual compliance training within the first quarter of each calendar year.",
        claim_b="New hires must complete the full compliance training curriculum within 30 days of their start date, regardless of the standard annual training cycle.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 3: LEGAL / COMPLIANCE  —  1 Entailment
    # =========================================================================

    # LC-E1: 24 months = 2 years for data retention
    dspy.Example(
        claim_a="Personal data may not be retained beyond 24 months following the termination of a customer relationship.",
        claim_b="Customer records must be permanently deleted no later than 2 years after the end of the service contract.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 4: HR / CORPORATE POLICY  —  3 Contradictions
    # =========================================================================

    # HR-C1: Maternity leave duration conflict (12 weeks vs. 8 weeks)
    dspy.Example(
        claim_a="Standard maternity leave entitlement is 12 weeks of fully paid leave for all full-time employees.",
        claim_b="Parental leave for primary caregivers is capped at 8 weeks of paid time off per birth or adoption event.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HR-C2: PIP remediation period before termination (60 days vs. 30 days notice)
    dspy.Example(
        claim_a="Performance improvement plans require a minimum 60-day active remediation period before termination proceedings may begin.",
        claim_b="Employees on an active PIP may be terminated with 30 days notice if two consecutive weekly milestone check-ins are missed.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # HR-C3: Remote work approval requirement vs. Remote-Primary exemption
    dspy.Example(
        claim_a="Remote work arrangements require manager approval for any period exceeding 5 consecutive business days.",
        claim_b="Employees classified as Remote-Primary in the HR system are not required to seek manager approval for work-from-home arrangements of any duration.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 4: HR / CORPORATE POLICY  —  3 Neutrals
    # =========================================================================

    # HR-N1: First 90-day new hire exemption from annual training requirement
    dspy.Example(
        claim_a="All employees must complete 40 hours of professional development training per calendar year.",
        claim_b="Employees in their first 90 days of employment are exempt from the annual 40-hour professional development requirement.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HR-N2: Sales team pre-coded client travel expense exception
    dspy.Example(
        claim_a="Travel expense reimbursements above $500 require VP-level approval.",
        claim_b="Sales team members with active enterprise accounts may submit travel expense reimbursements up to $2,000 for client-facing activities without VP approval, provided the expense is pre-coded to a valid client account number.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # HR-N3: Senior Director extended notice period on top of standard 2-week policy
    dspy.Example(
        claim_a="All employees must provide a minimum of 2 weeks written notice before voluntary resignation.",
        claim_b="Employees at Senior Director level and above must provide a minimum of 4 weeks written notice of voluntary resignation.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 4: HR / CORPORATE POLICY  —  1 Entailment
    # =========================================================================

    # HR-E1: 1.25 days/month × 12 months = 15 days/year — mathematically guaranteed, no work-week assumption
    dspy.Example(
        claim_a="Full-time employees accrue 1.25 vacation days per month of continuous service.",
        claim_b="Full-time employees accumulate 15 days of paid vacation per calendar year.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 5: DEVOPS / CYBERSECURITY  —  3 Contradictions
    # =========================================================================

    # DO-C1: Production merge approval requirement vs. hotfix bypass
    dspy.Example(
        claim_a="All code deployments to production require a minimum of 2 senior engineer peer reviews prior to merge approval.",
        claim_b="Hotfix patches targeting critical production infrastructure may bypass senior review loops and merge automatically with 1 junior engineer sign-off.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # DO-C2: S3 versioning policy — same entity (all S3 buckets), mutually exclusive boolean states
    dspy.Example(
        claim_a="Object versioning must be enabled on all AWS S3 buckets to allow recovery from accidental deletion.",
        claim_b="Object versioning must be disabled on all AWS S3 buckets to prevent unbounded storage cost accumulation.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # DO-C3: TLS minimum version conflict (1.2 required vs. 1.0 permitted internally)
    dspy.Example(
        claim_a="TLS 1.2 is the minimum required encryption protocol for all API endpoints without exception.",
        claim_b="Internal service-to-service API calls within the private VPC may use TLS 1.0 to maintain backward compatibility with legacy microservices.",
        logical_relationship="Contradiction"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 5: DEVOPS / CYBERSECURITY  —  3 Neutrals
    # =========================================================================

    # DO-N1: Certificate-based service account exemption from 90-day password rotation
    dspy.Example(
        claim_a="Passwords must be rotated every 90 days for all system accounts.",
        claim_b="Service accounts used exclusively for automated CI/CD pipeline execution are exempt from the 90-day rotation policy if they authenticate exclusively via certificate-based authentication.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # DO-N2: Financial DB 7-year retention supersedes 30-day minimum
    dspy.Example(
        claim_a="All database backups must be retained for a minimum of 30 days.",
        claim_b="Financial transaction databases are subject to a minimum backup retention period of 7 years to comply with SEC Rule 17a-4.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # DO-N3: Registered corporate IP read-only dashboard MFA exemption
    dspy.Example(
        claim_a="Multi-factor authentication is required for all employee access to production systems.",
        claim_b="Read-only operations monitoring dashboards accessed from a registered corporate IP address within the internal network are exempt from the MFA requirement for operations staff.",
        logical_relationship="Neutral"
    ).with_inputs('claim_a', 'claim_b'),

    # =========================================================================
    # DOMAIN 5: DEVOPS / CYBERSECURITY  —  1 Entailment
    # =========================================================================

    # DO-E1: 72 hours = 3 days for critical CVE patching
    dspy.Example(
        claim_a="Critical security vulnerabilities must be patched within 72 hours of public disclosure.",
        claim_b="System patches for vulnerabilities classified as CVSS score 9.0 or above must be deployed within 3 days of the public CVE publication date.",
        logical_relationship="Entailment"
    ).with_inputs('claim_a', 'claim_b'),

]


# =============================================================================
# Validation helpers
# =============================================================================

def validate_distribution(dataset=train_set):
    """
    Verify the dataset matches the target distribution matrix.
    Raises AssertionError if any count is wrong.
    """
    from collections import Counter
    labels = [ex.logical_relationship for ex in dataset]
    counts = Counter(labels)

    assert len(dataset) == 50,          f"Expected 50 examples, got {len(dataset)}"
    assert counts["Contradiction"] == 21, f"Expected 21 Contradictions, got {counts['Contradiction']}"
    assert counts["Neutral"] == 21,      f"Expected 21 Neutrals, got {counts['Neutral']}"
    assert counts["Entailment"] == 8,    f"Expected 8 Entailments, got {counts['Entailment']}"

    print("✅ Distribution validated: 21 Contradiction / 21 Neutral / 8 Entailment")
    return counts


def preview(dataset=train_set, n=5):
    """Print the first n examples for quick inspection."""
    for i, ex in enumerate(dataset[:n]):
        print(f"\n[{i+1}] {ex.logical_relationship}")
        print(f"  A: {ex.claim_a}")
        print(f"  B: {ex.claim_b}")


if __name__ == "__main__":
    validate_distribution()
    preview()
