import os
import sys
import click
import re
from datetime import datetime, timezone

# Setup explicit project path resolutions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from output_collector import SystemConfig
from claim_extractor import extract_claims
from embedder import embed_claims
from contradiction_detector import run_detection
from explainer import explain_batch
from reporter import generate_cli_report, generate_html_report
from main import execute_coherence_pipeline

# Import our complete reference data structures
from healthtrack.scenarios import DIABETES_RENAL_SCENARIO
from healthtrack.knowledge_bases import INTAKE_KB, GUIDELINES_KB, MEDICATION_KB, INSURANCE_KB, DISCHARGE_KB

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

console = Console()

def run_healthtrack_benchmark(api_key: str, output_html: str, sim_threshold: float) -> int:
    """
    Executes the internal benchmark suite (F8.1 and Gate Condition).
    Maps historical agent contexts, logs pipeline execution metrics, and verifies 6/6 collisions.
    """
    # Fix: Replaced deprecated utcnow() with timezone-aware UTC
    benchmark_start = datetime.now(timezone.utc)
    console.print("\n[bold purple]🏁 Booting HealthTrack Internal Verification Benchmark Suite[/bold purple]")
    console.print("-----------------------------------------------------------------")
    
    # Emulate the 5 system environments using our verified knowledge base variables
    agents_kb = {
        "IntakeAgent": INTAKE_KB,
        "ClinicalGuidelinesAgent": GUIDELINES_KB,
        "MedicationReviewAgent": MEDICATION_KB,
        "InsuranceCoverageAgent": INSURANCE_KB,
        "DischargeAgent": DISCHARGE_KB
    }

    # Configuration footprints for operational tasks
    base_config = SystemConfig(name="BenchmarkRunner", provider="openai", api_key=api_key, model="gpt-4o-mini")

    all_extracted_claims = {}
    
    # 1. Processing Step: Sequential claim extraction with progress indicators
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[purple]Decomposing agent knowledge bases to atomic claims...", total=len(agents_kb))
        
        for agent_name, kb_text in agents_kb.items():
            progress.update(task, description=f"[purple]Processing Factual Sub-states for: {agent_name}")
            raw_claims = extract_claims(kb_text, base_config)
            embedded_claims = embed_claims(raw_claims, base_config)
            all_extracted_claims[agent_name] = embedded_claims
            progress.advance(task)

    # Cross-reference pairs specified by the multi-agent system layout
    targeted_cross_checks = [
        ("ClinicalGuidelinesAgent", "MedicationReviewAgent", "HC-001"),
        ("ClinicalGuidelinesAgent", "DischargeAgent", "HC-002"),
        ("InsuranceCoverageAgent", "ClinicalGuidelinesAgent", "HC-003"),
        ("MedicationReviewAgent", "DischargeAgent", "HC-004"),
        ("IntakeAgent", "ClinicalGuidelinesAgent", "HC-005"),
        ("InsuranceCoverageAgent", "MedicationReviewAgent", "HC-006"),
    ]

    detected_contradiction_ids = set()
    global_contradictions = []

    # 2. Processing Step: Matrix cross-referencing loop
    console.print("\n[bold]🔄 Analyzing Cross-Agent Structural Mismatch Surfaces...[/bold]")
    for sys_a, sys_b, expected_id in targeted_cross_checks:
        claims_a = all_extracted_claims.get(sys_a, [])
        claims_b = all_extracted_claims.get(sys_b, [])
        
        collisions = run_detection(claims_a, claims_b, base_config, sys_a, sys_b, similarity_threshold=sim_threshold)
        
        if collisions:
            detected_contradiction_ids.add(expected_id)
            global_contradictions.extend(collisions)
            console.print(f" ✅ [bold green]MATCHED MATRIX POOL FOR {expected_id}:[/bold green] Factual anomaly located between {sys_a} and {sys_b}.")
        else:
            console.print(f" ❌ [bold red]MISSED CORRELATION LAYER FOR {expected_id}:[/bold red] No collision caught between {sys_a} and {sys_b}.")

    # 3. Processing Step: Compile explanation payloads for confirmed collisions
    console.print(f"\n[bold]🧠 Triggering Resolution Agents across {len(global_contradictions)} confirmed anomalies...[/bold]")
    explanations = explain_batch(global_contradictions, base_config)

    # Flush report files
    generate_cli_report(global_contradictions, explanations, "AgentGroupA", "AgentGroupB")
    generate_html_report(global_contradictions, explanations, "AgentGroupA", "AgentGroupB", output_html)

    # 4. Verification Check: Confirm gate criteria satisfaction
    total_detected = len(detected_contradiction_ids)
    console.print("\n" + "="*65)
    if total_detected == 6:
        console.print("[bold white on green]  Gate: PASS — all 6/6 contradictions detected seamlessly  [/bold white on green]")
        status_code = 0
    else:
        console.print(f"[bold white on red]  Gate: FAIL — captured only {total_detected}/6 targets  [/bold white on red]")
        status_code = 1
    console.print("="*65 + "\n")
    
    return status_code

