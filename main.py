import time
import logging
from typing import List, Dict
from output_collector import SystemConfig, OutputPair, collect_pairs, load_probe_set
from claim_extractor import ExtractedClaim, extract_claims
from embedder import EmbeddedClaim, embed_claims
from contradiction_detector import Contradiction, run_detection
from explainer import Explanation, explain_batch
from reporter import generate_cli_report, generate_html_report

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

logger = logging.getLogger("Orqestra.MainPipeline")
console = Console()

def execute_coherence_pipeline(
    probe_domain: str,
    sys_a_config: SystemConfig,
    sys_b_config: SystemConfig,
    output_html_path: str,
    similarity_threshold: float = 0.60,
    contradiction_threshold: float = 0.70
) -> tuple[List[Contradiction], List[Explanation], float]:
    """
    Executes the unified Orqestra Phase 0 pipeline.
    Tracks precise execution metrics and displays animated progress bars.
    """
    pipeline_start_time = time.perf_counter()
    
    # Track metrics inside an execution registry to map computational complexity
    telemetry: Dict[str, float] = {}

    console.print(f"\n[bold blue]🛫 Initiating Orqestra Pipeline Context for Domain: '{probe_domain}'[/bold blue]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        # Define structural pipeline step tasks
        task_probes = progress.add_task("[cyan]Step 1: Loading Probe Sets...", total=1)
        task_collect = progress.add_task("[cyan]Step 2: Probing Systems (Network API)...", total=1)
        task_extract = progress.add_task("[cyan]Step 3: Decomposing Factual Claims (SPO)...", total=2)
        task_embed = progress.add_task("[cyan]Step 4: Compiling Vector Embeddings...", total=2)
        task_detect = progress.add_task("[cyan]Step 5: Executing Coherence Funnel...", total=1)
        task_explain = progress.add_task("[cyan]Step 6: Running Resolution Agent (GPT-4o)...", total=1)
        task_report = progress.add_task("[cyan]Step 7: Rendering Comprehensive Reports...", total=1)

        # ─── STEP 1: LOAD PROBES ───
        start = time.perf_counter()
        questions = load_probe_set(probe_domain)
        telemetry["step1_load_probes"] = (time.perf_counter() - start) * 1000
        progress.advance(task_probes)

        # ─── STEP 2: COLLECT OUTPUT PAIRS ───
        start = time.perf_counter()
        pairs = collect_pairs(questions, sys_a_config, sys_b_config)
        telemetry["step2_collect_pairs"] = (time.perf_counter() - start) * 1000
        progress.advance(task_collect)

        if not pairs:
            console.print("[yellow]⚠️ Warning: Zero clean response pairs collected. Pipeline exiting open.[/yellow]")
            return [], [], 0.0

        # ─── STEP 3: CLAIM EXTRACTION ───
        start = time.perf_counter()
        claims_system_a: List[ExtractedClaim] = []
        claims_system_b: List[ExtractedClaim] = []

        # Progress sub-allocation for extraction tracking
        progress.update(task_extract, description=f"[cyan]Step 3: Extracting {sys_a_config.name} Factual Claims...")
        for p in pairs:
            claims_system_a.extend(extract_claims(p.system_a_output, sys_a_config))
        progress.advance(task_extract)

        progress.update(task_extract, description=f"[cyan]Step 3: Extracting {sys_b_config.name} Factual Claims...")
        for p in pairs:
            claims_system_b.extend(extract_claims(p.system_b_output, sys_b_config))
        progress.advance(task_extract)
        telemetry["step3_claim_extraction"] = (time.perf_counter() - start) * 1000

        # ─── STEP 4: VECTOR EMBEDDINGS ───
        start = time.perf_counter()
        progress.update(task_embed, description=f"[cyan]Step 4: Embedding Claims for {sys_a_config.name}...")
        embedded_claims_a = embed_claims(claims_system_a, sys_a_config)
        progress.advance(task_embed)

        progress.update(task_embed, description=f"[cyan]Step 4: Embedding Claims for {sys_b_config.name}...")
        embedded_claims_b = embed_claims(claims_system_b, sys_b_config)
        progress.advance(task_embed)
        telemetry["step4_vector_embedding"] = (time.perf_counter() - start) * 1000

        # ─── STEP 5: CONTRADICTION DETECTION ───
        start = time.perf_counter()
        progress.update(task_detect, description="[cyan]Step 5: Processing Cross-System Contradiction Funnel...")
        contradictions = run_detection(
            embedded_claims_a, 
            embedded_claims_b, 
            sys_a_config, # Using configuration key definitions
            sys_a_config.name, 
            sys_b_config.name,
            similarity_threshold=similarity_threshold
        )
        progress.advance(task_detect)
        telemetry["step5_contradiction_detection"] = (time.perf_counter() - start) * 1000

        # ─── STEP 6: RESOLUTION EXPLANATIONS ───
        start = time.perf_counter()
        progress.update(task_explain, description=f"[cyan]Step 6: Explaining {len(contradictions)} Identified Clashes (GPT-4o)...")
        explanations = explain_batch(contradictions, sys_a_config)
        progress.advance(task_explain)
        telemetry["step6_resolution_explanations"] = (time.perf_counter() - start) * 1000

        # ─── STEP 7: REPORTS FLUSH ───
        start = time.perf_counter()
        progress.update(task_report, description="[cyan]Step 7: Compiling Final Verification Dashboards...")
        generate_cli_report(contradictions, explanations, sys_a_config.name, sys_b_config.name)
        generate_html_report(contradictions, explanations, sys_a_config.name, sys_b_config.name, output_html_path)
        progress.advance(task_report)
        telemetry["step7_reporting_flush"] = (time.perf_counter() - start) * 1000

    pipeline_duration_ms = (time.perf_counter() - pipeline_start_time) * 1000
    
    # ─── OUTPUT COMPREHENSIVE COMPUTATIONAL TELEMETRY METRICS ───
    console.print("\n[bold green]⏱️  Orqestra Pipeline Computational Profiling Metrics[/bold green]")
    console.print("="*65)
    for step, duration in telemetry.items():
        console.print(f" 🔹 {step.ljust(35)}: [bold cyan]{duration:10.2f} ms[/bold cyan]")
    console.print("="*65)
    console.print(f" [bold white]Total Cumulative Clock Time[/bold white]: [bold green]{pipeline_duration_ms:.2f} ms ({pipeline_duration_ms/1000:.2f}s)[/bold green]\n")

    return contradictions, explanations, pipeline_duration_ms