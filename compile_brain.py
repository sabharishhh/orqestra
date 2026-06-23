import os
import dspy
from dspy.teleprompt import BootstrapFewShot
from workers.contradiction_detector import ApexJudge, EnterpriseContradictionSignature

# IMPORTANT: Ensure orqestra_50.py is in the same directory or adjust the import path
try:
    from dataset.orqestra_50 import train_set as raw_train_set
except ImportError:
    print("❌ ERROR: Could not find orqestra_50.py. Please place it in the same directory.")
    exit(1)

# Configure OpenAI
turbo = dspy.LM('openai/gpt-5.4-mini', api_key=os.environ.get("OPENAI_API_KEY"))
dspy.settings.configure(lm=turbo)

print("🚀 Booting DSPy Teleprompter for Orqestra v4.0...")
print(f"📥 Loaded {len(raw_train_set)} Golden Examples from orqestra_50.py")

# 1. Translate the Old Dataset into the New Signature
formatted_train_data = []
for example in raw_train_set:
    # Convert "Contradiction" to "True", "Neutral"/"Entailment" to "False"
    is_contra = "True" if example.logical_relationship.lower() == "contradiction" else "False"
    
    # We will dynamically generate a topic based on the subject matter if one isn't provided
    topic_hint = "enterprise policy"
    if "Metformin" in example.claim_a: topic_hint = "medication guidelines"
    if "budget" in example.claim_a.lower(): topic_hint = "budget allocation"
    if "workout" in example.claim_a.lower() or "lunges" in example.claim_a.lower(): topic_hint = "workout routine"
    
    formatted_example = dspy.Example(
        claim_a=example.claim_a,
        claim_b=example.claim_b,
        topic=topic_hint,
        is_contradiction=is_contra
    ).with_inputs("claim_a", "claim_b", "topic")
    
    formatted_train_data.append(formatted_example)

# 2. Define the Evaluation Metric (Exact Match)
def exact_match_metric(example, pred, trace=None):
    return str(example.is_contradiction).strip().lower() == str(pred.is_contradiction).strip().lower()

# 3. Compile the Brain using the massive 50-row dataset
print("🧠 Compiling optimized prompt weights across 50 enterprise scenarios (This may take 1-2 minutes)...")
# We increase bootstrapped demos to inject more context into the prompt
teleprompter = BootstrapFewShot(metric=exact_match_metric, max_bootstrapped_demos=8, max_labeled_demos=8)
compiled_judge = teleprompter.compile(ApexJudge(), trainset=formatted_train_data)

# 4. Save the new Version-Compatible JSON
output_dir = os.path.join(os.path.dirname(__file__), "models", "apex_compiled")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "optimized_config.json")

compiled_judge.save(output_path)
print(f"✅ SUCCESS: Enterprise-grade DSPy brain saved to {output_path}")