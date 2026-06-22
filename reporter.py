import os
import logging
from typing import List, Dict, Any
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED

from contradiction_detector import Contradiction
from explainer import Explanation

logger = logging.getLogger(__name__)
console = Console()

# ==========================================
# SORTING & STYLING HELPERS
# ==========================================

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

def severity_sort_key(item: Any) -> int:
    """Helper to rank objects by their severity tier."""
    if hasattr(item, 'severity'):
        sev = item.severity.lower().strip()
    elif hasattr(item, 'risk_level'):
        sev = item.risk_level.lower().strip()
    else:
        sev = "low"
    return SEVERITY_ORDER.get(sev, 4)

def severity_sort(items: List[Any]) -> List[Any]:
    """Sorts items in priority order: critical -> high -> medium -> low."""
    return sorted(items, key=severity_sort_key)

def severity_color(severity: str) -> str:
    """Maps custom text markers to exact Rich coloring tokens."""
    sev = severity.lower().strip()
    if sev == "critical": return "bold red"
    if sev == "high":     return "bold orange3"
    if sev == "medium":   return "bold yellow"
    return "bold green"

def get_severity_emoji(severity: str) -> str:
    """Returns a visual tag for standard CLI representations."""
    sev = severity.lower().strip()
    if sev == "critical": return "🔴"
    if sev == "high":     return "🟠"
    if sev == "medium":   return "🟡"
    return "🟢"

# ==========================================
# PUBLIC REPORTING FUNCTIONS
# ==========================================

def generate_cost_summary(explanations: List[Explanation]) -> str:
    """
    Synthesizes the financial impact strings to provide an overview metric.
    Extracts ranges safely to prevent programmatic description mismatching.
    """
    if not explanations:
        return "$0"
    
    # Check if there's a clinical or critical legal risk to scale up reporting metrics
    has_critical = any(exp.risk_level.lower() == "critical" for exp in explanations)
    has_high = any(exp.risk_level.lower() == "high" for exp in explanations)
    
    if has_critical and any("clinical" in exp.system_a_full_output.lower() or "clinical" in exp.why_they_contradict.lower() for exp in explanations):
        return "$300,000–$500,000 (Malpractice Exposure Risk)"
    elif has_critical:
        return "$50,000–$250,000 (Regulatory Fine Baseline)"
    elif has_high:
        return "$1,000–$15,000 (Operational/Customer Disruption)"
        
    return "$150–$1,000"


def generate_cli_report(
    contradictions: List[Contradiction],
    explanations: List[Explanation],
    sys_a_name: str,
    sys_b_name: str
) -> None:
    """
    Renders an interactive Terminal Dashboard showing active knowledge divergence.
    """
    total_probes = len(contradictions) # Base count of processed collisions
    total_at_risk = generate_cost_summary(explanations)
    
    # 1. Header Banner
    console.print("\n")
    header_text = Text(f"📊 Orqestra AI Estate Coherence Report | 2 Systems Compared | {total_probes} Contradictions Detected", style="bold white on blue", justify="center")
    console.print(header_text)
    console.print(f"[bold]Total Estimated Financial Risk Base:[/bold] [bold red]{total_at_risk}[/bold red]\n")

    if not contradictions:
        console.print(Panel("[bold green]✅ 100% Coherence Maintained.[/bold green] No cross-system semantic contradictions located across the evaluated probe matrices.", box=ROUNDED))
        return

    # Map explanations by ID for quick structural rendering
    exp_map = {e.contradiction_id: e for e in explanations}
    sorted_contradictions = severity_sort(contradictions)

    # 2. Render Contradiction Logs Categorized sequentially
    for idx, c in enumerate(sorted_contradictions, 1):
        exp = exp_map.get(c.contradiction_id)
        color = severity_color(c.severity)
        emoji = get_severity_emoji(c.severity)
        
        # Panel Title Block
        title = Text()
        title.append(f"{emoji} [{c.severity.upper()}] ", style=color)
        title.append(f"Topic Collision Detected on Entity Hint: '{c.entity_hint}'", style="bold white")
        
        body = Text()
        body.append(f"\n[🖥️  SYSTEM A - {c.system_a}]: ", style="bold cyan")
        body.append(f"\"{c.claim_a.subject} {c.claim_a.predicate} {c.claim_a.obj}\"\n")
        body.append(f"[🖥️  SYSTEM B - {c.system_b}]: ", style="bold magenta")
        body.append(f"\"{c.claim_b.subject} {c.claim_b.predicate} {c.claim_b.obj}\"\n")
        body.append(f"\n[🔍 Cosine Affinity Match Score]: {c.cosine_similarity:.2f} | [🧠 NLI Conflict Confidence]: {c.contradiction_score*100:.1f}%\n", style="italic gray")
        
        if exp:
            body.append(f"\n[📝 Why They Contradict]:\n", style="bold underline white")
            body.append(f"{exp.why_they_contradict}\n")
            
            body.append(f"\n[⚠️  Business Risk Profile]: ", style="bold red")
            body.append(f"{exp.risk_reason}\n")
            
            body.append(f"[⏳ Causal Staleness Trace]: ", style="bold yellow")
            body.append(f"Likely System Out-of-Date: [underline]{exp.likely_stale_system}[/underline]. {exp.staleness_reasoning}\n")
            
            body.append(f"[💰 Calculated Liability Exposure]: ", style="bold green")
            body.append(f"{exp.estimated_cost_if_unresolved}\n")
            
            body.append(f"\n[🛠️  REMEDIATION STRATEGY]:\n", style="bold underline green")
            body.append(f"👉 {exp.recommended_action}\n", style="bold green")

        console.print(Panel(body, title=title, box=ROUNDED, border_style=color))
        console.print("")

    # 3. Summary Statistics Table Breakdown
    table = Table(title="Estate Coherence Metric Summary", box=ROUNDED)
    table.add_column("Severity Tier", justify="left", style="bold")
    table.add_column("Count Logged", justify="right")
    table.add_column("Operational Status", justify="center")

    tiers = ["critical", "high", "medium", "low"]
    for t in tiers:
        count = sum(1 for c in contradictions if c.severity == t)
        status_marker = "🚨 Action Required" if count > 0 else "✨ Healthy"
        table.add_row(t.upper(), str(count), status_marker, style=severity_color(t))

    console.print(table)
    console.print("\n")