def sanitize_api_key(raw_key: str) -> str:
    """Removes accidental Mac Option-keystrokes (like ß) and hidden whitespace."""
    if not raw_key:
        return raw_key
    # Strip non-ASCII characters that crash httpx headers
    cleaned = raw_key.encode("ascii", "ignore").decode("ascii")
    # Remove all whitespace
    cleaned = re.sub(r'\s+', '', cleaned)
    return cleaned

@click.command()
@click.option("--mode", type=click.Choice(["orqestra", "benchmark"]), required=True, help="orqestra runs active live pipeline; benchmark hits internal verification gates.")
@click.option("--probe-domain", default="healthcare", help="Target domain file from probes folder.")
@click.option("--system-a-name", default="SystemA")
@click.option("--system-a-key", envvar="OPENAI_API_KEY", help="API credentials string. Defaults to environment variable.")
@click.option("--system-a-model", default="gpt-4o-mini")
@click.option("--system-b-name", default="SystemB")
@click.option("--system-b-key", envvar="OPENAI_API_KEY")
@click.option("--system-b-model", default="gpt-4o-mini")
@click.option("--output-html", default="report.html", help="Path to write the standalone HTML output.")
@click.option("--similarity-threshold", default=0.60, help="Lower-bound similarity pre-filter parameter.")
def run_cli(mode, probe_domain, system_a_name, system_a_key, system_a_model, system_b_name, system_b_key, system_b_model, output_html, similarity_threshold):
    """
    Orqestra CLI Orchestrator Engine. Handles live environment traffic mapping and quality assurance regression tests.
    """
    system_a_key = sanitize_api_key(system_a_key)
    system_b_key = sanitize_api_key(system_b_key)

    if not system_a_key:
        console.print("[bold red]API Error:[/bold red] Missing valid OpenAI API token. Set OPENAI_API_KEY environment variable or supply inline flags.")
        sys.exit(1)

    if mode == "benchmark":
        exit_code = run_healthtrack_benchmark(system_a_key, output_html, similarity_threshold)
        sys.exit(exit_code)
        
    elif mode == "orqestra":
        sys_a = SystemConfig(name=system_a_name, provider="openai", api_key=system_a_key, model=system_a_model)
        sys_b = SystemConfig(name=system_b_name, provider="openai", api_key=system_b_key, model=system_b_model)
        
        try:
            execute_coherence_pipeline(
                probe_domain=probe_domain,
                sys_a_config=sys_a,
                sys_b_config=sys_b,
                output_html_path=output_html,
                similarity_threshold=similarity_threshold
            )
        except Exception as err:
            console.print(f"[bold red]Critical Pipeline Panic Error Execution Uncaught:[/bold red] {err}")
            sys.exit(1)

if __name__ == "__main__":
    run_cli()