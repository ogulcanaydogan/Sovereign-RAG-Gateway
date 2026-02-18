import subprocess
from pathlib import Path

from scripts.generate_release_evidence_artifacts import generate_release_evidence


def test_generate_release_evidence_artifacts(tmp_path: Path) -> None:
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"

    subprocess.run(
        ["openssl", "genrsa", "-out", str(private_key), "2048"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
        text=True,
    )

    metadata = generate_release_evidence(
        out_dir=tmp_path,
        private_key=private_key,
        public_key=public_key,
    )

    assert Path(metadata["bundle_path"]).exists()
    assert Path(metadata["bundle_signature_path"]).exists()
    assert metadata["signature_verified"] == "True"
    assert Path(tmp_path / "release-evidence" / "release-evidence-metadata.json").exists()