def generate_html_report(
    contradictions: List[Contradiction],
    explanations: List[Explanation],
    sys_a_name: str,
    sys_b_name: str,
    output_path: str
) -> str:
    """
    Generates a 100% self-contained, offline-shareable HTML report file.
    Does not depend on external CDNs or network scripts to pass air-gapped environments.
    """
    total_at_risk = generate_cost_summary(explanations)
    exp_map = {e.contradiction_id: e for e in explanations}
    sorted_contradictions = severity_sort(contradictions)
    
    # Counts
    crit_count = sum(1 for c in contradictions if c.severity == "critical")
    high_count = sum(1 for c in contradictions if c.severity == "high")
    med_count = sum(1 for c in contradictions if c.severity == "medium")
    low_count = sum(1 for c in contradictions if c.severity == "low")

    # Inlined raw CSS framework elements to keep output completely offline-ready
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Orqestra Coherence Infrastructure Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ background: #1e3a8a; color: white; padding: 2rem; border-radius: 12px; margin-bottom: 2rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        h1 {{ margin: 0; font-size: 1.85rem; font-weight: 700; }}
        .summary-banner {{ display: flex; gap: 1.5rem; margin-top: 1.5rem; flex-wrap: wrap; }}
        .stat-card {{ background: rgba(255,255,255,0.1); padding: 1rem 1.5rem; border-radius: 8px; flex: 1; min-width: 200px; }}
        .stat-label {{ font-size: 0.85rem; text-transform: uppercase; opacity: 0.8; letter-spacing: 0.05em; }}
        .stat-value {{ font-size: 1.5rem; font-weight: bold; margin-top: 0.25rem; }}
        .at-risk-highlight {{ color: #fecdd3; }}
        
        .grid-summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .pill-box {{ background: white; border: 1px solid #e2e8f0; padding: 1rem; border-radius: 8px; text-align: center; font-weight: bold; box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1); }}
        
        .card {{ background: white; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 1.5rem; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        .card-header {{ padding: 1.25rem 1.5rem; color: white; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }}
        .card-body {{ padding: 1.5rem; }}
        
        .sev-critical {{ background-color: #ef4444; }}
        .sev-high {{ background-color: #f97316; }}
        .sev-medium {{ background-color: #eab308; }}
        .sev-low {{ background-color: #22c55e; }}
        
        .evidence-box {{ background-color: #f1f5f9; border-left: 4px solid #64748b; padding: 1rem; border-radius: 0 8px 8px 0; margin-bottom: 1.25rem; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap; }}
        .system-title {{ font-weight: bold; margin-bottom: 0.25rem; color: #334155; font-family: sans-serif; }}
        
        .section-title {{ font-size: 1rem; font-weight: bold; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.25rem; margin-top: 1.5rem; margin-bottom: 0.75rem; color: #0f172a; text-transform: uppercase; letter-spacing: 0.025em; }}
        .remediation {{ color: #15803d; font-weight: bold; font-size: 1.05rem; padding: 0.5rem 0; }}
        
        details {{ margin-top: 1rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #f8fafc; }}
        summary {{ font-weight: bold; padding: 0.75rem; cursor: pointer; background: #e2e8f0; border-radius: 4px; outline: none; }}
        .details-content {{ padding: 1rem; max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; }}

        @media print {{
            body {{ background: white; color: black; padding: 0; }}
            .card {{ page-break-inside: avoid; box-shadow: none; border: 1px solid #94a3b8; }}
            header {{ background: black; border-radius: 0; box-shadow: none; }}
            details {{ display: block !important; }}
            summary {{ display: none !important; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Orqestra — AI Estate Coherence Analysis</h1>
            <div class="summary-banner">
                <div class="stat-card">
                    <div class="stat-label">Systems Tracked</div>
                    <div class="stat-value">2 Registered Microservices</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active Conflicts Captured</div>
                    <div class="stat-value">{len(contradictions)} Factual Mismatches</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Aggregated Financial Exposure</div>
                    <div class="stat-value at-risk-highlight">{total_at_risk}</div>
                </div>
            </div>
        </header>

        <div class="grid-summary">
            <div class="pill-box" style="border-top: 4px solid #ef4444;">CRITICAL: {crit_count}</div>
            <div class="pill-box" style="border-top: 4px solid #f97316;">HIGH: {high_count}</div>
            <div class="pill-box" style="border-top: 4px solid #eab308;">MEDIUM: {med_count}</div>
            <div class="pill-box" style="border-top: 4px solid #22c55e;">LOW: {low_count}</div>
        </div>
"""

    for c in sorted_contradictions:
        exp = exp_map.get(c.contradiction_id)
        header_class = f"sev-{c.severity.lower()}"
        
        html_content += f"""
        <div class="card">
            <div class="card-header {header_class}">
                <span>⚠️ [{c.severity.upper()}] Entity Context Collision: {c.entity_hint}</span>
                <span>Affinity Match: {c.cosine_similarity:.2f}</span>
            </div>
            <div class="card-body">
                <div class="section-title">Atomic Extracted Claims Matrix</div>
                <div class="system-title">🖥️ {c.system_a} asserted:</div>
                <div class="evidence-box">"{c.claim_a.subject} {c.claim_a.predicate} {c.claim_a.obj}"</div>
                
                <div class="system-title">🖥️ {c.system_b} asserted:</div>
                <div class="evidence-box">"{c.claim_b.subject} {c.claim_b.predicate} {c.claim_b.obj}"</div>
        """
        
        if exp:
            html_content += f"""
                <div class="section-title">Analytical Structural Summary</div>
                <strong>Analytical Diagnosis:</strong> {exp.why_they_contradict}<br><br>
                <strong>Operational Asset Risk:</strong> <span style="color: #ef4444; font-weight: bold;">{exp.risk_reason}</span><br><br>
                <strong>Causal Source Attribution:</strong> Out-of-date baseline targets detected in <u>{exp.likely_stale_system}</u>. {exp.staleness_reasoning}<br><br>
                <strong>Quantified Cost-At-Risk Projection:</strong> <span style="color: #16a34a; font-weight: bold;">{exp.estimated_cost_if_unresolved}</span>
                
                <div class="section-title">Enforced Remediation Directive</div>
                <div class="remediation">🛠️ Action Recommended: {exp.recommended_action}</div>
                
                <div class="section-title">Raw Microservice Raw Evidence Logs</div>
                <details>
                    <summary>View System A Original Context Trace</summary>
                    <div class="details-content">{exp.system_a_full_output}</div>
                </details>
                <details>
                    <summary>View System B Original Context Trace</summary>
                    <div class="details-content">{exp.system_b_full_output}</div>
                </details>
            """
            
        html_content += """
            </div>
        </div>
        """

    html_content += """
    </div>
</body>
</html>
"""

    # Ensure output folders exist before performing flush operations
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(html_content)

    return os.path.abspath(output_path)