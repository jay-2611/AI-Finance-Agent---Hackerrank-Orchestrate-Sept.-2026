"""
Packages the complete solution into code.zip for contest submission.
Excludes bytecode, __pycache__, and temporary artifacts.
Ensures evaluation/usage_report.md is present as required by the contest spec.
"""

from pathlib import Path
import zipfile


def create_submission_zip(output_zip: str = "code.zip"):
    repo_root = Path(__file__).resolve().parent.parent
    zip_path = repo_root / output_zip

    print(f"Creating submission package at '{zip_path}'...")

    # Files and folders to include
    code_dir = repo_root / "code"
    run_file = repo_root / "run.py"
    readme_file = repo_root / "README.md"
    claude_file = repo_root / "CLAUDE.md"
    usage_file = repo_root / "code" / "evaluation" / "usage_report.md"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add all files in code/
        for p in code_dir.rglob("*"):
            if p.is_file():
                # Skip cache and temporary files
                if "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo", ".pyd"}:
                    continue
                rel_path = p.relative_to(repo_root)
                zf.write(p, arcname=str(rel_path).replace("\\", "/"))

        # 2. Add run.py, README.md, CLAUDE.md
        if run_file.exists():
            zf.write(run_file, arcname="run.py")
        if readme_file.exists():
            zf.write(readme_file, arcname="README.md")
        if claude_file.exists():
            zf.write(claude_file, arcname="CLAUDE.md")

        # 3. Add evaluation/usage_report.md at top level as required by spec
        if usage_file.exists():
            zf.write(usage_file, arcname="evaluation/usage_report.md")

    size_kb = zip_path.stat().st_size / 1024
    print(f"Successfully packaged '{output_zip}' ({size_kb:.1f} KB).")


if __name__ == "__main__":
    create_submission_zip()
