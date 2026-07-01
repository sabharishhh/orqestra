"""Split demo/.env.demo into one file per agent for docker-compose env_file consumption."""
import pathlib, re

src = pathlib.Path("demo/.env.demo").read_text()
out_dir = pathlib.Path("demo")

# Shared header (just the ORQESTRA_API line)
shared_lines = [l for l in src.splitlines() if l.startswith("ORQESTRA_API=")]

agents = ["FITNESS", "MEDICAL", "NUTRITION", "RECOVERY", "BUDGET"]
for agent in agents:
    system_id = next((l.split("=",1)[1] for l in src.splitlines() if l.startswith(f"{agent}_AGENT_SYSTEM_ID=")), None)
    key       = next((l.split("=",1)[1] for l in src.splitlines() if l.startswith(f"{agent}_AGENT_KEY=")),       None)
    if not (system_id and key):
        print(f"MISSING {agent}")
        continue
    out = out_dir / f".env.{agent.lower()}_agent"
    out.write_text("\n".join(shared_lines + [
        f"ORQESTRA_SYSTEM={system_id}",
        f"ORQESTRA_KEY={key}",
    ]) + "\n")
    out.chmod(0o600)
    print(f"wrote {out}")
